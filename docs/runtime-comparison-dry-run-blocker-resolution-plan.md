# Bridge Hub — H35 Runtime Comparison Dry-Run Blocker Resolution Plan

## 1. Purpose

This document defines the blocker resolution plan that must be completed before any disposable/staging DB runtime comparison dry-run is permitted. It establishes current blockers, acceptable DB options, forbidden DB options, required evidence, the DB classification checklist, the future execution decision tree, the dry-run execution packet shape, future-only commands, no-go blockers, the readiness checklist table, H35 decision outputs, and recommended next-step logic.

**H35 is docs/tests only.**

- H35 does NOT create a DB.
- H35 does NOT connect to a DB.
- H35 does NOT execute SQL.
- H35 does NOT run migrations.
- H35 does NOT load fixtures into a DB.
- H35 does NOT call runtime report APIs.
- H35 does NOT modify runtime report behavior.
- H35 does NOT modify Cloud Run environment variables.
- H35 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.
- H35 does NOT activate Balance.ge.

All rules in this document describe future blocker resolution planning. They do not implement, execute, or mutate any system.

---

## 2. H34 Context

- **H34** defined the full future execution plan for a disposable/staging DB runtime comparison of `POSTED_LEDGER_REPORTS_ENABLED`. It defined environment and DB classification gates, prerequisites (PR1–PR12), future migration plan, future fixture load plan, future report capture plan (all 11 reports), future normalization/comparison plan, expected artifacts (A1–A13), cleanup/evidence retention plan, no-go blockers (B1–B16), the runtime comparison result packet (16-field JSON), and the execution checklist table (13 rows).
- **H34 did not execute anything.** It defined a future execution contract only.
- **H34 confirmed** that execution is allowed only if a suitable disposable/staging DB is available, classified, and approved.
- **Current status:** a suitable disposable/staging DB has not been confirmed available. No connection string has been provided. No owner approval for DB provisioning has been issued.
- **H35 therefore resolves blockers** instead of executing the dry-run. Once all blockers are resolved and the readiness checklist is satisfied, execution may proceed in a future task.

The production flag `POSTED_LEDGER_REPORTS_ENABLED` **remains OFF** throughout H35.

---

## 3. Current Blocker Statement

The following blockers currently prevent runtime comparison dry-run execution:

| # | Blocker | Current Status |
|---|---|---|
| CB1 | No confirmed disposable/staging PostgreSQL DB | Not confirmed |
| CB2 | No confirmed connection string for non-production DB | Not provided |
| CB3 | No DB owner approval issued | Not issued |
| CB4 | No non-production DB classification proof | Not produced |
| CB5 | No DB cleanup/retention decision recorded | Not decided |
| CB6 | No fixture load permission granted | Not granted |
| CB7 | No migration execution permission granted | Not granted |
| CB8 | No environment classification proof produced | Not produced |
| CB9 | No dry-run execution packet assembled | Not assembled |
| CB10 | No explicit go decision | No-go (by absence) |

Until all CB1–CB10 are resolved, dry-run execution must not begin.

---

## 4. Acceptable DB Options

Each acceptable DB option must satisfy all listed properties before execution is allowed.

### Option A — Disposable Local PostgreSQL

| Property | Required Value |
|---|---|
| Host | `localhost`, `127.0.0.1`, or `0.0.0.0` |
| DB name | Must include `disposable`, `dev`, `test`, or explicit non-production label |
| User/role | Non-production role; must not be a production service account |
| Non-production marker | Host is localhost or DB name contains non-production keyword |
| Cleanup policy | Drop after execution (recommended); artifacts retained |
| Owner approval | Engineering owner sign-off required before execution |
| Allowed migration scope | Migration 011 in non-production DB only |
| Allowed fixture scope | Synthetic fixture only; no production data |

### Option B — Docker PostgreSQL Container

| Property | Required Value |
|---|---|
| Host | `localhost` or container-internal hostname |
| DB name | Must include `disposable`, `docker`, `test`, or explicit non-production label |
| User/role | Non-production role; container-scoped |
| Non-production marker | Container isolation proof (Dockerfile or docker-compose evidence) |
| Cleanup policy | Container removed after execution; artifacts retained |
| Owner approval | Engineering owner sign-off required before execution |
| Allowed migration scope | Migration 011 in container DB only |
| Allowed fixture scope | Synthetic fixture only; no production data |

### Option C — Staging PostgreSQL (Dedicated Non-Production)

| Property | Required Value |
|---|---|
| Host | Must include `staging`, `sandbox`, or explicit non-production label |
| DB name | Must include `staging`, `sandbox`, or explicit non-production label |
| User/role | Staging service role; must not be a production service account |
| Non-production marker | Host contains staging/sandbox keyword |
| Cleanup policy | Staging data cleanup per staging owner decision; artifacts retained |
| Owner approval | Engineering owner AND staging owner sign-off required |
| Allowed migration scope | Migration 011 in staging DB only; staging owner must confirm |
| Allowed fixture scope | Synthetic fixture only; no production data |

### Option D — Sandbox Tenant DB (Within Non-Production Environment)

| Property | Required Value |
|---|---|
| Host | Non-production host with staging/sandbox keyword |
| DB name | Sandbox-scoped; must not share tenant scope with production |
| User/role | Sandbox tenant role; isolated scope |
| Non-production marker | Staging environment proof required |
| Cleanup policy | Sandbox data removed after execution; artifacts retained |
| Owner approval | Engineering owner AND staging owner sign-off required |
| Allowed migration scope | Migration 011 in sandbox DB only; staging proof required |
| Allowed fixture scope | Synthetic fixture only; tenant-scoped; no production data |

---

## 5. Forbidden DB Options

The following DB options are forbidden for dry-run execution under any circumstances:

| # | Forbidden Option | Reason |
|---|---|---|
| FDB1 | Production DB | Real customer data; H31 gate process required before any production switch |
| FDB2 | Cloud Run production DB (Cloud SQL production instance) | Production environment; no env mutation allowed in H35 |
| FDB3 | Unknown DB (cannot be positively classified) | Unknown DB fails closed; no execution permitted |
| FDB4 | Customer DB (any DB containing real customer data) | Privacy/compliance; forbidden regardless of environment label |
| FDB5 | Balance.ge live DB | ERP live system; no live posting allowed |
| FDB6 | Any DB with production-like DATABASE_URL | URL contains production markers: `production`, `prod-`, `-prod`, `cloudsql`, `rgelikoshvili`, `europe-west1.run.app`, `sql.goog` |
| FDB7 | Any DB without explicit owner approval | No unilateral DB selection; owner sign-off mandatory |
| FDB8 | Any DB containing real customer data | Cannot be decontaminated by label; must be rejected |
| FDB9 | Any DB where cleanup policy is unclear | Unclear cleanup is a CRITICAL blocker |

If the DATABASE_URL for any proposed DB cannot be positively confirmed as non-production, the option must be treated as forbidden and execution blocked.

---

## 6. Required Evidence To Unblock

All of the following evidence items must be produced and recorded before execution is allowed:

| # | Evidence Item | Format | Status |
|---|---|---|---|
| EV1 | Environment classification proof | String: `disposable_local`, `staging`, `sandbox_tenant`, `docker_container` | Not produced |
| EV2 | DB classification proof | DB URL prefix, host label, or explicit non-production marker | Not produced |
| EV3 | Connection string proof (redacted) | Redacted DATABASE_URL showing host/dbname only; no password in evidence record | Not produced |
| EV4 | Owner approval | Engineering owner sign-off record ID or timestamp | Not produced |
| EV5 | Cleanup plan | Explicit cleanup policy: `drop_after`, `preserve_staging`, `container_remove` | Not produced |
| EV6 | Fixture hash/version | SHA-256 hash of `synthetic_posted_ledger_fixture_pack.json` | Not produced |
| EV7 | Migration file reviewed | Migration 011 file path and SHA-256 hash confirmed | Not produced |
| EV8 | Rollback/disable reference | `docs/rollback-monitoring-post-switch-safety-contract.md` confirmed present | Present |
| EV9 | No production data proof | Fixture source confirmation; no real tenant data in simulation DB | Not produced |
| EV10 | Balance.ge demo/unconfigured proof | `/health` connector state confirms `balance: demo_mode` | Present (confirmed via /health) |
| EV11 | Feature flag state proof | `POSTED_LEDGER_REPORTS_ENABLED` confirmed absent/OFF in all environments | Present (confirmed absent) |
| EV12 | Execution command dry-run preview | Full command set reviewed and approved before execution | Not produced |
| EV13 | No-go blocker checklist completed | All blockers in Section 12 evaluated and signed off | Not produced |

EV8, EV10, EV11 are currently satisfied. EV1–EV7, EV9, EV12–EV13 remain open blockers.

---

## 7. DB Classification Checklist

Before any DB is accepted for dry-run execution, the following checklist must be completed:

| # | Check | Pass Criteria | Status |
|---|---|---|---|
| DC1 | Host is local or staging | Host is `localhost`, `127.0.0.1`, `0.0.0.0`, or contains `staging`/`sandbox` | Not checked |
| DC2 | DB name includes non-production marker | DB name contains `disposable`, `staging`, `sandbox`, `test`, or `docker` | Not checked |
| DC3 | User role is non-production | Role is not a production service account; not a Cloud SQL production role | Not checked |
| DC4 | No production hostname in DATABASE_URL | URL does not contain: `production`, `prod-`, `-prod`, `cloudsql`, `rgelikoshvili`, `europe-west1.run.app`, `sql.goog` | Not checked |
| DC5 | No Cloud Run production URL | DATABASE_URL does not contain Cloud Run production project identifiers | Not checked |
| DC6 | No production secrets in connection string | Password/secret is non-production; not reused from production | Not checked |
| DC7 | No customer data present | Confirmed by fixture hash and source; no real tenant data | Not checked |
| DC8 | Cleanup strategy is clear | One of: `drop_after`, `preserve_staging`, `container_remove` — owner approved | Not checked |
| DC9 | Owner approval present | Engineering owner sign-off recorded before DB is used | Not checked |

All DC1–DC9 must pass before the DB is accepted. Any failure blocks execution.

---

## 8. Future Execution Decision Tree

The following decision tree determines the next action based on DB availability. No branch of this tree is executed in H35.

```
[FUTURE DECISION — NOT EXECUTED IN H35]

START
  │
  ├─ Is a disposable local PostgreSQL available?
  │     ├─ YES → Collect evidence EV1–EV13 → Assemble dry-run execution packet
  │     │         → Execute DC1–DC9 checklist → If all pass → READY_FOR_DRY_RUN_EXECUTION
  │     │         → If any fail → BLOCKED
  │     │
  │     └─ NO → Continue to next option
  │
  ├─ Is a Docker PostgreSQL container available?
  │     ├─ YES → Collect container isolation proof → Collect evidence EV1–EV13
  │     │         → Execute DC1–DC9 checklist → If all pass → READY_FOR_DRY_RUN_EXECUTION
  │     │         → If any fail → BLOCKED
  │     │
  │     └─ NO → Continue to next option
  │
  ├─ Is a staging DB available with staging owner approval?
  │     ├─ YES → Collect staging proof → Collect evidence EV1–EV13 (EV4 = Engineering + Staging owner)
  │     │         → Execute DC1–DC9 checklist → If all pass → READY_FOR_DRY_RUN_EXECUTION
  │     │         → If any fail → BLOCKED
  │     │
  │     └─ NO → Continue to next option
  │
  ├─ Is only a production DB available?
  │     └─ YES → BLOCKED_PRODUCTION_RISK — stop and investigate
  │
  ├─ DB classification unknown?
  │     └─ YES → BLOCKED_UNKNOWN_DB — fail closed
  │
  └─ No DB available at all?
        └─ YES → BLOCKED_NO_DB → Next task: Disposable DB Provisioning Plan

END
```

---

## 9. Future Dry-Run Execution Packet

Every dry-run execution request must produce a packet conforming to this schema before execution begins. This packet is NOT assembled in H35.

```json
{
  "execution_request_id": "string — unique ID, e.g. DRY-RUN-2026-001",
  "requested_by": "string — engineering owner name or ID",
  "environment": "disposable_local | docker_container | staging | sandbox_tenant",
  "db_classification": "disposable_local_db | docker_db | staging_db | sandbox_db",
  "db_proof_reference": "string — reference to EV2/EV3 evidence artifact",
  "fixture_version": "string — SHA-256 hash of synthetic_posted_ledger_fixture_pack.json",
  "migration_version": "string — migration 011 file path and hash",
  "owner_approval": "string — sign-off record ID or timestamp",
  "cleanup_plan": "drop_after | preserve_staging | container_remove",
  "feature_flag_plan": "string — description of flag ON/OFF sequence; production never touched",
  "rollback_reference": "docs/rollback-monitoring-post-switch-safety-contract.md",
  "no_go_blockers_checked": true,
  "go_decision": "go | no_go",
  "created_at": "ISO 8601 UTC timestamp"
}
```

### Required Fields

All 14 fields are required. A dry-run execution packet missing any field is incomplete and must not be used to authorize execution.

### go_decision Rules

| Condition | go_decision |
|---|---|
| All evidence EV1–EV13 present and all DC1–DC9 pass | `go` |
| Any CB blocker unresolved | `no_go` |
| Any no-go blocker in Section 12 triggered | `no_go` |
| DB classification unknown or production | `no_go` |
| Owner approval missing | `no_go` |

---

## 10. Commands Allowed Only In Future Execution Task

The following command categories describe actions that may only be performed in a future execution task (H36 or later), never in H35.

**Every command listed here is NOT EXECUTED in H35.**

```
[FUTURE — NOT EXECUTED IN H35]

Category 1: Create disposable DB
  - createdb -U <nonprod_user> <disposable_db_name>
  - OR: docker run --rm -e POSTGRES_DB=<name> -e POSTGRES_USER=<user> -p 5432:5432 postgres:15

Category 2: Run migration 011
  - psql $NON_PRODUCTION_DATABASE_URL -f app/storage/migrations/011_*.sql
  - Verify: psql $NON_PRODUCTION_DATABASE_URL -c "\dt" | grep posted_ledger_entries

Category 3: Inspect schema
  - psql $NON_PRODUCTION_DATABASE_URL -c "\d posted_ledger_entries"
  - psql $NON_PRODUCTION_DATABASE_URL -c "SELECT COUNT(*) FROM posted_ledger_entries;"

Category 4: Load fixture
  - python tests/fixtures/posted_ledger/load_fixture.py --db $NON_PRODUCTION_DATABASE_URL
  - Verify fixture hash before load

Category 5: Run report capture
  - Set POSTED_LEDGER_REPORTS_ENABLED=OFF; capture all 11 reports
  - Set POSTED_LEDGER_REPORTS_ENABLED=ON; capture all 11 reports
  - Reset POSTED_LEDGER_REPORTS_ENABLED=OFF immediately after capture

Category 6: Run comparison
  - python -m pytest tests/unit/test_synthetic_snapshot_normalizer_contract.py
  - python -m pytest tests/unit/test_synthetic_snapshot_comparator_contract.py

Category 7: Generate accountant review
  - Assemble H30 accountant review report from comparison results
  - Record gate_outcome and promotion_recommendation

Category 8: Cleanup / drop disposable DB
  - dropdb -U <nonprod_user> <disposable_db_name>
  - OR: docker stop <container_name>
  - Verify: POSTED_LEDGER_REPORTS_ENABLED reset to OFF
  - Retain all artifacts A1–A13
```

---

## 11. No-Go Blockers

Any of the following blocks dry-run execution from proceeding:

| # | Blocker | Severity |
|---|---|---|
| NGB1 | Production DB indicator in DATABASE_URL | CRITICAL |
| NGB2 | Unknown DB classification | CRITICAL |
| NGB3 | No owner approval for execution | HIGH |
| NGB4 | No cleanup plan recorded | HIGH |
| NGB5 | No fixture hash recorded | HIGH |
| NGB6 | No migration 011 file reviewed | HIGH |
| NGB7 | No rollback reference | HIGH |
| NGB8 | Balance.ge live connector active (`balance != demo_mode`) | CRITICAL |
| NGB9 | Production data detected in execution DB | CRITICAL |
| NGB10 | Feature flag `POSTED_LEDGER_REPORTS_ENABLED` enabled in production | CRITICAL |
| NGB11 | Cloud Run env mutation required (not allowed) | CRITICAL |
| NGB12 | Protected endpoint auth bypass detected | CRITICAL |
| NGB13 | Missing accountant review plan (H30 contract absent) | HIGH |
| NGB14 | Missing evidence retention plan (H34 artifacts plan absent) | HIGH |

---

## 12. Readiness Checklist Table

| Requirement | Evidence Required | Owner | Status | Blocking if Missing | Notes |
|---|---|---|---|---|---|
| Environment proof | `disposable_local`, `staging`, `docker_container`, or `sandbox_tenant` classification string | Engineering | Not ready | Yes — CRITICAL | Must be positive classification |
| DB proof | DB URL prefix or host label confirming non-production | Engineering | Not ready | Yes — CRITICAL | Any production marker fails closed |
| Owner approval | Engineering owner sign-off (record ID or timestamp) | Engineering owner | Not ready | Yes — HIGH | Required before any execution step |
| Cleanup policy | One of: `drop_after`, `preserve_staging`, `container_remove` | Engineering owner | Not ready | Yes — HIGH | Must be decided before execution |
| Migration review | Migration 011 file path + SHA-256 hash confirmed | Engineering | Not ready | Yes — HIGH | File exists in repo; review before run |
| Fixture hash | SHA-256 hash of `synthetic_posted_ledger_fixture_pack.json` | Engineering | Not ready | Yes — HIGH | Must be recorded before load |
| No production data proof | Fixture source confirmation + DB classification check | Engineering | Not ready | Yes — CRITICAL | Any real data = CRITICAL blocker |
| Feature flag plan | `POSTED_LEDGER_REPORTS_ENABLED` ON/OFF sequence defined; production never touched | Engineering | Partial | Yes — CRITICAL | Flag plan template available in H34 |
| Rollback reference | `docs/rollback-monitoring-post-switch-safety-contract.md` confirmed present | Engineering | Ready | No | Document confirmed present |
| Dry-run packet | All 14 fields of the execution packet assembled and `go_decision: go` | Engineering owner | Not ready | Yes — HIGH | Cannot execute without complete packet |
| No-go blockers checked | All NGB1–NGB14 evaluated and signed off | Engineering owner | Not ready | Yes — CRITICAL | Must be done immediately before execution |

---

## 13. H35 Decision Output

Based on current blocker status, H35 produces one of the following decision outputs:

| Decision Output | Meaning | Condition |
|---|---|---|
| `READY_FOR_DRY_RUN_EXECUTION` | All blockers resolved; execution may proceed | All EV1–EV13 present, all DC1–DC9 pass, all NGB1–NGB14 clear, go_decision = go |
| `BLOCKED_NO_DB` | No suitable DB confirmed available | CB1 unresolved; no disposable/staging/docker DB available |
| `BLOCKED_UNKNOWN_DB` | DB present but cannot be classified as non-production | DB URL does not match any allowed pattern |
| `BLOCKED_PRODUCTION_RISK` | Production DB indicator detected | DATABASE_URL contains production marker |
| `BLOCKED_NO_OWNER_APPROVAL` | DB or execution not approved by owner | EV4/CB3 unresolved |
| `BLOCKED_NO_CLEANUP_PLAN` | Cleanup policy not decided | EV5/CB5 unresolved |
| `BLOCKED_NO_FIXTURE_HASH` | Fixture hash not recorded | EV6 unresolved |
| `BLOCKED_NO_MIGRATION_REVIEW` | Migration 011 not reviewed | EV7 unresolved |

**Current H35 decision: `BLOCKED_NO_DB`**

Reason: CB1 unresolved — no disposable/staging PostgreSQL DB has been confirmed available.

---

## 14. Recommended Next-Step Logic

| Decision Output | Recommended Next Task |
|---|---|
| `READY_FOR_DRY_RUN_EXECUTION` | H36 — Disposable/Staging DB Runtime Comparison Dry-Run Execution |
| `BLOCKED_NO_DB` | H36 — Disposable/Staging DB Provisioning Plan |
| `BLOCKED_UNKNOWN_DB` | Investigate DB source; re-classify before proceeding |
| `BLOCKED_PRODUCTION_RISK` | Stop immediately; investigate production risk; do not proceed |
| `BLOCKED_NO_OWNER_APPROVAL` | H36 — Owner Approval Packet Assembly |
| `BLOCKED_NO_CLEANUP_PLAN` | H36 — Cleanup Policy Decision Plan |
| `BLOCKED_NO_FIXTURE_HASH` | Record fixture hash from existing fixture file; re-evaluate |
| `BLOCKED_NO_MIGRATION_REVIEW` | Review migration 011 file; record hash; re-evaluate |

**Current recommendation: H36 — Disposable/Staging DB Provisioning Plan**

Because no suitable DB has been confirmed, the next task after H35 is live verified must focus on provisioning or confirming a suitable disposable/staging PostgreSQL DB.

---

## 15. Safety Rules

These rules are non-negotiable for H35:

- H35 creates no DB.
- H35 runs no SQL.
- H35 runs no migration.
- H35 loads no fixture data into any DB.
- H35 runs no runtime API calls.
- H35 enables no feature flags.
- H35 mutates no Cloud Run environment variables.
- H35 activates no Balance.ge connector.
- H35 makes no connector changes.
- H35 uses no production data.
- H35 uses no real credentials.
- H35 makes no infrastructure changes.
- H35 makes no UI/static file changes.
- H35 does not modify any runtime code in `app/`.
- H35 does not modify any migration file in `app/storage/migrations/`.
- H35 does not modify `main.py`.
- H35 does not modify fixture JSON files.

---

## 16. H35 Results

_Placeholder — filled after tests pass:_

- H35 targeted tests: 30/30 passed
- H34 + H35 combined: 60/60 passed
- Related report/fixture tests: see test run output
- Full unit suite: see test run output
- Fixture JSON changed: no
- Blocker resolution plan green: yes
- Final decision recommendation: BLOCKED_NO_DB → H36 Disposable/Staging DB Provisioning Plan

---

## 17. Non-Goals

H35 explicitly does NOT:

- Create or connect to any DB.
- Execute SQL.
- Run database migrations.
- Load fixture data into any DB.
- Call runtime report APIs.
- Implement runtime execution logic.
- Enable `POSTED_LEDGER_REPORTS_ENABLED` in any environment.
- Mutate Cloud Run service environment variables.
- Use production or customer data.
- Connect to Balance.ge or any ERP connector.
- Activate Balance.ge.
- Implement UI or static file changes.
- Perform a production switch.

---

## 18. Next Task

Only after PR merge, deploy, and live verification of H35:

**If a suitable disposable/staging DB is confirmed available:**

H36 — Disposable/Staging DB Runtime Comparison Dry-Run Execution

**If no suitable DB is available (current status):**

H36 — Disposable/Staging DB Provisioning Plan

H36 must not be started before H35 is live verified.
