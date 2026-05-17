# Bridge Hub — H43 Local Docker Owner Approval Packet

## 1. Purpose

This document defines the owner approval packet required before local Docker PostgreSQL provisioning dry-run execution can proceed. H43 prepares the approval packet structure and documents scope, allowed/forbidden operations, cleanup commitment, and decision logic.

**H43 does NOT execute Docker.**
**H43 does NOT create a DB.**
**H43 does NOT run SQL or migrations.**
**H43 does NOT load fixtures.**
**H43 does NOT call runtime report APIs.**
**H43 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.**
**H43 does NOT mutate Cloud Run env vars.**

---

## 2. H42 Dependency

H43 requires the H42 sanitized evidence packet.

| Dependency | Value |
|---|---|
| H42 sanitization ID | SANITIZATION-2026-H42-001 |
| H42 decision | `EVIDENCE_SANITIZED` |
| H42 `ready_for_h43` | `true` |
| H41 underlying decision | `BLOCKED_DOCKER_UNAVAILABLE` |

**Important:** H42 sanitization is complete and `ready_for_h43: true`. However, the approval packet cannot be fully executed until Docker is installed (H41 `BLOCKED_DOCKER_UNAVAILABLE`). The approval packet is prepared here as `pending` — it will be activated when Docker becomes available.

---

## 3. Approval Scope

The approval packet covers only these future allowed operations:

| # | Allowed Operation | Notes |
|---|---|---|
| AO1 | `docker pull postgres:16` | Pull official PostgreSQL image only |
| AO2 | `docker run postgres:16` | Run disposable local container only |
| AO3 | Create disposable local DB / container | Must include `bridgehub_disposable` naming marker |
| AO4 | Run migration 011 in disposable local DB | Local container only; no production DB |
| AO5 | Load synthetic fixture | `synthetic_posted_ledger_fixture_pack.json` only; no production data |
| AO6 | Capture reports locally (flag OFF and ON) | Local shell only; `POSTED_LEDGER_REPORTS_ENABLED` never set in Cloud Run |
| AO7 | Cleanup container and volume | Stop + rm + volume rm after evidence captured |

**Forbidden operations (non-negotiable):**

| # | Forbidden Operation |
|---|---|
| FO1 | Connect to production DB |
| FO2 | Mutate Cloud Run env vars |
| FO3 | Activate Balance.ge live connector |
| FO4 | Load production or real tenant data |
| FO5 | Commit raw secrets to repository |
| FO6 | Change runtime app code in `app/` |
| FO7 | Enable `POSTED_LEDGER_REPORTS_ENABLED` in Cloud Run |
| FO8 | Run migrations against any non-disposable DB |

---

## 4. Owner Approval JSON

```json
{
  "approval_id": "APPROVAL-2026-H43-001",
  "approved_by": "placeholder — engineering owner name/ID at approval time",
  "requested_by": "Bridge Hub AI / Engineering team",
  "scope": "local_docker_postgres_dry_run",
  "environment": "local_only",
  "db_classification": "docker_db / disposable_local_db",
  "container_name_plan": "bridgehub_disposable_h43",
  "db_name_plan": "bridgehub_disposable_h43",
  "redacted_connection_proof": "postgresql://bridgehub_nonprod_user:***@localhost:5432/bridgehub_disposable_h43",
  "allowed_operations": [
    "docker_pull_postgres_16",
    "docker_run_disposable_container",
    "create_disposable_local_db",
    "run_migration_011_local_only",
    "load_synthetic_fixture_local_only",
    "capture_reports_flag_off_local_only",
    "capture_reports_flag_on_local_only",
    "cleanup_container_and_volume"
  ],
  "forbidden_operations": [
    "connect_to_production_db",
    "mutate_cloud_run_env_vars",
    "activate_balance_ge_live",
    "load_production_data",
    "commit_raw_secrets",
    "change_runtime_app_code",
    "enable_feature_flag_in_cloud_run",
    "migrate_non_disposable_db"
  ],
  "cleanup_policy": "container_remove",
  "retention_policy": "artifacts retained; no secrets; synthetic data only; container and volume removed after evidence captured",
  "docker_evidence_id": "DOCKER-EV-2026-H41-001",
  "sanitization_id": "SANITIZATION-2026-H42-001",
  "prerequisite_blocker": "BLOCKED_DOCKER_UNAVAILABLE",
  "expires_at": "ISO 8601 UTC — max 7 days after approval; filled at signature time",
  "status": "pending"
}
```

**Status is `pending`.** The packet is structurally complete but requires:
1. Docker to be installed (H41 blocker resolved).
2. Engineering owner signature at approval time.
3. `expires_at` to be set (max 7 days from signature).

---

## 5. Cleanup Commitment

Before any Docker container is started, the following cleanup steps are committed:

| Step | Action |
|---|---|
| C1 | Reset `POSTED_LEDGER_REPORTS_ENABLED` to OFF/unset before `docker stop` |
| C2 | `docker stop bridgehub_disposable_h43` |
| C3 | `docker rm bridgehub_disposable_h43` |
| C4 | `docker volume rm bridgehub_disposable_h43_volume` (unless retention approved) |
| C5 | Verify cleanup: `docker ps | grep bridgehub_disposable` must return empty |
| C6 | Verify volume: `docker volume ls | grep bridgehub_disposable` must return empty |
| C7 | No production cleanup required — production was not changed |

**All cleanup steps are future-only and will not be executed until Docker is installed and the approval packet is signed.**

---

## 6. H43 Decision

Allowed decision values:

| Decision Output | Meaning |
|---|---|
| `APPROVAL_PACKET_READY_PENDING_SIGNATURE` | Packet defined; awaiting owner signature |
| `APPROVED_FOR_LOCAL_DOCKER_DRY_RUN` | Owner signed; Docker available; ready for execution |
| `BLOCKED_NO_APPROVER` | No approver identified |
| `BLOCKED_SCOPE_UNCLEAR` | Allowed/forbidden operations not fully defined |
| `BLOCKED_CLEANUP_MISSING` | Cleanup policy not confirmed |
| `BLOCKED_MISSING_H42_SANITIZATION` | H42 sanitized evidence not available |

**Current H43 Decision: `APPROVAL_PACKET_READY_PENDING_SIGNATURE`**

Reason: The approval packet structure is complete and all fields are defined. However, it requires:
1. Docker to be installed first (H41 blocker must be resolved).
2. Engineering owner signature.
3. `expires_at` filled at signature time.

The packet is not yet signed and cannot authorize Docker provisioning execution until both prerequisites are met.

**If engineering owner explicitly approves and Docker is installed:**
Decision becomes `APPROVED_FOR_LOCAL_DOCKER_DRY_RUN`.

---

## 7. Safety Confirmation

- No Docker executed in H43.
- No DB created.
- No DB connected.
- No SQL executed.
- No migration executed.
- No fixture loaded.
- No runtime APIs called.
- No Cloud Run env mutated.
- No feature flag enabled.
- No Balance.ge activated.
- No production data accessed.
- No credentials committed.
