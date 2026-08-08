"""app/startup/migrations_rsge.py — RS.ge integration DB schema.

All tables include tenant_id for tenant isolation.
Run via run_rsge_migrations() at startup (non-destructive, CREATE IF NOT EXISTS).
"""
import logging

log = logging.getLogger(__name__)

_DDL = [
    # ── rsge_credentials ─────────────────────────────────────────────────────
    # Lightweight pointer table — actual secrets live in credential_vault.
    """
    CREATE TABLE IF NOT EXISTS rsge_credentials (
        id              SERIAL PRIMARY KEY,
        tenant_id       TEXT        NOT NULL,
        credential_type TEXT        NOT NULL DEFAULT 'soap_credentials',
        status          TEXT        NOT NULL DEFAULT 'configured',
        masked_su       TEXT,
        last_verified_at TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (tenant_id, credential_type)
    )
    """,
    # ── rsge_sync_jobs ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rsge_sync_jobs (
        id              SERIAL PRIMARY KEY,
        tenant_id       TEXT        NOT NULL,
        job_type        TEXT        NOT NULL DEFAULT 'document_sync',
        status          TEXT        NOT NULL DEFAULT 'pending',
        started_by      TEXT,
        started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at     TIMESTAMPTZ,
        doc_count       INTEGER     DEFAULT 0,
        synced_count    INTEGER     DEFAULT 0,
        skipped_count   INTEGER     DEFAULT 0,
        error_text      TEXT,
        meta            JSONB       DEFAULT '{}'
    )
    """,
    # ── rsge_documents ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rsge_documents (
        id              SERIAL PRIMARY KEY,
        tenant_id       TEXT        NOT NULL,
        rsge_id         TEXT        NOT NULL,
        reg_no          TEXT,
        doc_type        TEXT        NOT NULL DEFAULT 'invoice',
        seller_inn      TEXT,
        seller_name     TEXT,
        buyer_inn       TEXT,
        buyer_name      TEXT,
        doc_date        DATE,
        amount          NUMERIC(18,4) DEFAULT 0,
        vat_amount      NUMERIC(18,4) DEFAULT 0,
        currency        TEXT        DEFAULT 'GEL',
        rsge_status     TEXT,
        rsge_status_code TEXT,
        direction       TEXT        DEFAULT 'unknown',
        synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        evidence_id     INTEGER,
        draft_id        INTEGER,
        source_hash     TEXT,
        raw_payload     JSONB       DEFAULT '{}',
        UNIQUE (tenant_id, rsge_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rsge_documents_tenant ON rsge_documents (tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_rsge_documents_rsge_id ON rsge_documents (tenant_id, rsge_id)",
    # ── rsge_document_lines ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rsge_document_lines (
        id              SERIAL PRIMARY KEY,
        rsge_doc_id     INTEGER     NOT NULL REFERENCES rsge_documents(id) ON DELETE CASCADE,
        tenant_id       TEXT        NOT NULL,
        line_no         INTEGER     DEFAULT 1,
        product_name    TEXT,
        quantity        NUMERIC(18,4) DEFAULT 0,
        unit            TEXT,
        price           NUMERIC(18,4) DEFAULT 0,
        amount          NUMERIC(18,4) DEFAULT 0,
        vat_type        TEXT,
        bar_code        TEXT,
        raw             JSONB       DEFAULT '{}'
    )
    """,
    # ── rsge_document_status_history ─────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rsge_document_status_history (
        id              SERIAL PRIMARY KEY,
        rsge_doc_id     INTEGER     NOT NULL REFERENCES rsge_documents(id) ON DELETE CASCADE,
        tenant_id       TEXT        NOT NULL,
        old_status      TEXT,
        new_status      TEXT,
        changed_by      TEXT,
        changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        note            TEXT
    )
    """,
    # ── rsge_waybills ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rsge_waybills (
        id              SERIAL PRIMARY KEY,
        tenant_id       TEXT        NOT NULL,
        rsge_id         TEXT        NOT NULL,
        waybill_number  TEXT,
        wb_type         TEXT,
        rsge_status     TEXT,
        buyer_tin       TEXT,
        buyer_name      TEXT,
        start_address   TEXT,
        end_address     TEXT,
        driver_name     TEXT,
        car_number      TEXT,
        full_amount     NUMERIC(18,4) DEFAULT 0,
        begin_date      TIMESTAMPTZ,
        synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        evidence_id     INTEGER,
        raw_payload     JSONB       DEFAULT '{}',
        UNIQUE (tenant_id, rsge_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rsge_waybills_tenant ON rsge_waybills (tenant_id)",
    # ── rsge_actions ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rsge_actions (
        id              SERIAL PRIMARY KEY,
        tenant_id       TEXT        NOT NULL,
        rsge_doc_id     INTEGER,
        rsge_waybill_id INTEGER,
        action          TEXT        NOT NULL,
        doc_type        TEXT        DEFAULT 'document',
        is_test_mode    BOOLEAN     NOT NULL DEFAULT TRUE,
        is_dry_run      BOOLEAN     NOT NULL DEFAULT FALSE,
        requested_by    TEXT        NOT NULL,
        approved_by     TEXT,
        action_status   TEXT        NOT NULL DEFAULT 'pending',
        preview_payload JSONB       DEFAULT '{}',
        response_status TEXT,
        response_raw    TEXT,
        error_code      TEXT,
        error_text      TEXT,
        accounting_impact JSONB     DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at    TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rsge_actions_tenant ON rsge_actions (tenant_id)",
    # ── rsge_taxpayer_cache ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS rsge_taxpayer_cache (
        id              SERIAL PRIMARY KEY,
        tenant_id       TEXT        NOT NULL,
        inn             TEXT        NOT NULL,
        full_name       TEXT,
        status          TEXT,
        registered_subject TEXT,
        vat_payer       TEXT,
        start_date      TEXT,
        non_resident    TEXT,
        fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (tenant_id, inn)
    )
    """,
]


def run_rsge_migrations():
    """Run all RS.ge DDL migrations — safe, CREATE IF NOT EXISTS only."""
    try:
        from app.api.db import get_db_sync
        conn = get_db_sync()
        cur = conn.cursor()
        for stmt in _DDL:
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                log.debug("rsge migration skipped: %s | %s", type(exc).__name__, str(exc)[:120])
        cur.close()
        conn.close()
        log.info("action=rsge_migrations_ok")
    except Exception as exc:
        log.warning("action=rsge_migrations_failed non_fatal=true error=%s", exc)
