-- =============================================================================
-- Bridge Hub — Migration 012 (DRAFT — P0-2 RS.ge Credential Vault Migration)
-- Task P0-2: Migrate RS.ge credentials from plaintext to credential vault.
--
-- STATUS: DRAFT ONLY. Do NOT execute against production without explicit approval.
-- Runtime execution: handled by inline _ENSURE_SCHEMA in routes_rsge_credentials.py
--                    for each of the individual ALTER statements.
--
-- PURPOSE:
--   A) Make tenant_rsge_credentials.password nullable so new rows do not store plaintext.
--   B) Add credential_vault_ref TEXT — points to credential_vault_credentials(id).
--   C) Add credential_status TEXT — 'active', 'legacy_plaintext', 'rotation_required'.
--   D) Mark existing rows that have a non-empty password as 'rotation_required'.
--   E) Index for fast vault ref lookup.
--
-- SAFETY RULES:
--   - Does NOT delete the password column (backward compat for existing rows).
--   - Does NOT migrate plaintext values into the vault (that's a separate controlled task).
--   - Does NOT null out existing passwords — just flags them as rotation_required.
--   - Additive only: IF NOT EXISTS / IF EXISTS guards on all statements.
--   - New writes via routes_rsge_credentials.py:save_creds() already use vault.
--
-- AFTER APPROVAL, execute in this order:
--   1. Run this migration in a maintenance window.
--   2. Verify credential_status = 'rotation_required' for existing rows.
--   3. Ask each tenant to re-save credentials via POST /rsge-credentials/save.
--   4. After re-save, password column will contain '[stored-in-vault]' (not plaintext).
--   5. Future migration (013) may null out / drop the password column.
-- =============================================================================

-- A) Make password nullable (existing NOT NULL constraint)
ALTER TABLE tenant_rsge_credentials
    ALTER COLUMN password DROP NOT NULL;

-- B) Add credential_vault_ref
ALTER TABLE tenant_rsge_credentials
    ADD COLUMN IF NOT EXISTS credential_vault_ref TEXT;

-- C) Add credential_status
ALTER TABLE tenant_rsge_credentials
    ADD COLUMN IF NOT EXISTS credential_status TEXT NOT NULL DEFAULT 'legacy_plaintext';

-- D) Mark rows with plaintext passwords as rotation_required
UPDATE tenant_rsge_credentials
SET credential_status = 'rotation_required'
WHERE password IS NOT NULL
  AND password NOT IN ('', '[stored-in-vault]')
  AND credential_status = 'legacy_plaintext';

-- E) Index
CREATE INDEX IF NOT EXISTS idx_rsge_creds_status
    ON tenant_rsge_credentials (credential_status);

-- =============================================================================
-- VERIFICATION QUERIES (run after migration to confirm):
-- =============================================================================
-- SELECT tenant_id, username, credential_status,
--        CASE WHEN password IS NULL THEN 'NULL'
--             WHEN password = '[stored-in-vault]' THEN 'vault'
--             WHEN password = '' THEN 'empty'
--             ELSE 'PLAINTEXT (needs rotation)'
--        END AS password_state
-- FROM tenant_rsge_credentials;
--
-- Expected after rotation:
--   credential_status = 'active'
--   password = '[stored-in-vault]'
--   credential_vault_ref = '<UUID from credential_vault_credentials>'
-- =============================================================================
