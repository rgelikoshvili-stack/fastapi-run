# Auth and Tenant Schema Contract

## Purpose

Task 10E-E defines the auth and tenant schema contract before any auth/tenant migrations or runtime behavior changes.

This task is contract and test coverage only:

- It does not create migrations.
- It does not edit runtime app code.
- It does not change auth behavior.
- It does not change tenant behavior.
- It does not change credential or connector behavior.
- It does not enforce subscriptions yet.
- It does not activate Balance.ge.
- It does not execute SQL.
- It does not touch production databases.

## Auth and Tenant Objects Covered

This contract applies to:

- `users`
- `tenants`
- `tenant_settings`
- `password_reset_tokens`
- user roles
- user permissions
- tenant membership if present or planned
- TOTP fields such as `users.totp_secret`
- subscription and trial fields such as `trial_ends_at`
- tenant status fields
- audit and security metadata

## Tenant Isolation

Tenant isolation is a hard boundary:

- Tenant-owned tables must include `tenant_id` where applicable.
- All tenant-scoped queries must filter by `tenant_id`.
- Cross-tenant access must be forbidden by default.
- Tenant context must come from a trusted token, middleware, or explicitly validated tenant header.
- Global or admin-only tables must be explicitly documented as global.
- Root tenant registry tables such as `tenants` may be global, but tenant-owned child records must still be scoped.
- Tenant deletion, suspension, and archival must not expose or reassign another tenant's data.

Future auth/tenant migrations should preserve or add tenant lookup indexes and uniqueness constraints where applicable.

## User Identity and Auth

User identity must be stable and safe:

- `users` must have stable unique identity fields.
- Email or login identifiers must be normalized consistently.
- Password hashes must never be exposed in APIs, logs, exports, frontend state, or error messages.
- Disabled, suspended, locked, or deleted users must not authenticate.
- Authentication responses must not expose raw password hashes, password reset tokens, TOTP secrets, raw credentials, or connector secrets.
- Auth endpoints should avoid leaking whether a user or email exists where practical.

## Password Reset Tokens

`password_reset_tokens` must use hashed, expiring, single-use tokens.

Required properties:

- token hash, not raw token
- user reference
- `tenant_id` where applicable
- `created_at`
- `expires_at`
- `used_at`
- invalidation metadata where applicable
- uniqueness or lookup indexes for safe token verification

Password reset tokens must not be reusable and must not be logged in plaintext.

## TOTP Handling

TOTP fields such as `users.totp_secret` must be protected or encrypted at rest.

Rules:

- TOTP secret may be shown only during initial setup.
- TOTP status endpoints must return enabled/disabled state only.
- TOTP secret must never be returned unmasked after setup.
- TOTP reset must be audited.
- Disable/reset flows must clear or rotate protected secrets.

## RBAC and Permissions

Role and permission behavior must be explicit:

- User roles must be stored or derivable from a documented model.
- Permissions must be mapped to sensitive actions.
- Approval actions must require approval permissions.
- Posting actions must require posting permissions.
- Reporting actions must require reporting permissions.
- Admin, tenant, security, credential, and billing actions must require elevated permissions.
- Least privilege must be the default.
- Admin actions must be audited.
- Cross-tenant admin access, if supported, must be explicitly modeled and audited.

## Tenant Lifecycle

Tenant lifecycle state must be explicit.

Supported or planned tenant states:

- `active`
- `trial`
- `suspended`
- `expired`
- `inactive`

Rules:

- `trial_ends_at` and subscription state must be enforced before commercial pilot.
- Suspended or expired tenants must not execute mutating accounting actions.
- Suspended or expired tenants must not execute connector actions.
- Read-only access policy for suspended or expired tenants must be explicit.
- Tenant status changes must be audited.
- Tenant reactivation must be audited.

## Subscription and Trial Enforcement

Commercial SaaS readiness requires subscription and trial enforcement:

- Trial expiration must be enforced.
- Plan status must be checked before mutating ERP/accounting/connector actions.
- Plan limits must be documented before selling usage-based features.
- Billing state must not be inferred from frontend state alone.
- Subscription enforcement is still implementation work and is not changed by this task.

## Audit Metadata

Auth and security-sensitive events must be auditable:

- login
- failed login
- logout where tracked
- token refresh
- password reset request
- password reset use
- TOTP setup
- TOTP reset
- role changes
- permission changes
- tenant status changes
- subscription or trial changes
- admin user creation
- locked or disabled user changes

Audit entries should include:

- actor
- tenant
- timestamp
- action
- result
- source IP or request metadata where available
- safe error code

Audit entries must not include password hashes, reset tokens, TOTP secrets, raw credentials, connector secrets, or other plaintext secrets.

## Security Boundaries

API responses must not return:

- password hashes
- reset tokens
- TOTP secrets
- raw credentials
- connector secrets
- API keys
- webhook secrets

Login, reset, token refresh, TOTP, and credential-adjacent endpoints must be rate limited. Production rate limiting should use shared infrastructure such as Redis rather than process-local memory.

Session and token invalidation policy must be documented before commercial pilot:

- refresh token rotation
- password-change invalidation
- TOTP reset invalidation
- user suspension invalidation
- tenant suspension invalidation

## Migration Policy

Future auth/tenant migrations must be additive-only:

- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- no destructive migrations
- no `DROP TABLE`
- no `TRUNCATE`
- no destructive `ALTER`
- no data-rewriting migration without a separate reviewed data plan
- no production DB mutation during planning/contract tasks

Runtime DDL removal must wait until migration coverage and tests prove safety.

## Implementation Deferral

This task intentionally defers implementation:

- Auth/tenant migrations are still implementation work.
- Subscription and trial enforcement is still implementation work.
- Runtime DDL removal is still deferred.
- Auth runtime behavior is unchanged.
- Tenant runtime behavior is unchanged.
- Credential and connector runtime behavior is unchanged.
- Balance.ge live activation is still deferred.
- Production database is not touched by this task.

## Future Acceptance Criteria

Before commercial pilot:

- Tenant isolation contract is covered by tests.
- Password hashes, reset tokens, TOTP secrets, and credentials are never exposed in API responses.
- Password reset tokens are hashed, expiring, and single-use.
- TOTP secrets are protected and setup-only.
- Role and permission model is explicit.
- Trial and subscription state is enforced.
- Suspended/expired tenants cannot mutate accounting or connector state.
- Auth/security-sensitive events are audited.
- Login/reset/token endpoints are rate limited.
- Additive migrations cover auth/tenant tables before runtime DDL removal.
