# Bridge Hub — Chat Continuation Checkpoint

> **Purpose:** This document lets a new chat continue Bridge Hub work from exactly the current state without losing context. Read every section before starting any task.

---

## 1. Project Identity

**Project:** Bridge Hub
**Stack:** FastAPI / Google Cloud Run / PostgreSQL (asyncpg + psycopg2) / GCS
**Role:** AI Chief Accountant / Financial Controller Layer

**Core principle:**
> AI prepares. Human approves. ERP posts. Audit proves.

Bridge Hub sits between raw financial data (bank transactions, OCR documents) and the ERP system (Balance.ge). It classifies transactions with AI, builds journal drafts, routes them through human approval, and posts them to the ERP connector only after approval — never autonomously.

**Repository:** `rgelikoshvili-stack/fastapi-run`
**Cloud Run service:** `fastapi-run` — `europe-west1`
**Live base URL:** `https://fastapi-run-226875230147.europe-west1.run.app`

---

## 2. Current Production / Live State

| Item | Value |
|---|---|
| Last fully live-verified milestone | 11C-H1 Reports Ledger Integrity Audit |
| Live SHA (H1 merge) | `2ea163905863472461fb215ddef63f40fe0f14f5` |
| H1 commit | `b12e684` |
| H1 branch | `codex/reports-ledger-integrity-audit` |
| H1 live verification | **CONFIRMED** (local SHA = live SHA, all endpoints verified) |
| Balance.ge | `demo_mode` — **NOT activated** |
| BALANCE_API_KEY | `missing` (intentional — not activated) |

> **Important:** The H1 live SHA `2ea163905863472461fb215ddef63f40fe0f14f5` is the merge commit for PR #37. It is live on Cloud Run as of verification on 2026-05-12.

---

## 3. Completed Milestones (in order)

| Task | Description |
|---|---|
| 10E-C | Credential / Security Contract |
| 10E-D | Accounting Truth Contract |
| 10E-E | Auth / Tenant Contract |
| 10E-F | Trust Foundation Implementation Plan |
| 10F-B | Credential Vault Design + Interface Contract |
| 10F-C | Masked Read Behavior Contract + Tests |
| 10F-D | Subscription / Trial Enforcement Contract + Tests |
| 10F-E | Redis / Rate-Limit Contract + Tests |
| 10F-F | Runtime DDL Cutover Contract + Tests |
| 10F-G | Backup / PITR / Static Files Contract + Tests |
| 10F-H | Balance.ge Final Activation Checklist + Tests |
| — | Autopilot multi-tenant hotfix |
| 11C-A | Trust Foundation Runtime Implementation Sequence |
| 11C-B | Credential Vault Runtime Architecture |
| 11C-C | Credential Vault Foundation C1–C4 |
| 11C-D | Masked Reads Runtime Enforcement |
| 11C-E | Subscription / Trial Enforcement |
| 11C-E4 | Subscription Middleware Registration |
| 11C-F | Redis / Rate-Limit Runtime Enforcement |
| 11C-G | Evidence Bundle Foundation |
| 11C-H1 | Reports Ledger Integrity Audit + Contract Tests |

---

## 4. Important Live-Verified SHAs

| Milestone | Live SHA |
|---|---|
| 11C-B | `31a6cbd1d59f1b5128ffa3334e3285596852fddd` |
| 11C-C | `c4a68fb` |
| 11C-D | `43d3dd9de0c1dad68d2049c968329f978ec331ef` |
| 11C-E4 | `1ea073b217cc3dacc4b77cdfccaffa3fb8186cf8` |
| 11C-F | `5257e6fab82f0c5730a882242d641c1fba6b1ce6` |
| 11C-G | `2108fcf2caec727b6b92f1b656009566e42ac449` |
| 11C-H1 merge | `2ea163905863472461fb215ddef63f40fe0f14f5` |
| 11C-H1 commit | `b12e684` |

---

## 5. Current Immediate Next Step

```
CURRENT NEXT STEP:

Task 11C-H1 live verification is COMPLETE (confirmed 2026-05-12).
Local main SHA = live /version SHA = 2ea163905863472461fb215ddef63f40fe0f14f5.

The next task to run is: Task 11C-H2.

Do NOT start 11C-H2 without reading section 7 (Current Blockers) and
the audit doc at docs/reports-ledger-integrity-audit.md first.
```

---

## 6. Cloud Codex Prompt — H1 Live Verification (reference, already completed)

> This prompt has already been run and returned all answers YES. Included here for audit trail.

```
Follow the Bridge Hub Master Operating Protocol.

Do not edit code.
Do not commit.
Do not run SQL against any database.
Do not touch production database.
Do not start 11C-H2.
Do not modify runtime report code.
Do not create migrations.
Do not execute migrations.
Do not activate Balance.ge.
Do not change credentials.
Do not change connector behavior.
Do not change production infrastructure.

Verify Task 11C-H1 live deployment only.

Context:
Task 11C-H1 PR was merged:
docs(reports): add ledger integrity audit and contract tests (11C-H1)

Expected branch:
codex/reports-ledger-integrity-audit

Expected included commit:
b12e684 — docs(reports): add ledger integrity audit and contract tests

Steps:
1. Run:
   git switch main
   git pull origin main
   git status --short --branch
   git log --oneline -15
   git rev-parse HEAD

2. Confirm main includes Task 11C-H1:
   - merge pull request for codex/reports-ledger-integrity-audit
   - or commit b12e684

3. Confirm these files exist on main:
   - docs/reports-ledger-integrity-audit.md
   - tests/unit/test_reports_ledger_integrity_contract.py

4. Call live /version:
   https://fastapi-run-226875230147.europe-west1.run.app/version

5. Compare:
   - local main HEAD
   - live /version.commit_sha

6. Confirm live /health:
   https://fastapi-run-226875230147.europe-west1.run.app/health

7. Confirm static pages still load:
   https://fastapi-run-226875230147.europe-west1.run.app/static/approval.html
   https://fastapi-run-226875230147.europe-west1.run.app/static/reports.html
   https://fastapi-run-226875230147.europe-west1.run.app/static/documents.html

8. Confirm protected endpoints reject unauthenticated requests:
   https://fastapi-run-226875230147.europe-west1.run.app/approval/queue
   https://fastapi-run-226875230147.europe-west1.run.app/reports/trial-balance
   https://fastapi-run-226875230147.europe-west1.run.app/trade/customers

Expected:
- local main HEAD equals live /version commit
- /health = 200
- static pages = 200
- protected endpoints without token = 401 or 403
- Balance.ge remains demo_mode / not activated
- credentials unchanged
- no migration executed
- production DB/infrastructure unchanged
- report runtime behavior unchanged
- approval/posting business logic unchanged

Final answer:
A) Latest local main commit
B) Does local main include Task 11C-H1 / commit b12e684? yes/no
C) Confirm expected H1 files exist on main
D) Live /version commit
E) Do local main and live /version match? yes/no
F) /health HTTP status
G) Static page statuses
H) Protected endpoint unauthorized statuses
I) Is Task 11C-H1 live verified? yes/no
J) Is it safe to start Task 11C-H2 planning/implementation? yes/no
K) Confirm 11C-H2 was not started
L) Confirm no migration was executed
M) Confirm production DB was not touched
N) Confirm Balance.ge was not activated
O) Confirm credentials were not changed
P) Confirm production infrastructure was not changed
Q) Confirm report runtime behavior was not changed
R) Confirm approval/posting business logic was not changed

Important:
- Do not edit files.
- Do not start 11C-H2 during this verification.
- Do not execute migration.
- Do not touch production DB.
- Do not activate Balance.ge.
- Do not change credentials.
```

---

## 7. Current Blockers

**Reports ledger integrity is the current commercial pilot blocker.**

H1 audit (`docs/reports-ledger-integrity-audit.md`) found:

### CRITICAL (3)

1. `/reports/bs/detail` — **no status filter** — returns ALL journal drafts regardless of posting status. Balance Sheet detail is corrupted by unposted drafts.
2. `/reports/pnl/detail` — treats `status IN ('posted', 'simulated_success')` as accounting truth. `simulated_success` is a test/simulation status, not a real posted state.
3. **No separate immutable `journal_entries` table exists.** All reports source from `journal_drafts.journal_entries` JSONB column. There is no append-only ledger table.

### HIGH (8)

Trial balance, P&L summary, Balance Sheet summary, VAT register, account ledger, counterparty ledger, payroll ledger, and journal entry list all source from `journal_drafts` JSONB — acceptable as interim, but must be resolved before commercial pilot.

### MEDIUM (1)

`/reports/cashflow` queries `bank_transactions` only with no journal linkage. Cash flow does not reconcile with the ledger.

### Required future behavior (from H1 audit)

- All official reports must source from **posted journal entries only**.
- Approved drafts are not accounting truth — they are pending.
- Draft previews must be explicitly labeled as non-official.
- Every official report must include tenant filter and period filter.
- Reversals and corrections must be handled.
- Evidence bundle link must be planned for each posted entry.

---

## 8. Rules for the New Chat

These rules must be followed for every task without exception:

1. **Never skip live verification after merge/deploy.** Every task ends with: branch → PR → merge → deploy → live verification → confirmed yes before starting the next task.

2. **Never start the next task until the previous task's live verification returns yes.**

3. **Never activate Balance.ge** unless an explicit final activation PR is created and all activation gates are MET. The activation checklist is at `docs/balance-ge-activation-final-checklist.md`.

4. **Never touch the production DB or run SQL** unless the task explicitly authorizes it — and even then, verify first with a read-only check.

5. **Keep tasks small, branch-based, tests-first, PR, deploy, live verification.** One branch per task. One commit per logical phase. Tests must pass before commit.

6. **For every task confirm on completion:**
   - No DB touched
   - No SQL executed
   - No credentials changed
   - No Balance.ge activation
   - No production infrastructure changed
   - No connector behavior changed

7. **Patch at usage site, not definition site.** When mocking in tests: `patch("app.api.services.approval_service.get_conn", ...)` not at the defining module.

8. **Standard response envelope always:**
   ```json
   { "ok": true, "message": "...", "data": {...}, "error": null }
   ```
   Use `ok_response()` / `error_response()` from `app/api/response_utils.py`.

9. **Tenant isolation always:** Every query against a tenant-scoped table must include `WHERE tenant_id = $N`. Never fall back silently to `"default"`.

10. **Immutable core — do not modify without discussion:**
    - `app/api/engines/pattern_engine.py`
    - `app/api/services/learning_service.py`
    - `app/api/services/pattern_decay_service.py`
    - `app/api/services/transaction_classifier.py`

---

## 9. Key Files Reference

| File | Purpose |
|---|---|
| `main.py` | App entry, middleware registration (LIFO order), lifespan hooks |
| `app/api/policy/permission_map.py` | PERMISSION_MAP + COMPILED_PERMISSION_MAP |
| `app/api/authz.py` | ROLE_PERMISSIONS dict |
| `app/api/services/financial_statements_service.py` | Trial balance, P&L, BS — all from journal_drafts JSONB |
| `app/api/services/ledger_service.py` | Account/counterparty/payroll ledger — all from journal_drafts |
| `app/api/routes_reports.py` | Report HTTP routes — contains CRITICAL bugs found in H1 |
| `app/api/services/evidence_bundle_service.py` | Evidence bundle lifecycle, safe response, _strip_unsafe |
| `app/api/services/evidence_bundle_repository.py` | Async data-access for evidence bundles |
| `app/storage/migrations/010_evidence_bundle_schema.sql` | Evidence bundle schema (created G1, not yet executed) |
| `docs/reports-ledger-integrity-audit.md` | H1 full audit — 14 findings, risk table, H2–H6 plan |
| `docs/accounting-truth-schema-contract.md` | Existing accounting truth contract |
| `docs/trust-foundation-runtime-implementation-sequence.md` | Full implementation roadmap |
| `docs/balance-ge-activation-final-checklist.md` | Balance.ge activation gates |

---

## 10. Middleware Execution Order (LIFO — outermost first)

```
tenant_middleware        ← outermost (runs first on request)
auth_middleware
rbac_middleware
subscription_middleware
rate_limit_middleware
audit_log_middleware
correlation_middleware   ← innermost (runs last on request)
```

Registration in `main.py` is in reverse order (last registered = outermost in Starlette LIFO).

---

*Generated: 2026-05-12. Local main HEAD at time of creation: `2ea163905863472461fb215ddef63f40fe0f14f5`.*
