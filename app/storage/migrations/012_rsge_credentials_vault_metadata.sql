-- Bridge Hub P0 Fix Sprint
-- RS.ge credential vault metadata migration draft.
--
-- Do not run against production without explicit migration approval.
-- Existing plaintext rows are marked rotation_required; new saves must use
-- credential_vault_credentials via CredentialVaultService.

ALTER TABLE IF EXISTS tenant_rsge_credentials
    ADD COLUMN IF NOT EXISTS credential_vault_ref TEXT DEFAULT 'rsge:portal_password',
    ADD COLUMN IF NOT EXISTS credential_status TEXT DEFAULT 'legacy_plaintext';

UPDATE tenant_rsge_credentials
SET credential_status = 'rotation_required',
    credential_vault_ref = COALESCE(credential_vault_ref, 'rsge:portal_password')
WHERE credential_status IS NULL
   OR credential_status = 'legacy_plaintext';

COMMENT ON COLUMN tenant_rsge_credentials.credential_vault_ref IS
    'Reference to credential_vault_credentials. RS.ge passwords must not be stored plaintext.';

COMMENT ON COLUMN tenant_rsge_credentials.credential_status IS
    'vault, rotation_required, legacy_plaintext, disabled, or not_configured.';
