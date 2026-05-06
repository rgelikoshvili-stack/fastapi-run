"""app/startup/migrations_indexes.py — Indexes, FX columns, constraints, data migrations."""
import logging

log = logging.getLogger(__name__)


def run_index_migrations(cur):
    """Create indexes, add FX/currency columns, apply constraints, run data migrations."""
    conn = cur.connection

    # ── Performance indexes (core tables) ────────────────────────────────────
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_journal_drafts_tenant_status_created ON journal_drafts(tenant_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_processed_documents_tenant_status ON processed_documents(tenant_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_processed_documents_tenant_hash ON processed_documents(tenant_id, file_hash)",
        "CREATE INDEX IF NOT EXISTS idx_journal_drafts_source_document ON journal_drafts(source_document_id)",
        "CREATE INDEX IF NOT EXISTS idx_tenants_company_inn ON tenants(company_inn)",
    ]:
        try:
            cur.execute(idx_sql)
        except Exception:
            conn.rollback()

    # ── journal_entries dedup hash ────────────────────────────────────────────
    try:
        cur.execute("ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS entry_hash TEXT")
    except Exception:
        conn.rollback()
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_entries_hash
                ON journal_entries(entry_hash) WHERE entry_hash IS NOT NULL
        """)
    except Exception:
        conn.rollback()

    # ── outgoing_invoices status constraint ───────────────────────────────────
    for sql in [
        "ALTER TABLE outgoing_invoices DROP CONSTRAINT IF EXISTS outgoing_invoices_status_check",
        """ALTER TABLE outgoing_invoices ADD CONSTRAINT IF NOT EXISTS outgoing_invoices_status_check
           CHECK (status IN ('draft','pending','finalized','sent','cancelled','imported','paid'))""",
    ]:
        try:
            cur.execute(sql)
            conn.commit()
        except Exception:
            conn.rollback()

    # ── Data quality constraints ──────────────────────────────────────────────
    for sql in [
        "ALTER TABLE journal_drafts ADD CONSTRAINT IF NOT EXISTS chk_jd_amount_positive CHECK (amount IS NULL OR amount >= 0)",
        "ALTER TABLE expenses ADD CONSTRAINT IF NOT EXISTS chk_exp_amount_positive CHECK (amount IS NULL OR amount >= 0)",
        "ALTER TABLE invoices ADD CONSTRAINT IF NOT EXISTS chk_inv_total_positive CHECK (total IS NULL OR total >= 0)",
        "ALTER TABLE learning_patterns ADD CONSTRAINT IF NOT EXISTS chk_lp_confidence CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1))",
        "ALTER TABLE invoices ADD CONSTRAINT IF NOT EXISTS uq_invoice_number_tenant UNIQUE (tenant_id, invoice_number)",
    ]:
        try:
            cur.execute(sql)
        except Exception:
            conn.rollback()

    # ── Tenant normalization: replace company_inn with actual tenant_id ────────
    for tbl in ("journal_drafts", "processed_documents", "learning_patterns",
                "audit_log", "bank_transactions", "chart_of_accounts"):
        try:
            cur.execute(f"""
                UPDATE {tbl} d SET tenant_id = t.tenant_id
                FROM tenants t
                WHERE d.tenant_id = t.company_inn
                  AND d.tenant_id != t.tenant_id
                  AND t.company_inn IS NOT NULL AND t.company_inn != ''
            """)
        except Exception:
            conn.rollback()

    # ── Auto-classify drafts with missing accounts ────────────────────────────
    try:
        from app.knowledge.journal_builder import classify_transaction as _cls
        cur.execute("""
            SELECT id, description, tenant_id FROM journal_drafts
            WHERE (debit_account IS NULL OR credit_account IS NULL
                   OR debit_account = '????' OR credit_account = '????')
              AND description IS NOT NULL
            LIMIT 500
        """)
        rows = cur.fetchall()
        for row_id, desc, t_id in rows:
            try:
                res = _cls(desc or "", t_id or "default")
                acc = res.get("account", "")
                if not acc:
                    continue
                a = int(acc) if acc.isdigit() else 0
                if 1000 <= a <= 1999:
                    dr, cr = acc, "3110"
                elif 2000 <= a <= 2999:
                    dr, cr = acc, "3110"
                elif 3000 <= a <= 3999:
                    dr, cr = "1210", acc
                elif 5000 <= a <= 5999:
                    dr, cr = acc, "3110"
                elif 7000 <= a <= 7999:
                    dr, cr = acc, "1210"
                else:
                    dr, cr = acc, "3110"
                cur.execute(
                    "UPDATE journal_drafts SET debit_account=%s, credit_account=%s, account_code=%s WHERE id=%s",
                    (dr, cr, acc, row_id),
                )
            except Exception as e:
                log.warning("unexpected error: %s", e)
        log.info("action=auto_classify_drafts count=%d", len(rows))
    except Exception as e:
        log.warning("auto_classify_drafts skipped: %s", e)

    # ── Tenant isolation: add tenant_id to global tables ─────────────────────
    for tbl_col in [
        ("pipeline_runs",  "tenant_id TEXT NOT NULL DEFAULT 'default'"),
        ("search_history", "tenant_id TEXT NOT NULL DEFAULT 'default'"),
    ]:
        try:
            cur.execute(f"ALTER TABLE {tbl_col[0]} ADD COLUMN IF NOT EXISTS {tbl_col[1]}")
            conn.commit()
        except Exception:
            conn.rollback()

    # ── Domain indexes (expenses, contracts, customers, bank) ─────────────────
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_expenses_tenant_id ON expenses(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_contracts_tenant_id ON contracts(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_customers_tenant_id ON customers(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_bank_transactions_account_id ON bank_transactions(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_tenant_id ON pipeline_runs(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_search_history_tenant_id ON search_history(tenant_id)",
    ]:
        try:
            cur.execute(idx_sql)
            conn.commit()
        except Exception:
            conn.rollback()

    # ── Multi-currency: exchange_rates columns ────────────────────────────────
    for fx_sql in [
        "ALTER TABLE exchange_rates ADD COLUMN IF NOT EXISTS from_code VARCHAR(3)",
        "ALTER TABLE exchange_rates ADD COLUMN IF NOT EXISTS to_code   VARCHAR(3) DEFAULT 'GEL'",
        "ALTER TABLE exchange_rates ADD COLUMN IF NOT EXISTS source    TEXT       DEFAULT 'nbg'",
        "ALTER TABLE exchange_rates ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ",
    ]:
        try:
            cur.execute(fx_sql)
            conn.commit()
        except Exception:
            conn.rollback()

    for backfill in [
        "UPDATE exchange_rates SET from_code = currency WHERE from_code IS NULL AND currency IS NOT NULL",
        "UPDATE exchange_rates SET to_code   = 'GEL'     WHERE to_code   IS NULL",
        "UPDATE exchange_rates SET fetched_at = COALESCE(updated_at, NOW()) WHERE fetched_at IS NULL",
    ]:
        try:
            cur.execute(backfill)
            conn.commit()
        except Exception:
            conn.rollback()

    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchange_rates_lookup
                ON exchange_rates(from_code, to_code, fetched_at DESC)
        """)
        conn.commit()
    except Exception:
        conn.rollback()

    # ── Multi-currency: journal_drafts + journal_entries FX columns ────────────
    for jfx_sql in [
        "ALTER TABLE journal_drafts  ADD COLUMN IF NOT EXISTS currency      VARCHAR(3)     DEFAULT 'GEL'",
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS currency      VARCHAR(3)     DEFAULT 'GEL'",
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS amount_gel    NUMERIC(15,2)",
        "ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(20,8)  DEFAULT 1.0",
    ]:
        try:
            cur.execute(jfx_sql)
            conn.commit()
        except Exception:
            conn.rollback()

    # ── Idempotency: entry_hash on posting_logs ───────────────────────────────
    for idm_sql in [
        "ALTER TABLE posting_logs ADD COLUMN IF NOT EXISTS entry_hash VARCHAR(16)",
        "ALTER TABLE posting_logs ADD COLUMN IF NOT EXISTS source_draft_id INTEGER",
    ]:
        try:
            cur.execute(idm_sql)
            conn.commit()
        except Exception:
            conn.rollback()
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_posting_logs_entry_hash
                ON posting_logs(entry_hash)
                WHERE entry_hash IS NOT NULL
        """)
        conn.commit()
    except Exception:
        conn.rollback()

    # ── Speed Phase 1: composite indexes for hot queries ─────────────────────
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_expenses_tenant_id      ON expenses(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_contracts_tenant_id     ON contracts(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_customers_tenant_id     ON customers(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_bank_transactions_acct  ON bank_transactions(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_journal_drafts_tenant   ON journal_drafts(tenant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_journal_drafts_created  ON journal_drafts(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_posting_logs_draft      ON posting_logs(draft_id, tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_id       ON audit_log(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_created  ON audit_log(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_tenant  ON outgoing_invoices(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_learning_patterns_tenant  ON learning_patterns(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_journal_entries_tenant    ON journal_entries(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_journal_entries_tenant_dt ON journal_entries(tenant_id, entry_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_journal_drafts_tenant_created ON journal_drafts(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_journal_drafts_tenant_status ON journal_drafts(tenant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_created ON audit_events(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_bank_transactions_tenant_created ON bank_transactions(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_tenant_created     ON pipeline_runs(tenant_id, created_at DESC)",
    ]:
        try:
            cur.execute(idx_sql)
            conn.commit()
        except Exception:
            conn.rollback()
