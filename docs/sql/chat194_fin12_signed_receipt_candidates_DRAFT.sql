-- Chat194 FIN-12 TEST-ONLY cryptographic integrity envelope observations.
-- Standalone, UNAPPLIED, NON-PRODUCTION, no startup migration/worker/router.
-- This is NOT a verified Balance.ge/1C/Oris receipt, even if signed with
-- a synthetic key. Candidate metadata MUST NEVER settle an ERP intent.
-- Requires the separate Chat186 posting_outbox intent schema in disposable DB.
CREATE TABLE IF NOT EXISTS posting_outbox_receipt_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL CHECK
        (tenant_id <> '' AND tenant_id <> 'default' AND tenant_id = btrim(tenant_id)),
    outbox_id UUID NOT NULL,
    source_id TEXT NOT NULL CHECK (length(source_id) BETWEEN 1 AND 256),
    target_system TEXT NOT NULL CHECK (target_system IN ('balance','onec','oris')),
    idempotency_key TEXT NOT NULL CHECK (idempotency_key ~ '^[0-9a-f]{64}$'),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    provider_receipt_id TEXT NOT NULL CHECK
        (length(provider_receipt_id) BETWEEN 1 AND 200),
    outcome TEXT NOT NULL CHECK (outcome IN ('accepted','rejected')),
    signer_key_id TEXT NOT NULL CHECK
        (length(signer_key_id) BETWEEN 10 AND 200
         AND signer_key_id LIKE 'synthetic-%'),
    envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[0-9a-f]{64}$'),
    signature_sha256 TEXT NOT NULL CHECK (signature_sha256 ~ '^[0-9a-f]{64}$'),
    synthetic_integrity_ok BOOLEAN NOT NULL DEFAULT TRUE
        CHECK (synthetic_integrity_ok IS TRUE),
    vendor_authenticated BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (vendor_authenticated IS FALSE),
    provider_verified BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (provider_verified IS FALSE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id,target_system,signer_key_id,envelope_sha256),
    UNIQUE (tenant_id,target_system,provider_receipt_id),
    FOREIGN KEY (outbox_id,tenant_id)
        REFERENCES posting_outbox_intents (id,tenant_id)
);
ALTER TABLE posting_outbox_receipt_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_receipt_candidates FORCE ROW LEVEL SECURITY;
DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname=current_schema()
           AND tablename='posting_outbox_receipt_candidates'
           AND policyname='fin12_test_receipt_candidates_tenant'
    ) THEN
        CREATE POLICY fin12_test_receipt_candidates_tenant
          ON posting_outbox_receipt_candidates FOR ALL
          USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),''))
          WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
END;
$fin12$;

CREATE OR REPLACE FUNCTION fin12_test_receipt_source_guard()
RETURNS TRIGGER LANGUAGE plpgsql AS $fin12$
DECLARE src posting_outbox_intents%ROWTYPE;
BEGIN
    SELECT * INTO src FROM posting_outbox_intents
     WHERE id=NEW.outbox_id AND tenant_id=NEW.tenant_id;
    IF NOT FOUND OR src.state NOT IN ('unknown','in_flight')
        OR src.provider_receipt_id IS NOT NULL
        OR src.provider_verified_at IS NOT NULL
        OR src.source_type IS DISTINCT FROM 'journal_draft'
        OR src.source_id IS DISTINCT FROM NEW.source_id
        OR src.target_system IS DISTINCT FROM NEW.target_system
        OR src.idempotency_key IS DISTINCT FROM NEW.idempotency_key
        OR src.payload_sha256 IS DISTINCT FROM NEW.payload_sha256
    THEN
        RAISE EXCEPTION 'FIN12_RECEIPT_CANDIDATE_SOURCE_INVALID';
    END IF;
    RETURN NEW;
END;
$fin12$;

CREATE OR REPLACE FUNCTION fin12_test_receipt_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $fin12$
BEGIN
    RAISE EXCEPTION 'FIN12_RECEIPT_CANDIDATE_IMMUTABLE';
END;
$fin12$;

DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid='posting_outbox_receipt_candidates'::regclass
           AND tgname='fin12_test_receipt_source_check'
    ) THEN
        CREATE TRIGGER fin12_test_receipt_source_check
            BEFORE INSERT ON posting_outbox_receipt_candidates
            FOR EACH ROW EXECUTE FUNCTION fin12_test_receipt_source_guard();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid='posting_outbox_receipt_candidates'::regclass
           AND tgname='fin12_test_receipt_no_update_delete'
    ) THEN
        CREATE TRIGGER fin12_test_receipt_no_update_delete
            BEFORE UPDATE OR DELETE ON posting_outbox_receipt_candidates
            FOR EACH ROW EXECUTE FUNCTION fin12_test_receipt_immutable();
    END IF;
END;
$fin12$;
REVOKE ALL ON posting_outbox_receipt_candidates FROM PUBLIC;

-- This table has no FK/trigger that writes posting_outbox_receipts, updates
-- posting_outbox_intents to confirmed/rejected, or touches the ledger.
-- No runtime privileges are granted. The DB cannot validate Ed25519; only
-- the unregistered synthetic service checks test signatures. Production
-- vendor origin, key custody and adapter format remain EXTERNAL-HOLD.
