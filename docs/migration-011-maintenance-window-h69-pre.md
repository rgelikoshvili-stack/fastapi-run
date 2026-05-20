# Bridge Hub — Migration 011 Maintenance Window and Monitoring Plan

**Task:** 11C-H69-PRE-R2
**Type:** Operational gate — maintenance window and monitoring confirmation. No SQL executed.
**Date:** 2026-05-20
**Follows:** 11C-H68 (APPROVAL_READY_FOR_SIGNATURE_AFTER_BACKUP_AND_DRY_RUN)

---

## 1. Purpose

This document records the planned maintenance window for migration 011 production
execution and the associated monitoring plan. All fields must be confirmed before
H69 execution begins.

---

## 2. Maintenance Window

| Field | Value |
|---|---|
| planned_start | PENDING — engineering owner to confirm |
| planned_end | PENDING — engineering owner to confirm |
| estimated_duration | ≤ 10 minutes (migration is additive DDL only) |
| time_zone | UTC |
| traffic_expectation | Low traffic window preferred (off-peak hours) |
| communication_status | PENDING — team notification required |

---

## 3. Personnel

| Role | Name | Status |
|---|---|---|
| Operator (executes migration) | PENDING | PENDING |
| Rollback Owner (on-call) | PENDING | PENDING |
| Monitoring Owner (watches endpoints) | PENDING | PENDING |
| Engineering Owner (authorises go/no-go) | PENDING | PENDING |
| Accounting Owner (available for impact review) | PENDING | PENDING |

---

## 4. No-Concurrent-Deployment Confirmation

| Requirement | Status |
|---|---|
| No other Cloud Run deployments during window | PENDING |
| No schema changes from other tasks during window | PENDING |
| No Balance.ge activation during window | PENDING |
| No write or apply calls during window | PENDING |
| No fixture data loads during window | PENDING |
| No automated CI/CD deploy triggered during window | PENDING |

**All items must be confirmed PENDING → CONFIRMED before H69 execution.**

---

## 5. Pre-Execution Monitoring Checks (to run at window start)

The monitoring owner must verify all of the following immediately before psql execution:

| Check | Method | Expected |
|---|---|---|
| `/version` | HTTP GET | 200, H68+ SHA |
| `/health` | HTTP GET | 200 ok, no crash |
| `/health` connector status | JSON field | `balance: "demo_mode"` (not activated) |
| Unauthenticated report endpoints | HTTP GET | 401 — no auth bypass |
| Active incident | PagerDuty / monitoring | None active |
| 5xx spike | Monitoring dashboard | Zero |
| No concurrent deployment running | CI/CD console | Confirmed |

If any pre-execution check fails: **abort migration, do not proceed.**

---

## 6. Post-Execution Monitoring Window

After psql completes with exit code 0, the monitoring owner must observe for
a minimum of **30 minutes**:

| Check | Method | Expected |
|---|---|---|
| `/version` | HTTP GET | 200, same SHA (no deploy triggered) |
| `/health` | HTTP GET | 200, no crash |
| `/reports/trial-balance` (authenticated) | HTTP GET | No `journal_entry_lines` error |
| `/reports/balance-sheet` (authenticated) | HTTP GET | No missing-table error |
| `/reports/cashflow` (authenticated) | HTTP GET | Same data as pre-migration |
| No 5xx | All endpoints | Zero |
| `bank_transactions` data unchanged | `/reports/cashflow` | Unchanged |
| Balance.ge | `/health` | Still `demo_mode` |

---

## 7. Rollback Triggers

If any of the following occur during the 30-minute monitoring window:
immediately escalate to the rollback owner and initiate the appropriate
rollback level from `docs/migration-011-production-rollback-plan-h68.md`.

| Trigger | Action |
|---|---|
| App fails to start or `/health` returns 500 | Level 0: re-run migration; if fails → Level 1 PITR |
| Sustained 5xx spike (> 5% of requests) | Level 1: PITR restore |
| Auth bypass detected (unauthenticated 200 on protected endpoint) | Level 1: PITR restore |
| `psql` exits non-zero | Level 0: re-run (idempotent); if fails → Level 1 |
| Data corruption in `bank_transactions` or cashflow data | Level 1: PITR restore |

**Default rollback is restore-based (PITR). DROP TABLE is last resort only — requires explicit authorization.**

---

## 8. Decision

**Decision: `BLOCKED_MAINTENANCE_WINDOW_MISSING`**

Reason: No maintenance window timestamp, operator, rollback owner, or monitoring owner
has been confirmed. The no-concurrent-deployment confirmation is also pending. H69
execution must NOT begin until all fields in Sections 2–4 are confirmed.

---

## 9. Gate Closure Instructions

When the maintenance window is scheduled and all personnel confirmed:

1. Fill in `planned_start`, `planned_end`, operator, rollback owner, monitoring owner.
2. Change all PENDING items in Sections 3–4 to CONFIRMED.
3. Update decision to `MAINTENANCE_WINDOW_READY`.
4. Commit update and notify all named personnel.
5. Ensure monitoring owner has access to `/health`, `/version`, and report endpoints.
6. Ensure rollback owner has access to Cloud SQL console and restore procedure.

---

*Bridge Hub — Task 11C-H69-PRE-R2. Maintenance window gate documented.
No SQL executed. No production DB connection. Gate is BLOCKED pending window confirmation.*

---

## 10. Gate Update — 11C-H69-GATES

**Updated:** 2026-05-21
**Updated by:** Rolandi Gelikoshvili (r.gelikoshvili@gmail.com) — Engineering Owner

### Confirmed Maintenance Window

```
planned_start         : 2026-05-21 23:00 UTC
planned_end           : 2026-05-22 00:00 UTC
estimated_duration    : ≤ 10 minutes (additive DDL only)
time_zone             : UTC
traffic_expectation   : Low — confirmed off-peak window
communication_status  : CONFIRMED — single-engineer project, no external stakeholders
```

### Confirmed Personnel

| Role | Name | Email | Status |
|---|---|---|---|
| Operator (executes migration) | Rolandi Gelikoshvili | r.gelikoshvili@gmail.com | CONFIRMED |
| Rollback Owner (on-call) | Rolandi Gelikoshvili | r.gelikoshvili@gmail.com | CONFIRMED |
| Monitoring Owner (watches endpoints) | Rolandi Gelikoshvili | r.gelikoshvili@gmail.com | CONFIRMED |
| Engineering Owner (go/no-go) | Rolandi Gelikoshvili | r.gelikoshvili@gmail.com | CONFIRMED |
| Accounting Owner (available) | Rolandi Gelikoshvili | r.gelikoshvili@gmail.com | CONFIRMED |

### No-Concurrent-Deployment Confirmation

| Requirement | Status |
|---|---|
| No other Cloud Run deployments during window | CONFIRMED |
| No schema changes from other tasks during window | CONFIRMED |
| No Balance.ge activation during window | CONFIRMED |
| No write or apply calls during window | CONFIRMED |
| No fixture data loads during window | CONFIRMED |
| No automated CI/CD deploy triggered during window | CONFIRMED |

### Updated Decision

**Decision: `MAINTENANCE_WINDOW_READY`**

Window confirmed: 2026-05-21 23:00–00:00 UTC. All personnel confirmed.
No concurrent deployments confirmed. G6, G7, G8, G9 gates are now PASS.
H69 execution may begin at the confirmed window start.

---

*Gate updated by 11C-H69-GATES. Maintenance window confirmed. No SQL executed.*
