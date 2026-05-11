-- =============================================================================
-- Bridge Hub — Migration 009
-- Task 11C-C1: Credential Vault Additive Schema Migration
--
-- PURPOSE:
--   This file defines the additive credential vault schema required by the
--   runtime credential vault service (future Task 11C-C2/11C-C3).
--
-- REVIEW STATUS:
--   Review-only in Task 11C-C1. This file was created but NOT executed.
--
-- EXECUTION:
--   Do not execute manually against production.
--   Future execution must be through the approved migration process only.
--   Each statement uses IF NOT EXISTS / IF EXISTS guards and is idempotent.
--
-- SCOPE:
--   - Creates credential_vault_credentials table (new generic vault table).
--   - Creates credential_vault_audit_events table (new audit table).
--   - Adds additive compatibility columns to tenant_balance_credentials.
--   - Adds additive compatibility columns to tenant_email_credentials.
--   - Adds additive compatibility columns to tenant_rsge_credentials.
--   - Adds additive compatibility columns to webhooks.
--   - Creates required indexes.
--
-- SAFETY RULES:
--   - Additive only. Does not remove, modify, or destroy any existing data.
--   - All statements use CREATE IF NOT EXISTS / ALTER IF EXISTS / ADD COLUMN IF NOT EXISTS.
--   - Does not copy plaintext api_key into encrypted_value.
--   - Does not null or remove api_key.
--   - Does not set encrypted_value from any plaintext credential column.
--   - Does not activate Balance.ge.
--   - Does not change runtime behavior.
--   - Plaintext credential migration is a separate future controlled task.
--   - Runtime credential vault service implementation is future 11C-C2/11C-C3.
--
-- CROSS-REFERENCES:
--   docs/credential-vault-runtime-architecture.md (Task 11C-B)
--   docs/balance-ge-activation-final-checklist.md
-- =============================================================================


-- =============================================================================
-- A) Generic credential vault table
--    Central store for all encrypted credential values across all providers.
--    Replaces the per-provider plaintext credential tables over time.
-- =============================================================================

CREATE TABLE IF NOT EXISTS credential_vault_credentials (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           TEXT        NOT NULL,
    provider            TEXT        NOT NULL,
    credential_type     TEXT        NOT NULL,
    encrypted_value     TEXT        NOT NULL,
    key_version         TEXT        NOT NULL,
    masked_hint         TEXT,
    status              TEXT        NOT NULL DEFAULT 'active',
    active              BOOLEAN     NOT NULL DEFAULT TRUE,
    company_id          TEXT,
    api_base            TEXT,
    metadata            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    last_test_status    TEXT,
    last_tested_at      TIMESTAMPTZ,
    last_accessed_at    TIMESTAMPTZ,
    rotated_at          TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          TEXT,
    updated_by          TEXT,

    -- Status constraint: only known lifecycle states are allowed.
    CONSTRAINT ck_credential_vault_status
        CHECK (status IN ('active', 'disabled', 'revoked', 'rotation_required', 'test_failed')),

    -- Provider and credential_type must be non-empty strings.
    CONSTRAINT ck_credential_vault_provider_nonempty
        CHECK (provider <> ''),
    CONSTRAINT ck_credential_vault_type_nonempty
        CHECK (credential_type <> ''),

    -- Encrypted value must be non-empty (no blank ciphertext stored).
    CONSTRAINT ck_credential_vault_encrypted_value_nonempty
        CHECK (encrypted_value <> ''),

    -- Key version must be non-empty.
    CONSTRAINT ck_credential_vault_key_version_nonempty
        CHECK (key_version <> ''),

    -- Unique active credential per tenant/provider/type.
    CONSTRAINT uq_credential_vault_tenant_provider_type
        UNIQUE (tenant_id, provider, credential_type)
);

COMMENT ON TABLE credential_vault_credentials IS
    'Generic credential vault: stores encrypted credentials for all providers. '
    'Replaces per-provider plaintext tables in future migration phases. '
    'Runtime implementation: Task 11C-C2/11C-C3. '
    'Plaintext migration: separate future controlled task.';

COMMENT ON COLUMN credential_vault_credentials.encrypted_value IS
    'AES-256-GCM ciphertext, base64-encoded. Never stores plaintext.';
COMMENT ON COLUMN credential_vault_credentials.key_version IS
    'Identifier of the encryption key used to produce encrypted_value.';
COMMENT ON COLUMN credential_vault_credentials.masked_hint IS
    'Last 4 chars of the original secret prefixed with ****. Computed at save time only.';
COMMENT ON COLUMN credential_vault_credentials.metadata IS
    'Non-secret provider metadata. Must not contain api_key, password, token, or secret.';


-- =============================================================================
-- B) Credential audit events table
--    Immutable log of all credential lifecycle events.
--    Raw secret values must never appear in any row.
-- =============================================================================

CREATE TABLE IF NOT EXISTS credential_vault_audit_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT        NOT NULL,
    provider        TEXT        NOT NULL,
    credential_type TEXT        NOT NULL,
    action          TEXT        NOT NULL,
    actor           TEXT,
    purpose         TEXT,
    result          TEXT        NOT NULL,
    key_version     TEXT,
    request_id      TEXT,
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Result must be one of the known outcome values.
    CONSTRAINT ck_credential_vault_audit_result
        CHECK (result IN ('success', 'failure', 'not_found', 'disabled', 'denied', 'error'))
);

COMMENT ON TABLE credential_vault_audit_events IS
    'Immutable credential lifecycle audit log. '
    'Raw secret values (api_key, password, token, secret, encrypted_value) '
    'must never appear in any row. metadata JSONB must also be secret-free.';

COMMENT ON COLUMN credential_vault_audit_events.action IS
    'Lifecycle action: save, get_for_connector, get_status, rotate, disable, audit_access.';
COMMENT ON COLUMN credential_vault_audit_events.metadata IS
    'Non-secret context (e.g. provider metadata, error type). No secret fields allowed.';


-- =============================================================================
-- C) Additive compatibility columns — tenant_balance_credentials
--    Adds vault-ready columns to the existing plaintext credential table.
--    Does NOT remove, null, copy, or migrate api_key.
--    Plaintext api_key remains intact until future controlled migration phases.
-- =============================================================================

ALTER TABLE IF EXISTS tenant_balance_credentials
    ADD COLUMN IF NOT EXISTS encrypted_value      TEXT,
    ADD COLUMN IF NOT EXISTS key_version          TEXT,
    ADD COLUMN IF NOT EXISTS masked_hint          TEXT,
    ADD COLUMN IF NOT EXISTS credential_status    TEXT DEFAULT 'legacy_plaintext',
    ADD COLUMN IF NOT EXISTS last_accessed_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rotated_at           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revoked_at           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_by           TEXT,
    ADD COLUMN IF NOT EXISTS updated_by           TEXT;

-- Note: api_key column is intentionally left unchanged.
-- encrypted_value is NULL for all existing rows until Phase 6 migration.
-- credential_status defaults to 'legacy_plaintext' to track pre-vault rows.


-- =============================================================================
-- D) Additive compatibility columns — tenant_email_credentials
--    Adds vault-ready columns. app_password plaintext remains intact.
-- =============================================================================

ALTER TABLE IF EXISTS tenant_email_credentials
    ADD COLUMN IF NOT EXISTS encrypted_value      TEXT,
    ADD COLUMN IF NOT EXISTS key_version          TEXT,
    ADD COLUMN IF NOT EXISTS masked_hint          TEXT,
    ADD COLUMN IF NOT EXISTS credential_status    TEXT DEFAULT 'legacy_plaintext',
    ADD COLUMN IF NOT EXISTS last_accessed_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rotated_at           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revoked_at           TIMESTAMPTZ;


-- =============================================================================
-- E) Additive compatibility columns — tenant_rsge_credentials
--    Adds vault-ready columns. password plaintext remains intact.
-- =============================================================================

ALTER TABLE IF EXISTS tenant_rsge_credentials
    ADD COLUMN IF NOT EXISTS encrypted_value      TEXT,
    ADD COLUMN IF NOT EXISTS key_version          TEXT,
    ADD COLUMN IF NOT EXISTS masked_hint          TEXT,
    ADD COLUMN IF NOT EXISTS credential_status    TEXT DEFAULT 'legacy_plaintext',
    ADD COLUMN IF NOT EXISTS last_accessed_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rotated_at           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revoked_at           TIMESTAMPTZ;


-- =============================================================================
-- F) Additive compatibility columns — webhooks
--    Adds vault-ready columns if the table stores any secret material.
-- =============================================================================

ALTER TABLE IF EXISTS webhooks
    ADD COLUMN IF NOT EXISTS encrypted_value      TEXT,
    ADD COLUMN IF NOT EXISTS key_version          TEXT,
    ADD COLUMN IF NOT EXISTS masked_hint          TEXT,
    ADD COLUMN IF NOT EXISTS credential_status    TEXT DEFAULT 'legacy_plaintext',
    ADD COLUMN IF NOT EXISTS last_accessed_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rotated_at           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revoked_at           TIMESTAMPTZ;


-- =============================================================================
-- G) Indexes
-- =============================================================================

-- Primary lookup: find credential by tenant/provider/type
CREATE INDEX IF NOT EXISTS idx_credential_vault_tenant_provider_type
    ON credential_vault_credentials (tenant_id, provider, credential_type);

-- Fast filter for active-only queries
CREATE INDEX IF NOT EXISTS idx_credential_vault_active
    ON credential_vault_credentials (active)
    WHERE active = TRUE;

-- Status filter for rotation/disable operations
CREATE INDEX IF NOT EXISTS idx_credential_vault_status
    ON credential_vault_credentials (status);

-- Audit log lookup: find events by tenant/provider
CREATE INDEX IF NOT EXISTS idx_credential_vault_audit_tenant_provider
    ON credential_vault_audit_events (tenant_id, provider);

-- Audit log time-range queries
CREATE INDEX IF NOT EXISTS idx_credential_vault_audit_created_at
    ON credential_vault_audit_events (created_at);


-- =============================================================================
-- H) End — schema-only migration
--
--   This migration only prepares the schema.
--   Runtime credential vault service implementation: future Task 11C-C2/11C-C3.
--   Plaintext credential migration (Phase 6) and nulling (Phase 7): separate
--     future controlled tasks requiring explicit authorization.
--   api_key, app_password, and password columns: unchanged and NOT migrated here.
--   Balance.ge remains inactive. All 14 activation gates remain NOT MET.
--   No Balance.ge live activation occurs in this migration or any near-term task.
-- =============================================================================
