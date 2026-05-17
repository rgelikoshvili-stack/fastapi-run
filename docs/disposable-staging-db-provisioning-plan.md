# Bridge Hub — H36 Disposable/Staging DB Provisioning Plan

## 1. Purpose

This document defines the provisioning plan for a safe disposable/staging PostgreSQL database that can later be used for the runtime comparison dry-run execution. It establishes the recommended provisioning path, acceptable and forbidden provisioning options, DB naming and marker rules, redacted connection string requirements, owner approval contract, cleanup and retention policy, future-only command templates, the provisioning evidence packet shape, the H37 readiness gate, no-go blockers, decision outputs, and a provisioning checklist table.

**H36 is docs/tests only.**

- H36 does NOT create a DB.
- H36 does NOT connect to a DB.
- H36 does NOT execute SQL.
- H36 does NOT run migrations.
- H36 does NOT load fixtures into a DB.
- H36 does NOT call runtime report APIs.
- H36 does NOT modify runtime report behavior.
- H36 does NOT modify Cloud Run environment variables.
- H36 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.
- H36 does NOT activate Balance.ge.
- H36 does NOT start dry-run execution.

All rules in this document describe future provisioning planning only. Nothing is provisioned, executed, or mutated in H36.

---

## 2. H35 Context

- **H35** defined the blocker resolution plan for enabling a future disposable/staging DB runtime comparison dry-run.
- **H35 live verified the decision: `BLOCKED_NO_DB`** — no suitable disposable/staging PostgreSQL DB was confirmed available.
- **H35 confirmed:** no DB connection, no owner approval for DB provisioning, no dry-run execution packet assembled, CB1–CB10 all unresolved (except EV8/EV10/EV11 satisfied).
- **H35 recommendation:** next task = H36 — Disposable/Staging DB Provisioning Plan.
- **H36 therefore plans provisioning only.** No DB is provisioned, connected, or used in H36.

The production flag `POSTED_LEDGER_REPORTS_ENABLED` **remains OFF** throughout H36.

---

## 3. Provisioning Non-Action Statement

H36 does NOT provision a real database.

- H36 does NOT run Docker.
- H36 does NOT run `createdb`.
- H36 does NOT run `psql`.
- H36 does NOT connect to PostgreSQL.
- H36 does NOT create users or roles.
- H36 does NOT set `DATABASE_URL`.
- H36 does NOT mutate `.env` or Cloud Run.
- H36 does NOT start H37.

All provisioning commands documented in this file are marked `[FUTURE — NOT EXECUTED IN H36]` and describe only what a future execution task may do after owner approval and evidence collection.

---

## 4. Recommended Provisioning Path

The following options are ordered by safety and isolation. Option A is recommended first.

| Rank | Option | Reason |
|---|---|---|
| 1 | Docker PostgreSQL disposable container | Safest: fully isolated, ephemeral, no production network, easy cleanup |
| 2 | Local installed PostgreSQL disposable DB | Acceptable: clearly local, disposable, no network exposure |
| 3 | Dedicated staging PostgreSQL DB | Requires owner approval and stronger cleanup rules; not a first dry-run |
| 4 | Sandbox tenant DB after staging proof | Later-stage option only; requires staging DB proof first |

**Recommendation: Option A — Docker PostgreSQL disposable container** is the preferred first provisioning path because:
- It is isolated from the production network by default.
- It is ephemeral: the container and volume are removed after use.
- No persistent local PostgreSQL installation is required.
- The DB is created and destroyed within a single execution session.
- It leaves no residual database state after cleanup.

---

## 5. Acceptable Provisioning Options

### Option A — Docker PostgreSQL Disposable Container

| Property | Value |
|---|---|
| Description | A PostgreSQL container started via Docker for a single dry-run session |
| Allowed scope | Local development machine only; not production network |
| Required evidence | Docker container isolation proof; container name/image; non-production DB name |
| Cleanup policy | Container and volume removed after evidence captured (`docker stop` + `docker rm`) |
| Owner approval | Engineering owner sign-off before starting |
| Limitations | Requires Docker installed locally; port must not conflict with production services |
| When to use | First dry-run; no persistent local PostgreSQL needed |

### Option B — Local Installed PostgreSQL Disposable DB

| Property | Value |
|---|---|
| Description | A PostgreSQL database created on the local machine's installed PostgreSQL instance |
| Allowed scope | Local machine only; `localhost` connection; `DATABASE_URL` never committed |
| Required evidence | Host proof (`localhost` or `127.0.0.1`); DB name includes `disposable`/`bridgehub_disposable` |
| Cleanup policy | `dropdb` after evidence captured; DB name includes `disposable` marker |
| Owner approval | Engineering owner sign-off before creating |
| Limitations | Local PostgreSQL must be installed; must ensure no name collision with any production DB |
| When to use | If Docker is unavailable; local PostgreSQL already installed |

### Option C — Dedicated Staging PostgreSQL DB

| Property | Value |
|---|---|
| Description | A dedicated non-production PostgreSQL instance on a staging server |
| Allowed scope | Staging environment only; host must include `staging` or `sandbox` keyword |
| Required evidence | Staging environment proof; host classification; staging owner sign-off |
| Cleanup policy | Staging DB cleanup per staging owner decision; artifacts retained regardless |
| Owner approval | Engineering owner AND staging environment owner |
| Limitations | Requires staging infrastructure; higher coordination; not recommended for first dry-run |
| When to use | If local DB options are unavailable; staging infrastructure confirmed available |

### Option D — Sandbox Tenant DB After Staging Proof

| Property | Value |
|---|---|
| Description | An isolated tenant scope within a staging environment DB |
| Allowed scope | Non-production DB with confirmed staging proof; isolated tenant only |
| Required evidence | Staging environment proof; tenant isolation proof; no cross-tenant leakage |
| Cleanup policy | Sandbox tenant data removed after execution; artifacts retained |
| Owner approval | Engineering owner AND staging owner |
| Limitations | Requires Option C staging DB to be confirmed first |
| When to use | Only after Option C staging DB is fully confirmed and documented |

---

## 6. Forbidden Provisioning Options

The following DB options are forbidden under any circumstances in H36 and in any future provisioning:

| # | Forbidden Option | Reason |
|---|---|---|
| FP1 | Production DB | Real customer data; H31 gate process required before any production touch |
| FP2 | Cloud Run production DB | Production environment; Cloud SQL production instance forbidden |
| FP3 | Any DATABASE_URL with production markers | URL contains: `production`, `prod-`, `-prod`, `cloudsql`, `rgelikoshvili`, `europe-west1.run.app`, `sql.goog` |
| FP4 | Unknown DB | Cannot classify as non-production; fails closed |
| FP5 | Customer DB (contains real customer data) | Privacy/compliance; forbidden regardless of environment label |
| FP6 | Balance.ge live DB | ERP live system; no live posting allowed |
| FP7 | Shared DB without cleanup isolation | Cannot guarantee non-production isolation after use |
| FP8 | DB with real customer data | Cannot be decontaminated by label; must be rejected at detection |
| FP9 | DB without owner approval | No unilateral DB provisioning; owner sign-off mandatory |
| FP10 | DB with unclear retention policy | Unclear cleanup is a CRITICAL blocker |
| FP11 | DB requiring Cloud Run env mutation | No Cloud Run mutation allowed in provisioning task |

---

## 7. DB Naming and Marker Rules

All provisioned DBs for dry-run must follow these naming rules:

| # | Rule | Required Value |
|---|---|---|
| NR1 | Database name marker | Must include `bridgehub_disposable` or `bridgehub_staging` |
| NR2 | Username/role marker | Must include `nonprod`, `staging`, or `disposable` marker where possible |
| NR3 | Schema marker table | May only be created in a future execution task; never in H36 |
| NR4 | Connection string proof | Must be redacted before recording in docs or evidence |
| NR5 | No production hostnames | DATABASE_URL host must not contain production identifiers |
| NR6 | No production secrets | Password/secret must not be a production credential |
| NR7 | Port | Default `5432`; must not overlap with production services |

### Acceptable DB Names (examples, non-exhaustive)

- `bridgehub_disposable_h37`
- `bridgehub_disposable_dryrun`
- `bridgehub_staging_h37`
- `bridgehub_nonprod_dryrun`

### Forbidden DB Names (patterns that block provisioning)

- Any name that does not contain `disposable`, `staging`, `nonprod`, or `test`
- Any name matching a production DB name pattern
- Names containing tenant IDs from production

---

## 8. Redacted Connection String Proof

The redacted connection string proof must be recorded in the provisioning evidence packet and must follow this format:

```
postgresql://bridgehub_nonprod_user:***@<host>:<port>/<db_name>
```

### Rules

| # | Rule |
|---|---|
| RP1 | Host is shown only if local (`localhost`, `127.0.0.1`) or staging (`staging.*`) |
| RP2 | Password is always redacted — replaced with `***` |
| RP3 | Username is shown only if non-sensitive (non-production role); otherwise redacted |
| RP4 | DB name is visible — must include non-production marker |
| RP5 | Port is visible |
| RP6 | SSL mode noted if applicable |
| RP7 | Production-like hostnames are forbidden — any match blocks the proof |
| RP8 | Raw credentials must never be committed to the repository |

### Acceptable examples

```
postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37
postgresql://nonprod_role:***@127.0.0.1:5432/bridgehub_staging_dryrun
```

### Forbidden examples

```
postgresql://admin:realpassword@production.db.example.com:5432/bridge
postgresql://user:pw@rgelikoshvili-db:5432/bridge
postgresql://user:pw@sql.goog:5432/bridge
```

---

## 9. Owner Approval Contract

Before any DB provisioning can begin, the following approvals must be obtained and recorded:

| Approver | Required For | Scope |
|---|---|---|
| Engineering owner | All options | DB provisioning, migration execution, fixture load, cleanup |
| DB/provisioning owner | All options | DB name, user/role, cleanup policy, retention |
| Accounting/product owner | Option C or D (staging) | Staging data scope, tenant isolation, accountant review plan |
| Rollback/cleanup owner | All options | Cleanup policy execution, evidence retention decision |

### Approval Record Shape

Each approval must record:

```json
{
  "owner_id": "placeholder — filled at approval time",
  "owner_role": "engineering_owner | db_owner | accounting_owner | cleanup_owner",
  "scope": "disposable_local | staging | sandbox_tenant",
  "db_classification": "disposable_local_db | docker_db | staging_db",
  "allowed_operations": ["create_db", "run_migration_011", "load_fixture", "capture_reports", "drop_db"],
  "cleanup_policy": "drop_after | preserve_staging | container_remove",
  "approval_timestamp": "ISO 8601 UTC — filled at approval time",
  "approval_expires": "ISO 8601 UTC — max 7 days after approval"
}
```

Approvals expire after 7 days. An expired approval requires re-approval before execution.

---

## 10. Cleanup and Retention Policy

| Scenario | Policy |
|---|---|
| Docker disposable container | Drop container and volume after all evidence artifacts (A1–A13) captured; no persistent state |
| Local disposable DB | `dropdb` after all evidence captured; DB name includes `disposable` marker |
| Staging DB | Preserve only with staging owner approval and a documented cleanup schedule |
| Evidence artifacts | Retained in local evidence folder or repo artifact; no secrets in retained artifacts |
| Fixture data | Synthetic only; removed with DB drop; fixture JSON in repo is unchanged |
| Production cleanup | Not applicable — production was not changed in H36 or any preceding task |

### Rules

1. No DB is dropped before all evidence artifacts (A1–A13 per H34 plan) are captured and verified.
2. Cleanup is always performed and verified before closing the execution session.
3. Feature flag is reset to OFF and verified before DB cleanup.
4. All retained artifacts must be free of production secrets and real customer data.
5. Production cleanup is never required because production was not changed.
6. If a Docker container fails to stop cleanly, the container ID is recorded and manual cleanup is performed before the session is closed.

---

## 11. Future Provisioning Command Templates

**[FUTURE — NOT EXECUTED IN H36]**

All commands below describe what a future execution task may run after owner approval. They are documentation only and forbidden in H36.

```
[FUTURE] Option A — Docker PostgreSQL Disposable Container

  Step A1: Start disposable container (NOT EXECUTED IN H36)
    docker run --rm --name bridgehub_disposable_h37 \
      -e POSTGRES_DB=bridgehub_disposable_h37 \
      -e POSTGRES_USER=bridgehub_nonprod_user \
      -e POSTGRES_PASSWORD=<nonprod_password_not_committed> \
      -p 5432:5432 \
      -d postgres:15

  Step A2: Verify container is running (NOT EXECUTED IN H36)
    docker ps | grep bridgehub_disposable_h37

  Step A3: Verify PostgreSQL is ready (NOT EXECUTED IN H36)
    docker exec bridgehub_disposable_h37 pg_isready -U bridgehub_nonprod_user

  Step A4: Set local DATABASE_URL (NOT EXECUTED IN H36 — local shell only, never committed)
    export DATABASE_URL="postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37"

  Step A5: Run migration 011 (NOT EXECUTED IN H36 — future execution task only)
    psql $DATABASE_URL -f app/storage/migrations/011_*.sql

  Step A6: Load synthetic fixture (NOT EXECUTED IN H36 — future execution task only)
    python tests/fixtures/posted_ledger/load_fixture.py --db $DATABASE_URL

  Step A7: Capture reports and run comparison (NOT EXECUTED IN H36 — future execution task only)
    [see H34 report capture plan]

  Step A8: Stop and remove container after evidence captured (NOT EXECUTED IN H36)
    docker stop bridgehub_disposable_h37
    docker rm bridgehub_disposable_h37

[FUTURE] Option B — Local Installed PostgreSQL

  Step B1: Create disposable DB (NOT EXECUTED IN H36)
    createdb -U postgres bridgehub_disposable_h37

  Step B2: Verify PostgreSQL is ready (NOT EXECUTED IN H36)
    pg_isready -h localhost -p 5432

  Step B3: Set local DATABASE_URL (NOT EXECUTED IN H36 — local shell only, never committed)
    export DATABASE_URL="postgresql://postgres:***@localhost:5432/bridgehub_disposable_h37"

  Step B4: Run migration 011 (NOT EXECUTED IN H36 — future execution task only)
    psql $DATABASE_URL -f app/storage/migrations/011_*.sql

  Step B5: Drop DB after evidence captured (NOT EXECUTED IN H36)
    dropdb -U postgres bridgehub_disposable_h37
```

---

## 12. Provisioning Evidence Packet

Every provisioning must produce an evidence packet before execution is allowed. This packet is NOT produced in H36.

```json
{
  "provisioning_id": "string — unique ID, e.g. PROV-2026-001",
  "environment": "disposable_local | docker_container | staging | sandbox_tenant",
  "db_option": "docker_disposable | local_disposable | staging | sandbox_tenant",
  "db_classification": "disposable_local_db | docker_db | staging_db | sandbox_db",
  "db_name": "string — must include bridgehub_disposable or bridgehub_staging marker",
  "host_classification": "localhost | 127.0.0.1 | staging_host",
  "owner_approval_id": "string — approval record ID or timestamp",
  "cleanup_policy": "drop_after | preserve_staging | container_remove",
  "retention_policy": "string — artifacts retained; no secrets; synthetic data only",
  "redacted_connection_proof": "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37",
  "allowed_operations": ["create_db", "run_migration_011", "load_fixture", "capture_reports", "drop_db"],
  "forbidden_operations": ["write_production_data", "enable_flag_in_production", "mutate_cloud_run"],
  "ready_for_h37": false,
  "created_at": "ISO 8601 UTC timestamp",
  "created_by": "Bridge Hub"
}
```

### Required Fields

All 15 fields are required. A provisioning evidence packet missing any field is incomplete and cannot authorize H37 execution.

### `ready_for_h37` Rules

| Condition | `ready_for_h37` |
|---|---|
| All required evidence produced; all approvals obtained; cleanup policy defined | `true` |
| Any field missing or any no-go blocker triggered | `false` |
| DB classification unknown or production | `false` |
| Owner approval absent or expired | `false` |

---

## 13. H37 Readiness Gate

H37 (dry-run execution) may only start if ALL of the following are confirmed:

| # | Gate | Required |
|---|---|---|
| G1 | Provisioning evidence packet complete (all 15 fields) | Yes — CRITICAL |
| G2 | DB classification confirmed non-production | Yes — CRITICAL |
| G3 | Owner approval present and not expired | Yes — HIGH |
| G4 | Cleanup policy defined and owner-approved | Yes — HIGH |
| G5 | Fixture hash/version recorded | Yes — HIGH |
| G6 | Migration 011 reviewed and hash confirmed | Yes — HIGH |
| G7 | No production data proof | Yes — CRITICAL |
| G8 | Balance.ge in demo/unconfigured mode | Yes — CRITICAL |
| G9 | Feature flag plan documented (ON/OFF sequence; production never touched) | Yes — CRITICAL |
| G10 | Rollback reference confirmed (`docs/rollback-monitoring-post-switch-safety-contract.md`) | Yes — HIGH |
| G11 | Dry-run execution packet drafted (from H34 plan) | Yes — HIGH |

If any gate fails, H37 must not start. Gate failure returns `ready_for_h37: false` in the provisioning evidence packet.

---

## 14. Provisioning No-Go Blockers

Any of the following blocks provisioning from being approved:

| # | Blocker | Severity |
|---|---|---|
| PNB1 | No owner approval | HIGH |
| PNB2 | Unknown DB classification | CRITICAL |
| PNB3 | Production DB indicator in DATABASE_URL | CRITICAL |
| PNB4 | Cloud Run production DB indicator | CRITICAL |
| PNB5 | Raw credentials in docs or tests | CRITICAL |
| PNB6 | Production data risk detected | CRITICAL |
| PNB7 | Balance.ge live connector active (`balance != demo_mode`) | CRITICAL |
| PNB8 | Cleanup policy missing | HIGH |
| PNB9 | Retention policy missing | HIGH |
| PNB10 | DB name lacks `disposable` or `staging` marker | HIGH |
| PNB11 | Connection string proof not redacted | CRITICAL |
| PNB12 | Cloud Run env mutation required | CRITICAL |
| PNB13 | H37 readiness gate incomplete | HIGH |

---

## 15. Decision Outputs

Based on provisioning evidence status, H36 produces one of the following decision outputs:

| Decision Output | Meaning | Condition |
|---|---|---|
| `READY_FOR_H37_DRY_RUN` | All gates G1–G11 passed; provisioning evidence complete | All required evidence present; no no-go blockers |
| `BLOCKED_NO_PROVISIONING_OPTION` | No DB option has been selected or confirmed | No DB provisioned; no evidence packet |
| `BLOCKED_NO_OWNER_APPROVAL` | No owner approval for provisioning | PNB1 triggered |
| `BLOCKED_PRODUCTION_RISK` | Production DB indicator detected | PNB3 or PNB4 triggered |
| `BLOCKED_NO_CLEANUP_POLICY` | No cleanup policy defined | PNB8 triggered |
| `BLOCKED_RAW_SECRET_RISK` | Raw credentials detected in docs or tests | PNB5 triggered |
| `BLOCKED_NO_REDACTED_CONNECTION_PROOF` | Connection string proof not in redacted format | PNB11 triggered |

**Current H36 decision: `BLOCKED_NO_PROVISIONING_OPTION`**

Reason: H36 is docs/tests only. No DB has been provisioned. No provisioning evidence packet has been assembled. The plan is defined here for a future task to execute.

---

## 16. Provisioning Checklist Table

| Requirement | Evidence Required | Owner | Status | Blocking if Missing | Notes |
|---|---|---|---|---|---|
| Provisioning option selected | One of: docker_disposable, local_disposable, staging, sandbox_tenant | Engineering | Not ready | Yes — HIGH | Option A (Docker) recommended |
| DB classification | DB name + host confirming non-production classification | Engineering | Not ready | Yes — CRITICAL | Must exclude all production markers |
| Redacted connection proof | `postgresql://nonprod_user:***@host:port/db_name` | Engineering | Not ready | Yes — CRITICAL | Password always redacted |
| Owner approval | Approval record with ID, scope, expiry | Engineering owner | Not ready | Yes — HIGH | Expires in 7 days |
| Cleanup policy | One of: `drop_after`, `preserve_staging`, `container_remove` | Engineering owner | Not ready | Yes — HIGH | Must be decided before provisioning |
| Retention policy | Artifacts retained; no secrets; synthetic data only | Engineering owner | Not ready | Yes — HIGH | Evidence retained regardless of DB drop |
| Fixture hash | SHA-256 of `synthetic_posted_ledger_fixture_pack.json` | Engineering | Not ready | Yes — HIGH | Record before load |
| Migration review | Migration 011 file path + SHA-256 hash | Engineering | Not ready | Yes — HIGH | File exists in repo; review before run |
| No production data proof | Fixture source + DB classification confirmed | Engineering | Not ready | Yes — CRITICAL | Any real data = CRITICAL blocker |
| Balance.ge demo proof | `/health` confirms `balance: demo_mode` | Engineering | Ready | No | Confirmed via live /health |
| Feature flag plan | `POSTED_LEDGER_REPORTS_ENABLED` ON/OFF sequence; production never touched | Engineering | Partial | Yes — CRITICAL | Template defined in H34; needs execution-time confirmation |
| Rollback reference | `docs/rollback-monitoring-post-switch-safety-contract.md` | Engineering | Ready | No | Document present and live verified |
| H37 packet | Full dry-run execution packet from H34 plan (G11) | Engineering owner | Not ready | Yes — HIGH | Requires all above to be ready first |

---

## 17. Safety Rules

These rules are non-negotiable for H36:

- H36 creates no DB.
- H36 runs no SQL.
- H36 runs no migration.
- H36 loads no fixture data into any DB.
- H36 runs no runtime API calls.
- H36 enables no feature flags.
- H36 mutates no Cloud Run environment variables.
- H36 activates no Balance.ge connector.
- H36 makes no connector changes.
- H36 uses no production data.
- H36 uses no real credentials.
- H36 makes no infrastructure changes.
- H36 makes no UI/static file changes.
- H36 does not modify any runtime code in `app/`.
- H36 does not modify any migration file in `app/storage/migrations/`.
- H36 does not modify `main.py`.
- H36 does not modify fixture JSON files.
- H36 does not run Docker.

---

## 18. H36 Results

_Placeholder — filled after tests pass:_

- H36 targeted tests: 32/32 passed
- H35 + H36 combined: 62/62 passed
- Related report/fixture tests: see test run output
- Full unit suite: see test run output
- Fixture JSON changed: no
- Provisioning plan green: yes
- Final decision recommendation: BLOCKED_NO_PROVISIONING_OPTION → H37 Provisioning Evidence Completion / Local Docker PostgreSQL Setup Plan

---

## 19. Non-Goals

H36 explicitly does NOT:

- Create or connect to any DB.
- Execute Docker.
- Execute `psql`, `createdb`, or `dropdb`.
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

## 20. Next Task

Only after PR merge, deploy, and live verification of H36:

**If provisioning evidence is complete (all gates G1–G11 passed):**

H37 — Disposable/Staging DB Runtime Comparison Dry-Run Execution

**If provisioning evidence remains incomplete (current status):**

H37 — Provisioning Evidence Completion / Local Docker PostgreSQL Setup Plan

H37 must not be started before H36 is live verified.
