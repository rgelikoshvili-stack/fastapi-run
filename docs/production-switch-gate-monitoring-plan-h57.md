# Bridge Hub — H57 Production Switch Gate + Monitoring / Rollback Verification Plan

## 1. Purpose

This document defines the production switch gate checklist, required sign-offs, rollout stages, monitoring sentinels, and rollback procedure for enabling `POSTED_LEDGER_REPORTS_ENABLED` in production. H57 is a plan document only.

## 2. Non-Action Statement

**H57 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED` in production.**
**H57 does NOT mutate Cloud Run env vars.**
**H57 does NOT connect to production DB.**
**H57 does NOT execute any database migration against production.**
**H57 does NOT activate Balance.ge live.**
**H57 does NOT call authenticated production APIs.**
**H57 does NOT deploy any code.**
**H57 does NOT push any production configuration change.**

`POSTED_LEDGER_REPORTS_ENABLED` remains OFF/absent in production after H57.

---

## 3. Input Evidence H49–H56

| Task | Decision | Status |
|---|---|---|
| H49 Docker recheck | DOCKER_EVIDENCE_CAPTURED | ✅ |
| H50 Hash/approval preflight | PREFLIGHT_PASS | ✅ |
| H51 Owner approval | OWNER_APPROVAL_SIGNED | ✅ |
| H51 Final go gate | READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN | ✅ |
| H52 Local dry-run | SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE | ✅ |
| H53 Snapshot comparison | SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS | ✅ |
| H54 Accountant review | ACCOUNTANT_REVIEW_READY | ✅ |
| H55 Final evidence | FINAL_LOCAL_EVIDENCE_READY | ✅ |
| H56 Promotion decision | READY_FOR_PRODUCTION_SWITCH_PREPARATION_PLAN | ✅ |

---

## 4. Feature Flag Identity

| Property | Value |
|---|---|
| Flag name | `POSTED_LEDGER_REPORTS_ENABLED` |
| Current state | absent / OFF in production |
| Mechanism | Cloud Run environment variable |
| Behavior when absent | posted ledger reports disabled (fail-closed) |
| Behavior when set to `1` | posted ledger reports enabled |
| Rollback method | remove env var from Cloud Run service → redeploy |

---

## 5. Production Switch Remains OFF

`POSTED_LEDGER_REPORTS_ENABLED` is NOT enabled by H57. The switch requires:
- Explicit separate implementation task (H58 or later).
- Human owner sign-off on the switch plan.
- All no-go blockers cleared.
- Monitoring in place before switch.
- Rollback owner identified and on-call.

---

## 6. Required Sign-Offs

| Sign-Off | Owner | Required Before |
|---|---|---|
| Engineering owner approval of switch plan | ROLANDI GELIKOSHVILI | Switch execution |
| Accountant confirmation of local evidence | ROLANDI GELIKOSHVILI | Switch execution |
| Rollback owner identification | ROLANDI GELIKOSHVILI | Switch execution |
| Incident response owner | ROLANDI GELIKOSHVILI | Switch execution |

---

## 7. Required Rollout Stages

| Stage | Action | Validation |
|---|---|---|
| Pre-switch | Confirm POSTED_LEDGER_REPORTS_ENABLED absent | /health check, /version SHA confirmed |
| Pre-switch | Confirm Balance.ge demo_mode | /health connector.balance = demo_mode |
| Pre-switch | Confirm 0 failed tests on current main SHA | CI passing |
| Stage 1 — Canary (1 tenant) | Set POSTED_LEDGER_REPORTS_ENABLED=1 for one internal/test tenant | Monitor /health, 5xx, latency for 15 min |
| Stage 2 — Expand | Expand to all tenants if Stage 1 clean | Monitor for 30 min |
| Stage 3 — Full | Confirm stable across all tenants | Final health + test check |
| Post-switch | Document SHA, timestamp, decision | Evidence committed |

---

## 8. Required Monitoring

| Sentinel | Endpoint / Signal | Alert Threshold |
|---|---|---|
| M1 — Health | GET /health → HTTP 200 | any non-200 |
| M2 — Version | GET /version → commit_sha matches main | SHA mismatch |
| M3 — 5xx rate | Cloud Run request metrics | >0.1% over 5 min |
| M4 — Latency p95 | Cloud Run latency metric | >2× pre-switch baseline |
| M5 — Auth enforcement | GET /reports/trial-balance without token → HTTP 401 | any 200 without auth |
| M6 — Tenant leakage sentinel | Trial balance with tenant_alpha token must not return tenant_beta data | any cross-tenant data |
| M7 — Report mismatch sentinel | Local snapshot totals vs. production report totals | >0.01 GEL difference |
| M8 — Balance.ge guard | /health connector.balance must remain demo_mode until explicit live activation | any non-demo value |
| M9 — Feature flag state | /health or dedicated env check endpoint | unexpected POSTED_LEDGER_REPORTS_ENABLED=0 after enable |

---

## 9. Rollback Plan

If any sentinel triggers after switch, execute rollback immediately:

| Step | Action |
|---|---|
| R1 | Disable `POSTED_LEDGER_REPORTS_ENABLED`: remove env var from Cloud Run service |
| R2 | Trigger Cloud Run redeploy (or revert to previous revision) |
| R3 | Verify GET /health → HTTP 200, connector.balance = demo_mode |
| R4 | Verify GET /reports/trial-balance → HTTP 401 (unauthorized without token) |
| R5 | Verify GET /version → SHA matches last known-good commit |
| R6 | Notify rollback owner (ROLANDI GELIKOSHVILI) |
| R7 | Open incident record: timestamp, SHA before/after, sentinel that triggered, action taken |
| R8 | Do NOT re-enable until root cause identified and documented |

**Rollback target time: < 5 minutes from sentinel alert to flag disabled.**

---

## 10. No-Go Blockers

The production switch must NOT proceed if any of the following are true:

| Blocker | Condition |
|---|---|
| B1 | Tenant leakage detected in any test or monitoring check |
| B2 | Unbalanced totals in any report |
| B3 | Missing accountant review sign-off |
| B4 | Missing rollback owner |
| B5 | `POSTED_LEDGER_REPORTS_ENABLED` already enabled unexpectedly |
| B6 | Balance.ge live activation (non-demo mode) detected |
| B7 | Production data uncertainty (non-synthetic data in any new table) |
| B8 | Any CI test failure on main |
| B9 | Approval APPROVAL-2026-H50-001 expired (after 2026-05-25T16:00:00Z) without renewal |
| B10 | Missing monitoring sentinels M1–M9 |

**All B1–B10 must be clear before switch execution.**

---

## 11. Final H57 Decision

**H57 Decision: `PRODUCTION_SWITCH_PLAN_READY`**

All H49-H56 evidence complete. Switch plan documented. Monitoring sentinels M1–M9 defined. Rollback procedure R1–R8 documented. No-go blockers B1–B10 defined. Sign-off requirements documented.

`POSTED_LEDGER_REPORTS_ENABLED` remains OFF. Production switch requires separate implementation task with explicit owner sign-off.

---

## 12. Next Task

**H58 — Production Switch Approval Packet / Final Human Sign-Off**

H58 will:
1. Present the complete H49-H57 evidence chain to the engineering owner.
2. Request explicit sign-off on the production switch plan.
3. Record the sign-off decision.
4. If approved: schedule and execute the controlled production switch with monitoring active.
5. If rejected: document reason and plan next step.

`POSTED_LEDGER_REPORTS_ENABLED` must remain OFF until H58 sign-off is recorded.
