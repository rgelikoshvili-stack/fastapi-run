"""app/startup/migrations.py — Safe startup DB migrations (CREATE IF NOT EXISTS)."""
import logging
import os

log = logging.getLogger(__name__)


def run_db_migrations():
    """Safe startup migrations — CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS."""
    try:
        from app.api.db import get_db_sync
        conn = get_db_sync()
        cur = conn.cursor()

        # outgoing_invoices — sent_at + seller/buyer detail columns
        for _oi_col in [
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS invoice_date DATE",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS delivery_date DATE",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS seller_name TEXT",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS seller_inn TEXT",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS seller_address TEXT",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS seller_phone TEXT",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS seller_bank TEXT",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS seller_swift TEXT",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS seller_account TEXT",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS buyer_address TEXT",
            "ALTER TABLE outgoing_invoices ADD COLUMN IF NOT EXISTS buyer_phone TEXT",
        ]:
            try:
                cur.execute(_oi_col)
                conn.commit()
            except Exception as _e:
                conn.rollback()
                log.debug("outgoing_invoices col migration skipped: %s", _e)

        # tenants table — ensure all party_resolver columns exist
        for _t_col in [
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_inn TEXT",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_name_legal TEXT",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_name_aliases JSONB",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS owner_personal_id TEXT",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_type TEXT DEFAULT 'legal_entity'",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_vat_payer BOOLEAN DEFAULT TRUE",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'trial'",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS signature_b64 TEXT",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stamp_b64 TEXT",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS submit_token TEXT",
        ]:
            try:
                cur.execute(_t_col)
                conn.commit()
            except Exception as _e:
                conn.rollback()
                log.debug("tenants col migration skipped: %s", _e)

        # Populate submit_token for tenants that don't have one yet
        try:
            cur.execute("""
                UPDATE tenants
                SET submit_token = substring(md5(id::text || random()::text) from 1 for 10)
                WHERE submit_token IS NULL
            """)
            conn.commit()
        except Exception as _e:
            conn.rollback()
            log.debug("submit_token populate skipped: %s", _e)

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
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS attached_file_path TEXT",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS attached_file_name TEXT",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS attached_file_size INTEGER",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS autopilot_suggested  BOOLEAN DEFAULT FALSE",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS confidence_score     NUMERIC",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS effective_threshold  NUMERIC",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS review_required      BOOLEAN DEFAULT FALSE",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS partner              TEXT",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS autopilot_flag       TEXT",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS engine_metadata      JSONB",
            # Document Intelligence Engine columns
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS doc_set_score        NUMERIC",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS doc_set_summary      TEXT",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS doc_matrix           JSONB",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS provider_type        TEXT",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS tax_detail           JSONB",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS triangle_match_id    INTEGER",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS completeness_alerts  JSONB",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS journal_entries      JSONB",
            "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS raw_extraction       JSONB",
        ]:
            try:
                cur.execute(_jd_col)
                conn.commit()
            except Exception as _e:
                conn.rollback()
                log.debug("journal_drafts col migration skipped: %s", _e)

        # learning_patterns — weighted learning columns (added in weighted-learning feature)
        for _lp_col in [
            "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS weighted_success_score NUMERIC DEFAULT 0",
            "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS weighted_failure_score NUMERIC DEFAULT 0",
            "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS usage_count            INTEGER DEFAULT 0",
            "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS last_used_at           TIMESTAMPTZ",
        ]:
            try:
                cur.execute(_lp_col)
                conn.commit()
            except Exception as _e:
                conn.rollback()
                log.debug("learning_patterns col migration skipped: %s", _e)

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

        from app.startup.migrations_tables import run_table_migrations
        run_table_migrations(cur)
        from app.startup.migrations_indexes import run_index_migrations
        run_index_migrations(cur)

        # credential vault schema (009)
        try:
            from app.startup.migrations_vault import run_vault_migrations
            run_vault_migrations(cur)
        except Exception as _vault_e:
            log.warning("vault migration skipped: %s", _vault_e)

        # evidence bundle schema (010)
        try:
            from app.startup.migrations_evidence import run_evidence_bundle_migrations
            run_evidence_bundle_migrations(cur)
        except Exception as _eb_e:
            log.warning("evidence bundle migration skipped: %s", _eb_e)

        # tenant_settings — per-tenant config table (CFO thresholds, feature flags, etc.)
        try:
            from app.api.services.tenant_config_service import ensure_tenant_settings_table
            ensure_tenant_settings_table(conn)
        except Exception as _tcs_e:
            log.warning("tenant_settings migration skipped: %s", _tcs_e)

        conn.commit()
        cur.close()
        conn.close()
        log.info("action=db_migration_ok")
    except Exception as e:
        log.warning("action=db_migration_skipped reason=%s", e)

