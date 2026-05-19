# Bridge Hub — H65 Report Mismatch Deep Check

## 1. Purpose

This document records the report mismatch deep check comparing authenticated production report output against the H53 synthetic fixture baseline. This is the H64 M7 remaining limitation closure attempt.

---

## 2. H53 Baseline

H53 established the following expected values using the synthetic test fixture on a local Docker PostgreSQL environment:

| Report | Metric | H53 Baseline Value |
|---|---|---|
| Full DB balance | Total volume | 34,469.00 GEL |
| Standard-net (tenant_alpha) | Volume | 23,945.00 GEL |
| Trial balance | DR total | 14,480.00 GEL |
| Trial balance | CR total | 14,480.00 GEL |
| Trial balance | DR = CR | YES (balanced) |
| P&L | Income | 2,300.00 GEL |
| P&L | Expense | 3,525.00 GEL |
| P&L | Net | -1,225.00 GEL |
| Balance sheet | Assets | 10,955.00 GEL |
| Balance sheet | Liabilities | 2,180.00 GEL |
| Balance sheet | Equity | 8,775.00 GEL |
| VAT | Input | 180.00 GEL |
| VAT | Output | 180.00 GEL |
| VAT | Net | 0.00 GEL |
| Comparison checks | Total | 10/10 PASS |

**Important:** Production data will differ from H53 synthetic fixture unless production was seeded with the same data. Comparison uses `structural_match` classification unless exact seed is confirmed.

---

## 3. Production Response Summary

**Status: BLOCKED — H65_AUTH_TOKEN not available**

Authenticated production report calls could not be executed. Response comparison is not possible without an auth token.

| Endpoint | Production response | Status |
|---|---|---|
| GET /reports/trial-balance | Not obtained | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/balance-sheet | Not obtained | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/profit-loss | Not obtained | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/vat | Not obtained | BLOCKED_AUTH_TOKEN_MISSING |

---

## 4. Comparison Method

| Comparison type | Condition |
|---|---|
| `exact_match` | Production seeded with same synthetic fixture as H53 |
| `structural_match` | Response shape and internal invariants correct; totals differ from H53 synthetic values |
| `blocked_if_no_auth` | Auth token not available — no comparison possible |
| `blocked_if_no_data` | Endpoint returns empty data set |
| `rollback` | Only if critical internal inconsistency (DR ≠ CR, 5xx, malformed JSON) |

---

## 5. Invariant Checks

| Invariant | Check | Status |
|---|---|---|
| I1 | Trial balance DR = CR | BLOCKED (no auth) |
| I2 | P&L net = income - expense | BLOCKED (no auth) |
| I3 | Balance sheet equity = assets - liabilities | BLOCKED (no auth) |
| I4 | VAT net = output - input | BLOCKED (no auth) |
| I5 | No negative impossible values | BLOCKED (no auth) |
| I6 | No 5xx | ✅ No 5xx on unauthenticated probes |
| I7 | No malformed JSON | ✅ All 401 responses well-formed |
| I8 | No secret fields in response | ✅ Confirmed on unauthenticated probes |

---

## 6. Mismatch Classification

**Classification: BLOCKED_AUTH_TOKEN_MISSING**

No production report data could be obtained. All invariant checks I1-I5 deferred. I6-I8 confirmed PASS via unauthenticated probes.

---

## 7. H65 Report Mismatch Decision

**H65 Report Mismatch Decision: `REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_AUTH_TOKEN`**

Auth token not available. Production report comparison against H53 baseline deferred. No 5xx, no malformed JSON, no secrets exposed in unauthenticated probes. Rollback not required. Deep check deferred to H65 re-run with auth token or H66 accountant review.
