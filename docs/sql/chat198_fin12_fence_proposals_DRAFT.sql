-- Chat198 FIN-12: offline one-shot FENCE PROPOSAL evidence, NOT A LEASE.
-- DRAFT / DISPOSABLE PG15/16 ONLY. Do not register as startup migration.
-- Requires chat186_posting_outbox_DRAFT.sql in a disposable test schema.
-- No vendor-certified idempotency, dispatch lease, TTL/reclaim, worker,
-- ERP receipt, external callback, ledger mutation or provider network I/O.
-- This is a preparatory immutable record: epoch=1 is NOT a fencing credential.

CREATE TABLE IF NOT EXISTS posting_outbox_fence_proposals (
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
    owner_subject TEXT NOT NULL CHECK (
        length(owner_subject) BETWEEN 1 AND 200
        AND owner_subject = btrim(owner_subject)
    ),
    owner_role TEXT NOT NULL CHECK (owner_role IN ('accountant','admin')),
    fence_epoch BIGINT NOT NULL DEFAULT 1 CHECK (fence_epoch = 1),
    proposal_state TEXT NOT NULL DEFAULT 'hold_only'
        CHECK (proposal_state = 'hold_only'),
    lease_authoritative BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (lease_authoritative IS FALSE),
    dispatch_allowed BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (dispatch_allowed IS FALSE),
    retry_allowed BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (retry_allowed IS FALSE),
    provider_idempotency_certified BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (provider_idempotency_certified IS FALSE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id,outbox_id),
    FOREIGN KEY (outbox_id,tenant_id)
        REFERENCES posting_outbox_intents(id,tenant_id)
);

ALTER TABLE posting_outbox_fence_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_fence_proposals FORCE ROW LEVEL SECURITY;
DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
          AND tablename='posting_outbox_fence_proposals'
          AND policyname='fin12_fence_proposal_tenant'
    ) THEN
        CREATE POLICY fin12_fence_proposal_tenant
          ON posting_outbox_fence_proposals FOR ALL
          USING (tenant_id=nullif(current_setting('app.current_tenant_id',true),''))
          WITH CHECK (tenant_id=nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
END;
$fin12$;

CREATE OR REPLACE FUNCTION fin12_fence_proposal_insert_guard()
RETURNS trigger LANGUAGE plpgsql AS $fin12_fence$
DECLARE src posting_outbox_intents%ROWTYPE;
BEGIN
    IF NEW.fence_epoch IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'FIN12_FENCE_EPOCH_UNAUTHORIZED';
    END IF;
    SELECT * INTO src FROM posting_outbox_intents
      WHERE tenant_id=NEW.tenant_id AND id=NEW.outbox_id;
    IF NOT FOUND OR src.state IS DISTINCT FROM 'prepared' THEN
        RAISE EXCEPTION 'FIN12_FENCE_SOURCE_NOT_PREPARED';
    END IF;
    IF src.source_type IS DISTINCT FROM 'journal_draft'
       OR src.source_id IS DISTINCT FROM NEW.source_id
       OR src.target_system IS DISTINCT FROM NEW.target_system
       OR src.idempotency_key IS DISTINCT FROM NEW.idempotency_key
       OR src.payload_sha256 IS DISTINCT FROM NEW.payload_sha256
       OR src.provider_receipt_id IS NOT NULL
       OR src.provider_verified_at IS NOT NULL
    THEN
        RAISE EXCEPTION 'FIN12_FENCE_SOURCE_MISMATCH';
    END IF;
    RETURN NEW;
END;
$fin12_fence$;

CREATE OR REPLACE FUNCTION fin12_fence_proposal_immutable()
RETURNS trigger LANGUAGE plpgsql AS $fin12_fence$
BEGIN
    RAISE EXCEPTION 'FIN12_FENCE_EVIDENCE_IMMUTABLE';
END;
$fin12_fence$;

DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid='posting_outbox_fence_proposals'::regclass
           AND tgname='fin12_fence_source_guard'
    ) THEN
        CREATE TRIGGER fin12_fence_source_guard
            BEFORE INSERT ON posting_outbox_fence_proposals
            FOR EACH ROW EXECUTE FUNCTION fin12_fence_proposal_insert_guard();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid='posting_outbox_fence_proposals'::regclass
           AND tgname='fin12_fence_evidence_immutable'
    ) THEN
        CREATE TRIGGER fin12_fence_evidence_immutable
            BEFORE UPDATE OR DELETE ON posting_outbox_fence_proposals
            FOR EACH ROW EXECUTE FUNCTION fin12_fence_proposal_immutable();
    END IF;
END;
$fin12$;

REVOKE ALL ON posting_outbox_fence_proposals FROM PUBLIC;
-- Test-only grants are created by the isolated PG15/16 test fixture.
-- NO live credentials, no app/worker roles, no expiry-based retry,
-- no second epoch or external provider lease is authorized.
