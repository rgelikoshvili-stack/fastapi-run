# Credential and Security Schema Contract

## Purpose

Task 10E-C defines the credential and security schema contract for Bridge Hub before any credential migrations, encryption implementation, runtime behavior changes, or connector activation.

This task is planning and contract coverage only:

- It does not implement encryption.
- It does not create migrations.
- It does not touch production databases.
- It does not activate Balance.ge live posting.
- It does not change auth, credential, connector, approval, or posting behavior.

## Credential and Secret Objects Covered

This contract applies to:

- `tenant_secrets`
- `tenant_email_credentials`
- `tenant_balance_credentials`
- `tenant_rsge_credentials`
- `webhooks`
- `webhook_deliveries`
- `users.totp_secret`
- `password_reset_tokens`
- connector API keys
- email app passwords
- RS.ge passwords
- webhook secrets
- TOTP secrets

## Non-Exposure Requirement

Bridge Hub must never expose plaintext secrets through normal APIs, logs, exports, connector status responses, error messages, test payloads, webhooks, or frontend state.

Plaintext values include:

- Balance.ge API keys
- Balance.ge company credentials where secret
- email app passwords
- RS.ge usernames/passwords where sensitive
- webhook secrets
- TOTP secrets
- password reset tokens
- generic connector tokens and API keys

Connector status endpoints must return only safe states such as `configured`, `not_configured`, `demo`, `sandbox`, `dry_run`, `live_ready`, `last_test_status`, and `last_tested_at`. They must not return raw API keys, IMAP passwords, RS.ge passwords, webhook secrets, TOTP secrets, or password reset tokens.

## Encrypted-at-Rest Requirement

Future credential storage must use encrypted-at-rest value fields for secrets, API keys, app passwords, and sensitive tokens.

Required pattern:

- Store sensitive values in encrypted columns such as `encrypted_value`, `encrypted_api_key`, `encrypted_app_password`, `encrypted_password`, or equivalent table-specific names.
- Store key metadata separately from encrypted values.
- Do not rely on masking alone as storage protection.
- Do not store new plaintext credential values in canonical credential tables.
- Do not log decrypted values.

Encryption implementation is deferred to a later task. This contract only defines the requirement.

## Masked Reads Requirement

Read APIs and UI views may return only masked values or boolean status:

- `configured: true`
- `masked_value: "****1234"`
- `last_test_status`
- `last_tested_at`
- `is_active`

Read APIs must not return plaintext secret material after initial setup. TOTP setup may show the setup secret only in the setup step, and never as a normal status/read response after setup.

## Rotation Metadata Requirement

Credential and secret tables should support rotation and lifecycle metadata:

- `created_at`
- `updated_at`
- `rotated_at`
- `last_used_at`
- `revoked_at` or `is_active`

Where a table stores multiple named secrets per tenant, it should also track:

- `secret_key`, `credential_type`, or equivalent name
- unique tenant/key constraint where applicable
- active/inactive state

## Tenant Isolation Requirement

Tenant-owned credential/security tables must include `tenant_id` unless the data is globally intentional and documented.

Tenant-scoped credential records must be queried by tenant. Future migrations should add or preserve indexes and uniqueness rules such as:

- unique tenant/key constraints for named secrets
- unique tenant/provider constraints for connector credentials
- tenant/status indexes for active credential lookup
- tenant/created_at indexes for audit/history lookup

## Audit Metadata Requirement

Credential and security tables should support audit and operational metadata:

- `created_by`
- `updated_by`
- `last_tested_at`
- `last_test_status`
- `last_error_code`
- `last_error_message` with no secret values

Credential create, update, test, rotate, revoke, and failed access events should create audit events without storing secret values.

## Webhook Secret Handling

Webhook secrets must be encrypted or hashed depending on the verification model:

- If Bridge Hub needs to compute signatures for outgoing webhooks, the secret must be encrypted-at-rest and decrypted only for signing.
- If Bridge Hub only verifies inbound signatures, a hash may be sufficient.

`webhook_deliveries` must not store webhook secret values. Delivery logs may store event type, delivery URL, status, response code, response body summary, retry count, and timestamps, but never the secret.

## TOTP Handling

`users.totp_secret` must be encrypted or otherwise protected at rest.

Rules:

- TOTP secret may be shown only during initial setup.
- TOTP status endpoints must return enabled/disabled state only.
- TOTP secret must never be returned unmasked after setup.
- Disable/reset flows must clear or rotate the protected secret.

## Password Reset Token Requirement

`password_reset_tokens` must use hashed tokens, expiry, and single-use semantics.

Required fields or equivalent:

- token hash, not raw token
- `expires_at`
- `used_at`
- `created_at`
- `tenant_id` where applicable
- user reference

Password reset tokens must not be reusable and must not be logged in plaintext.

## Connector Credential Behavior

Connector credential flows must follow these rules:

- Status endpoints return configured/not_configured/demo/sandbox/dry_run/live_ready only.
- Test endpoints may return success/failure and safe error codes only.
- Save/update endpoints must write encrypted values in future implementation.
- Connector execution must require approved action/draft where accounting-impacting.
- Live connector activation is forbidden in this task.
- Balance.ge live posting remains deferred until credential vault, dry-run, approval, and audit controls are complete.

## Migration Policy

Future credential/security migrations must be additive-only:

- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- no destructive migrations
- no `DROP TABLE`
- no `TRUNCATE`
- no destructive `ALTER`
- no production DB mutation during planning/contract tasks

Runtime DDL removal must wait until additive migrations and replay/contract tests prove coverage.

## Implementation Deferral

This contract intentionally defers implementation:

- Encryption is still implementation work.
- Masked read behavior is still implementation work where missing.
- Credential migrations are still deferred.
- Balance.ge live activation is still deferred.
- Connector runtime behavior is unchanged.
- Auth runtime behavior is unchanged.
- Production database is not touched by this task.

## Future Acceptance Criteria

Before real connector pilot:

- No plaintext secret exposure in normal APIs.
- Credential values encrypted at rest.
- Masked reads enforced.
- Rotation metadata present.
- Tenant isolation tested.
- Credential audit events present.
- Password reset tokens hashed, expiring, and single-use.
- TOTP secrets protected and not exposed after setup.
- Webhook secrets absent from delivery logs.
- Balance.ge dry-run succeeds before live execution.
- Live connector execution requires approval and produces posting logs.
