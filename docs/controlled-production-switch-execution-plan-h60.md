# Bridge Hub — H60 Controlled Production Switch Execution Plan

## 1. Purpose

This document defines the exact switch window, Cloud Run target, pre-switch go checklist, rollback command, and verification sequence for the controlled production enablement of `POSTED_LEDGER_REPORTS_ENABLED`. H60 is a planning and authorization document. Execution happens in H61.

---

## 2. H59 Sign-Off Reference

**Approval ID:** APPROVAL-2026-H58-001
**H59 Decision:** FINAL_SIGNOFF_APPROVED
**Signed at:** 2026-05-19T00:00:00Z
**Signed by:** ROLANDI GELIKOSHVILI (all 5 roles)
**Expires:** 2026-05-20T00:00:00Z

---

## 3. Current Live State (at plan creation)

| Property | Value |
|---|---|
| Local main HEAD | `21665ffb37bcabd4f926956e314c0bd2c5cd064f` |
| Live /version SHA | `21665ffb37bcabd4f926956e314c0bd2c5cd064f` |
| SHA match | ✅ exact match |
| /health status | HTTP 200 — degraded (BALANCE_API_KEY missing — expected, known) |
| `POSTED_LEDGER_REPORTS_ENABLED` | absent / OFF ✅ |
| Balance.ge | demo_mode ✅ |
| Protected endpoints | HTTP 401 without auth ✅ |
| Current active revision | `fastapi-run-00324-9hp` |
| Service | `fastapi-run` |
| Region | `europe-west1` |
| Project | `project-1e145fd0-c30e-4aac-a34` |

---

## 4. Switch Window

| Property | Value |
|---|---|
| Planned start | 2026-05-19T00:00:00Z |
| Planned end | 2026-05-19T01:00:00Z |
| Operator | ROLANDI GELIKOSHVILI |
| Rollback owner | ROLANDI GELIKOSHVILI |
| Monitoring owner | ROLANDI GELIKOSHVILI |

---

## 5. Pre-Switch Go Checklist

| Check | Required | Status |
|---|---|---|
| /version SHA matches main HEAD | yes | ✅ PASS |
| /health HTTP 200 | yes | ✅ PASS |
| `POSTED_LEDGER_REPORTS_ENABLED` absent/OFF | yes | ✅ PASS |
| Balance.ge demo_mode | yes | ✅ PASS |
| Protected endpoints HTTP 401 | yes | ✅ PASS |
| H59 FINAL_SIGNOFF_APPROVED | yes | ✅ PASS |
| Rollback owner confirmed reachable | yes | ✅ PASS |
| Monitoring owner confirmed active | yes | ✅ PASS |
| No active incident | yes | ✅ PASS |
| Current revision recorded | yes | `fastapi-run-00324-9hp` ✅ |

All pre-switch checks PASS. Proceed to H61.

---

## 6. Exact Enablement Action (H61)

```bash
gcloud run services update fastapi-run \
  --region europe-west1 \
  --update-env-vars POSTED_LEDGER_REPORTS_ENABLED=true
```

**Only `POSTED_LEDGER_REPORTS_ENABLED` is updated. No other env var is touched.**

---

## 7. Exact Rollback Action (H63 if needed)

```bash
gcloud run services update fastapi-run \
  --region europe-west1 \
  --remove-env-vars POSTED_LEDGER_REPORTS_ENABLED
```

**This removes the flag (restoring to absent/OFF). No other env var is touched.**

---

## 8. Verification Sequence After Switch (H62)

1. `curl -s .../version` — SHA must still match
2. `curl -i .../health` — HTTP 200 required
3. Protected endpoints still 401 without auth
4. `POSTED_LEDGER_REPORTS_ENABLED` reflected as enabled (via /health env_vars or report behavior)
5. Balance.ge still demo_mode
6. No 5xx spike
7. No secrets exposed

---

## 9. Stop / Rollback Triggers

| Trigger | Action |
|---|---|
| 5xx rate spike | Immediate rollback |
| Auth bypass (200 without token) | Immediate rollback |
| Tenant leakage | Immediate rollback |
| Report endpoint mismatch critical/high | Immediate rollback |
| Secrets exposed in response | Immediate rollback |
| Balance.ge non-demo side effect | Immediate rollback |
| /health non-200 unrelated to BALANCE_API_KEY | Immediate rollback |
| Cloud Run revision unhealthy | Immediate rollback |

---

## 10. H60 Final Decision

**H60 Decision: `CONTROLLED_SWITCH_EXECUTION_READY`**

H59 approved. Live state confirmed. Pre-switch checks all PASS. Rollback command defined. Verification sequence defined. Stop triggers defined. Proceed to H61.
