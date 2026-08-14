# BIZ-2 Current State Audit — Cashflow & CFO Dashboard

**Date:** 2026-08-14  
**Task:** BIZ-2 — Cashflow Classification + CFO Dashboard Completion  
**Decision:** BIZ2_CURRENT_STATE_AUDIT_READY

---

## 1. Does Bridge Hub already generate cashflow?

**Partially.** `app/api/services/financial_statements_service.py` contains:
- `_build_cashflow_posted_ledger_query()` — a SQL stub that queries `jel.cashflow_category` (a DB column not yet populated by any classifier)
- No `build_cashflow_statement()` function is exported
- No cashflow route exists in `routes_financial_statements.py`

The stub queries `account_code LIKE '1%'` (cash/bank accounts) and groups by `cashflow_category`, but no code exists to populate that column with operating/investing/financing values.

**Conclusion:** Cashflow query scaffolding exists but classification logic and the exposed function do not.

---

## 2. Does it split operating / investing / financing?

**No.** No account-to-category mapping exists anywhere in the codebase.

The existing fixture `geotrade_expected_cashflow.json` contains:
- `_meta.gap_label: "EXPECTED_GAP_CASHFLOW_CLASSIFICATION"`
- Indirect method structure (net profit + adjustments)
- `cash_movements_direct` section with verified direct cash flows

---

## 3. Which accounts are currently classified?

None — no cashflow classification map exists. What exists:
- `_BALANCE_SHEET` map in `financial_statements_service.py`: assets/liabilities/equity classification for 35 accounts
- `_PNL` map: revenue/cogs/opex classification for 20 accounts
- `routes_aging.py` aging buckets: current(0-30), 31_60, 61_90, 91_120, over_120

---

## 4. Which GeoTrade cash movements are missing from cashflow?

All of them, since no cashflow service exists. Required classifications per spec:

| Movement | Amount (GEL) | Expected Category |
|---|---|---|
| Client payment (AR) | 1,888 | operating inflow |
| Customer advance | 1,000 | operating inflow |
| Supplier payment (AP) | 5,900 | operating outflow |
| Rent payment | 1,180 | operating outflow |
| Payroll payment | 2,730+70 (net+PIT) | operating outflow |
| PIT payment | 700 | operating outflow |
| Fixed asset (laptop) | 3,540 | investing outflow |
| Loan receipt | 10,000 | financing inflow |
| Loan principal repayment | 1,000 | financing outflow |
| Interest payment | 150 | operating outflow (policy: interest = operating) |
| Bank-to-cash transfer | 500 | internal — excluded |
| Petty cash expense | 118 | operating outflow |
| Depreciation 83.33 | — | non-cash — excluded |
| Accrued utility 300 | — | non-cash until paid — excluded |
| Prepaid insurance | 1,200 | operating outflow (when paid) |
| Prepaid monthly recognition | 100 | non-cash — excluded |
| FX revaluation | — | non-cash — excluded |
| Realized FX in payment | 50 | included in supplier payment |

---

## 5. Which CFO dashboard metrics exist?

`admin_dashboard_service.py` is an **ops/support** tool, not a financial CFO dashboard. It provides:
- System health (DB ping, connector status)
- Tenant list with plan, usage, draft count
- Tenant detail for support engineers
- Plan adjustment

**None** of the financial CFO metrics (cash position, P&L, VAT, AR/AP aging, RS.ge mismatches, fixed assets, payroll) are implemented in any dashboard service.

---

## 6. Which BIZ-1 dashboard metrics are missing?

All of them — there is no CFO financial dashboard service. Required:

| Metric Group | Status |
|---|---|
| Cash: bank + cash balances, net cashflow | Missing |
| Profitability: revenue, COGS, gross margin, net P&L | Missing (P&L exists, not in dashboard) |
| VAT: input/output/net position | Missing |
| AR/AP aging with 5 Bridge Hub buckets | Missing (aging routes exist, not in dashboard) |
| Inventory: value, quantity, low-stock | Missing |
| RS.ge: mismatch count, high-risk count | Missing |
| Workflow: unapproved drafts, posted entries | Missing |
| Fixed assets: cost, accum depr, NBV | Missing |
| Payroll: gross, tax, net payable | Missing |
| Period lock status | Missing |

---

## 7. Implementation Plan (BIZ-2)

1. **`app/api/services/cashflow_classification_service.py`** — pure functions, no DB
   - `INFLOW_MAP`, `OUTFLOW_MAP`, `NON_CASH_ACCOUNTS`, `INTERNAL_TRANSFER_PAIRS`
   - `classify_cashflow_line(dr, cr, amount)` → `{category, direction, amount}`
   - `build_cashflow_direct(lines)` → `{operating, investing, financing, internal, excluded}`
   - `build_cashflow_indirect(net_profit, adjustments, working_capital)` → indirect statement

2. **Add to `financial_statements_service.py`**:
   - `build_cashflow_statement(tenant_id, date_from, date_to)` using trial balance + classification

3. **Add to `routes_financial_statements.py`**:
   - `GET /reports/cashflow` endpoint

4. **`app/api/services/cfo_dashboard_service.py`** — pure aggregation
   - `build_cfo_dashboard(cash, pnl, vat, aging, inventory, rsge, drafts, fixed_assets, payroll, period_lock)`

5. **`app/api/routes_cfo_dashboard.py`** — DB-backed route calling cfo_dashboard_service

6. **Unit tests** — `test_cashflow_classification_biz2.py`, `test_cfo_dashboard_metrics_biz2.py`

7. **Integration tests** — add passing tests to `test_business_scenario_geotrade_full_coverage.py`

8. **Update fixtures** — remove gap_label from cashflow/CFO fixtures, mark `implemented: true`

---

## 8. Safety

- No RS.ge live endpoints touched
- No production DB mutations
- No Balance.ge activation
- Immutable core files untouched
