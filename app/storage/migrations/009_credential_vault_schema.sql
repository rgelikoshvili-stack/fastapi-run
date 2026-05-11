-- =============================================================================
-- Bridge Hub — Migration 009
-- Task 11C-C1: Credential Vault Additive Schema Migration
--
-- PURPOSE:
--   Additive schema required by the runtime credential vault service
--   (Task 11C-C2/11C-C3). This file prepares the schema only.
--
-- REVIEW STATUS:
--   Review-only in Task 11C-C1. Created but NOT executed.
--
-- EXECUTION:
--   Do not execute manually against production.
--   Future execution must be through the approved migration process only.
--   All statements use IF NOT EXISTS / IF EXISTS guards and are idempotent.
--
-- SCOPE:
--   A) CREATE TABLE IF NOT EXISTS credential_vault_credentials
--   B) CREATE TABLE IF NOT EXISTS credential_vault_audit_events
--   C) ALTER TABLE IF EXISTS tenant_balance_credentials (additive columns)
--   D) ALTER TABLE IF EXISTS tenant_email_credentials (additive columns)
--   E) ALTER TABLE IF EXISTS tenant_rsge_credentials (additive columns)
--   F) ALTER TABLE IF EXISTS webhooks (additive columns)
--   G) CREATE INDEX IF NOT EXISTS (all vault indexes)
--
-- SAFETY RULES:
--   - Additive only. Does not remove, modify, or destroy existing data.
--   - Does not copy plaintext api_key into encrypted_value.
--   - Does not null or remove api_key.
--   - Does not set encrypted_value from any plaintext credential column.
--   - Does not activate Balance.ge.
--   - Does not change runtime behavior.
--   - Plaintext credential migration is a separate future controlled task.
--   - Runtime credential vault service implementation is Task 11C-C2/11C-C3.
--
-- CROSS-REFERENCES:
--   docs/credential-vault-runtime-architecture.md (Task 11C-B)
--   docs/balance-ge-activation-final-checklist.md
-- =============================================================================


-- =============================================================================
-- A) Generic credential vault table
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

    CONSTRAINT ck_credential_vault_status
        CHECK (status IN ('active', 'disabled', 'revoked', 'rotation_required', 'test_failed')),
    CONSTRAINT ck_credential_vault_provider_nonempty
        CHECK (provider <> ''),
    CONSTRAINT ck_credential_vault_type_nonempty
        CHECK (credential_type <> ''),
    CONSTRAINT ck_credential_vault_encrypted_value_nonempty
        CHECK (encrypted_value <> ''),
    CONSTRAINT ck_credential_vault_key_version_nonempty
        CHECK (key_version <> ''),
    CONSTRAINT uq_credential_vault_tenant_provider_type
        UNIQUE (tenant_id, provider, credential_type)
);

COMMENT ON TABLE credential_vault_credentials IS
    'Generic credential vault: encrypted credentials for all providers. '
    'Runtime implementation: Task 11C-C2/11C-C3. '
    'Plaintext migration: separate future controlled task.';

COMMENT ON COLUMN credential_vault_credentials.encrypted_value IS
    'AES-256-GCM ciphertext, base64-encoded. Never stores plaintext.';
COMMENT ON COLUMN credential_vault_credentials.key_version IS
    'Identifier of the encryption key used for encrypted_value.';
COMMENT ON COLUMN credential_vault_credentials.masked_hint IS
    'Last 4 chars of original secret prefixed with ****. Computed at save time only.';
COMMENT ON COLUMN credential_vault_credentials.metadata IS
    'Non-secret provider metadata. Must not contain api_key, password, token, or secret.';


-- =============================================================================
-- B) Credential audit events table
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

    CONSTRAINT ck_credential_vault_audit_result
        CHECK (result IN ('success', 'failure', 'not_found', 'disabled', 'denied', 'error'))
);

COMMENT ON TABLE credential_vault_audit_events IS
    'Immutable credential lifecycle audit log. '
    'Raw secret values must never appear in any row.';


-- =============================================================================
-- C) Additive compatibility columns — tenant_balance_credentials
--    api_key is intentionally left unchanged.
--    encrypted_value is NULL until future Phase 6 migration.
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


-- =============================================================================
-- D) Additive compatibility columns — tenant_email_credentials
--    app_password plaintext remains intact.
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
--    password plaintext remains intact.
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

CREATE INDEX IF NOT EXISTS idx_credential_vault_tenant_provider_type
    ON credential_vault_credentials (tenant_id, provider, credential_type);

CREATE INDEX IF NOT EXISTS idx_credential_vault_active
    ON credential_vault_credentials (active)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_credential_vault_status
    ON credential_vault_credentials (status);

CREATE INDEX IF NOT EXISTS idx_credential_vault_audit_tenant_provider
    ON credential_vault_audit_events (tenant_id, provider);

CREATE INDEX IF NOT EXISTS idx_credential_vault_audit_created_at
    ON credential_vault_audit_events (created_at);


-- =============================================================================
-- H) End — schema-only migration
--
--   This migration only prepares schema.
--   Runtime service implementation: future Task 11C-C2/11C-C3.
--   Plaintext migration (Phase 6) and nulling (Phase 7): separate future tasks.
--   api_key, app_password, password columns: unchanged, NOT migrated here.
--   Balance.ge remains inactive. All 14 activation gates remain NOT MET.
-- =============================================================================
