# Trust Foundation Runtime Implementation Sequence

## A) Purpose

Task 11C-A defines the authoritative implementation sequence for the entire 11C
runtime implementation phase.

The Trust Foundation planning and checklist phase (Tasks 10E-C through 10F-H)
is complete and live-verified. Task 11C is the runtime implementation phase
that follows it. This document defines:

- The exact implementation order for all 11C sub-tasks.
- Allowed and forbidden files for each sub-task.
- Hard dependencies between sub-tasks.
- Testing strategy, rollback strategy, and live verification standard.
- Stop conditions that must halt a sub-task.
- Balance.ge activation boundary.
- Commercial pilot blockers that must be resolved before live pilot.

**This task is documentation and tests only.**
**This task does NOT implement runtime code.**
**This task does NOT create migrations.**
**This task does NOT touch the production database.**
**This task does NOT run SQL.**
**This task does NOT activate Balance.ge.**
**This task does NOT start 11C-B implementation.**

Cross-references:
- `docs/trust-foundation-implementation-plan.md` — overall Trust Foundation roadmap
- `docs/balance-ge-activation-final-checklist.md` — final Balance.ge gate checklist (authoritative)
- `docs/credential-vault-design.md` — credential vault design target
- `docs/masked-read-behavior-contract.md` — masked read behavior contract
- `docs/subscription-enforcement-plan.md` — subscription/trial enforcement plan
- `docs/redis-rate-limit-plan.md` — Redis/rate-limit plan
- `docs/runtime-ddl-cutover-plan.md` — runtime DDL cutover plan
- `docs/backup-pitr-static-files-plan.md` — backup/PITR/static files plan

---

## B) Current Baseline

As of main HEAD `5de1cdd9e135e6a04a6c6eba4bfb675f043f8e5f`:

| Item | Status |
|---|---|
| Latest live verified commit | `5de1cdd` (Task 10F-H merged and live) |
| Autopilot multi-tenant hotfix | Live at `3a4d61a` (merged into `5de1cdd` history) |
| Trust Foundation planning/checklists | **Complete** — 10F-B through 10F-H all merged and live-verified |
| Balance.ge status | **DEMO** — `BALANCE_API_KEY` absent from production |
| Credential vault | **NOT implemented** — api_key stored as plaintext TEXT |
| Masked read runtime enforcement | **NOT implemented** — contract defined (10F-C) only |
| Subscription enforcement middleware | **NOT implemented** — contract defined (10F-D) only |
| Redis/rate-limit runtime enforcement | **NOT implemented** — contract defined (10F-E) only |
| Evidence bundle | **NOT implemented** — column absent from journal_drafts |
| Reports ledger integrity | **CRITICAL** — reports use `journal_drafts` not `journal_entries` |
| Runtime DDL gap | **Unresolved** — 30+ DDL statements in startup code |
| Backup/PITR restore drill | **NOT completed** — plan defined (10F-G) only |
| Task 11C runtime implementation | **NOT started** before this document |
| Production DB/infrastructure | **Unchanged** |

---

## C) Core Rules for 11C

Every 11C runtime PR must follow these rules without exception:

1. **One runtime domain per PR.** No mixed-concern PRs. A credential vault migration PR must not also add subscription enforcement.

2. **Tests first.** Every runtime change must have targeted unit tests written before or alongside the runtime code. No untested runtime changes.

3. **Migrations only in explicit migration tasks.** If a task description says "no migration," no migration is created. If a migration is needed, the task must explicitly authorize it.

4. **No production SQL.** No direct `psql`, Cloud SQL console queries, or manual SQL execution against production. All schema changes must go through the migration framework.

5. **No live connector activation during implementation PRs.** Balance.ge connector must remain in `demo_mode` through 11C-B to 11C-K inclusive.

6. **No Balance.ge live activation until 11C-L final gate PR.** The final gate PR must satisfy all 14 gates from `docs/balance-ge-activation-final-checklist.md`.

7. **Every runtime change must have targeted tests + regression tests + deploy + live verification.** No PR is complete until live `/version` matches and live verification checklist passes.

8. **Every PR must state allowed/forbidden files explicitly.** The PR description must list which files are allowed and which are forbidden for that task.

9. **Every PR must include rollback notes.** Rollback instructions must be included in the PR description.

10. **Every PR must confirm Balance.ge remains inactive** unless it is explicitly the 11C-L final activation PR.

---

## D) 11C Implementation Order

### 11C-A — Runtime Implementation Sequence (current task)

**Scope:** Docs/tests only. This document.

**Allowed files:**
- `docs/trust-foundation-runtime-implementation-sequence.md`
- `tests/unit/test_trust_foundation_runtime_sequence.py`

**Forbidden files:** All runtime app code, connectors, services, migrations, workflows, infrastructure.

**Does not implement:** Any runtime code, migration, or connector change.

**Status:** In progress (this task).

---

### 11C-B — Credential Vault Runtime Architecture and Migration Plan

**Scope:** Docs/tests only — no live credential migration yet. Define the exact
migration schema, service interface, and test strategy for the vault before
any code is written.

**Allowed files:**
- `docs/credential-vault-runtime-plan.md` (new)
- `tests/unit/test_credential_vault_runtime_plan.py` (new)
- `docs/credential-vault-design.md` (cross-reference update only if needed)

**Forbidden files:** `app/api/services/balance_credentials_service.py`,
`app/api/routes_*.py`, `app/storage/migrations/*`, `app/startup/*`,
`app/api/connectors/*`, `.env`, production DB.

**Does not implement:** Any migration, encryption code, or credential change.

**Outputs:** Migration column spec (`encrypted_value`, `key_version`,
`masked_hint`, `rotated_at`, `last_accessed_at`), service interface contract,
test plan for masked-only API responses.

**Next:** 11C-C (after 11C-B is merged and live-verified).

---

### 11C-C — Credential Vault Migration and Storage Service

**Scope:** First true runtime PR. Adds credential vault migration and
updates the credential storage service to use `encrypted_value`.

**Allowed files:**
- `app/storage/migrations/` — new migration file only (explicit authorization required)
- `app/api/services/balance_credentials_service.py`
- `tests/unit/test_credential_vault_service.py` (new)
- `tests/unit/test_credential_vault_migration.py` (new)

**Forbidden files:** `app/api/connectors/*`, `app/startup/*`,
`app/api/routes_*.py`, `.env`, production DB write.

**Hard prerequisite:** 11C-B merged and live-verified.

**Does not implement:** Balance.ge live activation, masked read enforcement,
connector changes.

**Must confirm:**
- `encrypted_value` column added.
- `api_key` plaintext column nulled or removed.
- No API-facing function returns raw `api_key`.
- GATE-01 and GATE-02 from `docs/balance-ge-activation-final-checklist.md` closer to MET.

---

### 11C-D — Masked Reads Runtime Enforcement

**Scope:** Implement runtime enforcement of masked-read behavior contract.
Public/status credential endpoints return `configured`/`not_configured`/`demo`
only — no raw `api_key`, `password`, `token`, or `secret`.

**Allowed files:**
- `app/api/services/balance_credentials_service.py`
- `app/api/routes_connectors.py` or equivalent connector status route
- `tests/unit/test_masked_reads_runtime.py` (new)

**Forbidden files:** `app/api/connectors/*` (behavior change), `app/startup/*`,
migrations (unless explicitly authorized), production DB, `.env`.

**Hard prerequisite:** 11C-C merged and live-verified (vault must exist before
masking it).

**Must confirm:**
- Status endpoint returns no raw credentials.
- Response scan test shows no `api_key` in any status response.
- GATE-03 from `docs/balance-ge-activation-final-checklist.md` MET.

---

### 11C-E — Subscription / Trial Enforcement Middleware

**Scope:** Implement runtime enforcement blocking expired/suspended tenants
from connector execution, journal draft creation, and paid actions.

**Allowed files:**
- `app/api/middleware/` — new subscription enforcement middleware
- `main.py` — middleware registration only
- `tests/unit/test_subscription_enforcement_runtime.py` (new)

**Forbidden files:** `app/api/connectors/*`, `app/api/services/approval_service.py`,
`app/storage/migrations/*` (unless explicitly authorized), production DB, `.env`.

**Hard prerequisite:** 11C-A complete. May run concurrently with 11C-C/11C-D
as long as no connector behavior is changed.

**Must confirm:**
- Expired tenant receives `SUBSCRIPTION_REQUIRED` error from blocked endpoints.
- Suspended tenant is fully blocked from all mutating actions.
- Active tenants are not affected.
- GATE-04 from `docs/balance-ge-activation-final-checklist.md` MET.

---

### 11C-F — Redis / Rate-Limit Runtime Enforcement

**Scope:** Implement Redis-backed rate limiting for auth, credential, and
connector endpoints. Safe in-memory fallback when Redis unavailable.

**Allowed files:**
- `app/api/middleware/` — new or updated rate-limit middleware
- `main.py` — middleware registration only
- `tests/unit/test_redis_rate_limit_runtime.py` (new)

**Forbidden files:** `app/api/connectors/*`, `app/storage/migrations/*`
(unless explicitly authorized), production DB, `.env`.

**Hard prerequisite:** 11C-A complete. May run concurrently with 11C-C/11C-D/11C-E.

**Must confirm:**
- Auth endpoints throttled at configured limit.
- Connector endpoints throttled.
- In-memory fallback has a conservative cap (not unlimited).
- Redis connection failure does not crash the app.
- GATE-05 from `docs/balance-ge-activation-final-checklist.md` MET.

---

### 11C-G — Evidence Bundle Foundation

**Scope:** Add `evidence_bundle` JSONB column to `journal_drafts` and implement
population logic at each step of the approval/posting flow.

**Allowed files:**
- `app/storage/migrations/` — new migration adding `evidence_bundle` column
- `app/api/services/approval_service.py` — evidence population only
- `app/api/services/posting_service.py` — posting result appended to bundle
- `tests/unit/test_evidence_bundle_runtime.py` (new)

**Forbidden files:** `app/api/connectors/*` (no live activation),
`app/startup/*`, production DB write outside migration, `.env`.

**Hard prerequisite:** 11C-A complete. Migration explicitly authorized for this task.

**Must confirm:**
- `evidence_bundle` column exists after migration.
- Source document reference populated on draft creation.
- Approval event recorded in bundle.
- Posting result appended on successful posting.
- GATE-10 from `docs/balance-ge-activation-final-checklist.md` MET.

---

### 11C-H — Reports Ledger Integrity Plan / Migration

**Scope:** Fix the critical issue where financial reports (`trial-balance`,
`P&L`, `balance-sheet`) use `journal_drafts` instead of posted `journal_entries`.
This is a **commercial pilot blocker**.

**Allowed files:**
- `app/api/services/financial_statements_service.py`
- `app/storage/migrations/` — migration for `journal_entries` table if not existing
- `tests/unit/test_reports_ledger_integrity.py` (new)
- `docs/reports-ledger-integrity-plan.md` (new, for sub-task planning if needed)

**Forbidden files:** `app/api/connectors/*`, `app/startup/*`,
approval/posting service core logic, production DB direct write, `.env`.

**Hard prerequisite:** 11C-A complete. This is an independent but critical path.
May be prioritized alongside or before 11C-C if the reporting risk is judged
higher than the credential vault risk.

**Must confirm:**
- Trial balance uses posted `journal_entries` only.
- P&L uses posted `journal_entries` only.
- Balance sheet uses posted `journal_entries` only.
- Draft amounts do not appear in final ledger reports without explicit draft label.
- Accounting truth schema contract (10E-D) satisfied at runtime.

---

### 11C-I — Runtime DDL Gap Map and Migration Slices

**Scope:** Identify all tables created by `CREATE TABLE IF NOT EXISTS` in
startup/route/service code. Convert each to an explicit migration. Remove
startup DDL only after migration coverage is verified.

**Allowed files:**
- `app/storage/migrations/` — one migration per table domain (multiple PRs)
- `app/startup/migrations.py` — DDL removal only after migration coverage confirmed
- `tests/unit/test_runtime_ddl_coverage.py` (new)

**Forbidden files:** `app/api/connectors/*`, `app/api/routes_*.py` (logic changes),
production DB direct write, `.env`.

**Hard prerequisite:** 11C-A complete. Should run after 11C-C/11C-G migrations
to reduce overlap. One PR per migration domain.

**Must confirm:**
- Every startup DDL statement has a corresponding explicit migration.
- Startup DDL removed only after migration verified on production.
- Schema manifest updated.
- Runtime DDL cutover plan (10F-F) executed safely.

---

### 11C-J — Backup / PITR Ops Verification

**Scope:** Verify Cloud SQL automated backups, PITR, and complete a restore
drill on a non-production clone.

**Allowed files:**
- `docs/backup-pitr-restore-drill-report.md` (new evidence document)
- `tests/unit/test_backup_pitr_verification.py` (new, evidence-only checks)

**Forbidden files:** All runtime app code, production DB, production
infrastructure changes, `.env`.

**Hard prerequisite:** 11C-A complete. No dependency on other 11C tasks.
Can run in parallel with any 11C task.

**Must confirm:**
- Cloud SQL automated backups enabled and verified.
- PITR enabled on production Cloud SQL instance.
- Restore drill completed on a non-production clone (not production data).
- Restore drill report created as evidence.
- No production database overwritten.
- GATE-11 from `docs/balance-ge-activation-final-checklist.md` MET.

---

### 11C-K — Balance.ge Dry-Run and Payload Preview

**Scope:** Implement and verify `dry_run=True` mode in `balance_connector.py`,
accountant-facing payload preview, and idempotency key. No live posting.

**Allowed files:**
- `app/api/connectors/balance_connector.py`
- `app/api/services/posting_service.py` — dry_run parameter threading only
- `tests/unit/test_balance_dry_run.py` (new)

**Forbidden files:** Production Balance.ge credentials, `.env` with live
`BALANCE_API_KEY`, production DB direct write.

**Hard prerequisites:** 11C-C (vault), 11C-D (masked reads), 11C-E
(subscription enforcement), 11C-F (rate limiting), 11C-G (evidence bundle)
all merged and live-verified.

**Must confirm:**
- `dry_run=True` parameter exists in `balance_connector.py`.
- Dry-run execution creates a `posting_logs` entry with `mode = dry_run`.
- No live Balance.ge API write occurs in dry-run mode.
- Idempotency key present in posting attempt.
- Payload preview shows all required fields.
- GATE-07, GATE-08, GATE-09 from `docs/balance-ge-activation-final-checklist.md` MET.

---

### 11C-L — Balance.ge Final Live Activation PR

**Scope:** The one and only PR that activates live Balance.ge posting for the
pilot tenant. Must satisfy all 14 gates from
`docs/balance-ge-activation-final-checklist.md`.

**Allowed files:**
- `app/api/connectors/balance_connector.py` — live mode enablement
- `app/api/services/balance_credentials_service.py` — vault-backed credential read
- Pilot tenant configuration

**PR title must explicitly state:** "live Balance.ge activation — pilot tenant [name]"

**Hard prerequisites:** ALL of the following:
- 11C-C (vault) merged and live-verified
- 11C-D (masked reads) merged and live-verified
- 11C-E (subscription enforcement) merged and live-verified
- 11C-F (rate limiting) merged and live-verified
- 11C-G (evidence bundle) merged and live-verified
- 11C-J (backup/PITR restore drill) completed with evidence
- 11C-K (dry-run/preview) merged and live-verified
- All 14 GATE conditions in `docs/balance-ge-activation-final-checklist.md` MET
- Accountant pilot sign-off document attached to PR
- Live verification steps planned and documented

**Must NOT proceed if:** Any gate is NOT MET. Any evidence item is missing.
Any test fails. No accountant sign-off.

---

## E) Dependency Graph

```
11C-A (this task, docs/tests)
  │
  ├── 11C-B (vault runtime plan, docs/tests)
  │     │
  │     └── 11C-C (vault migration + service) ─────────────────────┐
  │               │                                                  │
  │               └── 11C-D (masked reads, depends on 11C-C) ──────┤
  │                                                                  │
  ├── 11C-E (subscription enforcement, independent after 11C-A) ───┤
  │                                                                  │
  ├── 11C-F (Redis rate-limit, independent after 11C-A) ───────────┤
  │                                                                  │
  ├── 11C-G (evidence bundle, independent migration) ───────────────┤
  │                                                                  │
  ├── 11C-H (reports ledger integrity, CRITICAL, independent) ──────┤
  │                                                                  │
  ├── 11C-I (runtime DDL gap, independent, multiple PRs) ──────────┤
  │                                                                  │
  ├── 11C-J (backup/PITR, independent, parallel) ──────────────────┤
  │                                                                  │
  └── 11C-K (Balance.ge dry-run, depends on C+D+E+F+G) ───────────┘
              │
              └── 11C-L (live activation, depends on ALL gates MET)
```

**Hard dependencies (must not be bypassed):**
- `11C-D` depends on `11C-C` — cannot mask what the vault doesn't store yet
- `11C-K` depends on `11C-C`, `11C-D`, `11C-E`, `11C-F`, `11C-G` — all safety
  layers must be in place before any connector dry-run
- `11C-L` depends on ALL 14 gates MET — no exceptions, no partial activation
- Reports ledger integrity (`11C-H`) must be fixed before commercial pilot

**Independent tasks (can run in parallel after 11C-A):**
- `11C-E`, `11C-F`, `11C-H`, `11C-I`, `11C-J` have no dependency on vault

---

## F) First Runtime Task Recommendation

After 11C-A is merged and live-verified, the recommended next task is:

**11C-B — Credential Vault Runtime Architecture and Migration Plan**

Rationale:
- The credential vault is the foundational security component that unblocks
  GATE-01 and GATE-02 and is required before 11C-D and 11C-K.
- 11C-B is still docs/tests only — it plans the migration schema and service
  interface without touching runtime code.
- It is safe, reversible, and low-risk.

If reports ledger integrity (`11C-H`) is judged a higher priority (because
it is a commercial pilot blocker and independent of the vault), it may be
started in parallel with 11C-B.

**Recommended first true runtime PR:** 11C-C — after 11C-B defines the exact
migration schema and service interface.

---

## G) Balance.ge Activation Boundary

- Balance.ge **must remain inactive** (`demo_mode`) through all of 11C-B,
  11C-C, 11C-D, 11C-E, 11C-F, 11C-G, 11C-H, 11C-I, 11C-J, and 11C-K.
- No live Balance.ge API write before 11C-L.
- No production `BALANCE_API_KEY` setup before:
  - Credential vault (11C-C) is implemented.
  - Masked reads (11C-D) are enforced.
  - Subscription enforcement (11C-E) is active.
  - All 14 gates in `docs/balance-ge-activation-final-checklist.md` are MET.
- `docs/balance-ge-activation-final-checklist.md` is the authoritative document
  for all Balance.ge activation decisions. It supersedes any other document.
- Any PR that attempts Balance.ge live activation without meeting all 14 gates
  must be rejected.

---

## H) Allowed/Forbidden Categories for 11C

| 11C Task | Allowed File Groups | Key Forbidden Files |
|---|---|---|
| 11C-A | `docs/`, `tests/unit/` | All `app/`, migrations, workflows, `.env` |
| 11C-B | `docs/`, `tests/unit/` | All `app/`, migrations, workflows, `.env` |
| 11C-C | `app/storage/migrations/` (1 file), `app/api/services/balance_credentials_service.py`, `tests/unit/` | `app/api/connectors/*`, `app/startup/*`, `app/api/routes_*.py`, `.env` |
| 11C-D | `app/api/services/balance_credentials_service.py`, connector status route, `tests/unit/` | `app/api/connectors/*` (logic change), migrations (unless authorized), `.env` |
| 11C-E | `app/api/middleware/` (new file), `main.py` (registration only), `tests/unit/` | `app/api/connectors/*`, `app/api/services/approval_service.py`, `.env` |
| 11C-F | `app/api/middleware/` (new/updated), `main.py` (registration only), `tests/unit/` | `app/api/connectors/*`, migrations (unless authorized), `.env` |
| 11C-G | `app/storage/migrations/` (1 file), `app/api/services/approval_service.py` (population only), `app/api/services/posting_service.py` (population only), `tests/unit/` | `app/api/connectors/*`, `app/startup/*`, `.env` |
| 11C-H | `app/api/services/financial_statements_service.py`, migrations (if needed), `tests/unit/` | `app/api/connectors/*`, approval/posting core logic, `.env` |
| 11C-I | `app/storage/migrations/` (one per domain), `app/startup/migrations.py` (DDL removal after coverage verified), `tests/unit/` | `app/api/routes_*.py` (logic), `app/api/connectors/*`, `.env` |
| 11C-J | `docs/` (restore drill report), `tests/unit/` | All runtime app code, production DB, production infrastructure |
| 11C-K | `app/api/connectors/balance_connector.py`, `app/api/services/posting_service.py` (dry_run param only), `tests/unit/` | Production credentials, `.env` with live key, production DB direct write |
| 11C-L | Explicit activation PR — all gates MET required | Any file if a gate is NOT MET |

---

## I) Testing Strategy

Every 11C runtime PR must include all of the following:

1. **Targeted tests:** Unit tests specifically for the new or changed function,
   endpoint, or migration. Written alongside or before the runtime code.

2. **Related contract tests:** Re-run the relevant 10F contract test suite to
   confirm the implementation satisfies the planning contract.

3. **Regression subset:** Re-run the full `tests/unit/` suite
   (`--ignore=tests/unit/test_document_upload.py`) to confirm no regressions.

4. **No-secrets tests:** Assert that no API response, log output, or test
   fixture contains a raw `api_key`, `password`, `token`, or `secret`.

5. **No live connector tests:** Tests must not call the live Balance.ge API
   unless the PR is explicitly 11C-L.

6. **Live verification after merge:** After every PR merges and deploys,
   confirm live `/version` matches, `/health` returns 200, static pages load,
   and protected endpoints reject unauthenticated requests.

---

## J) Rollback Strategy

Every 11C runtime PR must include rollback notes covering:

1. **Code rollback:** Revert the PR commit. The previous behavior must be
   restored without any manual steps.

2. **Migration rollback:** If the PR includes a migration, a `down` migration
   or additive-only strategy must be documented. `DROP COLUMN` on live data
   requires explicit sign-off.

3. **Safe disable flag:** For middleware tasks (11C-E, 11C-F), an environment
   variable or config flag must allow the middleware to be disabled without a
   code deploy.

4. **No data loss path:** No migration may destroy data without a backup/restore
   plan documented in the PR.

5. **Idempotent migration strategy:** All migrations must be safe to run
   multiple times (`IF NOT EXISTS`, `IF EXISTS`, idempotency guards).

6. **Emergency disable for connector tasks:** For 11C-K and 11C-L, removing or
   blanking the tenant's credential in the vault immediately reverts the
   connector to `demo_mode`.

---

## K) Live Verification Standard

After every 11C PR merges and deploys, the following must be verified before
the PR is considered complete:

1. Local `main` HEAD matches live `/version` commit SHA.
2. `GET /health` returns HTTP 200.
3. Static pages (`/static/approval.html`, `/static/reports.html`,
   `/static/documents.html`) return HTTP 200.
4. Protected endpoints (`/approval/queue`, `/reports/trial-balance`,
   `/trade/customers`) return HTTP 401 without an auth token.
5. Balance.ge connector status is `demo_mode` unless the PR is explicitly 11C-L.
6. No raw credential is visible in any checked response.
7. No unexpected tracked file changes exist in local working tree.

---

## L) Stop Conditions

An 11C sub-task must stop and report to the user if any of the following occur:

| Stop Condition | Action |
|---|---|
| Files outside allowed set need changes | Stop. Report which files and why. Do not proceed. |
| Migration is required but not authorized by task spec | Stop. Report the migration need. Do not create migration. |
| Production DB access is needed | Stop. Report. Do not run SQL. |
| Production credentials are needed | Stop. Report. Do not add credentials. |
| Balance.ge live API call is needed | Stop. Report. Do not call Balance.ge. |
| Tests fail | Stop. Fix the failing tests. Do not commit failing tests. |
| Working tree has unexpected tracked changes | Stop. Report the unexpected files. Do not commit. |
| A required dependency task is not yet merged | Stop. Report the dependency. Wait for the prerequisite PR. |

---

## M) Commercial Pilot Blockers

The following must be resolved before any commercial pilot with live tenants:

| Blocker | Current State | Blocking Task |
|---|---|---|
| Credential vault missing | `api_key` stored as plaintext TEXT | 11C-C |
| Masked read runtime enforcement missing | Contract defined only | 11C-D |
| Subscription enforcement missing | Contract defined only | 11C-E |
| Redis/rate-limit runtime enforcement missing | Contract defined only | 11C-F |
| Evidence bundle missing | Column absent from `journal_drafts` | 11C-G |
| **Reports use `journal_drafts` not `journal_entries`** | **CRITICAL** — financial reports show draft data as ledger truth | **11C-H** |
| Runtime DDL gap | 30+ startup CREATE TABLE statements | 11C-I |
| Backup/PITR restore drill not verified | Plan defined only | 11C-J |
| Balance.ge GATE-07 (dry-run) NOT MET | No `dry_run` param in connector | 11C-K |
| Balance.ge 14 gates NOT MET | 0 of 14 gates MET | 11C-L |
| Accountant pilot sign-off not obtained | Not started | Pre-11C-L |

**The reports ledger integrity issue (`11C-H`) is the most impactful commercial
pilot blocker** because it means trial balance, P&L, and balance sheet currently
show draft amounts as if they were posted accounting truth. This must be fixed
before any external accountant or paying tenant reviews reports.

---

## N) Final Status

- This document completes Task 11C-A only.
- No runtime implementation has been started.
- No migrations have been created.
- No production database has been touched.
- No SQL has been executed.
- Balance.ge has not been activated.
- Task 11C-B has not been started.

**Next safe task: 11C-B — Credential Vault Runtime Architecture and Migration Plan.**

11C-B is docs/tests only and defines the exact migration schema and service
interface for the credential vault before any code is written. It is the
recommended next step.
