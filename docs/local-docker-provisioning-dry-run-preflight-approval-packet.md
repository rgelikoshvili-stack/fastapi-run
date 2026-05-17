# Bridge Hub — H40 Local Docker Provisioning Dry-Run Preflight Approval Packet

## 1. Purpose

This document defines the H40 preflight approval packet required before any local Docker PostgreSQL provisioning execution is authorized. It establishes all preflight gates that must pass, the approval packet contract, future provisioning dry-run boundary, go/no-go criteria, decision outputs, and safety rules.

**H40 is docs/tests only.**

- H40 does NOT execute Docker.
- H40 does NOT run `docker pull`.
- H40 does NOT run `docker run`.
- H40 does NOT create a Docker container.
- H40 does NOT create a Docker volume.
- H40 does NOT create a DB.
- H40 does NOT connect to a DB.
- H40 does NOT execute SQL.
- H40 does NOT run migrations.
- H40 does NOT load fixture data.
- H40 does NOT call runtime report APIs.
- H40 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.
- H40 does NOT mutate Cloud Run env vars.
- H40 does NOT change production behavior.
- H40 does NOT activate Balance.ge.

All rules in this document describe future preflight gate planning only. Nothing is executed or provisioned in H40.

---

## 2. H39 Dependency

H40 requires the H39 Docker evidence packet to be complete before any preflight gate evaluation can proceed.

| Dependency | Status |
|---|---|
| H39 Docker evidence packet complete (EV1–EV10 all confirmed) | Not yet produced |
| Docker installed confirmed (EV1) | Not yet confirmed |
| Docker daemon available confirmed (EV2) | Not yet confirmed |
| Local-only context confirmed (EV4) | Not yet confirmed |
| Redaction confirmed | Not yet confirmed |
| H39 `ready_for_preflight` field | `false` |

In this combined H39-H40 PR, H40 defines the preflight approval contract only. It does not execute provisioning. The approval packet is not yet issued.

**Until H39 Docker evidence packet is complete with `ready_for_preflight: true`, H40 preflight gate evaluation cannot begin.**

The production flag `POSTED_LEDGER_REPORTS_ENABLED` **remains OFF** throughout H40.

---

## 3. Preflight Gate P1–P14

All gates must pass before any Docker provisioning execution is authorized:

| # | Gate | Description | Required Condition |
|---|---|---|---|
| P1 | Docker evidence packet | H39 evidence packet complete with `ready_for_preflight: true` | All 19 fields present |
| P2 | Docker installed | Docker confirmed installed on local machine | EV1 confirmed |
| P3 | Docker daemon available | Docker daemon running and responsive | EV2 confirmed |
| P4 | Local-only context | Docker context is local (not remote/cloud/production) | EV4 confirmed; L1–L6 pass |
| P5 | Owner approval | Engineering owner approval issued and valid | Approval not expired (≤ 7 days) |
| P6 | Cleanup policy | Container and volume removal policy confirmed | `cleanup_policy: container_remove` |
| P7 | Retention policy | Artifact retention policy defined; no secrets retained | Retention documented |
| P8 | Redaction checked | All captured evidence reviewed and redacted | `redaction_checked: true` |
| P9 | DB/container naming plan | Container name and DB name include `bridgehub_disposable` marker | Naming rules DNR1–DNR7 met |
| P10 | Fixture hash/version | SHA-256 of `synthetic_posted_ledger_fixture_pack.json` confirmed | Hash recorded |
| P11 | Migration 011 reviewed | Migration 011 file path and SHA-256 hash confirmed | Hash recorded |
| P12 | Balance.ge demo/unconfigured | Balance.ge connector remains demo_mode | `balance: demo_mode` in /health |
| P13 | Feature flag remains OFF | `POSTED_LEDGER_REPORTS_ENABLED` NOT set until local-only test phase | Absent from Cloud Run env |
| P14 | Rollback/cleanup reference | `docs/rollback-monitoring-post-switch-safety-contract.md` confirmed present | File exists |

### Gate Failure Rules

- Any single gate failure blocks provisioning execution.
- P1 failure (H39 packet incomplete) also blocks evaluation of P2–P14.
- P4 failure (non-local context) is CRITICAL — blocks immediately.
- P8 failure (redaction not confirmed) is CRITICAL — blocks immediately.
- P13 failure (feature flag ON in Cloud Run) is CRITICAL — blocks immediately.

---

## 4. Approval Packet Contract

Every authorized provisioning dry-run must produce and record an approval packet before Docker commands are run. This packet is **NOT produced in H40**.

```json
{
  "approval_packet_id": "string — unique ID, e.g. PREFLIGHT-2026-001",
  "docker_evidence_id": "string — reference to H39 evidence packet ID",
  "requested_by": "string — engineering owner name/ID",
  "approved_by": "string — approver name/ID",
  "environment": "local_docker",
  "db_classification": "docker_db / disposable_local_db",
  "container_name": "bridgehub_disposable_h39",
  "db_name": "bridgehub_disposable_h39",
  "host": "localhost",
  "port": 5432,
  "redacted_connection_proof": "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h39",
  "allowed_operations": [
    "docker_pull_postgres",
    "docker_run_postgres",
    "create_disposable_db",
    "run_migration_011",
    "load_synthetic_fixture",
    "capture_reports_flag_off",
    "capture_reports_flag_on_local_only",
    "normalize_outputs",
    "compare_outputs",
    "cleanup"
  ],
  "forbidden_operations": [
    "production_db",
    "cloud_run_env_mutation",
    "balance_live",
    "production_data",
    "raw_secret_commit",
    "connect_to_production_db",
    "enable_feature_flag_in_cloud_run"
  ],
  "cleanup_policy": "container_remove",
  "retention_policy": "artifacts retained; no secrets; synthetic data only",
  "fixture_hash": "string — SHA-256 of synthetic_posted_ledger_fixture_pack.json",
  "migration_hash": "string — SHA-256 of migration 011 file",
  "gates_passed": ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11","P12","P13","P14"],
  "expires_at": "ISO 8601 UTC — max 7 days after approval",
  "go_decision": "go | no_go",
  "created_at": "ISO 8601 UTC — filled at approval time"
}
```

### Required Fields

All fields are required. A packet missing any field cannot authorize provisioning execution.

### `go_decision` Rules

| Condition | `go_decision` |
|---|---|
| All P1–P14 pass; owner approval valid; no blockers | `"go"` |
| Any gate fails | `"no_go"` |
| H39 packet missing or incomplete | `"no_go"` |
| Non-local Docker context | `"no_go"` |
| Raw secret in evidence | `"no_go"` |
| Feature flag ON in Cloud Run | `"no_go"` |
| Owner approval missing or expired | `"no_go"` |

---

## 5. Future Provisioning Dry-Run Boundary

**[NOT EXECUTED IN H40]**

The operations below are future-only documentation. None is executed in H40.

```
[FUTURE] docker pull postgres:16         (NOT EXECUTED IN H40)
[FUTURE] docker run disposable container (NOT EXECUTED IN H40)
[FUTURE] create disposable DB            (NOT EXECUTED IN H40)
[FUTURE] run migration 011               (NOT EXECUTED IN H40)
[FUTURE] load synthetic fixture          (NOT EXECUTED IN H40)
[FUTURE] capture reports flag OFF        (NOT EXECUTED IN H40)
[FUTURE] capture reports flag ON (local) (NOT EXECUTED IN H40)
[FUTURE] normalize + compare outputs     (NOT EXECUTED IN H40)
[FUTURE] cleanup: stop + rm + volume rm  (NOT EXECUTED IN H40)
```

All of these require a complete H39 evidence packet and a valid H40 approval packet before they may proceed.

---

## 6. Go Criteria

All of the following must be true before `go_decision: "go"` is issued:

1. All P1–P14 gates pass.
2. H39 Docker evidence packet complete with `ready_for_preflight: true` (P1).
3. Docker installed and daemon running (P2, P3).
4. Docker context is local-only — not remote, not cloud, not production (P4).
5. Owner approval issued and not expired (P5).
6. Cleanup policy confirmed: container + volume removal after execution (P6).
7. Retention policy defined (P7).
8. All captured evidence reviewed and redacted (P8).
9. Container name and DB name include `bridgehub_disposable` marker (P9).
10. Fixture hash recorded (P10).
11. Migration 011 reviewed and hash recorded (P11).
12. Balance.ge remains demo_mode (P12).
13. `POSTED_LEDGER_REPORTS_ENABLED` NOT set in Cloud Run (P13).
14. Rollback/cleanup reference file confirmed present (P14).
15. No raw secret in any evidence file.
16. No production data in fixture.

---

## 7. No-Go Criteria

Any of the following triggers `go_decision: "no_go"`:

1. H39 evidence packet missing or incomplete (P1 fails).
2. Docker not installed (P2 fails).
3. Docker daemon unavailable (P3 fails).
4. Non-local Docker context — remote, cloud, or production (P4 fails — CRITICAL).
5. Owner approval missing or expired (P5 fails).
6. Cleanup policy not confirmed (P6 fails).
7. Retention policy not defined (P7 fails).
8. Redaction not confirmed (P8 fails — CRITICAL).
9. DB/container naming non-compliant (P9 fails).
10. Fixture hash not recorded (P10 fails).
11. Migration 011 not reviewed (P11 fails).
12. Balance.ge live connector active (P12 fails — CRITICAL).
13. `POSTED_LEDGER_REPORTS_ENABLED` set in Cloud Run (P13 fails — CRITICAL).
14. Rollback reference file missing (P14 fails).
15. Raw secret detected in evidence.
16. Production hostname detected in evidence.

---

## 8. H40 Decision Outputs

| Decision Output | Meaning | Condition |
|---|---|---|
| `READY_FOR_LOCAL_DOCKER_PROVISIONING_EXECUTION` | All P1–P14 pass; approval issued; go_decision: go | All gates confirmed; packet complete |
| `BLOCKED_MISSING_H39_EVIDENCE` | H39 packet not complete; ready_for_preflight is false | P1 fails |
| `BLOCKED_DOCKER_UNAVAILABLE` | Docker not installed or daemon not running | P2 or P3 fails |
| `BLOCKED_REMOTE_CONTEXT` | Non-local Docker context active | P4 fails |
| `BLOCKED_PRODUCTION_RISK` | Production indicator in context or evidence | P4 or data risk |
| `BLOCKED_RAW_SECRET_RISK` | Raw secret in evidence | P8 fails |
| `BLOCKED_NO_OWNER_APPROVAL` | Owner approval not issued or expired | P5 fails |
| `BLOCKED_NO_CLEANUP_POLICY` | Cleanup policy not confirmed | P6 fails |

**Expected current H40 decision: `BLOCKED_MISSING_H39_EVIDENCE`**

Reason: H40 is docs/tests only. H39 Docker evidence packet has not been captured. `ready_for_preflight` is `false`. No provisioning execution authorized.

---

## 9. Safety Rules

These rules are non-negotiable for H40:

- H40 executes no Docker commands.
- H40 creates no DB.
- H40 connects to no DB.
- H40 runs no SQL.
- H40 runs no migration.
- H40 loads no fixture data.
- H40 calls no runtime APIs.
- H40 enables no feature flags.
- H40 mutates no Cloud Run environment variables.
- H40 activates no Balance.ge connector.
- H40 uses no production data.
- H40 uses no real credentials.
- H40 makes no infrastructure changes.
- H40 makes no UI/static file changes.
- H40 does not modify any runtime code in `app/`.
- H40 does not modify any migration file.
- H40 does not modify fixture JSON files.

---

## 10. Next Task

Only after H39-H40 bundle PR is merged, deployed, and live verified:

**If Docker evidence + approval packet exists (EV1–EV10 complete, P1–P14 all pass):**

H41 — Local Docker PostgreSQL Provisioning Dry-Run Execution

**If Docker evidence is not yet available (current status):**

H41 — Docker Evidence Capture Execution

H41 must not be started before H39-H40 bundle is live verified and confirmed.
