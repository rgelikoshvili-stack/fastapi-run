-- Chat183 FIN-04 candidate: approved tenant COA classifications.
-- REVIEWED DRAFT ONLY. DO NOT REGISTER AS STARTUP MIGRATION OR APPLY TO LIVE.
-- A privileged importer must independently verify the source, reviewer,
-- tenant identity, periods and SHA-256 before inserting. There is NO public
-- write endpoint and NO runtime INSERT/UPDATE/DELETE permission.
-- RLS is defence in depth; tenant checks in the application remain required.
CREATE TABLE IF NOT EXISTS tenant_coa_mappings (
    tenant_id        TEXT NOT NULL CHECK (tenant_id <> '' AND tenant_id <> 'default'),
    account_code     TEXT NOT NULL CHECK (account_code = btrim(account_code)
                          AND length(account_code) BETWEEN 1 AND 80),
    account_type     TEXT NOT NULL CHECK
                       (account_type IN ('asset','liability','equity','income','expense')),
    effective_from   DATE NOT NULL,
    effective_until  DATE NULL,
    source_system    TEXT NOT NULL CHECK (btrim(source_system) <> ''),
    source_revision  TEXT NOT NULL CHECK (btrim(source_revision) <> ''),
    source_sha256    TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    approved_by      TEXT NOT NULL CHECK (btrim(approved_by) <> ''),
    approved_at      TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_tenant_coa_period CHECK
        (effective_until IS NULL OR effective_until >= effective_from),
    CONSTRAINT pk_tenant_coa_mapping PRIMARY KEY
        (tenant_id, account_code, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_tenant_coa_mapping_effective
    ON tenant_coa_mappings (tenant_id, account_code, effective_from);
ALTER TABLE tenant_coa_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_coa_mappings FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies
                   WHERE schemaname = current_schema()
                     AND tablename = 'tenant_coa_mappings'
                     AND policyname = 'tenant_coa_selected_tenant') THEN
        CREATE POLICY tenant_coa_selected_tenant ON tenant_coa_mappings
          FOR SELECT USING (
            tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')
            AND tenant_id <> 'default'
          );
    END IF;
END $$;
REVOKE ALL ON tenant_coa_mappings FROM PUBLIC;
-- Runtime SELECT grant, privileged import, legacy inspection, overlap review,
-- source approval and rollback are EXTERNAL-HOLD, not performed here.
-- Overlapping effective windows are deliberately refused by application.
-- Changing a historical mapping needs new audited provenance and review.
