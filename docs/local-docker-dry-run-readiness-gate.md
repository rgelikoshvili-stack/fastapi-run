# Bridge Hub — H38 Local Docker PostgreSQL Dry-Run Readiness Gate / Execution Packet Contract

## 1. Purpose

This document defines the H38 readiness gate and execution packet contract for local Docker PostgreSQL dry-run execution. It establishes all gates that must pass before any dry-run execution is authorized, the execution packet shape, go/no-go criteria, decision outputs, and safety rules.

**H38 is docs/tests only.**

- H38 does NOT execute Docker.
- H38 does NOT create a DB.
- H38 does NOT connect to a DB.
- H38 does NOT execute SQL.
- H38 does NOT run migrations.
- H38 does NOT load fixtures into a DB.
- H38 does NOT call runtime report APIs.
- H38 does NOT modify Cloud Run environment variables.
- H38 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.
- H38 does NOT activate Balance.ge.

All rules in this document describe future execution gate planning only. Nothing is executed or provisioned in H38.

---

## 2. H37 Dependency

H38 requires the H37 evidence packet to be complete before any gate evaluation can proceed. The combined H37-H38 PR defines both the evidence plan (H37) and the readiness gate (H38) as docs/tests only.

| Dependency | Status |
|---|---|
| H37 evidence packet complete (DE1–DE15 all confirmed) | Not yet produced |
| Owner approval issued (DE9) | Not yet produced |
| Docker availability confirmed (DE1) | Not yet confirmed |
| Redacted connection proof produced (DE8) | Not yet produced |
| H37 `ready_for_h38` field | `false` |

**Until H37 evidence packet is complete with `ready_for_h38: true`, H38 gate evaluation cannot begin.**

The production flag `POSTED_LEDGER_REPORTS_ENABLED` **remains OFF** throughout H38.

---

## 3. Readiness Gate G1–G12

All gates must pass before any dry-run execution is authorized:

| # | Gate | Description | Required Value |
|---|---|---|---|
| G1 | Docker availability | Docker installed and running on local machine | `docker version` returns successfully |
| G2 | H37 evidence packet | H37 evidence packet produced and complete | All 14 fields present; `ready_for_h38: true` |
| G3 | Owner approval | Engineering owner approval issued and not expired | Approval timestamp present; not expired (≤ 7 days) |
| G4 | Container name | Container name includes `bridgehub_disposable` marker | Name confirmed |
| G5 | DB name | DB name includes `bridgehub_disposable` marker | Name confirmed |
| G6 | Local-only host | DATABASE_URL host is `localhost` or `127.0.0.1` | No remote host present |
| G7 | No production indicators | DATABASE_URL contains no production hostname markers | No markers from PRODUCTION_URL_MARKERS list |
| G8 | No raw secrets | No plaintext password in any evidence document | Password replaced with `***` throughout |
| G9 | Synthetic fixture only | Fixture source confirmed as synthetic (no real tenant data) | `no_production_data_proof` field populated |
| G10 | Migration review | Migration 011 file path and SHA-256 hash confirmed | `migration_version` field populated |
| G11 | Cleanup plan | Container and volume removal policy confirmed | `cleanup_policy: container_remove` |
| G12 | Rollback reference | `docs/rollback-monitoring-post-switch-safety-contract.md` confirmed present | File exists |

### Gate Failure Rules

- Any single gate failure blocks dry-run execution.
- G2 failure (H37 packet incomplete) also blocks gate evaluation for G3–G12.
- G8 failure (raw secret) is CRITICAL and blocks execution even if all other gates pass.
- G7 failure (production indicator) is CRITICAL and blocks execution immediately.

---

## 4. Execution Packet Contract

Every authorized dry-run execution must produce and record an execution packet before Docker commands are run. This packet is NOT produced in H38.

```json
{
  "execution_id": "string — unique ID, e.g. DRY-RUN-2026-001",
  "h37_evidence_id": "string — reference to H37 evidence packet ID",
  "docker_image": "postgres:15 or postgres:16",
  "container_name": "bridgehub_disposable_h37",
  "db_name": "bridgehub_disposable_h37",
  "host": "localhost",
  "port": 5432,
  "redacted_connection_proof": "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h37",
  "owner_approval_id": "string — reference to approval record",
  "cleanup_policy": "container_remove",
  "allowed_operations": [
    "docker_pull_postgres",
    "docker_run_disposable_container",
    "run_migration_011_local_only",
    "load_synthetic_fixture_local_only",
    "capture_reports_flag_off_local_only",
    "capture_reports_flag_on_local_only",
    "normalize_report_outputs",
    "compare_report_outputs",
    "docker_stop",
    "docker_rm",
    "docker_volume_rm"
  ],
  "forbidden_operations": [
    "connect_to_production_db",
    "mutate_cloud_run_env",
    "enable_posted_ledger_reports_enabled_in_production",
    "load_real_tenant_data",
    "activate_balance_ge_live_connector",
    "commit_credentials",
    "push_real_database_url"
  ],
  "feature_flag_plan": "POSTED_LEDGER_REPORTS_ENABLED=1 set locally for flag-ON capture only; reset to OFF before docker stop; never set in Cloud Run",
  "rollback_reference": "docs/rollback-monitoring-post-switch-safety-contract.md",
  "gates_passed": ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12"],
  "go_decision": "go",
  "created_at": "ISO 8601 UTC — filled at execution-request time"
}
```

### Required Fields

All fields are required. A packet missing any field cannot authorize dry-run execution.

### `go_decision` Rules

| Condition | `go_decision` |
|---|---|
| All G1–G12 pass; owner approval valid; no blockers | `"go"` |
| Any gate fails | `"no_go"` |
| H37 packet missing or incomplete | `"no_go"` |
| Raw secret detected | `"no_go"` |
| Production indicator in DATABASE_URL | `"no_go"` |
| Owner approval missing or expired | `"no_go"` |

---

## 5. Future Dry-Run Sequence

**[NOT EXECUTED IN H38]**

The sequence below is documentation only. No step is executed in H38.

```
[FUTURE] Phase 1: Pre-run checks (NOT EXECUTED IN H38)
  - Confirm Docker availability (G1)
  - Confirm H37 evidence packet complete (G2)
  - Confirm owner approval valid (G3)
  - Confirm no production indicators in DATABASE_URL (G7)
  - Confirm no raw secrets in evidence (G8)

[FUTURE] Phase 2: Container provisioning (NOT EXECUTED IN H38)
  docker pull postgres:16
  docker run --rm --name bridgehub_disposable_h37 \
    -e POSTGRES_DB=bridgehub_disposable_h37 \
    -e POSTGRES_USER=bridgehub_nonprod_user \
    -e POSTGRES_PASSWORD=<nonprod_password_never_committed> \
    -p 5432:5432 \
    -d postgres:16

[FUTURE] Phase 3: Migration + fixture (NOT EXECUTED IN H38)
  - Run migration 011 against local Docker DB
  - Load synthetic_posted_ledger_fixture_pack.json into local Docker DB

[FUTURE] Phase 4: Capture reports — flag OFF (NOT EXECUTED IN H38)
  - POSTED_LEDGER_REPORTS_ENABLED not set (absent = OFF)
  - Capture all 11 report outputs locally

[FUTURE] Phase 5: Capture reports — flag ON (NOT EXECUTED IN H38)
  - export POSTED_LEDGER_REPORTS_ENABLED=1  (local shell only)
  - Capture all 11 report outputs locally
  - unset POSTED_LEDGER_REPORTS_ENABLED immediately after

[FUTURE] Phase 6: Normalize and compare (NOT EXECUTED IN H38)
  - Normalize both output sets (strip timestamps, IDs)
  - Compare flag-OFF vs flag-ON outputs
  - Record diff for accountant review

[FUTURE] Phase 7: Accountant review (NOT EXECUTED IN H38)
  - Accountant reviews normalized diff
  - Approval recorded before any production action

[FUTURE] Phase 8: Cleanup (NOT EXECUTED IN H38)
  - Verify POSTED_LEDGER_REPORTS_ENABLED is OFF
  - docker stop bridgehub_disposable_h37
  - docker rm bridgehub_disposable_h37
  - docker volume rm bridgehub_disposable_h37_volume
  - Verify container and volume removed
```

---

## 6. Go Criteria

All of the following must be true before `go_decision: "go"` is issued:

1. All G1–G12 gates pass.
2. No raw secret detected in any evidence file (G8).
3. No production hostname in DATABASE_URL (G7).
4. No production data in fixture (G9).
5. No Cloud Run environment mutation required or planned.
6. Owner approval issued and not expired (G3).
7. Cleanup plan confirmed: container + volume removal after execution (G11).
8. H37 evidence packet complete with `ready_for_h38: true` (G2).
9. Balance.ge live connector NOT active.
10. `POSTED_LEDGER_REPORTS_ENABLED` NOT set in Cloud Run.

---

## 7. No-Go Criteria

Any of the following triggers `go_decision: "no_go"`:

1. Docker unavailable (G1 fails).
2. H37 evidence packet incomplete or missing (G2 fails).
3. Owner approval missing or expired (G3 fails).
4. Container name missing `bridgehub_disposable` marker (G4 fails).
5. DB name missing `bridgehub_disposable` marker (G5 fails).
6. DATABASE_URL host is not `localhost` or `127.0.0.1` (G6 fails).
7. Production hostname indicator in DATABASE_URL (G7 fails — CRITICAL).
8. Raw password detected in any evidence (G8 fails — CRITICAL).
9. Real tenant data risk (G9 fails — CRITICAL).
10. Migration version not confirmed (G10 fails).
11. Cleanup plan not confirmed (G11 fails).
12. Rollback reference file missing (G12 fails).
13. Balance.ge live connector active.
14. `POSTED_LEDGER_REPORTS_ENABLED` set in Cloud Run.

---

## 8. H38 Decision Outputs

| Decision Output | Meaning | Condition |
|---|---|---|
| `READY_FOR_DRY_RUN_EXECUTION` | All G1–G12 pass; owner approved; go_decision: go | All gates confirmed; packet complete |
| `BLOCKED_MISSING_H37_EVIDENCE` | H37 packet not complete; ready_for_h38 is false | G2 fails |
| `BLOCKED_DOCKER_UNAVAILABLE` | Docker not installed or not running | G1 fails |
| `BLOCKED_NO_OWNER_APPROVAL` | Owner approval not issued or expired | G3 fails |
| `BLOCKED_PRODUCTION_RISK` | Production indicator in DATABASE_URL or data | G7 or G9 fails |
| `BLOCKED_RAW_SECRET_RISK` | Raw password in evidence | G8 fails |
| `BLOCKED_NO_CLEANUP_PLAN` | Cleanup plan not confirmed | G11 fails |

**Expected current H38 decision: `BLOCKED_MISSING_H37_EVIDENCE`**

Reason: H38 is docs/tests only. H37 evidence packet is not yet produced. `ready_for_h38` is `false`. No dry-run execution authorized.

---

## 9. Safety Rules

These rules are non-negotiable for H38:

- H38 creates no DB.
- H38 executes no Docker commands.
- H38 runs no SQL.
- H38 runs no migration.
- H38 loads no fixture data into any DB.
- H38 runs no runtime API calls.
- H38 enables no feature flags.
- H38 mutates no Cloud Run environment variables.
- H38 activates no Balance.ge connector.
- H38 uses no production data.
- H38 uses no real credentials.
- H38 makes no infrastructure changes.
- H38 makes no UI/static file changes.
- H38 does not modify any runtime code in `app/`.
- H38 does not modify any migration file.
- H38 does not modify fixture JSON files.

---

## 10. Next Task

After H37-H38 bundle PR is merged, deployed, and live verified:

**If Docker evidence becomes available (DE1–DE15 complete, owner approval issued):**

H39 — Local Docker PostgreSQL Provisioning Dry-Run Execution

**If Docker evidence is not yet available (current status):**

H39 — Local Docker Availability / Evidence Capture Plan

H39 must not be started before H37-H38 bundle is live verified and confirmed.
