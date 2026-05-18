# Bridge Hub — H53 Local Report Snapshot Comparison

## 1. Purpose

This document compares H53 local report snapshots against the fixture `expected_reports` section. Filter: tenant_alpha, status IN ('posted','correction'). All comparisons against disposable local Docker DB (127.0.0.1:55433) only. No production DB used.

---

## 2. Comparison Inputs

| Field | Value |
|---|---|
| comparison_id | H53-COMPARISON-2026-001 |
| fixture_sha256 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 |
| migration_sha256 | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA |
| db_target | 127.0.0.1:55433 (local Docker only) |
| captured_at | 2026-05-18 |
| approval_id | APPROVAL-2026-H50-001 |
| scope | local_docker_postgres_dry_run_only |

---

## 3. Expected Report Source

Source: `expected_reports.tenant_alpha` in fixture JSON.
Filter: `status IN ('posted', 'correction')` — standard-net.
Excludes: reversed, voided.

---

## 4. Comparison Table

| # | Check | Expected | Actual | Severity | Result |
|---|---|---|---|---|---|
| C1 | Standard-net entry count | 12 | 12 | critical | ✅ PASS |
| C2 | Total volume DR (std-net) | 23,945.00 GEL | 23,945.00 GEL | critical | ✅ PASS |
| C3 | Total volume CR (std-net) | 23,945.00 GEL | 23,945.00 GEL | critical | ✅ PASS |
| C4 | P&L total_income | 2,300.00 GEL | 2,300.00 GEL | high | ✅ PASS |
| C5 | P&L total_expense | 3,525.00 GEL | 3,525.00 GEL | high | ✅ PASS |
| C6 | P&L net_profit_loss | -1,225.00 GEL | -1,225.00 GEL | high | ✅ PASS |
| C7 | Balance sheet total_assets | 10,955.00 GEL | 10,955.00 GEL | high | ✅ PASS |
| C8 | Balance sheet total_liabilities | 2,180.00 GEL | 2,180.00 GEL | high | ✅ PASS |
| C9 | VAT input reclaimable | 180.00 GEL | 180.00 GEL | medium | ✅ PASS |
| C10 | VAT output payable | 180.00 GEL | 180.00 GEL | medium | ✅ PASS |
| C11 | Tenant isolation (tenant_beta absent from tenant_alpha) | no leakage | WHERE enforced | critical | ✅ PASS |
| C12 | Full DB balance | 34,469.00 = 34,469.00 | 34,469.00 = 34,469.00 | critical | ✅ PASS |

**reports_compared: 12 | reports_passed: 12 | reports_failed: 0**

---

## 5. Mismatch Classifier

| Severity | Count |
|---|---|
| critical | 0 |
| high | 0 |
| medium | 0 |
| low | 0 |
| **Total mismatches** | **0** |

```json
{
  "comparison_id": "H53-COMPARISON-2026-001",
  "reports_compared": 12,
  "reports_passed": 12,
  "reports_failed": 0,
  "reports_blocked": 0,
  "mismatches": [],
  "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
  "final_decision": "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS"
}
```

---

## 6. Tenant Leakage Check

- All tenant_alpha queries: `WHERE tenant_id = 'tenant_alpha'` enforced.
- tenant_beta (1 header, 2 lines, 9,999.00 GEL) present in DB but never appears in tenant_alpha reports.
- No cross-tenant leakage detected. ✅

---

## 7. Balance Check

| Level | DR | CR | Balanced |
|---|---|---|---|
| Full DB (all entries, all tenants) | 34,469.00 GEL | 34,469.00 GEL | ✅ |
| tenant_alpha standard-net volume | 23,945.00 GEL | 23,945.00 GEL | ✅ |
| tenant_alpha trial balance net sum | 0.00 GEL | — | ✅ |
| tenant_beta | 9,999.00 GEL | 9,999.00 GEL | ✅ |

---

## 8. Final Comparison Decision

**H53 Decision: `SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS`**

12/12 checks PASS. 0 mismatches. All balances confirmed at every level. Tenant isolation holds. Cleanup complete. See [local-comparison-cleanup-h53-h57.md](local-comparison-cleanup-h53-h57.md).

---

## 9. Next Phase

H54 — Accountant Review Packet / Local Comparison Review.
