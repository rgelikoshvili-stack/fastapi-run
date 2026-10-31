-- Chat189 FIN-11 reversal source uniqueness — DRAFT / DISPOSABLE TESTS ONLY.
-- NOT a registered migration. DO NOT APPLY TO CLOUD SQL OR PRODUCTION.
-- Requires reviewed journal_drafts(tenant_id,entry_type,status,
-- reversal_of_draft_id) schema and full-row inventory before rollout.
-- Has no automatic data repair, status rewrite, or historical deletion.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
-- If the running reviewer cannot read all tenants, fail rather than verify
-- a misleading RLS-filtered subset of existing journal_drafts.
SET LOCAL row_security = off;

DO $fin11$
BEGIN
    -- An active linked legacy row labelled normal/standard/unknown could
    -- actually be an older reversal. Do not certify a misleading clean index.
    IF EXISTS (
        SELECT 1 FROM journal_drafts
         WHERE reversal_of_draft_id IS NOT NULL
           AND status IS DISTINCT FROM 'rejected'
           AND (entry_type IS NULL OR entry_type NOT IN ('reversal','adjustment'))
    ) THEN
        RAISE EXCEPTION 'FIN11_AMBIGUOUS_CORRECTION_HISTORY_PREFLIGHT'
            USING HINT = 'Classify each linked legacy entry with separate evidence; do not auto-rewrite.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM journal_drafts
         WHERE entry_type = 'reversal'
           AND status IS DISTINCT FROM 'rejected'
           AND (tenant_id IS NULL OR btrim(tenant_id) = ''
                OR tenant_id = 'default' OR reversal_of_draft_id IS NULL)
    ) THEN
        RAISE EXCEPTION 'FIN11_REVERSAL_IDENTITY_PREFLIGHT'
            USING HINT = 'Review existing reversal identities; never backfill automatically.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM journal_drafts
         WHERE entry_type = 'reversal'
           AND status IS DISTINCT FROM 'rejected'
         GROUP BY tenant_id, reversal_of_draft_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'FIN11_REVERSAL_DUPLICATE_PREFLIGHT'
            USING HINT = 'Review duplicate histories with maker/checker; never delete.';
    END IF;
END
$fin11$;

-- The ordinary adjustment rows share reversal_of_draft_id as a reference;
-- they MUST NOT exhaust this unique reversal identity.
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat189_tenant_active_reversal
    ON journal_drafts (tenant_id, reversal_of_draft_id)
    WHERE entry_type = 'reversal'
      AND status IS DISTINCT FROM 'rejected';

-- Null/invalid source must never pass as a separate unique-key identity.
DO $fin11$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'journal_drafts'::regclass
           AND conname = 'ck_chat189_reversal_identity'
    ) THEN
        ALTER TABLE journal_drafts
          ADD CONSTRAINT ck_chat189_reversal_identity
          CHECK (entry_type IS DISTINCT FROM 'reversal'
                 OR status = 'rejected'
                 OR (tenant_id IS NOT NULL AND btrim(tenant_id) <> ''
                     AND tenant_id <> 'default'
                     AND reversal_of_draft_id IS NOT NULL));
    END IF;
END
$fin11$;
COMMIT;

-- This index is DB uniqueness, not exactly-once ERP posting, maker/checker,
-- receipt proof, or a durable event-audit system. Concurrent direct SQL
-- attempts are refused but live write roles and release checklist are HOLD.
