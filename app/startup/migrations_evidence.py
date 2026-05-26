"""app/startup/migrations_evidence.py — Evidence bundle schema migration (010).

Idempotent — all DDL uses IF NOT EXISTS / IF EXISTS guards.
Called from run_db_migrations() in migrations.py.
"""
import logging

log = logging.getLogger(__name__)


def run_evidence_bundle_migrations(cur) -> None:
    """Create evidence_bundles and evidence_bundle_events tables (idempotent)."""
    conn = cur.connection

    # A) evidence_bundles — one row per document/draft audit trail
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evidence_bundles (
                id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id            TEXT        NOT NULL,
                source_type          TEXT        NOT NULL,
                source_id            TEXT,
                source_file_id       TEXT,
                source_file_hash     TEXT,
                bank_transaction_id  TEXT,
                document_id          TEXT,
                ocr_result_id        TEXT,
                journal_draft_id     TEXT,
                journal_entry_id     TEXT,
                approval_event_id    TEXT,
                posting_log_id       TEXT,
                connector_provider   TEXT,
                connector_operation  TEXT,
                payload_preview_hash TEXT,
                ai_reasoning         JSONB       NOT NULL DEFAULT '{}'::jsonb,
                extracted_fields     JSONB       NOT NULL DEFAULT '{}'::jsonb,
                risk_flags           JSONB       NOT NULL DEFAULT '[]'::jsonb,
                confidence           NUMERIC,
                status               TEXT        NOT NULL DEFAULT 'draft',
                created_by           TEXT,
                updated_by           TEXT,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.warning("evidence_bundles create skipped: %s", exc)

    # B) evidence_bundle_events — append-only audit log of bundle state changes
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evidence_bundle_events (
                id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id           TEXT        NOT NULL,
                evidence_bundle_id  UUID        NOT NULL,
                event_type          TEXT        NOT NULL,
                actor               TEXT,
                event_ref_type      TEXT,
                event_ref_id        TEXT,
                metadata            JSONB       NOT NULL DEFAULT '{}'::jsonb,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.warning("evidence_bundle_events create skipped: %s", exc)

    # C) Performance indexes
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_evidence_bundles_tenant       ON evidence_bundles(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_evidence_bundles_draft        ON evidence_bundles(tenant_id, journal_draft_id)",
        "CREATE INDEX IF NOT EXISTS idx_evidence_bundles_posting      ON evidence_bundles(tenant_id, posting_log_id)",
        "CREATE INDEX IF NOT EXISTS idx_evidence_bundle_events_bundle ON evidence_bundle_events(evidence_bundle_id, tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_evidence_bundle_events_type   ON evidence_bundle_events(tenant_id, event_type)",
    ]:
        try:
            cur.execute(idx_sql)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            log.debug("evidence_bundle index skipped: %s", exc)
