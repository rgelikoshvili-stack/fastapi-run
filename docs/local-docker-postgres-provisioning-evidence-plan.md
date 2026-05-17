# Bridge Hub — H37 Provisioning Evidence Completion / Local Docker PostgreSQL Setup Plan

## 1. Purpose

This document defines the evidence completion plan for local Docker PostgreSQL provisioning before any runtime comparison dry-run. It establishes the local Docker option, all evidence required before execution, naming rules, redacted connection proof requirements, owner approval placeholder, cleanup and retention plan, future-only command templates, the H37 evidence packet shape, no-go blockers, and decision outputs.

**H37 is docs/tests only.**

- H37 does NOT execute Docker.
- H37 does NOT create a DB.
- H37 does NOT connect to a DB.
- H37 does NOT execute SQL.
- H37 does NOT run migrations.
- H37 does NOT load fixtures into a DB.
- H37 does NOT call runtime report APIs.
- H37 does NOT modify Cloud Run environment variables.
- H37 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.
- H37 does NOT activate Balance.ge.

All rules in this document describe future evidence planning only. Nothing is executed or provisioned in H37.

---

## 2. H36 Context

- **H36** defined the full disposable/staging DB provisioning plan: acceptable options (A–D), forbidden options (FP1–FP11), naming rules (NR1–NR7), redacted connection proof (RP1–RP8), owner approval contract, cleanup/retention policy, future command templates, provisioning evidence packet (15 fields), H37 readiness gate (G1–G11), no-go blockers (PNB1–PNB13), and decision outputs (7 outputs).
- **H36 live verified decision: `BLOCKED_NO_PROVISIONING_OPTION`** — no provisioning evidence packet assembled, no DB provisioned.
- **H36 recommendation:** Docker-first path (Option A) is recommended first provisioning path.
- **H37 therefore focuses on completing the evidence for local Docker PostgreSQL provisioning.** No Docker is executed in H37.

The production flag `POSTED_LEDGER_REPORTS_ENABLED` **remains OFF** throughout H37.

---

## 3. Local Docker Option

The recommended first provisioning path is a **local Docker PostgreSQL disposable container**:

| Property | Value |
|---|---|
| Type | Docker PostgreSQL container |
| Scope | Local development machine only |
| Network | localhost / 127.0.0.1 — isolated from production network |
| Data | Synthetic fixture only — no production data |
| Credentials | Generated locally — not committed to repository |
| Cleanup | Container and volume removed after evidence captured |
| Cloud Run | No Cloud Run env mutation required |
| Production credentials | Forbidden |
| Production network | Forbidden |

**Why Docker first:**
- Fully isolated from production network by default.
- Ephemeral — container and volume are removed after use.
- No persistent local PostgreSQL installation required.
- No residual database state after cleanup.
- Easiest to verify: container name and DB name include `bridgehub_disposable` marker.

---

## 4. Evidence Required Before Execution

All of the following evidence items must be produced and recorded before any Docker provisioning execution is allowed:

| # | Evidence Item | Description | Status |
|---|---|---|---|
| DE1 | Docker availability proof | `docker version` output confirms Docker is installed and running | Not produced |
| DE2 | Local-only host proof | DATABASE_URL host confirmed as `localhost` or `127.0.0.1` | Not produced |
| DE3 | Image/version proof | Docker image confirmed: `postgres:15` or `postgres:16` | Not produced |
| DE4 | Container name plan | Container name includes `bridgehub_disposable` marker | Defined here |
| DE5 | Volume cleanup plan | Volume removal policy confirmed before container start | Defined here |
| DE6 | DB name plan | DB name includes `bridgehub_disposable_h37` or similar | Defined here |
| DE7 | User/role plan | Username includes `bridgehub_nonprod_user` or `nonprod`/`disposable` marker | Defined here |
| DE8 | Redacted connection proof | `postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37` | Defined here |
| DE9 | Owner approval | Engineering owner sign-off record | Not produced |
| DE10 | Cleanup policy | `container_remove` — stop + rm + volume rm after evidence captured | Defined here |
| DE11 | Retention policy | Artifacts retained; no secrets; no production data | Defined here |
| DE12 | Migration review | Migration 011 file path and SHA-256 hash confirmed | Not produced |
| DE13 | Fixture hash/version | SHA-256 of `synthetic_posted_ledger_fixture_pack.json` | Not produced |
| DE14 | Rollback/disable reference | `docs/rollback-monitoring-post-switch-safety-contract.md` confirmed | Present |
| DE15 | No production data proof | Fixture source + DB classification — no real tenant data | Not produced |

DE4–DE8, DE10–DE11, DE14 are defined in this document. DE1–DE3, DE9, DE12–DE13, DE15 require future execution-time confirmation.

---

## 5. Local Docker Naming Rules

All Docker provisioning artifacts must follow these naming rules:

| # | Rule | Required Value |
|---|---|---|
| DNR1 | Container name | Must include `bridgehub_disposable` — e.g., `bridgehub_disposable_h37` |
| DNR2 | DB name | Must include `bridgehub_disposable` — e.g., `bridgehub_disposable_h37` |
| DNR3 | Username | Must include `bridgehub_nonprod_user` or `nonprod`/`disposable` marker |
| DNR4 | No production hostname | DATABASE_URL host must be `localhost` or `127.0.0.1` only |
| DNR5 | No production secret | Password must be locally generated; not reused from production; not committed |
| DNR6 | Password in docs | Always replaced with `***`; never committed as plaintext |
| DNR7 | Port | Default `5432`; must not conflict with production services |

### Acceptable Container Names (examples)

- `bridgehub_disposable_h37`
- `bridgehub_disposable_dryrun_h37`

### Acceptable DB Names (examples)

- `bridgehub_disposable_h37`
- `bridgehub_nonprod_h37`

### Forbidden Names

- Any name without `disposable`, `nonprod`, or `staging` marker
- Names matching production DB name patterns
- Names containing production tenant IDs

---

## 6. Redacted Connection Proof

The redacted connection proof must use this format exactly:

```
postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37
```

### Rules

| # | Rule |
|---|---|
| RCP1 | Host must be `localhost` or `127.0.0.1` — never a remote host |
| RCP2 | Password always replaced with `***` — never recorded as plaintext |
| RCP3 | Username shown only if non-sensitive; otherwise redacted |
| RCP4 | DB name visible — must include `bridgehub_disposable` marker |
| RCP5 | Port visible |
| RCP6 | Raw credentials must never be committed to any file |
| RCP7 | Any production hostname in the connection string blocks provisioning |

### Acceptable

```
postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37
postgresql://nonprod_role:***@127.0.0.1:5432/bridgehub_disposable_dryrun
```

### Forbidden

```
postgresql://user:realpassword@localhost:5432/bridgehub_disposable_h37
postgresql://user:pw@production.db.example.com:5432/bridge
postgresql://user:pw@sql.goog:5432/bridge
```

---

## 7. Owner Approval Placeholder

Before Docker provisioning execution, the following approval record must be completed:

```json
{
  "approver": "placeholder — engineering owner name/ID at approval time",
  "scope": "local_docker_postgres_disposable",
  "db_classification": "docker_db / disposable_local_db",
  "allowed_operations": [
    "docker_pull_postgres",
    "docker_run_disposable_container",
    "run_migration_011_local_only",
    "load_synthetic_fixture_local_only",
    "capture_reports_local_only",
    "docker_stop",
    "docker_rm",
    "docker_volume_rm"
  ],
  "cleanup_policy": "container_remove",
  "approval_timestamp": "ISO 8601 UTC — filled at approval time",
  "approval_expires": "ISO 8601 UTC — max 7 days after approval",
  "status": "pending"
}
```

No approval has been issued in H37. Status is `pending` until a future execution task requests approval.

---

## 8. Cleanup and Retention Plan

| Item | Policy |
|---|---|
| Docker container | Stop and remove after all evidence artifacts captured |
| Docker volume | Remove unless staging retention approved; no residual state |
| Synthetic fixture data | Removed with container; fixture JSON in repo unchanged |
| Feature flag | Reset to OFF and verified before container stop |
| Logs/snapshots | Retained as artifacts; no secrets in retained files |
| Production cleanup | Not applicable — production was not changed in H37 or preceding tasks |

### Rules

1. All evidence artifacts must be captured before container is removed.
2. `POSTED_LEDGER_REPORTS_ENABLED` is reset to OFF and verified before `docker stop`.
3. Container removal is verified: `docker ps | grep bridgehub_disposable_h37` must return empty.
4. Volume removal is verified: `docker volume ls | grep bridgehub_disposable_h37` must return empty (unless retention approved).
5. No production cleanup is required because production was not changed.

---

## 9. Future-Only Command Templates

**[FUTURE — NOT EXECUTED IN H37]**

All commands below are documentation only and forbidden in H37.

```
[FUTURE] Step D0: Check Docker availability (NOT EXECUTED IN H37)
  docker version

[FUTURE] Step D1: Pull PostgreSQL image (NOT EXECUTED IN H37)
  docker pull postgres:16

[FUTURE] Step D2: Start disposable container (NOT EXECUTED IN H37)
  docker run --rm --name bridgehub_disposable_h37 \
    -e POSTGRES_DB=bridgehub_disposable_h37 \
    -e POSTGRES_USER=bridgehub_nonprod_user \
    -e POSTGRES_PASSWORD=<nonprod_password_never_committed> \
    -p 5432:5432 \
    -d postgres:16

[FUTURE] Step D3: View container logs (NOT EXECUTED IN H37)
  docker logs bridgehub_disposable_h37

[FUTURE] Step D4: Set local DATABASE_URL (NOT EXECUTED IN H37 — local shell only, never committed)
  export DATABASE_URL="postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37"

[FUTURE] Step D5: Stop container (NOT EXECUTED IN H37)
  docker stop bridgehub_disposable_h37

[FUTURE] Step D6: Remove container (NOT EXECUTED IN H37)
  docker rm bridgehub_disposable_h37

[FUTURE] Step D7: Remove volume (NOT EXECUTED IN H37)
  docker volume rm bridgehub_disposable_h37_volume

[FUTURE] Step D8: Verify cleanup complete (NOT EXECUTED IN H37)
  docker ps | grep bridgehub_disposable_h37   # must return empty
  docker volume ls | grep bridgehub_disposable  # must return empty
```

---

## 10. H37 Evidence Packet

Every Docker provisioning must produce an evidence packet before execution proceeds. This packet is NOT produced in H37.

```json
{
  "evidence_id": "string — unique ID, e.g. DOCKER-PROV-2026-001",
  "db_option": "local_docker_postgres",
  "container_name": "bridgehub_disposable_h37",
  "db_name": "bridgehub_disposable_h37",
  "host": "localhost",
  "port": 5432,
  "redacted_connection_proof": "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37",
  "owner_approval_id": "string — filled at approval time",
  "cleanup_policy": "container_remove",
  "retention_policy": "artifacts retained; no secrets; synthetic data only",
  "fixture_version": "string — SHA-256 of synthetic_posted_ledger_fixture_pack.json",
  "migration_version": "string — migration 011 file path and hash",
  "no_production_data_proof": "string — fixture source confirmation",
  "ready_for_h38": false
}
```

### Required Fields

All 14 fields are required. A packet missing any field is incomplete and cannot authorize H38 gate evaluation.

### `ready_for_h38` Rules

| Condition | `ready_for_h38` |
|---|---|
| All DE1–DE15 evidence produced; owner approval issued; no blockers | `true` |
| Any field missing or any no-go blocker triggered | `false` |
| Docker unavailable | `false` |
| Raw password detected | `false` |
| Owner approval missing or expired | `false` |

---

## 11. H37 No-Go Blockers

Any of the following blocks H37 provisioning evidence from being accepted:

| # | Blocker | Severity |
|---|---|---|
| HB1 | Docker unavailable or not installed | HIGH |
| HB2 | Raw secret in docs or evidence | CRITICAL |
| HB3 | DB name missing `disposable` or `nonprod` marker | HIGH |
| HB4 | Owner approval missing | HIGH |
| HB5 | Cleanup policy missing | HIGH |
| HB6 | Production DB indicator in DATABASE_URL | CRITICAL |
| HB7 | Production data risk detected | CRITICAL |
| HB8 | Balance.ge live connector active | CRITICAL |
| HB9 | Cloud Run env mutation required | CRITICAL |

---

## 12. H37 Decision Outputs

| Decision Output | Meaning | Condition |
|---|---|---|
| `READY_FOR_H38_READINESS_GATE` | All DE1–DE15 evidence present; owner approved; no blockers | All evidence confirmed; `ready_for_h38: true` |
| `BLOCKED_DOCKER_NOT_EXECUTED` | H37 is docs/tests only; Docker not run | Current H37 status |
| `BLOCKED_DOCKER_UNAVAILABLE` | Docker not installed or not running | DE1 missing |
| `BLOCKED_NO_OWNER_APPROVAL` | Owner approval not yet issued | DE9 missing |
| `BLOCKED_RAW_SECRET_RISK` | Raw password detected in docs or evidence | HB2 triggered |
| `BLOCKED_NO_CLEANUP_POLICY` | Cleanup policy not confirmed | DE10 missing |
| `BLOCKED_PRODUCTION_RISK` | Production indicator detected in DATABASE_URL | HB6 triggered |

**Current H37 decision: `BLOCKED_DOCKER_NOT_EXECUTED`**

Reason: H37 is docs/tests only. Docker was not executed. No Docker evidence packet produced.

---

## 13. Safety Rules

These rules are non-negotiable for H37:

- H37 creates no DB.
- H37 executes no Docker commands.
- H37 runs no SQL.
- H37 runs no migration.
- H37 loads no fixture data into any DB.
- H37 runs no runtime API calls.
- H37 enables no feature flags.
- H37 mutates no Cloud Run environment variables.
- H37 activates no Balance.ge connector.
- H37 uses no production data.
- H37 uses no real credentials.
- H37 makes no infrastructure changes.
- H37 makes no UI/static file changes.
- H37 does not modify any runtime code in `app/`.
- H37 does not modify any migration file.
- H37 does not modify fixture JSON files.

---

## 14. Next Task Link

H38 — Local Docker PostgreSQL Dry-Run Readiness Gate / Execution Packet Contract is included in this combined PR as docs/tests only. See `docs/local-docker-dry-run-readiness-gate.md`.

Only after PR merge, deploy, and live verification of the H37-H38 bundle:

**If Docker evidence is available (DE1–DE15 complete):**

H39 — Local Docker PostgreSQL Provisioning Dry-Run Execution

**If Docker evidence is not available (current status):**

H39 — Local Docker Availability / Evidence Capture Plan

H39 must not be started before H37-H38 bundle is live verified.
