# Bridge Hub — H34 Disposable/Staging DB Runtime Comparison Execution Plan

## 1. Purpose

This document defines the future execution plan for a disposable/staging DB runtime comparison of `POSTED_LEDGER_REPORTS_ENABLED`. It covers environment and DB classification, migration, fixture load, report capture, normalization, comparison, accountant review, cleanup, and evidence retention — all as a future execution contract.

**H34 is docs/tests only.**

- H34 does NOT create a DB.
- H34 does NOT connect to a DB.
- H34 does NOT execute SQL.
- H34 does NOT run migrations.
- H34 does NOT load fixtures into a DB.
- H34 does NOT call runtime report APIs.
- H34 does NOT modify runtime report behavior.
- H34 does NOT modify Cloud Run environment variables.
- H34 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.
- H34 does NOT activate Balance.ge.

All rules in this document describe future execution planning only. Nothing is executed in H34.

---

## 2. H24–H33 Context

- **H24** — Disposable DB dry-run was blocked because PostgreSQL was unavailable in the local environment.
- **H25** — Synthetic fixture pack created (`synthetic_posted_ledger_fixture_pack.json`): tenants, headers, lines, sources, invalid rows, balanced entries, correction/reversal entries, evidence links.
- **H26** — Expected totals validated against the synthetic fixture; decimal arithmetic confirmed.
- **H27** — Comparison plan defined: old-vs-new report comparison strategy, mismatch classification, severity rules.
- **H28** — Normalizer contract defined: canonical snapshot shape, 10 normalization error codes, stable row key priority, 11 report name mapping.
- **H29** — Comparator contract defined: 20 mismatch codes, severity rules, 3 comparison modes, mismatch item shape.
- **H30** — Accountant review report contract defined: overall status (`passed`, `passed_with_rounding`, `blocked`, `failed`), sign-off contract, audit metadata, production switch gates.
- **H31** — Production switch gates G1–G12 defined; no-go blockers; switch request packet; sign-off requirements; staged rollout.
- **H32** — Rollback/monitoring/post-switch safety contract defined: rollback triggers, rollback plan, monitoring metrics, alert thresholds, on-call ownership, incident/audit report.
- **H33** — Controlled non-production feature flag simulation plan defined: environment/DB classification rules, simulation matrix, production guard rules, promotion blockers, simulation result packet.
- **H34** — Defines the future runtime comparison execution plan: step-by-step, artifact-by-artifact, gate-by-gate.

The production flag `POSTED_LEDGER_REPORTS_ENABLED` **remains OFF** throughout H34.

---

## 3. Execution Non-Action Statement

H34 does not execute the plan described in this document.

- H34 does NOT run commands against any DB.
- H34 does NOT connect to any local, staging, or production DB.
- H34 does NOT run migration 011.
- H34 does NOT load the synthetic fixture into any DB.
- H34 does NOT call any report endpoint.
- H34 does NOT set `POSTED_LEDGER_REPORTS_ENABLED` to any value.
- H34 does NOT mutate any Cloud Run service.
- H34 does NOT start H35.

All commands and steps in this document are marked `[FUTURE]` and are documentation only.

---

## 4. Environment Classification Gate

### Environment Classes

| Class | Description | Execution Allowed? |
|---|---|---|
| `disposable_local` | Developer laptop or isolated CI VM; ephemeral | Yes |
| `staging` | Dedicated non-production server or Cloud Run staging revision | Yes |
| `sandbox_tenant` | Isolated tenant in non-production DB; requires prior staging evidence | Only after staging evidence |
| `ci_monkeypatch` | Pytest with env override; no real DB | Test-only; cannot prove runtime readiness |
| `production` | Live production service and DB | **FORBIDDEN** |
| `unknown` | Cannot be positively classified | **FORBIDDEN** |

### Rules

1. Execution is allowed only for `disposable_local` or `staging`.
2. `sandbox_tenant` is allowed only after at least one successful `staging` execution with evidence.
3. `ci_monkeypatch` cannot be used to prove runtime readiness for production promotion.
4. `production` is forbidden in all future H34 execution scenarios.
5. `unknown` is forbidden; any ambiguous environment must be resolved before execution.
6. Environment proof must be recorded before any execution step begins.

---

## 5. DB Classification Gate

### DB Classes

| Class | Description | Execution Allowed? |
|---|---|---|
| `disposable_local_db` | Local Postgres (`localhost`, `127.0.0.1`, Docker) | Yes |
| `staging_db` | Dedicated staging Postgres; host clearly non-production | Yes |
| `production_db` | Live production Postgres | **FORBIDDEN** |
| `cloud_run_production_db` | Cloud SQL connected to Cloud Run production | **FORBIDDEN** |
| `unknown_db` | DB host cannot be classified | **FORBIDDEN** |

### Rules

1. Execution is allowed only for `disposable_local_db` or `staging_db`.
2. `production_db` and `cloud_run_production_db` are forbidden.
3. `unknown_db` is forbidden; must be resolved before any execution.
4. DB proof must include: host, DB name, user role, and explicit non-production marker.
5. A `DATABASE_URL` containing any production hostname, Cloud SQL instance suffix, or production project ID blocks execution immediately.

---

## 6. Required Prerequisites

All of the following must be confirmed before any future execution step:

| # | Prerequisite | Status in H34 |
|---|---|---|
| PR1 | H31 gates accepted for planning | Accepted (H31 live verified) |
| PR2 | H32 rollback/monitoring accepted for planning | Accepted (H32 live verified) |
| PR3 | H33 simulation plan accepted | Accepted (H33 live verified) |
| PR4 | PostgreSQL available in disposable/staging environment | Not confirmed — pending future execution |
| PR5 | Migration 011 reviewed and available | Available at `app/storage/migrations/` — not executed in H34 |
| PR6 | Synthetic fixture available | Available at `tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json` |
| PR7 | Fixture hash/version recorded | To be recorded at future execution time |
| PR8 | No production data present in simulation DB | To be confirmed at future execution time |
| PR9 | Balance.ge connector in demo/unconfigured mode | Confirmed by `/health` check before execution |
| PR10 | Old/current report path available | Available in deployed app |
| PR11 | Posted-ledger report path available behind flag | Available when flag enabled in non-production |
| PR12 | Owner approval for non-production execution | Required — not yet issued |

---

## 7. Future Migration Execution Plan

**[FUTURE — NOT EXECUTED IN H34]**

The following steps describe a future migration execution in a disposable/staging DB only.

### Steps

```
[FUTURE] Step M1: Verify DB classification
  - Confirm DB host is disposable_local_db or staging_db
  - Abort if production or unknown

[FUTURE] Step M2: Verify migration file path
  - Confirm app/storage/migrations/011_*.sql exists
  - Record migration file SHA-256 hash

[FUTURE] Step M3: Run migration 011 against disposable/staging DB only
  - Command template (NOT EXECUTED IN H34):
    psql $NON_PRODUCTION_DATABASE_URL -f app/storage/migrations/011_*.sql
  - This command must ONLY target a disposable or staging DATABASE_URL.

[FUTURE] Step M4: Verify created tables and indexes
  - Confirm expected tables exist
  - Confirm expected indexes exist

[FUTURE] Step M5: Verify idempotency
  - Run migration again against same DB
  - Verify no error (idempotent migration)

[FUTURE] Step M6: Verify no destructive statements outside expected scope
  - Review migration DDL for unexpected DROP, TRUNCATE, DELETE

[FUTURE] Step M7: Capture migration log
  - Record all DDL output as a migration artifact

No migration commands are run in H34.
```

---

## 8. Future Fixture Load Plan

**[FUTURE — NOT EXECUTED IN H34]**

The following steps describe loading the synthetic fixture into a disposable/staging DB.

### Steps

```
[FUTURE] Step F1: Verify fixture hash/version
  - Compute SHA-256 of synthetic_posted_ledger_fixture_pack.json
  - Compare against expected version

[FUTURE] Step F2: Verify no real data
  - Confirm fixture contains only synthetic tenants
  - Confirm no real GEL amounts matching production patterns

[FUTURE] Step F3: Load fixture data into non-production DB only
  - Load tenants
  - Load journal headers
  - Load journal lines
  - Load source links
  - Load invalid test rows
  - Command template (NOT EXECUTED IN H34):
    python scripts/load_fixture.py --env non-production --fixture tests/fixtures/posted_ledger/...

[FUTURE] Step F4: Verify row counts match fixture specification
  - Confirm posted rows: 6 main + correction + reversal
  - Confirm invalid rows: 4

[FUTURE] Step F5: Verify balanced entries
  - Confirm each header's debit sum equals credit sum

[FUTURE] Step F6: Verify tenant isolation rows
  - Confirm tenant_alpha and tenant_beta data is isolated

[FUTURE] Step F7: Verify correction/reversal data
  - Confirm correction row references original
  - Confirm reversal row references original

[FUTURE] Step F8: Verify evidence/posting/source links
  - Confirm evidence_url present on all valid rows
  - Confirm posting_ref present where expected

[FUTURE] Step F9: Capture fixture load log
  - Record all INSERT counts and verification results

No fixture loading is performed in H34.
```

---

## 9. Future Report Capture Plan

**[FUTURE — NOT EXECUTED IN H34]**

### Old/Current Report Capture (Flag OFF)

```
[FUTURE] Step C1: Set POSTED_LEDGER_REPORTS_ENABLED=OFF in non-production environment
[FUTURE] Step C2: Capture all 11 reports with flag OFF:
  1. Trial Balance
  2. P&L Summary
  3. P&L Detail
  4. Balance Sheet Summary
  5. Balance Sheet Detail
  6. VAT Register
  7. Account Ledger
  8. Counterparty Ledger
  9. Payroll Ledger
  10. Journal Entries List
  11. Cashflow
[FUTURE] Step C3: Store raw snapshots; record flag state, tenant, period, currency, git SHA
```

### Posted-Ledger Report Capture (Flag ON — Non-Production Only)

```
[FUTURE] Step C4: Set POSTED_LEDGER_REPORTS_ENABLED=ON in disposable/staging environment ONLY
[FUTURE] Step C5: Capture all 11 reports with flag ON
[FUTURE] Step C6: Store raw snapshots; record flag state, tenant, period, currency, git SHA
[FUTURE] Step C7: Reset POSTED_LEDGER_REPORTS_ENABLED=OFF immediately after capture
[FUTURE] Step C8: Verify flag is OFF after reset
```

---

## 10. Future Normalization / Comparison Plan

**[FUTURE — NOT EXECUTED IN H34]**

### Normalization

```
[FUTURE] Step N1: Normalize old/current snapshot using H28 normalizer contract
[FUTURE] Step N2: Normalize posted-ledger snapshot using H28 normalizer contract
[FUTURE] Step N3: Normalize expected fixture snapshot using H28 normalizer contract
[FUTURE] Step N4: Record any normalization error codes
```

### Comparison

```
[FUTURE] Step CP1: Compare all 11 normalized reports using H29 comparator contract
[FUTURE] Step CP2: Classify each mismatch by severity (critical/high/medium/low/rounding_only)
[FUTURE] Step CP3: Produce machine-readable JSON comparison result
[FUTURE] Step CP4: Produce H30 accountant review report (overall_status, recommended actions)
[FUTURE] Step CP5: Block promotion if critical or high mismatches found
```

---

## 11. Feature Flag Handling

| State | When | Environment |
|---|---|---|
| OFF | Old/current report capture | Any |
| ON | Posted-ledger capture only | `disposable_local` or `staging` only |
| OFF | After posted-ledger capture | Any |
| OFF | Production at all times | Production — never ON in H34 |

### Rules

1. Flag name: `POSTED_LEDGER_REPORTS_ENABLED`.
2. OFF for old/current report capture; ON only in non-production for posted-ledger capture.
3. Flag must **never** be ON in production during any H34 execution.
4. Flag must be reset to OFF immediately after posted-ledger capture.
5. Flag OFF verified after reset before any promotion step.
6. Unknown flag state blocks execution.
7. Fail-closed behavior required: absent or unrecognized value treated as OFF.

---

## 12. Expected Artifacts

Every completed future execution must produce all of the following:

| # | Artifact | Description |
|---|---|---|
| A1 | Environment classification proof | Class string + host/DB/env label |
| A2 | DB classification proof | Host, DB name, user role, non-production marker |
| A3 | Migration log | DDL output from migration 011 |
| A4 | Fixture load log | Row counts, verification results |
| A5 | Fixture hash/version | SHA-256 of fixture file |
| A6 | Old/current raw report snapshots (×11) | One per report, flag OFF state recorded |
| A7 | Posted-ledger raw report snapshots (×11) | One per report, flag ON state recorded |
| A8 | Normalized snapshots | H28 normalizer output for both paths |
| A9 | Comparison result JSON | H29 comparator output: mismatch list |
| A10 | Accountant review report | H30 review report: overall_status, sign-off |
| A11 | Rollback/cleanup log | Feature flag reset proof; DB cleanup status |
| A12 | No-go blocker report | Any blocked conditions recorded |
| A13 | Final execution summary | All above referenced; gate outcome; promotion recommendation |

---

## 13. Cleanup / Evidence Retention Plan

| Item | Disposable Local DB | Staging DB |
|---|---|---|
| DB drop after execution | Allowed (recommended) | Preserve if approved |
| Fixture data | Removed with DB drop | Can be removed; fixture JSON remains in repo |
| Feature flag | Reset to OFF; verified | Reset to OFF; verified |
| Logs | Retained as artifacts | Retained as artifacts |
| Snapshots | Retained | Retained |
| Comparison result | Retained | Retained |
| Accountant review | Retained | Retained |
| Production cleanup | Not applicable — production not changed | Not applicable |

### Rules

1. A disposable DB may be dropped after all artifacts (A1–A13) are captured.
2. A staging DB may be preserved if the staging owner approves.
3. Feature flag reset is always performed and verified before DB cleanup.
4. All artifact files must be retained regardless of DB drop.
5. Production is never involved in cleanup because production was not changed in H34.

---

## 14. No-Go Blockers

Any of the following blocks execution from proceeding to the next step:

| # | Blocker | Severity |
|---|---|---|
| B1 | Environment class `unknown` or `production` | CRITICAL |
| B2 | DB class `unknown_db`, `production_db`, or `cloud_run_production_db` | CRITICAL |
| B3 | Any production DB indicator in DATABASE_URL | CRITICAL |
| B4 | `POSTED_LEDGER_REPORTS_ENABLED=ON` in production during any execution step | CRITICAL |
| B5 | Balance.ge live connector active (`balance != demo_mode`) | CRITICAL |
| B6 | Production data detected in simulation DB | CRITICAL |
| B7 | Migration file not reviewed or hash missing | HIGH |
| B8 | Fixture hash missing or mismatch | HIGH |
| B9 | Fixture load row count mismatch | HIGH |
| B10 | Tenant leakage between tenant_alpha and tenant_beta | CRITICAL |
| B11 | Critical mismatch in comparison result | CRITICAL |
| B12 | High mismatch in comparison result | HIGH |
| B13 | Missing required evidence/drilldown on material item | HIGH |
| B14 | Rollback plan reference missing | HIGH |
| B15 | Owner approval missing | HIGH |
| B16 | Protected report endpoint auth bypass detected | CRITICAL |

---

## 15. Runtime Comparison Result Packet

Every completed future execution must produce a result packet:

```json
{
  "execution_id": "string — unique ID, e.g. EXEC-2026-001",
  "environment": "disposable_local | staging",
  "db_classification": "disposable_local_db | staging_db",
  "git_sha": "string — deployed SHA at time of execution",
  "fixture_version": "string — SHA-256 or version label of fixture file",
  "migration_version": "string — migration file version executed",
  "feature_flag_states": {
    "old_capture": "off",
    "new_capture": "on",
    "post_reset": "off"
  },
  "reports_captured": [
    "trial_balance", "pl_summary", "pl_detail",
    "balance_sheet_summary", "balance_sheet_detail",
    "vat_register", "account_ledger", "counterparty_ledger",
    "payroll_ledger", "journal_entries_list", "cashflow"
  ],
  "comparison_result_id": "string — reference to H29 comparator output",
  "accountant_review_id": "string — reference to H30 review report",
  "gate_outcome": "pass | pass_with_rounding | fail | blocked",
  "promotion_recommendation": "proceed_to_next_stage | fix_and_retry | block_promotion",
  "cleanup_status": "db_dropped | db_preserved | cleanup_pending",
  "evidence_artifacts": [
    "A1_environment_proof", "A2_db_proof", "A3_migration_log",
    "A4_fixture_load_log", "A5_fixture_hash", "A6_old_snapshots",
    "A7_new_snapshots", "A8_normalized_snapshots", "A9_comparison_result",
    "A10_accountant_review", "A11_rollback_cleanup_log",
    "A12_nogo_blocker_report", "A13_execution_summary"
  ],
  "created_at": "ISO 8601 UTC timestamp",
  "created_by": "Bridge Hub"
}
```

### Required Fields

All 16 top-level fields are required. A result packet missing any field is incomplete and cannot be used as promotion evidence.

---

## 16. Execution Checklist Table

| Step | Action | Environment | Allowed in H34? | Future Execution Allowed? | Required Evidence | Blocking if Failed? |
|---|---|---|---|---|---|---|
| 1 | Classify environment | Any | No (docs only) | Yes (disposable/staging only) | Environment classification proof (A1) | Yes — CRITICAL |
| 2 | Classify DB | Any | No (docs only) | Yes (disposable/staging DB only) | DB classification proof (A2) | Yes — CRITICAL |
| 3 | Run migration 011 | Non-production only | No | Yes | Migration log (A3) | Yes — HIGH |
| 4 | Load synthetic fixture | Non-production only | No | Yes | Fixture load log (A4) + hash (A5) | Yes — HIGH |
| 5 | Capture old reports (flag OFF) | Non-production only | No | Yes | Old snapshots (A6) | Yes — HIGH |
| 6 | Enable flag (non-production only) | Non-production only | No | Yes | Flag state proof (feature_flag_states.new_capture=on) | Yes — CRITICAL if in production |
| 7 | Capture posted-ledger reports (flag ON) | Non-production only | No | Yes | New snapshots (A7) | Yes — HIGH |
| 8 | Reset flag to OFF | Non-production only | No | Yes | Post-reset flag proof (feature_flag_states.post_reset=off) | Yes — CRITICAL |
| 9 | Normalize snapshots | Local | No (docs only) | Yes | Normalized snapshots (A8) | Yes — HIGH |
| 10 | Compare snapshots | Local | No (docs only) | Yes | Comparison result (A9) | Yes — CRITICAL if critical mismatch |
| 11 | Generate accountant review | Local | No (docs only) | Yes | Accountant review (A10) | Yes — HIGH |
| 12 | Cleanup / preserve DB | Non-production only | No | Yes | Rollback/cleanup log (A11) | No (informational) |
| 13 | Produce final summary | Local | No (docs only) | Yes | Execution summary (A13) | Yes — HIGH |

---

## 17. Safety Rules

These rules are non-negotiable for H34:

- H34 creates no DB.
- H34 executes no SQL.
- H34 runs no migrations.
- H34 loads no fixture data into any DB.
- H34 runs no runtime API calls.
- H34 enables no feature flags.
- H34 mutates no Cloud Run environment variables.
- H34 activates no Balance.ge connector.
- H34 makes no connector changes.
- H34 uses no production data.
- H34 uses no real credentials.
- H34 makes no infrastructure changes.
- H34 makes no UI/static file changes.
- H34 does not modify any runtime code in `app/`.
- H34 does not modify any migration file in `app/storage/migrations/`.
- H34 does not modify `main.py`.
- H34 does not modify fixture JSON files.

---

## 18. H34 Results

_Placeholder — filled after tests pass:_

- H34 targeted tests: 30/30 passed
- H33 + H34 combined: 59/59 passed
- Related report/fixture tests: see test run output
- Full unit suite: see test run output
- Fixture JSON changed: no
- Execution plan green: yes

---

## 19. Non-Goals

H34 explicitly does NOT:

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

---

## 20. Next Task

Only after PR merge, deploy, and live verification of H34:

**H35 — Disposable/Staging DB Runtime Comparison Dry-Run Execution**
(Only if a suitable disposable/staging DB is available.)

If a suitable DB is not available:

**H35 — Runtime Comparison Dry-Run Blocker Resolution Plan**

H35 must not be started before H34 is live verified.
