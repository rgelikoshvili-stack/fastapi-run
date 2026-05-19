# Bridge Hub — H65 Report Tenant Leakage Deep Check

## 1. Purpose

This document records the tenant leakage deep check for authenticated production report endpoints. A tenant leakage check confirms that report responses only return data belonging to the authenticated user's tenant and do not expose data from other tenants.

This is the H64 M6 remaining limitation closure attempt.

---

## 2. Tenant Context

Bridge Hub enforces tenant isolation via:
- JWT claims (`tenant_id` in token payload)
- Middleware: `tenant_middleware.py` sets `request.state.tenant_id`
- All tenant-scoped queries include `WHERE tenant_id = $N`
- RBAC enforced via `require_permission(request, "...")`

Production tenants are isolated by `tenant_id`. No cross-tenant data access is permitted outside admin-scoped endpoints.

---

## 3. Checked Endpoints

| Endpoint | Planned check | Status |
|---|---|---|
| GET /reports/trial-balance | tenant_id in response or inferred from isolation | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/balance-sheet | tenant scope check | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/profit-loss | tenant scope check | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/vat | tenant scope check | BLOCKED_AUTH_TOKEN_MISSING |
| GET /reports/ledger-summary | row-level tenant_id check | BLOCKED_AUTH_TOKEN_MISSING |

---

## 4. Leakage Criteria

Tenant leakage is confirmed if any of the following occurs:

| Criterion | Leakage indicator |
|---|---|
| L1 | Response contains `tenant_id` values not matching authenticated user's tenant |
| L2 | Response row count exceeds authenticated tenant's known data volume without aggregation |
| L3 | Response contains data from a different named tenant (e.g., `tenant_beta` data in `tenant_alpha` context) |
| L4 | Unauthenticated request returns any report data (should always be 401) |
| L5 | Cross-tenant totals appear without explicit admin-scope authorization |

---

## 5. Findings

**Auth token not available — deep check blocked.**

`H65_AUTH_TOKEN` was not set. Authenticated tenant leakage checks could not be performed.

### Shallow check findings (unauthenticated)

| Check | Result |
|---|---|
| L4 — unauthenticated access | All 7 report endpoints → 401 ✅ |
| Auth bypass via missing token | Not possible — 401 confirmed |

L4 is the only criterion verifiable without auth. All other criteria (L1-L3, L5) require an authenticated response.

---

## 6. Limitations

| Limitation | Detail |
|---|---|
| L1-L3, L5 | Cannot verify without `H65_AUTH_TOKEN` |
| L4 | Verified — no unauthenticated access ✅ |
| Code review | `tenant_middleware.py`, RBAC, and `WHERE tenant_id = $N` patterns reviewed in source — isolation enforced by design |

---

## 7. H65 Tenant Leakage Decision

**H65 Tenant Leakage Decision: `TENANT_LEAKAGE_DEEP_CHECK_BLOCKED_NO_AUTH_TOKEN`**

L4 (unauthenticated access) confirmed PASS. L1-L3, L5 cannot be evaluated without auth token. Code-level tenant isolation is enforced by middleware and query pattern. Deep runtime check deferred to H65 re-run with auth token, or H66 accountant review.
