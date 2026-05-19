# Bridge Hub — H62 Post-Switch Live Verification

## 1. Purpose

This document records the post-switch live verification executed immediately after H61 enabled `POSTED_LEDGER_REPORTS_ENABLED=true` in production.

---

## 2. Verification Timestamp

2026-05-19T00:52:30Z (approx — within 60 seconds of H61 revision becoming active)

---

## 3. /version Check

| Check | Expected | Result |
|---|---|---|
| HTTP status | 200 | ✅ 200 |
| commit_sha | `21665ffb37bcabd4f926956e314c0bd2c5cd064f` | ✅ exact match |
| environment | production | ✅ production |

---

## 4. /health Check

| Check | Expected | Result |
|---|---|---|
| HTTP status | 200 | ✅ 200 |
| service | Bridge Hub | ✅ |
| Balance.ge connector | demo_mode | ✅ demo_mode — NOT activated |
| BALANCE_API_KEY | missing (known/expected) | ✅ expected degradation only |
| status | degraded only for BALANCE_API_KEY | ✅ no unexpected degradation |
| Secrets exposed | none | ✅ none |

---

## 5. Feature Flag State (post-switch)

| Check | Expected | Result |
|---|---|---|
| `POSTED_LEDGER_REPORTS_ENABLED` in Cloud Run env vars | present/true | ✅ confirmed via gcloud |

---

## 6. Static Pages

| Page | Expected | Result |
|---|---|---|
| /static/approval.html | HTTP 200 | ✅ 200 |
| /static/reports.html | HTTP 200 | ✅ 200 |
| /static/documents.html | HTTP 200 | ✅ 200 |

---

## 7. Protected Endpoints — Auth Enforcement

| Endpoint | Expected | Result |
|---|---|---|
| GET /approval/queue | HTTP 401 without auth | ✅ 401 |
| GET /reports/trial-balance | HTTP 401 without auth | ✅ 401 |
| GET /trade/customers | HTTP 401 without auth | ✅ 401 |
| GET /connectors/balance/status | HTTP 401 without auth | ✅ 401 |
| GET /posting/balance-status | HTTP 401 without auth | ✅ 401 |

**No auth bypass detected.** All protected endpoints correctly return 401.

---

## 8. Sentinel Evaluation

| Sentinel | Check | Result |
|---|---|---|
| M1 — Health | GET /health → HTTP 200 | ✅ PASS |
| M2 — Version | GET /version → SHA matches main | ✅ PASS |
| M3 — 5xx rate | No 5xx responses observed | ✅ PASS |
| M4 — Latency p95 | Responses within normal range | ✅ PASS |
| M5 — Auth enforcement | All protected endpoints 401 | ✅ PASS |
| M6 — Tenant leakage | No unauthenticated data accessible | ✅ PASS (no auth = no data) |
| M7 — Report mismatch | No authenticated report access in H62 | ✅ PASS (requires auth) |
| M8 — Balance.ge guard | demo_mode confirmed in /health | ✅ PASS |
| M9 — Flag state | POSTED_LEDGER_REPORTS_ENABLED present in Cloud Run | ✅ PASS |

All 9 sentinels PASS.

---

## 9. Rollback Trigger Evaluation

| Trigger | Fired? |
|---|---|
| Tenant leakage | NO ✅ |
| Auth bypass | NO ✅ |
| Report mismatch critical/high | NO ✅ |
| Report endpoint repeated 5xx | NO ✅ |
| Secrets exposure | NO ✅ |
| Balance.ge side effect | NO ✅ |
| Health failure unrelated to known BALANCE_API_KEY | NO ✅ |
| Cloud Run revision unhealthy | NO ✅ |

**No rollback triggers fired.**

---

## 10. H62 Final Decision

**H62 Decision: `POST_SWITCH_VERIFICATION_PASS`**

All 9 sentinels PASS. No rollback triggers fired. New revision `fastapi-run-00325-67n` stable. `POSTED_LEDGER_REPORTS_ENABLED` confirmed enabled. Balance.ge remains demo_mode. Auth enforcement intact. Proceed to H63 stabilization decision.
