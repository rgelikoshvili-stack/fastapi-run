-- Chat201 FIN-12: deny premature local posted-ledger/outbox coexistence.
-- UNAPPLIED DRAFT. DISPOSABLE PG15/16 ONLY. Not a startup migration.
-- Prerequisites: migration 011 + Chat179 composite tenant FKs + Chat185
-- immutable/unique posted sources + Chat186 unverified ERP intent schema.
-- No real ERP call, no dispatch, no provider receipt and NO backfill/deletion.
--
-- Without trusted real provider acknowledgment a journal_draft must NEVER
-- simultaneously have a posted-ledger source and an unverified outbox intent.
-- This is a temporary HOLD interlock, NOT a production-ready finalizer.
-- Real verified receipt + atomic local commit needs a separately approved
-- replacement protocol and vendor-specific certified idempotency.

DO $chat201_preflight$
BEGIN
    IF to_regclass('journal_entry_sources') IS NULL
       OR to_regclass('posting_outbox_intents') IS NULL
       OR NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conrelid='journal_entry_sources'::regclass
             AND conname='fk_chat179_jes_header_tenant'
       )
       OR NOT EXISTS (
           SELECT 1 FROM pg_indexes
           WHERE schemaname=current_schema()
             AND tablename='journal_entry_sources'
             AND indexname='uq_chat185_posted_source_identity'
       )
    THEN
        RAISE EXCEPTION 'FIN12_LOCAL_PAIR_PREREQUISITES_MISSING';
    END IF;

    -- A constrained-role migration must NOT falsely certify an RLS subset.
    -- row_security=off causes an error when rows would be filtered.
    PERFORM set_config('row_security','off',true);
    IF EXISTS (
        SELECT 1
          FROM posting_outbox_intents o
          JOIN journal_entry_sources s
            ON s.tenant_id=o.tenant_id
           AND s.source_type='journal_draft'
           AND s.source_id=o.source_id
         WHERE o.source_type='journal_draft'
    ) THEN
        RAISE EXCEPTION 'FIN12_LOCAL_PAIR_PREFLIGHT_CONFLICT'
          USING HINT='Preserve all historical records and investigate; no automatic repair.';
    END IF;
END;
$chat201_preflight$;

-- All writers to the two local tables use ONE tenant/source advisory
-- transaction lock. The second transaction re-reads after acquiring it,
-- to prevent two concurrent READ COMMITTED transactions from each seeing
-- absence of the other uncommitted row. A separate isolation level fails
-- closed because a stale transaction snapshot defeats this guarantee.
--
-- This is not a vendor fencing token and never permits retry.
CREATE OR REPLACE FUNCTION chat201_block_unverified_local_pair()
RETURNS trigger LANGUAGE plpgsql AS $chat201_guard$
BEGIN
    IF NEW.source_type IS DISTINCT FROM 'journal_draft' THEN
        RETURN NEW;
    END IF;
    IF current_setting('transaction_isolation') IS DISTINCT FROM 'read committed' THEN
        RAISE EXCEPTION 'FIN12_LOCAL_PAIR_ISOLATION_UNSUPPORTED';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            jsonb_build_array('fin12-local-pair-v1',NEW.tenant_id,NEW.source_id)::text,
            0
        )
    );

    IF TG_TABLE_NAME='posting_outbox_intents' THEN
        IF EXISTS (
            SELECT 1 FROM journal_entry_sources s
            WHERE s.tenant_id=NEW.tenant_id
              AND s.source_type='journal_draft'
              AND s.source_id=NEW.source_id
        ) THEN
            RAISE EXCEPTION 'FIN12_LOCAL_EARLY_LEDGER_OUTBOX_HOLD';
        END IF;
    ELSIF TG_TABLE_NAME='journal_entry_sources' THEN
        IF EXISTS (
            SELECT 1 FROM posting_outbox_intents o
            WHERE o.tenant_id=NEW.tenant_id
              AND o.source_type='journal_draft'
              AND o.source_id=NEW.source_id
        ) THEN
            RAISE EXCEPTION 'FIN12_LOCAL_UNVERIFIED_OUTBOX_LEDGER_HOLD';
        END IF;
    ELSE
        RAISE EXCEPTION 'FIN12_LOCAL_PAIR_UNEXPECTED_TABLE';
    END IF;
    RETURN NEW;
END;
$chat201_guard$;

DO $chat201_install$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='posting_outbox_intents'::regclass
          AND tgname='chat201_outbox_vs_ledger_guard'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER chat201_outbox_vs_ledger_guard
        BEFORE INSERT ON posting_outbox_intents
        FOR EACH ROW EXECUTE FUNCTION chat201_block_unverified_local_pair();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='journal_entry_sources'::regclass
          AND tgname='chat201_ledger_vs_outbox_guard'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER chat201_ledger_vs_outbox_guard
        BEFORE INSERT ON journal_entry_sources
        FOR EACH ROW EXECUTE FUNCTION chat201_block_unverified_local_pair();
    END IF;
END;
$chat201_install$;

-- No runtime grants, no public route, no outbox/ledger/receipt updates, no
-- production authorization. Operator review required for old conflicting data.
-- This HOLD-only guard must be versioned/reviewed before any eventual
-- vendor-verified posted-ledger/receipt/outbox transaction could be enabled.
