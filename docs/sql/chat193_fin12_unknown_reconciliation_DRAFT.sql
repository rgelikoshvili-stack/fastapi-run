-- Chat193 FIN-12: independent manual UNKNOWN investigation ONLY.
-- UNAPPLIED / NO STARTUP MIGRATION / SYNTHETIC PG15/16 ONLY.
-- Requires existing, unapplied Chat186 posting_outbox DRAFT schema.
-- A manual claim/digest is NOT vendor-authenticated, never a receipt;
-- NEVER dispatch, retry, confirm, reject, update ledger or ERP.
CREATE TABLE IF NOT EXISTS posting_outbox_reconciliation_cases (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK (tenant_id <> '' AND tenant_id <> 'default'
                                   AND tenant_id=btrim(tenant_id)),
    outbox_id UUID NOT NULL,
    source_id TEXT NOT NULL CHECK (length(source_id) BETWEEN 1 AND 256),
    target_system TEXT NOT NULL CHECK (target_system IN ('balance','onec','oris')),
    idempotency_key TEXT NOT NULL CHECK (idempotency_key ~ '^[0-9a-f]{64}$'),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    opener_subject TEXT NOT NULL CHECK (btrim(opener_subject) <> ''),
    opener_role TEXT NOT NULL CHECK (opener_role IN ('accountant','admin')),
    claimed_outcome TEXT NOT NULL CHECK
        (claimed_outcome IN ('claimed_accepted','claimed_rejected','undetermined')),
    evidence_sha256 TEXT NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL DEFAULT 'open'
        CHECK (state IN ('open','reviewed_hold')),
    reviewer_subject TEXT,
    reviewer_role TEXT CHECK (reviewer_role IN ('cfo','admin')),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id,outbox_id),
    UNIQUE (id,tenant_id),
    CONSTRAINT fk_fin12_recon_intent FOREIGN KEY (outbox_id,tenant_id)
        REFERENCES posting_outbox_intents(id,tenant_id),
    CONSTRAINT ck_fin12_recon_review_state CHECK (
        (state='open' AND reviewer_subject IS NULL
                      AND reviewer_role IS NULL AND reviewed_at IS NULL)
        OR (state='reviewed_hold' AND reviewer_subject IS NOT NULL
                AND btrim(reviewer_subject) <> ''
                AND reviewer_role IS NOT NULL AND reviewed_at IS NOT NULL
                AND lower(reviewer_subject) <> lower(opener_subject))
    )
);
CREATE TABLE IF NOT EXISTS posting_outbox_reconciliation_events (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    case_id BIGINT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('opened','reviewed_hold')),
    actor_subject TEXT NOT NULL CHECK (btrim(actor_subject) <> ''),
    actor_role TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (case_id,action),
    CONSTRAINT fk_fin12_recon_event_case FOREIGN KEY (case_id,tenant_id)
        REFERENCES posting_outbox_reconciliation_cases(id,tenant_id)
);

ALTER TABLE posting_outbox_reconciliation_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_reconciliation_cases FORCE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_reconciliation_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE posting_outbox_reconciliation_events FORCE ROW LEVEL SECURITY;
DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
          AND tablename='posting_outbox_reconciliation_cases'
          AND policyname='fin12_reconciliation_cases_tenant'
    ) THEN
        CREATE POLICY fin12_reconciliation_cases_tenant
          ON posting_outbox_reconciliation_cases FOR ALL
          USING (tenant_id=nullif(current_setting('app.current_tenant_id',true),''))
          WITH CHECK (tenant_id=nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
          AND tablename='posting_outbox_reconciliation_events'
          AND policyname='fin12_reconciliation_events_tenant'
    ) THEN
        CREATE POLICY fin12_reconciliation_events_tenant
          ON posting_outbox_reconciliation_events FOR ALL
          USING (tenant_id=nullif(current_setting('app.current_tenant_id',true),''))
          WITH CHECK (tenant_id=nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
END;
$fin12$;

-- Direct SQL must not claim a fabricated case for a non-UNKNOWN operation.
CREATE OR REPLACE FUNCTION fin12_reconciliation_check_source()
RETURNS TRIGGER LANGUAGE plpgsql AS $fin12$
DECLARE src posting_outbox_intents%ROWTYPE;
BEGIN
    SELECT * INTO src FROM posting_outbox_intents
     WHERE id=NEW.outbox_id AND tenant_id=NEW.tenant_id FOR UPDATE;
    IF NOT FOUND OR src.state IS DISTINCT FROM 'unknown' THEN
        RAISE EXCEPTION 'FIN12_RECON_SOURCE_NOT_UNKNOWN';
    END IF;
    IF src.source_type IS DISTINCT FROM 'journal_draft'
       OR src.source_id IS DISTINCT FROM NEW.source_id
       OR src.target_system IS DISTINCT FROM NEW.target_system
       OR src.idempotency_key IS DISTINCT FROM NEW.idempotency_key
       OR src.payload_sha256 IS DISTINCT FROM NEW.payload_sha256
       OR src.provider_receipt_id IS NOT NULL
       OR src.provider_verified_at IS NOT NULL
    THEN
        RAISE EXCEPTION 'FIN12_RECON_SOURCE_MISMATCH';
    END IF;
    RETURN NEW;
END;
$fin12$;

-- Immutable event identity; only the one independent HOLD review transition.
CREATE OR REPLACE FUNCTION fin12_reconciliation_guard_case()
RETURNS TRIGGER LANGUAGE plpgsql AS $fin12$
DECLARE still_unknown BOOLEAN;
BEGIN
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION 'FIN12_RECON_HISTORY_IMMUTABLE';
    END IF;
    IF OLD.state <> 'open'
       OR NEW.state <> 'reviewed_hold'
       OR NEW.id IS DISTINCT FROM OLD.id
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.outbox_id IS DISTINCT FROM OLD.outbox_id
       OR NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.target_system IS DISTINCT FROM OLD.target_system
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256
       OR NEW.opener_subject IS DISTINCT FROM OLD.opener_subject
       OR NEW.opener_role IS DISTINCT FROM OLD.opener_role
       OR NEW.claimed_outcome IS DISTINCT FROM OLD.claimed_outcome
       OR NEW.evidence_sha256 IS DISTINCT FROM OLD.evidence_sha256
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.reviewer_role NOT IN ('cfo','admin')
       OR NEW.reviewer_subject IS NULL
       OR lower(NEW.reviewer_subject)=lower(OLD.opener_subject)
    THEN
        RAISE EXCEPTION 'FIN12_RECON_HISTORY_IMMUTABLE';
    END IF;
    SELECT EXISTS (
        SELECT 1 FROM posting_outbox_intents i
         WHERE i.id=NEW.outbox_id AND i.tenant_id=NEW.tenant_id
           AND i.state='unknown'
    ) INTO still_unknown;
    IF NOT still_unknown OR NOT EXISTS (
        SELECT 1 FROM posting_outbox_reconciliation_events e
         WHERE e.case_id=NEW.id AND e.tenant_id=NEW.tenant_id
           AND e.action='reviewed_hold'
           AND e.actor_subject=NEW.reviewer_subject
           AND e.actor_role=NEW.reviewer_role
           AND e.evidence_sha256=OLD.evidence_sha256
    ) THEN
        RAISE EXCEPTION 'FIN12_RECON_REVIEW_EVIDENCE_REQUIRED';
    END IF;
    RETURN NEW;
END;
$fin12$;

CREATE OR REPLACE FUNCTION fin12_reconciliation_guard_event()
RETURNS TRIGGER LANGUAGE plpgsql AS $fin12$
DECLARE parent posting_outbox_reconciliation_cases%ROWTYPE;
BEGIN
    IF TG_OP IN ('UPDATE','DELETE') THEN
        RAISE EXCEPTION 'FIN12_RECON_HISTORY_IMMUTABLE';
    END IF;
    SELECT * INTO parent FROM posting_outbox_reconciliation_cases
     WHERE id=NEW.case_id AND tenant_id=NEW.tenant_id FOR UPDATE;
    IF NOT FOUND OR parent.state <> 'open'
       OR NEW.evidence_sha256 IS DISTINCT FROM parent.evidence_sha256
       OR (NEW.action='opened'
           AND (NEW.actor_subject IS DISTINCT FROM parent.opener_subject
                OR NEW.actor_role IS DISTINCT FROM parent.opener_role))
       OR (NEW.action='reviewed_hold'
           AND (NEW.actor_role NOT IN ('cfo','admin')
                OR lower(NEW.actor_subject)=lower(parent.opener_subject)))
    THEN
        RAISE EXCEPTION 'FIN12_RECON_EVENT_ORIGIN_INVALID';
    END IF;
    RETURN NEW;
END;
$fin12$;

DO $fin12$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='posting_outbox_reconciliation_cases'::regclass
          AND tgname='fin12_recon_source_guard'
    ) THEN
        CREATE TRIGGER fin12_recon_source_guard
            BEFORE INSERT ON posting_outbox_reconciliation_cases
            FOR EACH ROW EXECUTE FUNCTION fin12_reconciliation_check_source();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='posting_outbox_reconciliation_cases'::regclass
          AND tgname='fin12_recon_case_guard'
    ) THEN
        CREATE TRIGGER fin12_recon_case_guard
            BEFORE UPDATE OR DELETE ON posting_outbox_reconciliation_cases
            FOR EACH ROW EXECUTE FUNCTION fin12_reconciliation_guard_case();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='posting_outbox_reconciliation_events'::regclass
          AND tgname='fin12_recon_event_guard'
    ) THEN
        CREATE TRIGGER fin12_recon_event_guard
            BEFORE INSERT OR UPDATE OR DELETE ON posting_outbox_reconciliation_events
            FOR EACH ROW EXECUTE FUNCTION fin12_reconciliation_guard_event();
    END IF;
END;
$fin12$;

REVOKE ALL ON posting_outbox_reconciliation_cases,
              posting_outbox_reconciliation_events FROM PUBLIC;
REVOKE ALL ON SEQUENCE posting_outbox_reconciliation_cases_id_seq,
                       posting_outbox_reconciliation_events_id_seq FROM PUBLIC;
-- NO live role GRANTS. Signed tenant/JWT identity, vendor receipt verification,
-- vendor-certified idempotency and ERP/ledger local atomicity: EXTERNAL-HOLD.
