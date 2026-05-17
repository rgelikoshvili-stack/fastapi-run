# Bridge Hub — H33 Controlled Non-Production Feature Flag Simulation Plan

## 1. Purpose

This document defines how to simulate `POSTED_LEDGER_REPORTS_ENABLED` safely in a non-production environment only. It establishes prerequisites, environment classification rules, a simulation matrix, production guard rules, required evidence, expected outputs, rollback/disable rules, promotion blockers, and the simulation result packet shape.

**H33 is docs/tests only.**

- H33 does NOT create a DB.
- H33 does NOT connect to a DB.
- H33 does NOT execute SQL.
- H33 does NOT run migrations.
- H33 does NOT load fixtures into a DB.
- H33 does NOT call runtime report APIs.
- H33 does NOT modify runtime report behavior.
- H33 does NOT modify Cloud Run environment variables.
- H33 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED` anywhere.
- H33 does NOT activate Balance.ge.

All rules in this document describe future operational planning. They do not implement, execute, or mutate any system.

---

## 2. H31–H32 Context

- **H31** defined production switch gates G1–G12, no-go blockers, the switch request packet, staged rollout rules, emergency disable rules, and sign-off requirements. The production flag must remain OFF until all G1–G12 gates pass.
- **H32** defined rollback, monitoring, alerting, emergency disable, and post-switch safety: rollback triggers, rollback plan contract, rollback verification checklist, monitoring metrics, alert thresholds, on-call ownership, post-switch watch windows, staged rollout halt rules, safe re-enable rules, incident/audit report contract, and post-switch safety dashboard design.
- The production flag `POSTED_LEDGER_REPORTS_ENABLED` **remains OFF** as of H32. No production switch has occurred.
- **H33** now defines the controlled non-production simulation planning only. It does not execute any simulation. It defines the contract for how a future simulation should be set up, governed, and evaluated.

---

## 3. Feature Flag Identity

| Property | Value |
|---|---|
| Flag name | `POSTED_LEDGER_REPORTS_ENABLED` |
| Default | OFF / absent / not set |
| Production value | OFF — must remain absent or explicitly `""` / `"0"` / `"false"` |
| Allowed true values (non-production only) | `"1"`, `"true"`, `"yes"` |
| Behavior | Fail-closed — absence treated as OFF |
| Silent fallback | Forbidden — flag absence must route to old path explicitly |
| Production enablement in H33 | Forbidden |
| Unknown value handling | Treat as OFF; log warning |

### Fail-Closed Requirement

If the flag is absent, malformed, or set to any value not in the allowed true set, the system must treat it as OFF and serve the old report path. No silent fallback to the new path is permitted.

---

## 4. Non-Production Environment Classification

### Allowed Simulation Environments

| Environment | Description | DB Source | Feature Flag Allowed ON? |
|---|---|---|---|
| Disposable local | Developer laptop, isolated process | Disposable in-memory or local Postgres | Yes — for simulation only |
| Staging | Dedicated non-production Cloud Run or local server | Dedicated staging DB with synthetic data | Yes — for simulation only |
| Sandbox tenant | Isolated tenant scope within a non-production environment | Non-production DB | Yes — isolated tenant only |
| CI / monkeypatch tests | Pytest with monkeypatch or env override | No real DB (TEST_MODE=1) | Yes — test-scoped only |

### Forbidden Environments

| Environment | Reason |
|---|---|
| Production | Never — H31 gate process required |
| Cloud Run production service | Never — no env mutation allowed in H33 |
| Production DB | Never — real customer data |
| Production customer data | Never — privacy/compliance |
| Balance.ge live connector | Never — no real ERP posting |

### Unknown Environment Rule

If the environment cannot be positively classified as non-production, the simulation must **fail closed**: flag treated as OFF, simulation blocked, warning logged. No promotion allowed from an unclassified environment.

---

## 5. Simulation Preconditions

All of the following must be confirmed before any simulation can begin:

| # | Precondition | Verification Method |
|---|---|---|
| P1 | Disposable or staging DB available and classified non-production | DB URL contains `localhost`, `staging`, `sandbox`, or explicit non-production label |
| P2 | Posted-ledger schema migrated in non-production DB only | Migration version check in non-production environment |
| P3 | Synthetic fixture loaded in non-production DB only | Fixture hash/version recorded; no production data |
| P4 | Old/current report output captured with flag OFF | Snapshot captured before flag set ON |
| P5 | Posted-ledger report output available with flag ON in non-production | Captured only after P1–P4 confirmed |
| P6 | Normalizer contract (H28) available or accepted | `docs/synthetic-snapshot-normalizer-contract.md` present |
| P7 | Comparator contract (H29) available or accepted | `docs/synthetic-snapshot-comparator-contract.md` present |
| P8 | Accountant review contract (H30) available | `docs/accountant-review-report-contract.md` present |
| P9 | Rollback/disable plan available | `docs/rollback-monitoring-post-switch-safety-contract.md` present |
| P10 | No production data in simulation DB | Confirmed by fixture hash and DB classification |
| P11 | Balance.ge connector in demo/unconfigured mode | `/health` shows `balance: demo_mode` or equivalent |
| P12 | Owner approval for non-production simulation | Engineering owner sign-off recorded |

---

## 6. Simulation Matrix

| Environment | DB Source | Data Source | Flag State | Allowed? | Required Approval | Expected Output | Promotion Allowed? |
|---|---|---|---|---|---|---|---|
| Disposable local | Local/in-memory | Synthetic fixture | OFF | Yes | None | Old path snapshot | No (baseline only) |
| Disposable local | Local/in-memory | Synthetic fixture | ON | Yes | Engineering owner | Comparison + review | Only if no critical/high mismatch |
| Staging | Staging DB | Synthetic fixture | OFF | Yes | None | Old path snapshot | No (baseline only) |
| Staging | Staging DB | Synthetic fixture | ON | Yes | Engineering + Accounting | Full simulation result | Only if all gates pass |
| Production | Production DB | Customer data | OFF | Yes (read-only, no flag change) | N/A | N/A | N/A |
| Production | Production DB | Customer data | ON | **FORBIDDEN** | N/A | N/A | **Never** |
| Unknown | Unknown | Unknown | ON | **FORBIDDEN** | N/A | N/A | **Never** |
| CI / monkeypatch | None (TEST_MODE=1) | Synthetic dict | ON (scoped) | Yes | None | Test pass/fail | No |

---

## 7. Production Guard Rules

1. **Production flag ON is forbidden in H33.** No H33 action may set `POSTED_LEDGER_REPORTS_ENABLED=1` in any production environment.
2. **Production DB must never be used** in any simulation step defined by H33. Production DB access requires H31 gate completion.
3. **Production Cloud Run env must not be mutated.** H33 defines no Cloud Run update command.
4. **Production customer data must not be used.** All simulation data must be synthetic fixtures.
5. **Any production indicator forces simulation blocked.** If the DB URL contains a production hostname, Cloud Run project, or production tenant data, the simulation plan requires immediate halt.
6. **Flag must remain absent/OFF in production.** H33 adds no mechanism to set the flag in production.
7. **Balance.ge live connector must remain inactive.** If `balance != demo_mode`, simulation is blocked regardless of environment.

---

## 8. Required Evidence Before Simulation

Before any non-production simulation can be recorded as a valid evidence artifact:

| # | Evidence Item | Format |
|---|---|---|
| E1 | Environment classification proof | String: `disposable_local`, `staging`, `sandbox_tenant`, `ci_monkeypatch` |
| E2 | DB classification proof | DB URL prefix or explicit label; must exclude production identifiers |
| E3 | Fixture hash/version | SHA-256 hash of fixture file or recorded fixture version string |
| E4 | Migration version proof | Migration file list or version number at time of simulation |
| E5 | Feature flag state proof | Env var value recorded before and after each simulation step |
| E6 | Balance.ge demo/unconfigured proof | `/health` connector state or equivalent |
| E7 | No production data proof | Fixture source confirmation; no real tenant data in simulation DB |
| E8 | Test command output | Full pytest output recorded as artifact |
| E9 | Rollback reference | `docs/rollback-monitoring-post-switch-safety-contract.md` or equivalent runbook |
| E10 | Owner approval for non-production simulation | Engineering owner sign-off (record ID or timestamp) |

---

## 9. Expected Simulation Outputs

A complete non-production simulation must produce all of the following outputs:

| # | Output | Description |
|---|---|---|
| O1 | Old path snapshot | Report output with `POSTED_LEDGER_REPORTS_ENABLED=OFF`; normalized per H28 |
| O2 | Posted-ledger path snapshot | Report output with flag ON in non-production; normalized per H28 |
| O3 | Normalizer output | Both snapshots passed through H28 normalizer; error codes if any |
| O4 | Comparator result | H29 comparator output: mismatch list, severity, mismatch codes |
| O5 | Accountant review report | H30 review report: overall_status, summary, recommended actions |
| O6 | Mismatch summary | Count of critical / high / medium / low / rounding_only mismatches |
| O7 | Gate outcome | `pass`, `pass_with_rounding`, `fail`, or `blocked` |
| O8 | Promotion recommendation | One of: `proceed_to_next_stage`, `fix_and_retry`, `block_promotion` |

### Promotion Decision Rules

| Gate Outcome | Promotion Recommendation |
|---|---|
| `pass` | `proceed_to_next_stage` |
| `pass_with_rounding` | `proceed_to_next_stage` (with accounting owner sign-off) |
| `fail` (critical/high mismatch) | `block_promotion` |
| `blocked` (environment/guard failure) | `block_promotion` |
| `fail` (medium/low only) | `fix_and_retry` |

---

## 10. Non-Production Rollback / Disable Rules

If a critical mismatch or any production guard violation is detected during simulation:

| Step | Action |
|---|---|
| D1 | Immediately set `POSTED_LEDGER_REPORTS_ENABLED` to OFF in the non-production environment |
| D2 | Verify flag is OFF (env var absent or `""`) |
| D3 | Verify old report path restored and returning results |
| D4 | Record simulation result with `gate_outcome: blocked` or `fail` |
| D5 | Preserve all snapshot artifacts and comparator output |
| D6 | No production rollback needed — production was not changed in H33 |
| D7 | Update simulation result packet with rollback timestamp and trigger |

Non-production disable has **no RTO requirement** (production is unaffected), but should be completed within the simulation session.

---

## 11. Promotion Blockers

Any of the following blocks promotion from simulation to the next stage:

| # | Blocker | Severity |
|---|---|---|
| PB1 | Any critical mismatch in comparator output | CRITICAL |
| PB2 | Any high mismatch in comparator output | HIGH |
| PB3 | Tenant leakage detected | CRITICAL |
| PB4 | Missing required evidence/drilldown on material item | HIGH |
| PB5 | Status policy mismatch (voided/reversed rows in net totals) | CRITICAL |
| PB6 | Fixture load failure or fixture hash mismatch | HIGH |
| PB7 | DB classification uncertain or ambiguous | CRITICAL |
| PB8 | Environment classification uncertain | CRITICAL |
| PB9 | Balance.ge live connector active (`balance != demo_mode`) | CRITICAL |
| PB10 | Production data detected in simulation DB | CRITICAL |
| PB11 | No accountant review report produced | HIGH |
| PB12 | No rollback plan referenced | HIGH |
| PB13 | No owner approval for simulation | HIGH |
| PB14 | Feature flag state mismatch (flag shows ON when expected OFF or vice versa) | CRITICAL |

---

## 12. Simulation Result Packet

Every completed non-production simulation must produce a result packet conforming to this schema:

```json
{
  "simulation_id": "string — unique ID, e.g. SIM-2026-001",
  "environment": "disposable_local | staging | sandbox_tenant | ci_monkeypatch",
  "tenant_id": "string — non-production tenant ID, e.g. tenant_alpha",
  "feature_flag": "POSTED_LEDGER_REPORTS_ENABLED",
  "flag_state": "on | off",
  "db_classification": "string — disposable_local | staging | ci_no_db",
  "fixture_version": "string — fixture hash or version label",
  "migration_version": "string — migration version at time of simulation",
  "old_snapshot_id": "string — reference to old path snapshot artifact",
  "new_snapshot_id": "string — reference to posted-ledger path snapshot artifact",
  "comparison_result_id": "string — reference to H29 comparator output",
  "accountant_review_id": "string — reference to H30 review report",
  "gate_outcome": "pass | pass_with_rounding | fail | blocked",
  "promotion_recommendation": "proceed_to_next_stage | fix_and_retry | block_promotion",
  "rollback_reference": "string — docs/rollback-monitoring-post-switch-safety-contract.md",
  "created_at": "ISO 8601 UTC timestamp",
  "created_by": "Bridge Hub"
}
```

### Required Fields

All 18 fields are required. A simulation result packet missing any field is incomplete and cannot be used as promotion evidence.

---

## 13. CI / Monkeypatch Simulation Rules

CI and unit-test monkeypatch simulation is the lowest-risk simulation path:

1. **Allowed only in test scope.** Flag is set via environment variable override or monkeypatch; no Cloud Run mutation.
2. **No real DB.** `TEST_MODE=1`, `DATABASE_URL=""`. All DB calls mocked or skipped.
3. **No Cloud Run mutation.** Flag is set only for the duration of a single test process.
4. **No production data.** All data is synthetic dictionaries inside the test.
5. **Assert production guard blocks production.** Any test that simulates the flag ON must also assert that the guard function rejects a production environment classification.
6. **Assert unknown environment fails closed.** The flag parser must return OFF for any unknown environment string.
7. **Flag scope is test-local.** After the test session, the flag state is reset. No persistent env var is written.
8. **CI simulation results cannot be used for production promotion.** CI results inform the simulation plan but do not replace a staging simulation.

---

## 14. Safety Rules

These rules are non-negotiable for H33:

- H33 creates no DB.
- H33 runs no runtime API calls.
- H33 enables no feature flags.
- H33 mutates no Cloud Run environment variables.
- H33 activates no Balance.ge connector.
- H33 makes no connector changes.
- H33 uses no production data.
- H33 uses no real credentials.
- H33 makes no infrastructure changes.
- H33 makes no UI/static file changes.
- H33 does not modify any runtime code in `app/`.
- H33 does not modify any migration file in `app/storage/migrations/`.
- H33 does not modify `main.py`.
- H33 does not modify fixture JSON files.

---

## 15. H33 Results

_Placeholder — filled after tests pass:_

- H33 targeted tests: 29/29 passed
- H32 + H33 combined: 59/59 passed
- Related report/fixture tests: see test run output
- Full unit suite: see test run output
- Fixture JSON changed: no
- Simulation plan green: yes

---

## 16. Non-Goals

H33 explicitly does NOT:

- Create or connect to any DB.
- Execute SQL.
- Run database migrations.
- Load fixture data into any DB.
- Call runtime report APIs.
- Implement runtime simulation logic.
- Enable `POSTED_LEDGER_REPORTS_ENABLED` in any environment.
- Mutate Cloud Run service environment variables.
- Use production or customer data.
- Connect to Balance.ge or any ERP connector.
- Activate Balance.ge.
- Implement UI or static file changes.

---

## 17. Next Task

Only after PR merge, deploy, and live verification of H33:

**H34 — Disposable/Staging DB Runtime Comparison Execution Plan**

or, if a suitable non-production DB is confirmed available:

**H34 — Non-Production Feature Flag Simulation Execution Dry-Run**

H34 must not be started before H33 is live verified.
