"""app/startup/migrations_vault.py — Credential vault schema migration (009).

Idempotent — all statements use IF NOT EXISTS / IF EXISTS guards.
Called from run_db_migrations() in migrations.py.
"""
import logging

log = logging.getLogger(__name__)


def run_vault_migrations(cur) -> None:
    """Create credential vault tables and additive columns (idempotent)."""
    conn = cur.connection

    # A) Generic credential vault table
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS credential_vault_credentials (
                id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id           TEXT        NOT NULL,
                provider            TEXT        NOT NULL,
                credential_type     TEXT        NOT NULL,
                encrypted_value     TEXT        NOT NULL,
                key_version         TEXT        NOT NULL,
                masked_hint         TEXT,
                status              TEXT        NOT NULL DEFAULT 'active',
                active              BOOLEAN     NOT NULL DEFAULT TRUE,
                company_id          TEXT,
                api_base            TEXT,
                metadata            JSONB       NOT NULL DEFAULT '{}'::jsonb,
                last_test_status    TEXT,
                last_tested_at      TIMESTAMPTZ,
                last_accessed_at    TIMESTAMPTZ,
                rotated_at          TIMESTAMPTZ,
                revoked_at          TIMESTAMPTZ,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_by          TEXT,
                updated_by          TEXT,
                CONSTRAINT ck_credential_vault_status
                    CHECK (status IN ('active', 'disabled', 'revoked', 'rotation_required', 'test_failed')),
                CONSTRAINT uq_credential_vault_tenant_provider_type
                    UNIQUE (tenant_id, provider, credential_type)
            )
        """)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.warning("credential_vault_credentials create skipped: %s", exc)

    # B) Audit events table
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS credential_vault_audit_events (
                id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id       TEXT        NOT NULL,
                provider        TEXT        NOT NULL,
                credential_type TEXT        NOT NULL,
                action          TEXT        NOT NULL,
                actor           TEXT,
                purpose         TEXT,
                result          TEXT        NOT NULL,
                key_version     TEXT,
                request_id      TEXT,
                metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_credential_vault_audit_result
                    CHECK (result IN ('success', 'failure', 'not_found', 'disabled', 'denied', 'error'))
            )
        """)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.warning("credential_vault_audit_events create skipped: %s", exc)

    # C–F) Additive columns on existing credential tables
    _vault_columns = [
        ("tenant_balance_credentials", "encrypted_value", "TEXT"),
        ("tenant_balance_credentials", "key_version", "TEXT"),
        ("tenant_balance_credentials", "masked_hint", "TEXT"),
        ("tenant_balance_credentials", "credential_status", "TEXT DEFAULT 'legacy_plaintext'"),
        ("tenant_balance_credentials", "last_accessed_at", "TIMESTAMPTZ"),
        ("tenant_balance_credentials", "rotated_at", "TIMESTAMPTZ"),
        ("tenant_email_credentials", "encrypted_value", "TEXT"),
        ("tenant_email_credentials", "key_version", "TEXT"),
        ("tenant_email_credentials", "masked_hint", "TEXT"),
        ("tenant_email_credentials", "credential_status", "TEXT DEFAULT 'legacy_plaintext'"),
        ("tenant_email_credentials", "last_accessed_at", "TIMESTAMPTZ"),
        ("tenant_email_credentials", "rotated_at", "TIMESTAMPTZ"),
    ]
    for table, col, col_type in _vault_columns:
        try:
            cur.execute(
                f"ALTER TABLE IF EXISTS {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            log.debug("vault additive column %s.%s skipped: %s", table, col, exc)

    # G) Indexes
    _indexes = [
        ("idx_credential_vault_tenant_provider_type",
         "credential_vault_credentials (tenant_id, provider, credential_type)"),
        ("idx_credential_vault_audit_tenant_provider",
         "credential_vault_audit_events (tenant_id, provider)"),
        ("idx_credential_vault_audit_created_at",
         "credential_vault_audit_events (created_at)"),
    ]
    for idx_name, idx_def in _indexes:
        try:
            cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
            conn.commit()
        except Exception as exc:
            conn.rollback()
            log.debug("vault index %s skipped: %s", idx_name, exc)

    log.info("action=vault_migration_ok")
