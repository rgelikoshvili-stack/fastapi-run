-- Chat207 FIN-11 — candidate DDL ONLY. NOT a registered migration.
-- NEVER apply to a live database without separately approved preflight,
-- role/grant/RLS audit, deployment procedure and rollback/retention plan.
-- In this PR it is executed ONLY inside disposable localhost PG15/PG16 tests.
-- Chat192 Maker/Checker remains an INERT service; ERP/production HOLD.
--
-- Strict identity: one correction-creation event per tenant+draft across
-- BOTH reversal_draft_created and adjustment_draft_created actions.
-- Existing history MUST be evaluated first; never delete/repair it silently.
DO $fin11$
BEGIN
    IF EXISTS (
        SELECT 1 FROM audit_log
         WHERE resource = 'journal_drafts'
           AND action IN ('reversal_draft_created','adjustment_draft_created')
         GROUP BY tenant_id, resource_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'FIN11_CREATOR_AUDIT_DUPLICATE_PREFLIGHT_FAILED';
    END IF;
    IF EXISTS (
        SELECT 1 FROM audit_log
         WHERE resource = 'journal_drafts'
           AND action IN ('reversal_draft_created','adjustment_draft_created')
           AND (tenant_id IS NULL OR btrim(tenant_id) IN ('', 'default')
                OR resource_id IS NULL
                OR resource_id !~ '^[1-9][0-9]*$')
    ) THEN
        RAISE EXCEPTION 'FIN11_CREATOR_AUDIT_IDENTITY_PREFLIGHT_FAILED';
    END IF;
END;
$fin11$;

-- A partial UNIQUE index also rejects concurrent new inserts not protected
-- by Chat206 SELECT ... FOR SHARE (which locks old matching rows only).
-- No status predicate: an event cannot bypass uniqueness by choosing an
-- alternate status. Different tenant IDs remain independent.
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat207_fin11_creator_event_per_draft
    ON audit_log (tenant_id, resource_id)
    WHERE resource = 'journal_drafts'
      AND action IN ('reversal_draft_created','adjustment_draft_created');

CREATE OR REPLACE FUNCTION chat207_fin11_creator_audit_guard()
RETURNS trigger LANGUAGE plpgsql AS $fin11$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.resource = 'journal_drafts'
           AND NEW.action IN ('reversal_draft_created','adjustment_draft_created')
           AND (NEW.tenant_id IS NULL
                OR btrim(NEW.tenant_id) IN ('','default')
                OR NEW.resource_id IS NULL
                OR NEW.resource_id !~ '^[1-9][0-9]*$')
        THEN
            RAISE EXCEPTION 'FIN11_CREATOR_AUDIT_INVALID_IDENTITY';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        IF OLD.resource = 'journal_drafts'
           AND OLD.action IN ('reversal_draft_created','adjustment_draft_created')
        THEN
            RAISE EXCEPTION 'FIN11_CREATOR_AUDIT_IMMUTABLE';
        END IF;
        RETURN OLD;
    END IF;

    -- UPDATE: block changes TO OR FROM a protected creation-audit row.
    -- This prevents hiding the event by changing action/resource/status.
    IF (OLD.resource = 'journal_drafts'
        AND OLD.action IN ('reversal_draft_created','adjustment_draft_created'))
       OR (NEW.resource = 'journal_drafts'
        AND NEW.action IN ('reversal_draft_created','adjustment_draft_created'))
    THEN
        RAISE EXCEPTION 'FIN11_CREATOR_AUDIT_IMMUTABLE';
    END IF;
    RETURN NEW;
END;
$fin11$;

-- Repeated application in disposable tests must not duplicate triggers.
DO $fin11$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid = 'audit_log'::regclass
           AND tgname = 'chat207_fin11_creator_audit_guard'
           AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER chat207_fin11_creator_audit_guard
            BEFORE INSERT OR UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION chat207_fin11_creator_audit_guard();
    END IF;
END;
$fin11$;

-- Does NOT establish authenticated JWT creator identity, authoritative
-- audit table grants, owner/superuser trigger safety, approval transitions,
-- posted-ledger reversals, provider receipts or production migration safety.
-- No runtime GRANT and NO activation. Production HOLD.
