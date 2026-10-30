-- Chat192 FIN-11 candidate ONLY: maker/checker correction review evidence.
-- NOT a registered migration. NO Production execution, router or ERP dispatch.
-- Requires operator-reviewed source schema, nonowner roles/grants, idp identity
-- and audit_log append-only policy before any activation. Safe for disposable PG.
CREATE TABLE IF NOT EXISTS correction_review_intents (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK (tenant_id <> '' AND tenant_id <> 'default'
                                   AND tenant_id = btrim(tenant_id)),
    draft_id BIGINT NOT NULL CHECK (draft_id > 0),
    source_id BIGINT NOT NULL CHECK (source_id > 0),
    entry_type TEXT NOT NULL CHECK (entry_type IN ('reversal','adjustment')),
    maker_subject TEXT NOT NULL CHECK (btrim(maker_subject) <> ''),
    maker_role TEXT NOT NULL CHECK (maker_role IN ('accountant','admin')),
    source_fingerprint TEXT NOT NULL CHECK (source_fingerprint ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL DEFAULT 'awaiting_checker'
        CHECK (state IN ('awaiting_checker','approved','rejected')),
    checker_subject TEXT,
    checker_role TEXT CHECK (checker_role IN ('cfo','admin')),
    decision_reason TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, draft_id),
    UNIQUE (id, tenant_id),
    CONSTRAINT ck_chat192_independent_checker CHECK (
        checker_subject IS NULL OR lower(checker_subject) <> lower(maker_subject)
    ),
    CONSTRAINT ck_chat192_review_state CHECK (
        (state = 'awaiting_checker' AND checker_subject IS NULL
            AND checker_role IS NULL AND decision_reason IS NULL
            AND decided_at IS NULL)
        OR
        (state IN ('approved','rejected')
            AND checker_subject IS NOT NULL AND btrim(checker_subject) <> ''
            AND checker_role IS NOT NULL AND decided_at IS NOT NULL
            AND (state <> 'rejected'
                 OR (decision_reason IS NOT NULL AND btrim(decision_reason) <> '')))
    )
);

CREATE TABLE IF NOT EXISTS correction_review_events (
    id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL,
    tenant_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('submitted','approved','rejected')),
    actor_subject TEXT NOT NULL CHECK (btrim(actor_subject) <> ''),
    actor_role TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL CHECK (source_fingerprint ~ '^[0-9a-f]{64}$'),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (review_id, action),
    FOREIGN KEY (review_id, tenant_id)
        REFERENCES correction_review_intents (id, tenant_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat192_one_terminal_decision
    ON correction_review_events (review_id)
    WHERE action IN ('approved','rejected');

ALTER TABLE correction_review_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE correction_review_intents FORCE ROW LEVEL SECURITY;
ALTER TABLE correction_review_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE correction_review_events FORCE ROW LEVEL SECURITY;
DO $fin11$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
            AND tablename='correction_review_intents'
            AND policyname='chat192_reviews_tenant'
    ) THEN
        CREATE POLICY chat192_reviews_tenant ON correction_review_intents FOR ALL
            USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),''))
            WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
            AND tablename='correction_review_events'
            AND policyname='chat192_events_tenant'
    ) THEN
        CREATE POLICY chat192_events_tenant ON correction_review_events FOR ALL
            USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),''))
            WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id',true),''));
    END IF;
END;
$fin11$;

CREATE OR REPLACE FUNCTION chat192_review_immutable_or_require_event()
RETURNS trigger LANGUAGE plpgsql AS $fin11$
BEGIN
    IF TG_OP = 'DELETE' OR TG_TABLE_NAME = 'correction_review_events' THEN
        RAISE EXCEPTION 'FIN11_REVIEW_EVIDENCE_IMMUTABLE';
    END IF;
    IF OLD.state <> 'awaiting_checker'
       OR NEW.state NOT IN ('approved','rejected')
       OR NEW.id IS DISTINCT FROM OLD.id
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.draft_id IS DISTINCT FROM OLD.draft_id
       OR NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.entry_type IS DISTINCT FROM OLD.entry_type
       OR NEW.maker_subject IS DISTINCT FROM OLD.maker_subject
       OR NEW.maker_role IS DISTINCT FROM OLD.maker_role
       OR NEW.source_fingerprint IS DISTINCT FROM OLD.source_fingerprint
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'FIN11_REVIEW_EVIDENCE_IMMUTABLE';
    END IF;
    IF NEW.checker_subject IS NULL
       OR NEW.checker_role NOT IN ('cfo','admin')
       OR lower(NEW.checker_subject) = lower(OLD.maker_subject)
       OR NOT EXISTS (
           SELECT 1 FROM correction_review_events e
            WHERE e.review_id=NEW.id AND e.tenant_id=NEW.tenant_id
              AND e.action=NEW.state
              AND e.actor_subject=NEW.checker_subject
              AND e.actor_role=NEW.checker_role
              AND e.source_fingerprint=OLD.source_fingerprint
              AND (NEW.decision_reason IS NOT DISTINCT FROM e.reason)
       )
    THEN
        RAISE EXCEPTION 'FIN11_REVIEW_CHECKER_EVIDENCE_REQUIRED';
    END IF;
    RETURN NEW;
END;
$fin11$;
DO $fin11$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid='correction_review_intents'::regclass
           AND tgname='chat192_review_intent_guard'
    ) THEN
        CREATE TRIGGER chat192_review_intent_guard
            BEFORE UPDATE OR DELETE ON correction_review_intents
            FOR EACH ROW EXECUTE FUNCTION chat192_review_immutable_or_require_event();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid='correction_review_events'::regclass
           AND tgname='chat192_review_event_guard'
    ) THEN
        CREATE TRIGGER chat192_review_event_guard
            BEFORE UPDATE OR DELETE ON correction_review_events
            FOR EACH ROW EXECUTE FUNCTION chat192_review_immutable_or_require_event();
    END IF;
END;
$fin11$;
REVOKE ALL ON correction_review_intents, correction_review_events FROM PUBLIC;
REVOKE ALL ON SEQUENCE correction_review_intents_id_seq,
                   correction_review_events_id_seq FROM PUBLIC;
-- No GRANT to live API, no status update in journal_drafts.
-- Application roles/verified identity and migration acceptance are EXTERNAL-HOLD.
