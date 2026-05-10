# Trust Foundation Implementation Plan

## A) Purpose

Task 10E-F defines the Trust Foundation implementation roadmap for Bridge Hub.

Trust Foundation must be implemented **before**:

- Balance.ge live activation and any real ERP writes.
- Commercial pilot with paying tenants.
- Autonomous accounting workflows at any scale.

The three schema contracts completed in Tasks 10E-C, 10E-D, and 10E-E defined
**what** the system must look like. This plan defines **how** to get there safely,
in what order, and with what tests and rollback conditions at each step.

The following are complete and live-verified (as of main HEAD ac8d777):

- **Task 10E-C** — Credential/Security Schema Contract
- **Task 10E-D** — Accounting Truth Schema Contract
- **Task 10E-E** — Auth/Tenant Schema Contract
- **Task 11B** — AI Chief Accountant Master Plan

Implementation has NOT started. No migration, no runtime code change, no
credential encryption, no subscription enforcement, and no connector activation
has occurred. All of the following pillars remain future implementation work.

This task is planning and documentation only:

- It does not implement encryption.
- It does not enforce subscription or trial yet.
- It does not change rate limiting.
- It does not change runtime DDL behavior.
- It does not change connectors.
- It does not activate Balance.ge.
- It does not touch production database.
- It does not run SQL.

---

## B) Current Completed Contracts

### Credential/Security Contract (Task 10E-C)

`docs/credential-security-schema-contract.md`

Defines: encrypted-at-rest fields, masked reads, no plaintext secret exposure,
rotation metadata, tenant isolation, audit metadata, TOTP handling, password
reset token lifecycle, webhook secret handling, connector credential behavior,
and additive-only migration policy.

Current runtime gap confirmed: `tenant_balance_credentials.api_key` is stored
as a plaintext `TEXT` column. No encryption is in place. This is the most
critical credential gap.

### Accounting Truth Contract (Task 10E-D)

`docs/accounting-truth-schema-contract.md`

Defines: approval-first workflow, posted-only ledger truth, immutability and
reversal policy, posting log requirements, audit trail, idempotency, tenant
isolation, period lock, evidence bundle prerequisites, and reporting source rules.

Current runtime gap: evidence bundle is not yet implemented. Posting logs exist
but do not yet carry full source document references. Reports do not yet
consistently distinguish draft from posted data.

### Auth/Tenant Contract (Task 10E-E)

`docs/auth-tenant-schema-contract.md`

Defines: tenant isolation, user identity stability, password reset token
lifecycle, TOTP protection, RBAC, tenant lifecycle states, subscription and trial
enforcement, audit metadata, security boundaries, rate limiting requirements, and
additive-only migration policy.

Current runtime gap confirmed: `trial_ends_at` column exists in `tenants` table
(added via `app/startup/migrations.py` runtime DDL) but is never checked in
`app/api/middleware/auth_middleware.py` or any RBAC/permission layer. Expired
tenants can execute all accounting and connector actions without restriction.

### AI Chief Accountant Master Plan (Task 11B)

`docs/bridge-hub-ai-chief-accountant-master-plan.md`

Defines: product vision, target architecture (Input → Ingestion → Canonical →
AI Reasoning → Control → Human Approval → Execution → Audit/Reporting/Learning),
seven-phase roadmap, first pilot V1 scope, success metrics, and risks.

Overall assessment from Task 11A: architecture 8.5/10, production readiness
4.5/10, total readiness 6.5/10.

---

## C) Implementation Pillars

### Pillar 1 — Credential Vault / Encryption

**Current state:**
`tenant_balance_credentials.api_key` is stored as plaintext TEXT. No encryption
library is integrated. No key management exists. No masked-read enforcement exists
at the service layer.

**What must be planned and implemented:**

- Identify a symmetric encryption approach: AES-256-GCM via `cryptography` Python
  library (Fernet or raw GCM) or external vault such as GCP Secret Manager or
  HashiCorp Vault. Bridge Hub currently runs on Cloud Run; GCP Secret Manager is
  the lowest-friction option.

- Encrypted column pattern: existing columns such as `api_key`, `app_password`,
  `encrypted_password` must migrate to `encrypted_value` columns with a
  corresponding `encryption_key_id` or `key_version` metadata column so that
  key rotation is possible.

- Per-tenant secret handling: each tenant's credential record must be readable
  only in the context of that tenant. The encryption key or derivation must not
  be globally shared without a per-tenant salt or per-record key reference.

- Rotation metadata: `rotated_at`, `last_used_at`, `last_tested_at`,
  `last_test_status`, `revoked_at` or `is_active` must be present on all
  credential tables before real credentials are stored.

- Migration approach:
  1. Add `encrypted_value` column and `key_version` column (additive, nullable).
  2. Write migration script that reads existing plaintext, encrypts, writes to
     `encrypted_value`, and marks `key_version`.
  3. Switch read path to use `encrypted_value`.
  4. In a later task, null out the legacy plaintext column.
  5. Never DROP the plaintext column in the same migration as the data migration.

- Masked reads: after migration, the read service must return only masked values
  or boolean status. No API response or log must contain the decrypted secret
  after the initial setup step.

- Test strategy: unit tests that mock the encryption service, verify that saved
  credentials are never returned as plaintext from the read service, and verify
  that the masked format (`****1234` or `configured: true`) is returned.

- Rollout strategy: implement in a dedicated micro-task (10F-B). Deploy to a test
  tenant first. Verify in dry-run mode. Then apply to production tenants.

- Rollback strategy: if encryption service fails, fall back gracefully rather
  than crashing. Never fall back to exposing plaintext on error. Return
  `configured: false` or `status: error` on decryption failure.

**Forbidden in this task:**
- Do not implement encryption in Task 10E-F.
- Do not migrate credentials in Task 10E-F.
- Do not change balance_credentials_service.py in Task 10E-F.

---

### Pillar 2 — Masked Secret Reads

**Current state:**
`get_balance_credentials()` in `balance_credentials_service.py` returns the raw
`api_key` directly from the database to callers. Connector status endpoints may
surface this value. No enforced masked-read layer exists.

**What must be planned and implemented:**

- No API response must return a plaintext secret after initial setup. The service
  must have a `get_balance_credentials_for_use()` path (internal only, for
  connector execution) and a `get_balance_credentials_status()` path (API-facing,
  returns only safe state).

- API-facing connector status response shape must be:
  ```json
  {
    "configured": true,
    "mode": "live_ready",
    "last_test_status": "ok",
    "last_tested_at": "2026-05-01T10:00:00Z",
    "masked_key": "****7a3f"
  }
  ```
  When no credential is stored: `{"configured": false, "mode": "not_configured"}`.
  It must never include `api_key`, `app_password`, or any secret value.

- Admin-safe testing endpoints: connector test endpoints must return pass/fail
  and safe error codes only, never the credential value itself.

- Audit events for credential access: every read-for-use, test, update, and
  revoke event must create an audit record without storing the secret value.

- TOTP setup: the TOTP secret may be returned once during initial setup. After
  setup, status endpoints must return `enabled: true` or `enabled: false` only.
  The raw TOTP secret must never appear in a normal status or profile response.

**Forbidden in this task:**
- Do not change the masked read behavior in Task 10E-F.
- Do not change any service or route in Task 10E-F.

---

### Pillar 3 — Subscription / Trial Enforcement

**Current state:**
`tenants.trial_ends_at` column exists (added via runtime DDL in
`app/startup/migrations.py`). `tenants.subscription_tier` column also exists
with default `'trial'`. Neither column is checked in `auth_middleware.py`,
`rbac_middleware.py`, or any route handler. Any tenant, including expired ones,
can execute all accounting, connector, and payroll actions without restriction.

**What must be planned and implemented:**

- `trial_ends_at` enforcement: a middleware or dependency injection check must
  compare `tenants.trial_ends_at` against `now()` before mutating endpoints
  proceed. An expired trial should return HTTP 402 Payment Required with error
  code `SUBSCRIPTION_EXPIRED`.

- Tenant status enforcement: `tenants.status` or equivalent field (currently
  `subscription_tier`) must control access. States and their effects:
  - `active`: full access per RBAC.
  - `trial`: full access until `trial_ends_at` expires.
  - `suspended`: read-only access, no mutations, no connector execution.
  - `expired`: read-only access, HTTP 402 on all mutating endpoints.
  - `inactive`: full block, HTTP 403.

- Mutating endpoint blocking for suspended/expired tenants:
  - POST/PUT/PATCH/DELETE to accounting, payroll, trade, inventory routes.
  - Connector execution endpoints.
  - Approval and posting endpoints.

- Read-only mode policy: suspended/expired tenants should still be able to read
  their historical data (GET reports, GET journal entries, GET audit log) without
  blocking.

- Admin override policy: admin role or super-admin must be able to reactivate,
  extend trial, or suspend a tenant. All such actions must create audit events.

- Tests: unit tests that mock the tenants table response and verify that:
  1. Active tenants pass through.
  2. Expired trial tenants receive 402 on mutating endpoints.
  3. Suspended tenants receive 402/403 on mutating endpoints.
  4. Expired tenants can still read historical data.
  5. Admin override is audited.

**Forbidden in this task:**
- Do not implement subscription enforcement in Task 10E-F.
- Do not change auth_middleware.py or rbac_middleware.py in Task 10E-F.

---

### Pillar 4 — Redis / Rate Limiting

**Current state:**
`app/api/security.py` checks for `REDIS_URL` environment variable. If set, it
uses Redis storage for SlowAPI rate limiting. If not set, it falls back to
in-memory storage. In the current Cloud Run deployment, `REDIS_URL` is NOT set.
In a multi-instance Cloud Run auto-scale scenario, each instance has independent
in-memory limits. Global per-user/per-IP limits are not enforced across instances.

**What must be planned and implemented:**

- REDIS_URL production setup: provision a Redis instance compatible with Cloud
  Run (Google Memorystore for Redis, or an equivalent managed Redis). Add
  `REDIS_URL` to the Cloud Run environment variables.

- Endpoint coverage: rate limiting must protect:
  - `POST /auth/login`
  - `POST /auth/register`
  - `POST /auth/refresh`
  - Password reset request and use endpoints
  - TOTP verification endpoints
  - Connector test/activation endpoints

- Fallback behavior: if Redis connection fails at runtime, the system must not
  crash. It must log a warning and fall back to in-memory limiting for that
  instance, but it must also emit an alert metric or log that can trigger an
  ops alert (Redis unavailable).

- Tests: unit tests that verify that:
  1. When `REDIS_URL` is set, the limiter is initialized with Redis storage.
  2. When `REDIS_URL` is not set, the limiter uses in-memory storage.
  3. Rate limit exceeded returns HTTP 429 with `RATE_LIMIT` error code.

- Deployment verification: after setting `REDIS_URL`, call `/health` and confirm
  that the rate limiter is no longer reporting in-memory fallback.

**Forbidden in this task:**
- Do not set REDIS_URL or change security.py in Task 10E-F.

---

### Pillar 5 — Runtime DDL Cutover

**Current state:**
The following runtime DDL shims remain active and execute at every app startup:

- `app/startup/migrations.py`: runs `ALTER TABLE` for `outgoing_invoices`,
  `tenants`, `expenses`, `invoices`, `contracts`, `customers`, and other tables
  at startup via psycopg2.
- `app/api/services/balance_credentials_service.py`: `ensure_table()` creates
  `tenant_balance_credentials` if not exists.
- `app/api/services/inventory_service.py`: `ensure_inventory_tables()` creates
  inventory tables at startup.
- `app/api/services/payroll_service.py`: `ensure_payroll_erp_tables()` creates
  payroll tables at startup.

Additive SQL migrations 005–008 cover inventory, payroll, trade, and outgoing
invoice columns, but the runtime shims have not been removed and run alongside
the formal migrations.

**What must be planned and implemented:**

- Coverage verification: before any shim is removed, a read-only test must prove
  that the formal migration covers every table and column that the shim creates or
  alters. The test must compare migration DDL output against the runtime shim DDL
  side by side.

- Cutover strategy per shim:
  1. Write additive migration that covers the shim.
  2. Add test that proves coverage.
  3. Deploy migration to production.
  4. Verify production schema matches expected state.
  5. Only then remove the shim from runtime code.
  6. Deploy the shim removal separately, with a rollback plan that is simply
     re-adding the shim if production reports failures.

- Compatibility wrappers: during cutover, the shim functions (`ensure_table()`,
  `ensure_inventory_tables()`) may remain but be converted to no-ops that only
  log and return without executing DDL. This reduces risk compared to outright
  removal.

- Test strategy: `tests/unit/test_schema_manifest.py` and
  `tests/unit/test_inventory_migration_schema.py` already prove that the formal
  migrations are additive. Extend these with shim-vs-migration comparison tests.

- No removal until: additive migration exists, test passes, production deployment
  verified, existing-DB upgrade test passes against a copy of production schema.

**Forbidden in this task:**
- Do not remove any runtime DDL shim in Task 10E-F.
- Do not edit app/startup/migrations.py or any service with ensure_* functions
  in Task 10E-F.

---

### Pillar 6 — DB Backup / PITR

**Current state:**
No documented backup configuration checklist exists for Bridge Hub. Cloud Run
with PostgreSQL backend (likely Cloud SQL or Neon) may have automatic backups
enabled by default, but there is no confirmed PITR window, restore drill, or
pre-migration backup procedure.

**What must be planned and implemented:**

- Backup configuration checklist:
  - Confirm automated daily backups are enabled on the PostgreSQL host.
  - Confirm point-in-time recovery (PITR) window is at least 7 days.
  - Confirm backup location is in a different region from the primary.
  - Confirm backup access is restricted to ops/admin roles only.
  - Document backup retention policy.

- Pre-migration backup requirement: before any production migration runs, a
  manual or automated backup must be taken and confirmed restorable. This must be
  a documented step in every migration runbook.

- Restore drill: a restore drill must be run at least once in a staging/test
  environment before the first real schema migration is applied to production.
  The drill must verify that a backup taken before a migration can be restored
  to a clean environment and the app can start against it.

- Environment separation: production database must not be used for testing
  migrations. A staging/test environment with a copy of the production schema
  (not data) must be used to validate migrations before production apply.

- Migration safety: every migration runbook must include:
  1. Pre-migration: take backup, confirm PITR is current.
  2. Apply migration in staging, run tests.
  3. Apply migration in production.
  4. Verify production health after migration.
  5. If health fails: restore from backup, not rollback SQL.

**Forbidden in this task:**
- Do not configure backups in Task 10E-F. This is ops work for a later task.

---

### Pillar 7 — Static Files GCS/CDN

**Current state:**
All static files (`app/templates/*.html`, `app/static/`) are served directly
from the FastAPI application container on Cloud Run. The container bundles the
static files at build time. This means:

- Static file serving competes for Cloud Run CPU/memory with API request
  handling.
- Large static files (approval.html at 361KB) are served from app container.
- Uploaded documents and evidence files may be growing in the container if not
  already offloaded.

**What must be planned and implemented:**

- GCS bucket strategy: static HTML, JS, CSS, and image assets should be served
  from a Google Cloud Storage bucket with Cloud CDN enabled, rather than from
  the app container.

- Cache strategy: static versioned assets (JS, CSS with content hashes) can use
  long cache TTLs (1 year). HTML pages should use shorter TTLs (5–60 minutes)
  or `no-cache` with ETags to prevent stale UI after deployments.

- Deployment implications: the deployment pipeline must include a step to upload
  updated static assets to GCS before the new app container starts receiving
  traffic. Asset version mismatches between CDN and backend API must be handled
  (API version header, cache busting).

- Rollback: rollback of static assets requires reverting the GCS upload or
  invalidating the CDN cache and re-uploading the previous version.

- Uploaded evidence files: user-uploaded documents and OCR source files must be
  stored in GCS (already partially implemented with `GCS_BUCKET_NAME` env var).
  Any remaining container-local evidence storage must be moved to GCS before
  production use.

**Forbidden in this task:**
- Do not move static files or configure GCS/CDN in Task 10E-F.

---

### Pillar 8 — Evidence Bundle

**Current state:**
The Accounting Truth Contract (Task 10E-D) requires an evidence bundle before
any Balance.ge or ERP write pilot. Currently, journal drafts reference source
documents via `source_document`, `reference_type`, and related fields, but there
is no standardized evidence bundle structure that travels with a draft through
approval to posting.

**What must be planned and implemented:**

An evidence bundle must be attached to every approved accounting action before
it reaches a connector. The bundle must include:

- **Source document**: the original file (PDF, image, Excel) stored in GCS, with
  a signed URL or storage reference.
- **Extracted fields**: the OCR or parser output that produced the journal draft.
- **AI reasoning**: the classification rationale, confidence score, tax risk
  flags, and proposed journal lines from the AI reasoning layer.
- **Validation warnings**: any risk flags or validation failures that were
  reviewed and accepted by the human approver.
- **Reviewer decision**: who approved, when, notes, and CFO approval if required.
- **Connector payload preview**: the exact payload that will be sent to Balance.ge
  or the ERP, in a human-readable format, shown to the approver before execution.
- **Posting result**: the connector response, status, idempotency key, and any
  error mapping after execution.
- **Audit trace**: the full state transition log for the draft from creation to
  posting.

Evidence bundle implementation steps:
1. Define the `EvidenceBundle` schema (Pydantic model or JSONB column).
2. Add `evidence_bundle` JSONB column to `journal_drafts` (additive migration).
3. Update OCR, bank parser, and email collector to populate evidence fields.
4. Update approval UI to show the evidence panel.
5. Update posting service to attach the bundle to `posting_logs`.

**Forbidden in this task:**
- Do not implement evidence bundle in Task 10E-F.

---

### Pillar 9 — Balance.ge Activation Gate

**Current state:**
Balance.ge connector operates in demo mode when `BALANCE_API_KEY` environment
variable is absent. Per-tenant credentials can be stored in
`tenant_balance_credentials`, but `api_key` is plaintext. No dry-run mode, no
payload preview, no activation gate, and no rollback strategy exist for live
Balance.ge posting.

**What must be planned and implemented:**

Balance.ge must remain inactive in production until all activation gate criteria
are verified. See `docs/balance-ge-activation-gate.md` for the full gate checklist.

Summary of gates:

1. Encrypted credentials: credential encryption complete and verified.
2. Masked reads enforced at all API surfaces.
3. Approval-first flow verified end-to-end for the pilot tenant.
4. Evidence bundle implemented and attached to every approved action.
5. Idempotency verified: duplicate posting attempts return existing result, not
   a new ERP entry.
6. Dry-run mode verified: Balance.ge dry run succeeds for the pilot tenant
   without writing to production ERP.
7. Payload preview verified: the exact payload is shown to and accepted by the
   accountant before live execution.
8. `posting_logs` verified: every execution attempt, success, and failure is
   logged with tenant ID, draft ID, payload summary, response, and idempotency
   key.
9. Test tenant verified: at least one full end-to-end dry run on an isolated
   test tenant before any production tenant execution.
10. Accountant review complete: a qualified Georgian accountant has reviewed the
    proposed journal lines, COA mapping, VAT treatment, and connector payload.
11. Rollback/manual fallback documented: if Balance.ge returns an error, the
    system must have a defined manual fallback (human exports the payload and
    posts manually to Balance.ge).
12. Production secrets configured safely: `BALANCE_API_KEY` or per-tenant
    credentials must be encrypted at rest and configured in Cloud Run secret
    references, not plaintext environment variables.

**Forbidden in this task:**
- Do not activate Balance.ge in Task 10E-F.

---

## D) Risk Matrix

| Pillar | Risk | Severity | Why It Matters | Mitigation | Required Tests | Go/No-Go |
|---|---|---|---|---|---|---|
| Credential Vault | Plaintext `api_key` in DB | Critical | Real credentials exposed in DB and any DB backup | Encrypt before storing real credentials; never store plaintext | Unit: masked read enforced; Integration: credential never returned plaintext | No real credentials until encrypted |
| Masked Reads | API returns raw secret | Critical | Credential leaks via status APIs, logs, frontends | Service-layer masked read path before any API surface | Unit: status endpoint never returns raw value | No live API before masked reads |
| Subscription Enforcement | Expired tenants transact | High | Revenue integrity; expired tenants use the product for free | Enforce `trial_ends_at` check in middleware | Unit: expired tenant gets 402; active tenant passes | No commercial pilot before enforcement |
| Redis / Rate Limiting | In-memory limits per instance | High | Login brute force possible in multi-instance prod | Set REDIS_URL before public pilot | Unit: limiter uses Redis when REDIS_URL set | No public pilot before Redis configured |
| Runtime DDL Cutover | Dual DDL paths at startup | Medium | Schema drift between runtime and migrations; hard to reason about prod state | Migration coverage tests; convert shims to no-ops; remove only after tests pass | Unit: migration covers all shim DDL | No shim removal before migration proves coverage |
| DB Backup / PITR | No confirmed backup/restore | High | Migration failure without backup = data loss | Confirm PITR before first production migration; run restore drill | Ops checklist verification | No production migration without confirmed backup |
| Static Files GCS/CDN | Static in container | Low | Performance; evidence files must not stay in container long-term | Move to GCS; CDN cache strategy | Deployment verification | Before commercial scale |
| Evidence Bundle | No audit trail for connector payloads | High | Cannot prove what was sent to ERP; cannot dispute/reverse | Implement EvidenceBundle schema and attach to posting | Unit: posting_logs carries evidence reference | No connector pilot without evidence bundle |
| Balance.ge Gate | Live ERP write without gates | Critical | Incorrect ERP entries cannot be easily reversed; accounting damage | All 12 gate criteria must pass | Full end-to-end dry run on test tenant | No live posting before all gates pass |

---

## E) Implementation Order

### Recommended Safe Micro-Task Sequence

#### 10F-A — Trust Foundation Docs and Tests Finalize (this task)
- Type: docs/tests only
- Deliverables: this document, implementation sequence, Balance.ge gate checklist, test suite
- Allowed: docs/, tests/unit/
- Forbidden: app/*, migrations, runtime code, production DB

#### 10F-B — Credential Vault Design and Tests
- Type: docs/tests only (no implementation yet)
- Deliverables: detailed credential vault design doc (key management, GCP Secret Manager
  vs Fernet decision, migration plan, rotation model), unit tests that prove design
  assumptions, mock-based tests for the masked read service contract
- Allowed: docs/, tests/unit/
- Forbidden: app/, migrations, production credentials

#### 10F-C — Masked Read Behavior Tests
- Type: tests only
- Deliverables: unit tests that mock the credential service layer and assert that
  no API-facing function returns a raw secret value; tests for each credential type
  (Balance.ge, email, RS.ge, TOTP, webhook)
- Allowed: tests/unit/
- Forbidden: app/api/services/ changes in this micro-task

#### 10F-D — Subscription/Trial Enforcement Plan and Tests
- Type: docs/tests only
- Deliverables: detailed enforcement design (middleware approach, dependency injection
  approach, which endpoints are protected), unit tests that mock the tenants table
  and verify 402/403 responses for expired/suspended tenants
- Allowed: docs/, tests/unit/
- Forbidden: app/api/middleware/ changes in this micro-task

#### 10F-E — Redis/Rate-Limit Plan and Tests
- Type: docs/tests only
- Deliverables: Redis setup runbook (Cloud Run env var, Memorystore provisioning),
  unit tests that assert limiter uses Redis storage when REDIS_URL is set
- Allowed: docs/, tests/unit/
- Forbidden: app/api/security.py changes in this micro-task

#### 10F-F — Runtime DDL Cutover Plan
- Type: docs/tests only
- Deliverables: per-shim cutover runbook, shim-vs-migration comparison tests,
  no-op conversion design
- Allowed: docs/, tests/unit/
- Forbidden: app/startup/migrations.py changes, shim removal in this micro-task

#### 10F-G — Backup / Static Ops Checklist
- Type: docs/checklist only
- Deliverables: backup/PITR configuration checklist, restore drill guide, static files
  GCS migration runbook
- Allowed: docs/
- Forbidden: ops infrastructure changes in this micro-task

#### 10F-H — Balance.ge Activation Gate Checklist
- Type: docs/tests only
- Deliverables: gate checklist validation tests (proves docs/balance-ge-activation-gate.md
  covers all required conditions), dry-run design doc
- Allowed: docs/, tests/unit/
- Forbidden: Balance.ge activation, connector changes in this micro-task

#### Later Implementation Tasks (only after 10F-A through 10F-H are approved)
- 11C-A: Credential encryption implementation (app/api/services/ changes allowed)
- 11C-B: Subscription enforcement implementation (app/api/middleware/ changes allowed)
- 11C-C: Redis configuration deployment (ops change)
- 11C-D: Runtime DDL shim conversion to no-ops (app/startup/ and service changes)
- 11C-E: Evidence bundle schema and JSONB migration (migration allowed)
- 11C-F: Balance.ge dry-run pilot (connector changes allowed, after all gates pass)

---

## F) What Not To Implement Yet

This task and the entire 10F series are planning and documentation only. The
following actions are explicitly forbidden until dedicated implementation tasks
are assigned and approved:

- **No Balance.ge activation**: `BALANCE_API_KEY` must not be set in production
  and the connector must not be switched to live mode in any 10F task.
- **No live ERP writes**: no connector, service, or route may write to a real ERP
  system in any 10F task.
- **No runtime DDL removal**: `ensure_table()`, `ensure_inventory_tables()`,
  `ensure_payroll_erp_tables()`, and `app/startup/migrations.py` shims must not
  be removed or converted to no-ops in any 10F task.
- **No destructive migrations**: no DROP TABLE, TRUNCATE, DELETE, or destructive
  ALTER in any 10F task.
- **No auth behavior change in 10F**: auth_middleware.py must not be changed.
- **No connector behavior change in 10F**: connector files must not be changed.
- **No subscription enforcement in 10F**: trial_ends_at is not enforced until a
  dedicated implementation task is assigned.
- **No encryption implementation in 10F**: credential tables remain as-is until
  dedicated implementation tasks are assigned.
- **No production database mutation in any 10F task**.
