# Bridge Hub — H65 Authenticated Report Endpoint Verification

## 1. Purpose

This document records the authenticated report endpoint deep verification following H64 production switch closure. H65 closes the remaining limitations from H64: M6 (tenant leakage deep check) and M7 (report mismatch deep check) require an authorized auth token to execute. H65 also confirms unauthenticated report endpoint protection is intact.

H65 does NOT change code, does NOT mutate Cloud Run env vars, does NOT touch production DB, does NOT activate Balance.ge, does NOT call write/posting/apply endpoints.

---

## 2. H64 Context

| Field | Value |
|---|---|
| H64 decision | PRODUCTION_SWITCH_COMPLETE_WITH_LIMITED_AUTH_DEEP_CHECKS |
| Live SHA | `50782e46c73214c5fde3b0b40362c7cfefbec26a` |
| `POSTED_LEDGER_REPORTS_ENABLED` | true |
| Balance.ge | `demo_mode` |
| Remaining limitations | M3/M4 (GCP Console), M6 (tenant leakage), M7 (report mismatch) |

---

## 3. Auth Token Handling

Auth token source: environment variable `H65_AUTH_TOKEN` only.

Rules applied:
- Token not printed, not committed, not stored in any doc or test file.
- Authorization header redacted in all output.
- Token used only for read-only GET endpoints.
- Write endpoints not called.

**H65 auth token availability: NOT AVAILABLE**

`H65_AUTH_TOKEN` environment variable was not set at time of H65 execution. Authenticated deep checks cannot proceed. Decision: `BLOCKED_AUTH_TOKEN_MISSING_FOR_DEEP_CHECKS`.

See `docs/h65-auth-token-handling-safety.md` for full token handling policy.

---

## 4. Unauthenticated Baseline Checks

All checks performed against production SHA `50782e46c73214c5fde3b0b40362c7cfefbec26a` at `https://fastapi-run-226875230147.europe-west1.run.app`.

### /version

| Field | Value | Status |
|---|---|---|
| HTTP status | 200 | ✅ PASS |
| commit_sha | `50782e46c73214c5fde3b0b40362c7cfefbec26a` | ✅ matches main HEAD |
| environment | production | ✅ PASS |
| app | Bridge Hub | ✅ PASS |

### /health

| Field | Value | Status |
|---|---|---|
| HTTP status | 200 | ✅ PASS |
| status | degraded (BALANCE_API_KEY missing — expected) | ✅ expected |
| environment | production | ✅ PASS |
| Balance.ge | demo_mode | ✅ NOT activated |
| Secrets exposed | none | ✅ PASS |

### Report endpoints without auth

| Endpoint | HTTP Status | Auth bypass? |
|---|---|---|
| GET /reports/trial-balance | 401 | NO ✅ |
| GET /reports/balance-sheet | 401 | NO ✅ |
| GET /reports/profit-loss | 401 | NO ✅ |
| GET /reports/vat | 401 | NO ✅ |
| GET /reports/ledger-summary | 401 | NO ✅ |
| GET /reports/status-summary | 401 | NO ✅ |
| GET /reports/source-summary | 401 | NO ✅ |

All 7 report endpoints return 401 without auth. No report data exposed. No auth bypass detected.

### Protected endpoints without auth

| Endpoint | HTTP Status | Auth bypass? |
|---|---|---|
| GET /approval/queue | 401 | NO ✅ |
| GET /connectors/balance/status | 401 | NO ✅ |
| GET /posting/balance-status | 401 | NO ✅ |

---

## 5. Authenticated Endpoint Matrix

**Status: BLOCKED — H65_AUTH_TOKEN not available**

| Endpoint | Planned check | Status |
|---|---|---|
| GET /reports/trial-balance | response shape, totals, tenant scope | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/balance-sheet | assets/liabilities/equity check | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/profit-loss | income/expense/net check | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/vat | input/output/net check | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/ledger-summary | line count, total check | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/status-summary | status fields check | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/source-summary | source fields check | BLOCKED_AUTH_TOKEN_MISSING |

---

## 6. HTTP Status Summary

| Check | Result |
|---|---|
| /version | 200 ✅ |
| /health | 200 ✅ |
| Report endpoints (unauthenticated) | 401 × 7 ✅ |
| Protected endpoints (unauthenticated) | 401 × 3 ✅ |
| Authenticated report checks | BLOCKED |
| 5xx errors | 0 |
| Auth bypass | 0 |
| Secrets exposed | 0 |

---

## 7. Response Shape Summary

Unauthenticated report endpoints return 401 — response shape not available. Full shape verification requires auth token.

Standard Bridge Hub error envelope expected on authenticated calls:
```json
{"ok": false, "message": "...", "data": null, "error": {"code": "...", "details": "..."}}
```

---

## 8. Error Summary

No unexpected errors encountered in unauthenticated checks. All 401 responses are expected and correct.

---

## 9. H65 Endpoint Verification Decision

**H65 Decision: `BLOCKED_AUTH_TOKEN_MISSING_FOR_DEEP_CHECKS`**

Unauthenticated baseline: all report and protected endpoints correctly return 401. No auth bypass. No secrets exposed. SHA `50782e46` matches main HEAD. `POSTED_LEDGER_REPORTS_ENABLED=true` confirmed via H64. Balance.ge `demo_mode` confirmed.

Authenticated deep checks (tenant leakage M6, report mismatch M7) cannot proceed without `H65_AUTH_TOKEN`. To complete H65, provide `H65_AUTH_TOKEN` as an environment variable pointing to a valid read-only production token and re-run H65 Phase 3-5.

---

## 10. Rollback Assessment

No rollback triggers fired during H65:
- No auth bypass detected
- No 5xx errors
- No secrets exposed
- No Balance.ge activation
- No production DB touched

**Rollback required: NO**
