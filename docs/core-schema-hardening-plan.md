# Bridge Hub Core Schema Hardening Plan

Task 10E is high-risk because it covers authentication, tenant identity,
credentials/secrets, approval state, posted ledger truth, posting idempotency,
and audit evidence. These schemas must not be changed by broad runtime DDL,
manual scripts, or destructive migrations. Production database changes must wait
until additive migrations and read-only contract tests prove the intended
schema.

## Scope

### Auth and tenant core tables

- `users`
- `password_reset_tokens`
- `tenants`
- `tenant_settings`

These tables define who can access Bridge Hub and which tenant owns each
session, record, and workflow. `users` must remain tenant-aware. Tenant registry
columns such as `tenant_id`, `slug`, `company_inn`, status, and audit metadata
must have one canonical schema owner before runtime DDL is removed.

### Credential and secret tables

- `tenant_secrets`
- `tenant_email_credentials`
- `tenant_balance_credentials`
- `tenant_rsge_credentials`
- `webhooks`
- `webhook_deliveries`
- `users.totp_secret`

Credential and secret values must use encryption-at-rest or encrypted value
fields before real customer credentials are stored. Any read path must return
masked secret reads by default. Rotation metadata must be available, including
created, updated, rotated, disabled, and last-used timestamps where practical.
Credential access must be tenant-scoped and audit logged.

### Accounting truth tables

- `journal_drafts`
- `draft_comments`
- `journal_entries`
- `posting_logs`
- `audit_events`

These tables carry the approval-first workflow, posted-only ledger truth,
posting idempotency, and audit trail. `journal_drafts` may hold pending
approval data, but reports that represent ledger truth must use posted-only
logic. `posting_logs` must preserve source draft references and idempotency
keys. `audit_events` must preserve tenant, actor, entity, action, timestamp,
and metadata context.

## Required Schema Principles

- Tenant isolation is mandatory for tenant-owned tables.
- Credential and secret columns must not remain plain-text in the target
  production schema.
- Credential/secret APIs must support masked reads and must not expose raw
  values by default.
- Rotation metadata is required for credential and secret records.
- Audit metadata is required for auth, credential, approval, posting, and
  connector-sensitive changes.
- Idempotency keys and unique idempotency indexes are required for posting and
  external connector execution logs.
- Approval-first workflow must be preserved: modules create journal drafts, not
  direct posted entries.
- Posted-only ledger truth must be preserved for reporting, trial balance,
  financial statements, and close controls.
- Destructive migrations are forbidden. No `DROP TABLE`, `TRUNCATE`,
  broad `DELETE`, unsafe `UPDATE`, destructive `ALTER`, or constraint
  replacement should be introduced without a separate reviewed plan.
- Production DB must not be touched during planning or contract phases.
- Runtime DDL removal must wait until additive migrations, replay tests, and
  regression tests exist for the covered tables.

## Task 10E Roadmap

### Task 10E-C: Credential and security schema contract

Define the target contract for `tenant_secrets`, `tenant_email_credentials`,
`tenant_balance_credentials`, `tenant_rsge_credentials`, webhook secrets, and
TOTP secret fields. This task should add tests and documentation only unless a
separate implementation task is approved. It must specify encrypted value
fields, masked reads, rotation metadata, tenant indexes, and access audit
requirements.

### Task 10E-D: Accounting truth schema contract

Define the target contract for `journal_drafts`, `draft_comments`,
`journal_entries`, `posting_logs`, and `audit_events`. This task must lock down
approval-first behavior, posted-only reporting, posting idempotency, source
document references, tenant/status/date indexes, and audit evidence
requirements.

### Task 10E-E: Auth and tenant schema contract

Define the target contract for `users`, `password_reset_tokens`, `tenants`, and
`tenant_settings`. This task must specify tenant-aware user uniqueness, password
reset token lifecycle, tenant registry uniqueness, and audit metadata. It must
keep auth runtime behavior unchanged until additive migrations are reviewed and
tested.

### Later additive migrations

Only after 10E-C, 10E-D, and 10E-E contract tests pass should implementation
tasks create additive migrations. Runtime DDL cutover and removal must wait
until migration replay, existing DB upgrade, tenant isolation, auth, approval,
posting, connector, and reporting regression tests pass.

## Explicit Non-Goals For Task 10E-B

- No SQL migrations.
- No runtime Python changes.
- No startup behavior changes.
- No auth behavior changes.
- No credential or secret service changes.
- No approval or posting service changes.
- No connector behavior changes.
- No production database access.
