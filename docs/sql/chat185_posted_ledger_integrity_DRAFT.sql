-- Chat185 FIN-06: DB-enforced ledger source uniqueness, immutability and
-- deferred header/line balancing. DRAFT / DISPOSABLE TEST ONLY.
-- This file is NOT a registered startup migration or a Production operation.
-- Requires migration 011 AND reviewed Chat179 composite-tenant FKs first.
-- No backfill, truncation, correction or deletion of legacy financial data.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SET LOCAL row_security = off; -- fail rather than falsely pass an RLS-filtered preflight

DO $chat185$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'journal_entry_lines'::regclass
          AND conname = 'fk_chat179_jel_header_tenant'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'journal_entry_sources'::regclass
          AND conname = 'fk_chat179_jes_header_tenant'
    ) THEN
        RAISE EXCEPTION 'LEDGER_TENANT_FK_PREREQUISITE_MISSING';
    END IF;

    IF EXISTS (
        SELECT 1 FROM journal_entry_sources
        WHERE source_type IN ('journal_draft', 'posting_log')
        GROUP BY tenant_id, source_type, source_id HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'LEDGER_SOURCE_DUPLICATE_PREFLIGHT_FAILED'
            USING HINT = 'Review all duplicates; no automatic repair or deletion.';
    END IF;

    -- Check the ENTIRE existing source, not only the runtime-tenant slice.
    IF EXISTS (
        SELECT 1
        FROM journal_entry_headers h
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS line_count,
                   COALESCE(SUM(l.debit),0) AS debits,
                   COALESCE(SUM(l.credit),0) AS credits,
                   COALESCE(SUM(CASE WHEN l.debit > 0 THEN l.amount_gel ELSE 0 END),0) AS gel_debits,
                   COALESCE(SUM(CASE WHEN l.credit > 0 THEN l.amount_gel ELSE 0 END),0) AS gel_credits,
                   COALESCE(BOOL_AND(
                       l.currency = h.currency
                       AND l.exchange_rate = h.exchange_rate
                       AND l.amount_gel = ROUND((l.debit + l.credit) * h.exchange_rate,2)
                   ),FALSE) AS valid_lines
              FROM journal_entry_lines l
             WHERE l.journal_entry_id = h.id AND l.tenant_id = h.tenant_id
        ) agg ON TRUE
        WHERE agg.line_count < 2
           OR agg.debits <> h.total_debit OR agg.credits <> h.total_credit
           OR agg.gel_debits <> agg.gel_credits OR NOT agg.valid_lines
           OR NOT EXISTS (
                SELECT 1 FROM journal_entry_sources s
                WHERE s.journal_entry_id = h.id AND s.tenant_id = h.tenant_id
           )
    ) THEN
        RAISE EXCEPTION 'LEDGER_INTEGRITY_PREFLIGHT_FAILED'
            USING HINT = 'Preserve and review historical rows; no automatic backfill.';
    END IF;
END;
$chat185$;

-- Direct SQL bypassing the cooperative application advisory lock still
-- cannot link the same draft or receipt to another posted header in a tenant.
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat185_posted_source_identity
    ON journal_entry_sources (tenant_id, source_type, source_id)
    WHERE source_type IN ('journal_draft', 'posting_log');

CREATE OR REPLACE FUNCTION chat185_block_ledger_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'LEDGER_IMMUTABLE';
END;
$$;

DO $chat185$
DECLARE table_name TEXT;
DECLARE trigger_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'journal_entry_headers', 'journal_entry_lines', 'journal_entry_sources'
    ] LOOP
        trigger_name := 'chat185_immutable_' || table_name;
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgrelid = to_regclass(table_name) AND tgname = trigger_name
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I '
                || 'FOR EACH ROW EXECUTE FUNCTION chat185_block_ledger_mutation()',
                trigger_name, table_name
            );
        END IF;
    END LOOP;
END;
$chat185$;

CREATE OR REPLACE FUNCTION chat185_check_posted_entry_at_commit()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE head_id UUID;
DECLARE head RECORD;
DECLARE totals RECORD;
BEGIN
    IF TG_TABLE_NAME = 'journal_entry_headers' THEN
        head_id := NEW.id;
    ELSE
        head_id := NEW.journal_entry_id;
    END IF;

    SELECT id, tenant_id, total_debit, total_credit, currency, exchange_rate
      INTO head FROM journal_entry_headers WHERE id = head_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LEDGER_HEADER_MISSING';
    END IF;

    SELECT COUNT(*) AS line_count,
           COALESCE(SUM(l.debit),0) AS debits,
           COALESCE(SUM(l.credit),0) AS credits,
           COALESCE(SUM(CASE WHEN l.debit > 0 THEN l.amount_gel ELSE 0 END),0) AS gel_debits,
           COALESCE(SUM(CASE WHEN l.credit > 0 THEN l.amount_gel ELSE 0 END),0) AS gel_credits,
           COALESCE(BOOL_AND(
               l.currency = head.currency
               AND l.exchange_rate = head.exchange_rate
               AND l.amount_gel = ROUND((l.debit + l.credit) * head.exchange_rate,2)
           ),FALSE) AS valid_lines
      INTO totals
      FROM journal_entry_lines l
     WHERE l.journal_entry_id = head.id AND l.tenant_id = head.tenant_id;

    IF totals.line_count < 2
       OR totals.debits <> head.total_debit OR totals.credits <> head.total_credit
       OR totals.gel_debits <> totals.gel_credits OR NOT totals.valid_lines
       OR NOT EXISTS (
           SELECT 1 FROM journal_entry_sources s
            WHERE s.journal_entry_id = head.id AND s.tenant_id = head.tenant_id
       )
    THEN
        RAISE EXCEPTION 'LEDGER_HEADER_TOTAL_MISMATCH';
    END IF;
    RETURN NULL;
END;
$$;

DO $chat185$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'journal_entry_headers'::regclass
          AND tgname = 'chat185_header_balance_commit'
    ) THEN
        CREATE CONSTRAINT TRIGGER chat185_header_balance_commit
            AFTER INSERT ON journal_entry_headers
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION chat185_check_posted_entry_at_commit();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'journal_entry_lines'::regclass
          AND tgname = 'chat185_line_balance_commit'
    ) THEN
        CREATE CONSTRAINT TRIGGER chat185_line_balance_commit
            AFTER INSERT ON journal_entry_lines
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION chat185_check_posted_entry_at_commit();
    END IF;
END;
$chat185$;
COMMIT;
-- NOT applied to live DB. Existing rows, privileges, restoration plan and
-- long-running migration locks require independent signed authorization.
-- An append-only reversal/correction transaction is FIN-11, not implemented
-- by these triggers. Durable ERP receipt/outbox is separately FIN-12.
