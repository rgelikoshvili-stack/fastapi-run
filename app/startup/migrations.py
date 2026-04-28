"""app/startup/migrations.py — Safe startup DB migrations (CREATE IF NOT EXISTS)."""
import logging
import os

log = logging.getLogger(__name__)


def run_db_migrations():
    """Safe startup migrations — CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS."""
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        # Fix tenant_id UUID → TEXT for tables created with wrong type
        for tbl in ("expenses", "invoices", "contracts", "customers"):
            cur.execute(f"""
                DO $$ BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='{tbl}' AND column_name='tenant_id' AND data_type='uuid'
                    ) THEN
                        ALTER TABLE {tbl} ALTER COLUMN tenant_id TYPE TEXT USING tenant_id::text;
                    END IF;
                END $$;
            """)

        # processed_documents — add missing columns one-by-one so one failure doesn't block others
        for col_sql in [
            "ALTER TABLE processed_documents ADD COLUMN IF NOT EXISTS gcs_path TEXT",
            "ALTER TABLE processed_documents ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'processing'",
            "ALTER TABLE processed_documents ADD COLUMN IF NOT EXISTS approved_by TEXT",
            "ALTER TABLE processed_documents ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ",
            "ALTER TABLE processed_documents ADD COLUMN IF NOT EXISTS source_document_id INTEGER",
        ]:
            try:
                cur.execute(col_sql)
                conn.commit()
            except Exception as _col_err:
                conn.rollback()
                log.warning("processed_documents column migration skipped: %s", _col_err)

        # journal_drafts columns (each separately to survive partial failures)
        for _jd_col in [
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS autopilot_suggested  BOOLEAN DEFAULT FALSE",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS confidence_score     NUMERIC",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS effective_threshold  NUMERIC",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS review_required      BOOLEAN DEFAULT FALSE",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS partner              TEXT",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS autopilot_flag       TEXT",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS engine_metadata      JSONB",
        ]:
            try:
                cur.execute(_jd_col)
                conn.commit()
            except Exception as _e:
                conn.rollback()
                log.debug("journal_drafts col migration skipped: %s", _e)

        # CRM tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id          SERIAL PRIMARY KEY,
                tenant_id   TEXT NOT NULL DEFAULT 'default',
                name        TEXT NOT NULL,
                email       TEXT,
                phone       TEXT,
                company     TEXT,
                type        TEXT DEFAULT 'client',
                tax_id      TEXT,
                address     TEXT,
                notes       TEXT,
                status      TEXT DEFAULT 'active',
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS customer_interactions (
                id          SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
                tenant_id   TEXT NOT NULL DEFAULT 'default',
                type        TEXT,
                note        TEXT,
                amount      NUMERIC,
                created_by  TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # Contracts tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id              SERIAL PRIMARY KEY,
                tenant_id       TEXT NOT NULL DEFAULT 'default',
                contract_number TEXT,
                title           TEXT NOT NULL,
                party_name      TEXT,
                party_tax_id    TEXT,
                contract_type   TEXT DEFAULT 'service',
                status          TEXT DEFAULT 'draft',
                value           NUMERIC DEFAULT 0,
                currency        TEXT DEFAULT 'GEL',
                start_date      DATE,
                end_date        DATE,
                payment_terms   TEXT,
                auto_renew      BOOLEAN DEFAULT FALSE,
                notes           TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS contract_milestones (
                id          SERIAL PRIMARY KEY,
                tenant_id   TEXT NOT NULL DEFAULT 'default',
                contract_id INTEGER REFERENCES contracts(id) ON DELETE CASCADE,
                title       TEXT NOT NULL,
                due_date    DATE,
                amount      NUMERIC DEFAULT 0,
                status      TEXT DEFAULT 'pending',
                notes       TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        _run_remaining_migrations(cur)

        conn.commit()
        cur.close()
        conn.close()
        log.info("action=db_migration_ok")
    except Exception as e:
        log.warning("action=db_migration_skipped reason=%s", e)


def _run_remaining_migrations(cur):
    """Continuation of run_db_migrations — additional tables and indexes."""
    import psycopg2

    # Expense categories + expenses
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expense_articles (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            code        TEXT,
            name        TEXT NOT NULL,
            account     TEXT,
            vat_rate    NUMERIC DEFAULT 18,
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id              SERIAL PRIMARY KEY,
            tenant_id       TEXT NOT NULL DEFAULT 'default',
            article_id      INTEGER REFERENCES expense_articles(id),
            description     TEXT NOT NULL,
            amount          NUMERIC NOT NULL,
            currency        TEXT DEFAULT 'GEL',
            expense_date    DATE,
            supplier        TEXT,
            supplier_inn    TEXT,
            vat_amount      NUMERIC DEFAULT 0,
            status          TEXT DEFAULT 'draft',
            notes           TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Invoices
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id              SERIAL PRIMARY KEY,
            tenant_id       TEXT NOT NULL DEFAULT 'default',
            invoice_number  TEXT,
            customer_id     INTEGER REFERENCES customers(id),
            customer_name   TEXT,
            customer_inn    TEXT,
            invoice_date    DATE,
            due_date        DATE,
            subtotal        NUMERIC DEFAULT 0,
            vat_amount      NUMERIC DEFAULT 0,
            total           NUMERIC DEFAULT 0,
            currency        TEXT DEFAULT 'GEL',
            status          TEXT DEFAULT 'draft',
            notes           TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS invoice_lines (
            id          SERIAL PRIMARY KEY,
            invoice_id  INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            description TEXT NOT NULL,
            quantity    NUMERIC DEFAULT 1,
            unit_price  NUMERIC NOT NULL,
            vat_rate    NUMERIC DEFAULT 18,
            line_total  NUMERIC,
            account     TEXT
        );
    """)

    # Collaboration
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            entity_type TEXT NOT NULL,
            entity_id   INTEGER NOT NULL,
            author      TEXT,
            content     TEXT NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS attachments (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            entity_type TEXT NOT NULL,
            entity_id   INTEGER NOT NULL,
            file_name   TEXT NOT NULL,
            file_size   INTEGER,
            mime_type   TEXT,
            gcs_path    TEXT,
            uploaded_by TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Chat sessions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          SERIAL PRIMARY KEY,
            session_id  TEXT UNIQUE NOT NULL,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            user_id     TEXT,
            messages    JSONB DEFAULT '[]',
            context     JSONB DEFAULT '{}',
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant_session
            ON chat_sessions(tenant_id, session_id);
    """)

    # Idempotency keys
    cur.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            id              SERIAL PRIMARY KEY,
            tenant_id       TEXT NOT NULL,
            idempotent_key  TEXT NOT NULL,
            endpoint        TEXT,
            response        JSONB,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(tenant_id, idempotent_key, endpoint)
        );
        CREATE INDEX IF NOT EXISTS idx_idempotency_keys_lookup
            ON idempotency_keys(tenant_id, idempotent_key, endpoint);
    """)

    conn = cur.connection

    # Performance indexes
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

    # journal_entries dedup
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

    # Data quality constraints
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

    # Normalize tenant_id: replace company_inn with actual tenant_id
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

    # Auto-classify drafts with missing debit/credit accounts
    try:
        from app.knowledge.journal_builder import classify_transaction as _cls
        cur.execute("""
            SELECT id, description, tenant_id FROM journal_drafts
            WHERE (debit_account IS NULL OR credit_account IS NULL)
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
            except Exception:
                pass
        log.info("action=auto_classify_drafts count=%d", len(rows))
    except Exception as e:
        log.warning("auto_classify_drafts skipped: %s", e)
