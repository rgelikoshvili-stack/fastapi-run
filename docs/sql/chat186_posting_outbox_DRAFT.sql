-- Chat186 FIN-12: durable ERP mutation intent / append-only receipts.
-- DRAFT / DISPOSABLE PG15/16 TESTS ONLY. NEVER a startup migration.
-- NO worker, webhook, route, live ERP write, or provider idempotency contract
-- is activated by creating this schema. Production still EXTERNAL-HOLD.
CREATE TABLE IF NOT EXISTS posting_outbox_intents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL CHECK (tenant_id <> '' AND tenant_id <> 'default'),
    source_type TEXT NOT NULL DEFAULT 'journal_draft'
        CHECK (source_type = 'journal_draft'),
    source_id TEXT NOT NULL CHECK (length(source_id) BETWEEN 1 AND 256),
    target_system TEXT NOT NULL CHECK (target_system IN ('balance','onec','oris')),
    idempotency_key TEXT NOT NULL CHECK (idempotency_key ~ '^[0-9a-f]{64}$'),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    state TEXT NOT NULL DEFAULT 'prepared' CHECK
        (state IN ('prepared','in_flight','unknown','confirmed','rejected')),
    provider_receipt_id TEXT NULL,
    provider_verified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id,source_type,source_id,target_system),
    UNIQUE(tenant_id,target_system,idempotency_key),
    UNIQUE(id,tenant_id),
    CONSTRAINT ck_fin12_receipt_consistency CHECK
        ((state='confirmed' AND provider_receipt_id IS NOT NULL AND provider_verified_at IS NOT NULL)
        OR (state<>'confirmed' AND provider_receipt_id IS NULL AND provider_verified_at IS NULL))
);
CREATE TABLE IF NOT EXISTS posting_outbox_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    outbox_id UUID NOT NULL,
    tenant_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('accepted','unknown','rejected')),
    provider_receipt_id TEXT NULL,
    evidence_sha256 TEXT NULL CHECK
        (evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'),
    verified_by TEXT NULL,
    verified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_fin12_acceptance_evidence CHECK
        (outcome = 'unknown' OR
         (evidence_sha256 IS NOT NULL AND verified_by IS NOT NULL
          AND btrim(verified_by) <> '' AND verified_at IS NOT NULL
          AND (outcome <> 'accepted' OR
               (provider_receipt_id IS NOT NULL AND btrim(provider_receipt_id) <> '')))),
    FOREIGN KEY (outbox_id,tenant_id)
        REFERENCES posting_outbox_intents (id,tenant_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fin12_verified_provider_receipt
    ON posting_outbox_receipts (tenant_id,provider_receipt_id)
    WHERE outcome = 'accepted' AND provider_receipt_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fin12_accepted_intent
    ON posting_outbox_receipts (outbox_id) WHERE outcome = 'accepted';

ALTER TABLE posting_outbox_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_intents FORCE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_receipts FORCE ROW LEVEL SECURITY;
DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'posting_outbox_intents'
          AND policyname = 'fin12_intent_tenant'
    ) THEN
        CREATE POLICY fin12_intent_tenant ON posting_outbox_intents FOR ALL
            USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),''))
            WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'posting_outbox_receipts'
          AND policyname = 'fin12_receipt_tenant'
    ) THEN
        CREATE POLICY fin12_receipt_tenant ON posting_outbox_receipts FOR ALL
            USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),''))
            WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
END;
$fin12$;

CREATE OR REPLACE FUNCTION fin12_block_delete_or_identity_change()
RETURNS trigger LANGUAGE plpgsql AS $fin12_lock$
BEGIN
    -- Chat195: a direct SQL INSERT must not forge an already-finished or
    -- already-in-flight vendor mutation. Only a fresh prepared intent is safe.
    IF TG_OP = 'INSERT' THEN
        IF NEW.state IS DISTINCT FROM 'prepared'
           OR NEW.provider_receipt_id IS NOT NULL
           OR NEW.provider_verified_at IS NOT NULL
        THEN
            RAISE EXCEPTION 'FIN12_INITIAL_STATE_NOT_PREPARED';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'FIN12_RECEIPT_OR_INTENT_IMMUTABLE';
    END IF;
    IF TG_TABLE_NAME = 'posting_outbox_receipts' THEN
        RAISE EXCEPTION 'FIN12_RECEIPT_OR_INTENT_IMMUTABLE';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.source_type IS DISTINCT FROM OLD.source_type
       OR NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.target_system IS DISTINCT FROM OLD.target_system
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256
       OR NEW.payload_json IS DISTINCT FROM OLD.payload_json
       OR (OLD.state = 'unknown' AND NEW.state = 'in_flight')
       OR (OLD.state = 'confirmed' AND NEW.state <> 'confirmed')
       OR (OLD.state = 'confirmed' AND
           (NEW.provider_receipt_id IS DISTINCT FROM OLD.provider_receipt_id OR
            NEW.provider_verified_at IS DISTINCT FROM OLD.provider_verified_at))
       OR (OLD.state = 'rejected' AND NEW IS DISTINCT FROM OLD)
    THEN
        RAISE EXCEPTION 'FIN12_RECEIPT_OR_INTENT_IMMUTABLE';
    END IF;

    -- Chat196: a prepared intent may be stored but MUST NOT enter the
    -- vendor-dispatch state until a certified provider idempotency/lease
    -- protocol exists. Otherwise a privileged direct SQL UPDATE bypasses
    -- the inactive worker/API gates and could be misread as a sent request.
    IF NEW.state = 'in_flight'
       AND OLD.state IS DISTINCT FROM NEW.state THEN
        RAISE EXCEPTION 'FIN12_DISPATCH_CONTRACT_UNVERIFIED';
    END IF;

    -- Chat195: no real provider authentication, independently attested
    -- receipt format or certified idempotency contract has been established.
    -- The older metadata-only gate is NOT a safe finalization authority.
    -- All synthetic receipts and operator observations remain HOLD.
    IF NEW.state IN ('confirmed','rejected')
       AND NEW.state IS DISTINCT FROM OLD.state THEN
        RAISE EXCEPTION 'FIN12_VENDOR_AUTHENTICATION_NOT_CONFIGURED';
    END IF;

    -- Existing local consistency conditions are defense-in-depth ONLY.
    -- They must not be interpreted as external provider verification.
    IF (OLD.state = 'prepared' AND NEW.state NOT IN ('prepared','in_flight','unknown'))
        OR (OLD.state = 'in_flight' AND NEW.state NOT IN
            ('in_flight','unknown','confirmed','rejected'))
        OR (OLD.state = 'unknown' AND NEW.state NOT IN
            ('unknown','confirmed','rejected'))
    THEN
        RAISE EXCEPTION 'FIN12_INVALID_STATE_TRANSITION';
    END IF;
    IF NEW.state IN ('confirmed','rejected')
       AND NEW.state IS DISTINCT FROM OLD.state
       AND NOT EXISTS (
            SELECT 1 FROM posting_outbox_receipts r
             WHERE r.outbox_id = NEW.id AND r.tenant_id = NEW.tenant_id
               AND r.outcome = CASE WHEN NEW.state = 'confirmed'
                                    THEN 'accepted' ELSE 'rejected' END
               AND r.evidence_sha256 IS NOT NULL
               AND r.verified_by IS NOT NULL AND btrim(r.verified_by) <> ''
               AND r.verified_at IS NOT NULL
               AND (NEW.state <> 'confirmed'
                    OR r.provider_receipt_id = NEW.provider_receipt_id)
       )
    THEN
        RAISE EXCEPTION 'FIN12_VERIFIED_RECEIPT_REQUIRED';
    END IF;
    RETURN NEW;
END;
$fin12_lock$;
DO $fin12$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgrelid='posting_outbox_intents'::regclass
                     AND tgname='fin12_intent_guard') THEN
        CREATE TRIGGER fin12_intent_guard
            BEFORE INSERT OR UPDATE OR DELETE ON posting_outbox_intents
            FOR EACH ROW EXECUTE FUNCTION fin12_block_delete_or_identity_change();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgrelid='posting_outbox_receipts'::regclass
                     AND tgname='fin12_receipt_guard') THEN
        CREATE TRIGGER fin12_receipt_guard
            BEFORE UPDATE OR DELETE ON posting_outbox_receipts
            FOR EACH ROW EXECUTE FUNCTION fin12_block_delete_or_identity_change();
    END IF;
END;
$fin12$;
-- Chat195: receipt metadata provided by any human or local adapter is NOT
-- authenticated vendor evidence. Until a separately reviewed real provider
-- contract/key-custody protocol exists, deny insertion of terminal receipts.
-- Chat197: no outcome, including `unknown`, may be inserted into the
-- provider-receipt table without an approved vendor-authentication contract.
-- Untrusted observations belong ONLY in the separate immutable HOLD tables.
-- A spoofed `unknown` row with fake verified_by/provider_receipt_id must not
-- become a misleading receipt for any future component.
CREATE OR REPLACE FUNCTION fin12_hold_unverified_provider_receipt()
RETURNS trigger LANGUAGE plpgsql AS $fin12_receipt$
BEGIN
    -- Chat197: verify even syntactically unknown observations do not bind
    -- across tenant boundaries. A matching FK by itself is not provider proof.
    IF NOT EXISTS (
        SELECT 1 FROM posting_outbox_intents i
        WHERE i.id=NEW.outbox_id AND i.tenant_id=NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'FIN12_RECEIPT_SOURCE_TENANT_MISMATCH';
    END IF;

    -- A local UNKNOWN observation is not a vendor-issued receipt, whether
    -- or not it carries forged receipt ID / verified_by / timestamp fields.
    -- Record manual uncertainty in the separate Chat193/196 HOLD model,
    -- never in a table that could later be mistaken for provider evidence.
    IF NEW.outcome = 'unknown' THEN
        RAISE EXCEPTION 'FIN12_UNKNOWN_PROVIDER_RECEIPT_HOLD';
    END IF;
    IF NEW.outcome IN ('accepted','rejected') THEN
        RAISE EXCEPTION 'FIN12_UNVERIFIED_PROVIDER_RECEIPT_HOLD';
    END IF;
    RAISE EXCEPTION 'FIN12_UNRECOGNIZED_PROVIDER_RECEIPT_HOLD';
END;
$fin12_receipt$;
DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid='posting_outbox_receipts'::regclass
           AND tgname='fin12_unverified_vendor_receipt_guard'
    ) THEN
        CREATE TRIGGER fin12_unverified_vendor_receipt_guard
            BEFORE INSERT ON posting_outbox_receipts
            FOR EACH ROW EXECUTE FUNCTION fin12_hold_unverified_provider_receipt();
    END IF;
END;
$fin12$;

REVOKE ALL ON posting_outbox_intents, posting_outbox_receipts FROM PUBLIC;
-- Runtime producer role may receive ONLY reviewed SELECT/INSERT rights;
-- reconciliation/receipt writers need separate privileged service accounts.
-- No proof of vendor idempotency, delivery, callback, external receipt validity
-- or ledger/ERP atomicity is claimed by this local Draft schema.
