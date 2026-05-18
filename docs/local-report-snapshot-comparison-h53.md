# Bridge Hub — H53 Local Report Snapshot Comparison

## 1. Purpose

This document compares the H53 local report snapshots against the `expected_reports` section of the approved synthetic fixture (`tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json`). All comparisons are performed against the disposable local Docker DB (bridge-hub-h53-postgres, 127.0.0.1:55433) only. No production DB was used.

---

## 2. Comparison Inputs

| Input | Value |
|---|---|
| comparison_id | H53-COMPARISON-2026-001 |
| fixture_path | tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json |
| fixture_sha256 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 |
| migration_sha256 | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA |
| db_target | 127.0.0.1:55433 (local Docker only) |
| captured_at | 2026-05-18 (H53 execution) |
| approval_id | APPROVAL-2026-H50-001 |
| scope | local_docker_postgres_dry_run_only |

---

## 3. Expected Report Source

Expected values come from `expected_reports` in the fixture JSON. The filter is:

```
tenant_alpha only
status IN ('posted', 'correction')   -- standard-net filter
standard_net_excludes: ['reversed', 'voided']
```

---

## 4. Comparison Table

### C1 — Standard-Net Entry Count

| Metric | Expected | Actual | Severity | Result |
|---|---|---|---|---|
| standard_net_entry_count (tenant_alpha, posted+correction) | 12 | 12 | critical | ✅ PASS |

### C2 — Trial Balance (tenant_alpha, standard-net)

| Account | Expected net | Actual net | Result |
|---|---|---|---|
| 1010 Bank | +4,475.00 DR | +4,475.00 DR | ✅ PASS |
| 1200 AR | +1,300.00 DR | +1,300.00 DR | ✅ PASS |
| 1211 VAT Input | +180.00 DR | +180.00 DR | ✅ PASS |
| 1500 Fixed Assets | +5,000.00 DR | +5,000.00 DR | ✅ PASS |
| 2100 AP | 0.00 | 0.00 | ✅ PASS |
| 2200 VAT Payable | 180.00 CR | 180.00 CR | ✅ PASS |
| 2300 Salary Payable | 1,600.00 CR | 1,600.00 CR | ✅ PASS |
| 2310 Tax Payable | 400.00 CR | 400.00 CR | ✅ PASS |
| 3000 Share Capital | 10,000.00 CR | 10,000.00 CR | ✅ PASS |
| 4100 Service Revenue | 1,800.00 CR | 1,800.00 CR | ✅ PASS |
| 4200 Product Revenue | 500.00 CR | 500.00 CR | ✅ PASS |
| 5100 Office Expense | +1,500.00 DR | +1,500.00 DR | ✅ PASS |
| 5200 Salary Expense | +2,000.00 DR | +2,000.00 DR | ✅ PASS |
| 5300 Bank Fees | +25.00 DR | +25.00 DR | ✅ PASS |
| **Trial Balance DR column total** | **14,480.00** | **14,480.00** | ✅ PASS |
| **Trial Balance CR column total** | **14,480.00** | **14,480.00** | ✅ PASS |

### C3 — Total Volume (tenant_alpha, standard-net)

| Metric | Expected | Actual | Severity | Result |
|---|---|---|---|---|
| total_volume_dr | 23,945.00 GEL | 23,945.00 GEL | critical | ✅ PASS |
| total_volume_cr | 23,945.00 GEL | 23,945.00 GEL | critical | ✅ PASS |

### C4 — P&L Summary (tenant_alpha, standard-net)

| Metric | Expected | Actual | Severity | Result |
|---|---|---|---|---|
| total_income | 2,300.00 GEL | 2,300.00 GEL | high | ✅ PASS |
| total_expense | 3,525.00 GEL | 3,525.00 GEL | high | ✅ PASS |
| net_profit_loss | -1,225.00 GEL | -1,225.00 GEL | high | ✅ PASS |

### C5 — Balance Sheet (tenant_alpha, standard-net)

| Metric | Expected | Actual | Severity | Result |
|---|---|---|---|---|
| total_assets | 10,955.00 GEL | 10,955.00 GEL | high | ✅ PASS |
| total_liabilities | 2,180.00 GEL | 2,180.00 GEL | high | ✅ PASS |
| equity_total | 8,775.00 GEL | 8,775.00 GEL | high | ✅ PASS |
| assets = liabilities + equity | 10,955.00 = 2,180.00 + 8,775.00 | ✅ | high | ✅ PASS |

### C6 — VAT Register (tenant_alpha, standard-net)

| Metric | Expected | Actual | Severity | Result |
|---|---|---|---|---|
| vat_input_reclaimable | 180.00 GEL | 180.00 GEL | medium | ✅ PASS |
| vat_output_payable | 180.00 GEL | 180.00 GEL | medium | ✅ PASS |
| net_vat_position | 0.00 GEL | 0.00 GEL | medium | ✅ PASS |

### C7 — Tenant Isolation

| Check | Expected | Actual | Severity | Result |
|---|---|---|---|---|
| tenant_alpha entries isolated | tenant_beta must NOT appear in tenant_alpha queries | all tenant_alpha queries use WHERE tenant_id='tenant_alpha' | critical | ✅ PASS |
| tenant_beta exists in DB | 1 entry, 2 lines, 9,999.00 GEL balanced | 1 header, 2 lines, 9,999.00/9,999.00 GEL | critical | ✅ PASS |
| No cross-tenant leakage | none | none — WHERE clause enforced | critical | ✅ PASS |

---

## 5. Mismatch Classifier

| Severity | Meaning | Count |
|---|---|---|
| critical | tenant leakage, unbalanced totals, missing required table | 0 |
| high | account totals mismatch, P&L/balance sheet error | 0 |
| medium | optional report unavailable, VAT mismatch | 0 |
| low | formatting/rounding only | 0 |

**Total mismatches: 0**

---

## 6. Severity Counts

```json
{
  "critical": 0,
  "high": 0,
  "medium": 0,
  "low": 0,
  "total_mismatches": 0
}
```

---

## 7. Reports Compared

| Report | Status |
|---|---|
| C1 — Standard-net entry count | ✅ PASS |
| C2 — Trial balance by account (14 accounts) | ✅ PASS |
| C3 — Total volume (standard-net) | ✅ PASS |
| C4 — P&L summary | ✅ PASS |
| C5 — Balance sheet | ✅ PASS |
| C6 — VAT register | ✅ PASS |
| C7 — Tenant isolation | ✅ PASS |

**reports_compared: 7**
**reports_passed: 7**
**reports_failed: 0**
**reports_blocked: 0**

---

## 8. Tenant Leakage Check

No tenant leakage detected:
- All tenant_alpha queries explicitly filter `WHERE tenant_id = 'tenant_alpha'`.
- tenant_beta's entry (B001, 9,999.00 GEL) is present in the DB but never appears in tenant_alpha reports.
- No cross-tenant data contamination.

---

## 9. Balance Check

| Check | Value |
|---|---|
| Full DB balance (all entries, all tenants) | 34,469.00 / 34,469.00 GEL — balanced ✅ |
| tenant_alpha standard-net volume | 23,945.00 / 23,945.00 GEL — balanced ✅ |
| tenant_alpha trial balance net sum | 0.00 GEL — balanced ✅ |
| tenant_beta balance | 9,999.00 / 9,999.00 GEL — balanced ✅ |

All balances confirmed. Double-entry invariant holds at every level.

---

## 10. Final Comparison Decision

**H53 Comparison Decision: `SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS`**

All 7 reports compared. 7 of 7 passed. 0 mismatches. 0 critical/high/medium/low failures. Trial balance balanced. P&L, balance sheet, VAT, and tenant isolation all match expected_reports in fixture exactly. No production DB was used. Cleanup was completed (see [local-report-snapshot-cleanup-h53.md](local-report-snapshot-cleanup-h53.md)).

```json
{
  "comparison_id": "H53-COMPARISON-2026-001",
  "fixture_sha256": "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299",
  "migration_sha256": "F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA",
  "db_target": "127.0.0.1:55433 (local Docker only)",
  "captured_at": "2026-05-18",
  "reports_compared": 7,
  "reports_passed": 7,
  "reports_failed": 0,
  "reports_blocked": 0,
  "mismatches": [],
  "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
  "final_decision": "SUCCESS_LOCAL_REPORT_SNAPSHOT_COMPARISON_PASS"
}
```

---

## 11. Next Task

**H54 — Accountant Review Packet / Local Comparison Review**

H54 will:
1. Assemble the full accountant review packet from H53 evidence.
2. Document the delta between journal_drafts-based reports and posted-ledger reports.
3. Prepare the review packet for human accountant sign-off.
4. Record the review decision.

**None of H54's steps are executed in H53.**
