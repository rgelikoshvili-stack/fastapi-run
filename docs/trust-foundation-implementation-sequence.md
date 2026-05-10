# Trust Foundation Implementation Sequence

## Purpose

This document defines the exact recommended sequence of future implementation
tasks for Bridge Hub Trust Foundation. Each entry specifies what is allowed,
what is forbidden, what tests are required, and what the success criteria and
rollback conditions are.

No task in this sequence may be started until the previous task's PR is merged,
CI passes, deployment succeeds (if triggered), and live verification is complete.

---

## Sequence Table

### Task 10F-A — Trust Foundation Docs and Tests Finalize

| Field | Value |
|---|---|
| Task ID | 10F-A |
| Task Name | Trust Foundation Docs and Tests Finalize |
| Purpose | Create the planning documents and test suite that prove the Trust Foundation plan is complete and coherent. |
| Type | docs/tests only — no code editing |
| Allowed files | docs/trust-foundation-implementation-plan.md, docs/trust-foundation-implementation-sequence.md, docs/balance-ge-activation-gate.md, tests/unit/test_trust_foundation_plan_docs.py |
| Forbidden files | app/*, app/startup/*, app/api/*, app/storage/migrations/*, scripts/*, .env files, production database |
| Required tests | tests/unit/test_trust_foundation_plan_docs.py — all pass |
| Success criteria | All three docs exist. All required keywords present. Test suite passes with 0 failures. |
| Rollback condition | If tests fail: fix the docs or tests (no runtime rollback needed, docs/tests only). |
| Code editing | No |

---

### Task 10F-B — Credential Vault Design and Tests

| Field | Value |
|---|---|
| Task ID | 10F-B |
| Task Name | Credential Vault Design and Tests |
| Purpose | Design the credential encryption/vault layer in detail and add unit tests that prove the design contract, without implementing the encryption yet. |
| Type | docs/tests only |
| Allowed files | docs/credential-vault-design.md, tests/unit/test_credential_vault_design.py |
| Forbidden files | app/api/services/balance_credentials_service.py, app/api/services/email_collector.py, app/storage/migrations/*, production database |
| Required tests | Unit tests using mocks: (1) credential service never returns plaintext from get_status(); (2) encryption key reference is separate from encrypted value; (3) masked format is returned correctly |
| Success criteria | Design doc exists. Tests pass. No runtime code changed. |
| Rollback condition | Docs/tests only — no rollback needed. |
| Code editing | No |

---

### Task 10F-C — Masked Read Behavior Tests

| Field | Value |
|---|---|
| Task ID | 10F-C |
| Task Name | Masked Read Behavior Tests |
| Purpose | Add unit tests for each credential type that prove the masked read contract from docs/credential-security-schema-contract.md. Tests must mock the DB layer and verify that API-facing functions never return raw secrets. |
| Type | tests only |
| Allowed files | tests/unit/test_masked_read_contract.py |
| Forbidden files | app/api/services/*, app/api/routes_*, production database |
| Required tests | Per credential type (Balance.ge, email, RS.ge, TOTP, webhook): API-facing function returns only masked value or boolean status, never raw secret. |
| Success criteria | Tests pass. No runtime code changed. Each credential type covered. |
| Rollback condition | Tests only — no rollback needed. |
| Code editing | No |

---

### Task 10F-D — Subscription / Trial Enforcement Plan and Tests

| Field | Value |
|---|---|
| Task ID | 10F-D |
| Task Name | Subscription / Trial Enforcement Plan and Tests |
| Purpose | Document the enforcement design and add unit tests that prove the enforcement contract from docs/auth-tenant-schema-contract.md. Tests must mock the tenants table and verify HTTP 402 for expired/suspended tenants. |
| Type | docs/tests only |
| Allowed files | docs/subscription-enforcement-plan.md, tests/unit/test_subscription_enforcement_contract.py |
| Forbidden files | app/api/middleware/auth_middleware.py, app/api/middleware/rbac_middleware.py, production database |
| Required tests | (1) Expired trial -> 402 on POST endpoints; (2) Active trial -> 200; (3) Suspended -> 402/403 on mutating endpoints; (4) Expired tenant can GET historical data; (5) Admin override is audited |
| Success criteria | Enforcement design doc exists. Tests pass. No middleware changed. |
| Rollback condition | Docs/tests only — no rollback needed. |
| Code editing | No |

---

### Task 10F-E — Redis / Rate-Limit Plan and Tests

| Field | Value |
|---|---|
| Task ID | 10F-E |
| Task Name | Redis / Rate-Limit Plan and Tests |
| Purpose | Document the Redis setup runbook and add unit tests that prove the limiter correctly selects Redis vs in-memory based on REDIS_URL environment variable. |
| Type | docs/tests only |
| Allowed files | docs/redis-rate-limit-plan.md, tests/unit/test_redis_rate_limit_contract.py |
| Forbidden files | app/api/security.py, production infrastructure |
| Required tests | (1) REDIS_URL set -> limiter initialized with Redis storage; (2) REDIS_URL not set -> in-memory warning logged; (3) Rate limit exceeded -> HTTP 429 with RATE_LIMIT code |
| Success criteria | Plan doc exists. Tests pass. security.py not changed. |
| Rollback condition | Docs/tests only — no rollback needed. |
| Code editing | No |

---

### Task 10F-F — Runtime DDL Cutover Plan

| Field | Value |
|---|---|
| Task ID | 10F-F |
| Task Name | Runtime DDL Cutover Plan |
| Purpose | Document the per-shim cutover strategy and add tests that compare runtime shim DDL against formal migration DDL to prove coverage before any shim is removed. |
| Type | docs/tests only |
| Allowed files | docs/runtime-ddl-cutover-plan.md, tests/unit/test_runtime_ddl_coverage.py |
| Forbidden files | app/startup/migrations.py, app/api/services/balance_credentials_service.py, app/api/services/inventory_service.py, app/api/services/payroll_service.py, app/storage/migrations/* |
| Required tests | Read shim source and migration source; assert that every table/column in the shim is covered by a formal migration; flag any shim DDL not covered. |
| Success criteria | Cutover plan doc exists. Coverage tests pass. No shim removed. |
| Rollback condition | Docs/tests only — no rollback needed. |
| Code editing | No |

---

### Task 10F-G — Backup / Static Ops Checklist

| Field | Value |
|---|---|
| Task ID | 10F-G |
| Task Name | Backup / Static Ops Checklist |
| Purpose | Document the DB backup/PITR requirements and the static files GCS/CDN migration plan. No infrastructure changes yet. |
| Type | docs only |
| Allowed files | docs/db-backup-pitr-checklist.md, docs/static-files-gcs-cdn-plan.md |
| Forbidden files | App code, infrastructure configs, GCS buckets, Cloud Run configs |
| Required tests | None beyond confirming the docs exist (can be asserted in test_trust_foundation_plan_docs.py) |
| Success criteria | Both docs exist. Backup checklist covers PITR, restore drill, pre-migration backup, and environment separation. |
| Rollback condition | Docs only — no rollback needed. |
| Code editing | No |

---

### Task 10F-H — Balance.ge Activation Gate Checklist

| Field | Value |
|---|---|
| Task ID | 10F-H |
| Task Name | Balance.ge Activation Gate Checklist |
| Purpose | Add tests that validate docs/balance-ge-activation-gate.md is complete and covers all required gate conditions. |
| Type | docs/tests only |
| Allowed files | docs/balance-ge-activation-gate.md (update if needed), tests/unit/test_balance_ge_gate_checklist.py |
| Forbidden files | app/api/connectors/balance_connector.py, Balance.ge credentials, production database |
| Required tests | Gate doc covers: approval, dry_run, payload preview, idempotency, posting_logs, encrypted credentials, rollback/manual fallback, test tenant, accountant review |
| Success criteria | Gate doc exists. Gate test passes. Balance.ge remains inactive. |
| Rollback condition | Docs/tests only — no rollback needed. |
| Code editing | No |

---

## Later Implementation Tasks (after 10F-A through 10F-H approved and merged)

These tasks involve runtime code editing and migrations. They must not be started
until all 10F planning tasks are approved.

### Task 11C-A — Credential Encryption Implementation

| Field | Value |
|---|---|
| Task ID | 11C-A |
| Task Name | Credential Encryption Implementation |
| Purpose | Implement encryption-at-rest for credential tables. Add encrypted_value columns. Migrate existing credentials. Update service layer to use encryption. |
| Type | Code editing + additive migration |
| Allowed files | app/api/services/balance_credentials_service.py, app/api/services/email_collector.py, app/storage/migrations/009_credential_encryption.sql, tests/unit/ |
| Forbidden files | Production DB direct manipulation, Balance.ge activation, auth_middleware.py |
| Required tests | Unit: credentials are never returned as plaintext; Integration: encrypted value survives round-trip |
| Success criteria | 0 plaintext secrets in any API response. All unit tests pass. |
| Rollback condition | Remove encryption columns (additive rollback), revert service to plaintext (deploy old version). |
| Code editing | Yes |

---

### Task 11C-B — Subscription Enforcement Implementation

| Field | Value |
|---|---|
| Task ID | 11C-B |
| Task Name | Subscription Enforcement Implementation |
| Purpose | Add trial_ends_at and subscription_tier enforcement to auth middleware or a dependency injection check. Return HTTP 402 for expired/suspended tenants on mutating endpoints. |
| Type | Code editing |
| Allowed files | app/api/middleware/auth_middleware.py or new app/api/dependencies/subscription.py, tests/unit/ |
| Forbidden files | Connector files, Balance.ge activation, production database |
| Required tests | Unit: expired trial -> 402; suspended -> 402/403; active -> passes; GET historical -> passes |
| Success criteria | Expired tenants cannot mutate accounting state. Tests pass. |
| Rollback condition | Revert middleware change (deploy previous version). |
| Code editing | Yes |

---

### Task 11C-C — Redis Configuration Deployment

| Field | Value |
|---|---|
| Task ID | 11C-C |
| Task Name | Redis Configuration Deployment |
| Purpose | Provision Redis (Google Memorystore or equivalent). Set REDIS_URL in Cloud Run. Verify rate limiting is now Redis-backed. |
| Type | Ops change |
| Allowed files | Cloud Run env vars, infrastructure config |
| Forbidden files | App code (no code change needed if security.py already handles REDIS_URL) |
| Required tests | Live health check. /version shows correct HEAD. Rate limit test with multiple requests. |
| Success criteria | Rate limiter uses Redis. Multi-instance rate limiting is global. |
| Rollback condition | Remove REDIS_URL from Cloud Run; system falls back to in-memory. |
| Code editing | No (env var only) |

---

### Task 11C-D — Runtime DDL Shim Conversion to No-Ops

| Field | Value |
|---|---|
| Task ID | 11C-D |
| Task Name | Runtime DDL Shim Conversion |
| Purpose | Convert ensure_* functions to no-ops that only log and return. Do not remove them yet. Verify production startup still succeeds. |
| Type | Code editing |
| Allowed files | app/startup/migrations.py, app/api/services/balance_credentials_service.py (ensure_table only), app/api/services/inventory_service.py (ensure_* only), app/api/services/payroll_service.py (ensure_* only) |
| Forbidden files | Any business logic in the above files, production database |
| Required tests | Unit: startup does not crash. Integration: all tables exist after migration-only startup. |
| Success criteria | No DDL executed at startup except formal migrations. Shim functions return without executing SQL. |
| Rollback condition | Revert to previous version where shims execute. |
| Code editing | Yes |

---

### Task 11C-E — Evidence Bundle Schema and Migration

| Field | Value |
|---|---|
| Task ID | 11C-E |
| Task Name | Evidence Bundle Schema and Migration |
| Purpose | Add evidence_bundle JSONB column to journal_drafts and posting_logs. Update OCR, bank parser, and posting service to populate evidence fields. |
| Type | Code editing + additive migration |
| Allowed files | app/storage/migrations/010_evidence_bundle.sql, app/api/services/ocr_service.py, app/api/services/posting_service.py, tests/unit/ |
| Forbidden files | Balance.ge activation, auth_middleware, production database direct manipulation |
| Required tests | Unit: posting_logs carries evidence reference; Integration: full OCR-to-posting flow populates evidence bundle |
| Success criteria | Every posted entry has a populated evidence bundle. Tests pass. |
| Rollback condition | Evidence bundle is additive; removing it requires a nullable column drop (acceptable in a separate task). |
| Code editing | Yes |

---

### Task 11C-F — Balance.ge Dry-Run Pilot

| Field | Value |
|---|---|
| Task ID | 11C-F |
| Task Name | Balance.ge Dry-Run Pilot |
| Purpose | Activate Balance.ge dry-run for a test tenant. Verify payload preview, dry-run execution, posting logs, and idempotency before any live execution. |
| Type | Code editing + ops |
| Allowed files | app/api/connectors/balance_connector.py, Cloud Run env vars (test tenant credential only) |
| Forbidden files | Production tenant credentials, live execution mode |
| Prerequisites | All 12 activation gate criteria in docs/balance-ge-activation-gate.md must be verified |
| Required tests | End-to-end dry run: payload shown to reviewer, approved, sent to Balance.ge dry-run, response logged, idempotency key stored |
| Success criteria | Dry run succeeds for test tenant. Posting log contains full evidence bundle reference. No live ERP entry created. |
| Rollback condition | Remove BALANCE_API_KEY for test tenant. System returns to demo mode. |
| Code editing | Yes |

---

## Sequence Diagram

```
10F-A (docs/tests finalize) ─► 10F-B (vault design) ─► 10F-C (masked reads)
                                                              │
10F-D (subscription plan) ◄──────────────────────────────────┘
    │
    ▼
10F-E (Redis plan) ─► 10F-F (DDL cutover plan) ─► 10F-G (backup/static ops)
                                                          │
                                                          ▼
                                                    10F-H (Balance.ge gate)
                                                          │
                                          ┌───────────────┘
                                          ▼
                                   IMPLEMENTATION
                              11C-A ─► 11C-B ─► 11C-C
                                   ─► 11C-D ─► 11C-E ─► 11C-F
```

All 10F tasks are docs/tests only (no code editing).
All 11C tasks involve code editing and/or migrations.
No 11C task may start before all relevant 10F planning tasks are approved and
merged.
