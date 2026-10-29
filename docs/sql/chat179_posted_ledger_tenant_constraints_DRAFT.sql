-- DRAFT / DISPOSABLE TESTS ONLY. NOT REGISTERED WITH STARTUP MIGRATIONS.
-- Requires migration 011 and a privileged migration identity. No row edits,
-- deletes, backfill, RLS/grant changes or activation of ledger feature flags.
-- Production requires separate approval, preservation/backup evidence and
-- a reviewed maintenance/lock plan. This file is NOT production authorization.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
-- Prevent an RLS-filtered preflight from falsely certifying the whole table.
-- A role unable to see all rows must fail, rather than silently skip them.
SET LOCAL row_security = off;

DO $chat179$
BEGIN
    IF EXISTS (
        SELECT 1 FROM journal_entry_lines l
        LEFT JOIN journal_entry_headers h ON h.id = l.journal_entry_id
        WHERE h.id IS NULL OR l.tenant_id IS DISTINCT FROM h.tenant_id
    ) OR EXISTS (
        SELECT 1 FROM journal_entry_sources s
        LEFT JOIN journal_entry_headers h ON h.id = s.journal_entry_id
        WHERE h.id IS NULL OR s.tenant_id IS DISTINCT FROM h.tenant_id
    ) THEN
        RAISE EXCEPTION 'LEDGER_TENANT_INTEGRITY_PREFLIGHT_FAILED'
            USING HINT = 'Preserve and review existing rows; do not auto-repair or delete.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'journal_entry_headers'::regclass
          AND conname = 'uq_chat179_jeh_id_tenant'
    ) THEN
        ALTER TABLE journal_entry_headers ADD CONSTRAINT uq_chat179_jeh_id_tenant
            UNIQUE (id, tenant_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'journal_entry_lines'::regclass
          AND conname = 'fk_chat179_jel_header_tenant'
    ) THEN
        ALTER TABLE journal_entry_lines ADD CONSTRAINT fk_chat179_jel_header_tenant
            FOREIGN KEY (journal_entry_id, tenant_id)
            REFERENCES journal_entry_headers (id, tenant_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'journal_entry_sources'::regclass
          AND conname = 'fk_chat179_jes_header_tenant'
    ) THEN
        ALTER TABLE journal_entry_sources ADD CONSTRAINT fk_chat179_jes_header_tenant
            FOREIGN KEY (journal_entry_id, tenant_id)
            REFERENCES journal_entry_headers (id, tenant_id);
    END IF;
END;
$chat179$;
COMMIT;
