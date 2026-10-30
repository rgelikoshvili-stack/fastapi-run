-- Chat196 FIN-12 crash ambiguity quarantine (standalone/unapplied DRAFT).
-- NEVER REGISTER AS A LIVE MIGRATION, WORKER, ROUTE, ERP DISPATCH OR LEDGER POST.
-- Depends on docs/sql/chat186_posting_outbox_DRAFT.sql in a disposable PG DB.
-- An old in_flight/unknown attempt is ambiguous; neither an elapsed created_at
-- nor a missing lease is proof that the external provider did not commit.
-- This table is audit-only, not a dispatch lease, replay or status transition.
CREATE TABLE IF NOT EXISTS posting_outbox_crash_holds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL CHECK (
        tenant_id <> '' AND tenant_id <> 'default'
        AND tenant_id = btrim(tenant_id)
    ),
    outbox_id UUID NOT NULL,
    source_id TEXT NOT NULL CHECK (length(source_id) BETWEEN 1 AND 256),
    target_system TEXT NOT NULL CHECK (target_system IN ('balance','onec','oris')),
    idempotency_key TEXT NOT NULL CHECK (idempotency_key ~ '^[0-9a-f]{64}$'),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    observed_state TEXT NOT NULL CHECK (observed_state IN ('in_flight','unknown')),
    reason TEXT NOT NULL CHECK (
        reason IN ('worker_crash','timeout','missing_lease','manual_investigation')
    ),
    opener_subject TEXT NOT NULL CHECK (
        length(opener_subject) BETWEEN 1 AND 200
        AND opener_subject = btrim(opener_subject)
    ),
    opener_role TEXT NOT NULL CHECK (opener_role IN ('accountant','admin')),
    provider_verified BOOLEAN NOT NULL DEFAULT FALSE CHECK (provider_verified IS FALSE),
    dispatch_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (dispatch_allowed IS FALSE),
    retry_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (retry_allowed IS FALSE),
    confirm_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (confirm_allowed IS FALSE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id,outbox_id),
    FOREIGN KEY (outbox_id,tenant_id)
        REFERENCES posting_outbox_intents (id,tenant_id)
);

ALTER TABLE posting_outbox_crash_holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_crash_holds FORCE ROW LEVEL SECURITY;
DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname=current_schema()
           AND tablename='posting_outbox_crash_holds'
           AND policyname='fin12_crash_hold_tenant'
    ) THEN
        CREATE POLICY fin12_crash_hold_tenant
            ON posting_outbox_crash_holds FOR ALL
            USING (tenant_id=nullif(current_setting('app.current_tenant_id',true),''))
            WITH CHECK (tenant_id=nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
END;
$fin12$;

-- A direct SQL INSERT cannot manufacture a crash report for a prepared or
-- completed operation or bind somebody else's source/tenant/hash.
CREATE OR REPLACE FUNCTION fin12_check_crash_hold_source()
RETURNS trigger LANGUAGE plpgsql AS $fin12_hold$
DECLARE src posting_outbox_intents%ROWTYPE;
BEGIN
    SELECT * INTO src FROM posting_outbox_intents
      WHERE id=NEW.outbox_id AND tenant_id=NEW.tenant_id;
    IF NOT FOUND OR src.state NOT IN ('in_flight','unknown')
       OR src.state IS DISTINCT FROM NEW.observed_state
       OR src.source_type IS DISTINCT FROM 'journal_draft'
       OR src.source_id IS DISTINCT FROM NEW.source_id
       OR src.target_system IS DISTINCT FROM NEW.target_system
       OR src.idempotency_key IS DISTINCT FROM NEW.idempotency_key
       OR src.payload_sha256 IS DISTINCT FROM NEW.payload_sha256
       OR src.provider_receipt_id IS NOT NULL
       OR src.provider_verified_at IS NOT NULL
    THEN
        RAISE EXCEPTION 'FIN12_CRASH_SOURCE_NOT_AMBIGUOUS';
    END IF;
    RETURN NEW;
END;
$fin12_hold$;

CREATE OR REPLACE FUNCTION fin12_block_crash_hold_history_mutation()
RETURNS trigger LANGUAGE plpgsql AS $fin12_hold$
BEGIN
    RAISE EXCEPTION 'FIN12_CRASH_HOLD_IMMUTABLE';
END;
$fin12_hold$;

DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='posting_outbox_crash_holds'::regclass
          AND tgname='fin12_crash_hold_source_guard'
    ) THEN
        CREATE TRIGGER fin12_crash_hold_source_guard
            BEFORE INSERT ON posting_outbox_crash_holds
            FOR EACH ROW EXECUTE FUNCTION fin12_check_crash_hold_source();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='posting_outbox_crash_holds'::regclass
          AND tgname='fin12_crash_hold_immutable'
    ) THEN
        CREATE TRIGGER fin12_crash_hold_immutable
            BEFORE UPDATE OR DELETE ON posting_outbox_crash_holds
            FOR EACH ROW EXECUTE FUNCTION fin12_block_crash_hold_history_mutation();
    END IF;
END;
$fin12$;

REVOKE ALL ON posting_outbox_crash_holds FROM PUBLIC;
-- Do not grant live runtime rights. Test grants are only in disposable PG15/16.
-- No INSERT into posting_outbox_receipts, no state change, no retry, no network.
