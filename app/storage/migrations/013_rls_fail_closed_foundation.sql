-- NEXT-04A: replace the historical fail-open tenant policies.
-- Apply only through the approved migration process; never at application startup.

DO $$
DECLARE
    target_table TEXT;
    policy_row RECORD;
    target_tables CONSTANT TEXT[] := ARRAY[
        'counterparties',
        'processed_documents',
        'journal_drafts',
        'waybills',
        'tax_invoices',
        'commercial_invoices',
        'triangle_matches',
        'document_corrections',
        'outgoing_invoices'
    ];
BEGIN
    FOREACH target_table IN ARRAY target_tables LOOP
        IF to_regclass(target_table) IS NULL THEN
            RAISE EXCEPTION 'NEXT-04A expected tenant table is missing: %', target_table;
        END IF;
    END LOOP;

    -- Remove every policy on these tables so no permissive legacy policy can
    -- OR together with the fail-closed policy below.
    FOR policy_row IN
        SELECT schemaname, tablename, policyname
          FROM pg_policies
         WHERE schemaname = current_schema()
           AND tablename = ANY(target_tables)
    LOOP
        EXECUTE format(
            'DROP POLICY %I ON %I.%I',
            policy_row.policyname,
            policy_row.schemaname,
            policy_row.tablename
        );
    END LOOP;
END $$;

ALTER TABLE counterparties ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE waybills ENABLE ROW LEVEL SECURITY;
ALTER TABLE tax_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE commercial_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE triangle_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_corrections ENABLE ROW LEVEL SECURITY;
ALTER TABLE outgoing_invoices ENABLE ROW LEVEL SECURITY;

ALTER TABLE counterparties FORCE ROW LEVEL SECURITY;
ALTER TABLE processed_documents FORCE ROW LEVEL SECURITY;
ALTER TABLE journal_drafts FORCE ROW LEVEL SECURITY;
ALTER TABLE waybills FORCE ROW LEVEL SECURITY;
ALTER TABLE tax_invoices FORCE ROW LEVEL SECURITY;
ALTER TABLE commercial_invoices FORCE ROW LEVEL SECURITY;
ALTER TABLE triangle_matches FORCE ROW LEVEL SECURITY;
ALTER TABLE document_corrections FORCE ROW LEVEL SECURITY;
ALTER TABLE outgoing_invoices FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_fail_closed_counterparties ON counterparties
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );

CREATE POLICY tenant_fail_closed_processed_documents ON processed_documents
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );

CREATE POLICY tenant_fail_closed_journal_drafts ON journal_drafts
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );

CREATE POLICY tenant_fail_closed_waybills ON waybills
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );

CREATE POLICY tenant_fail_closed_tax_invoices ON tax_invoices
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );

CREATE POLICY tenant_fail_closed_commercial_invoices ON commercial_invoices
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );

CREATE POLICY tenant_fail_closed_triangle_matches ON triangle_matches
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );

CREATE POLICY tenant_fail_closed_document_corrections ON document_corrections
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );

CREATE POLICY tenant_fail_closed_outgoing_invoices ON outgoing_invoices
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );
