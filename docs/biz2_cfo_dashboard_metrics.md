# BIZ-2: CFO Dashboard Metrics — Implementation

**Service:** `app/api/services/cfo_dashboard_service.py`  
**Route:** `GET /reports/cfo-dashboard`  
**Decision:** BIZ2_CFO_DASHBOARD_PASS

---

## Overview

The CFO Financial Dashboard aggregates key business metrics across all financial domains. It is separate from `admin_dashboard_service.py` (which is an ops/support tool for system health and tenant management).

Entry points:
- `build_cfo_dashboard_from_data(...)` — pure function, no DB, fully testable
- `build_cfo_dashboard(tenant_id, as_of, date_from, date_to)` — DB-backed async

---

## Dashboard Sections

### Cash Position

| Metric | Source | Account |
|---|---|---|
| cash_1110 | Trial balance | 1110 |
| bank_1120 | Trial balance | 1120 |
| total_liquid | 1110 + 1120 | — |
| net_cashflow | Cashflow service | net_change_in_cash |
| operating_cf | Cashflow service | operating.net |
| investing_cf | Cashflow service | investing.net |
| financing_cf | Cashflow service | financing.net |

### Profitability

| Metric | Source |
|---|---|
| revenue | P&L service revenue.total |
| cogs | P&L service cogs.total |
| gross_profit | P&L gross_profit |
| gross_margin_pct | gross_profit / revenue × 100 |
| opex | P&L opex.total |
| net_profit_loss | P&L ebit |
| net_margin_pct | ebit / revenue × 100 |

Note: `net_margin_pct = None` when revenue = 0 (no division by zero).

### VAT Position

| Metric | Account |
|---|---|
| input_vat | 3311 (debit = receivable from tax authority) |
| output_vat | 3310 (credit balance = payable) |
| net_vat | input_vat − output_vat |
| label | `vat_receivable` if net ≥ 0, else `vat_payable` |

### AR Status

| Metric | Source |
|---|---|
| total_ar | Sum of all AR aging buckets |
| overdue_ar | Sum of 31_60 + 61_90 + 91_120 + over_120 |
| buckets | 5 Bridge Hub buckets (current_0_30 ... over_120) |

### AP Status

Same bucket structure as AR.

### Inventory

| Metric | Source |
|---|---|
| total_inventory_value | Trial balance account 1310 |
| low_stock_count | 0 (no low-stock rules implemented) |
| low_stock_note | Documented limitation |

**Limitation:** Low-stock rules (reorder points, min quantities) are not yet implemented. `low_stock_count` is always 0. This is documented in the metric and is a known partial implementation.

### RS.ge Summary

| Metric | Source |
|---|---|
| synced_documents | COUNT rsge_documents WHERE tenant_id |
| synced_waybills | COUNT rsge_waybills WHERE tenant_id |
| total_mismatches | COUNT WHERE mismatch_type IS NOT NULL |
| high_risk_mismatches | COUNT WHERE risk_level = 'high' |
| unlinked_waybills | COUNT WHERE linked_invoice_id IS NULL |

**Security:** No RS.ge access token, pin token, or credentials appear in dashboard output. `_strip_forbidden()` removes any forbidden field.

### Workflow

| Metric | Source |
|---|---|
| unapproved_drafts | journal_drafts WHERE status = 'drafted' |
| awaiting_cfo | journal_drafts WHERE status = 'awaiting_cfo' |
| posted_entries | journal_drafts WHERE status = 'posted' |
| rejected | journal_drafts WHERE status = 'rejected' |
| total_drafts | Total count |

### Fixed Assets

| Metric | Account |
|---|---|
| cost | 1510 (debit balance) |
| accumulated_depr | abs(1520) (credit balance → positive) |
| net_book_value | cost − accumulated_depr |
| monthly_depreciation | Sum of 7610 debit entries in period |

### Payroll

| Metric | Source |
|---|---|
| gross | From payroll_data input |
| pit | PIT withheld |
| payg_employee | Employee pension (2%) |
| payg_employer | Employer pension (2%) |
| net_payable | Net salary payable to employees |

### Period Lock

| Metric | Source |
|---|---|
| locked | period_locks table (period_key = YYYY-MM) |
| period | Period key string |

---

## Aging Buckets

Must use Bridge Hub bucket names (confirmed from `routes_aging.py`):

| Bucket | Days |
|---|---|
| current_0_30 | 0–30 days |
| 31_60 | 31–60 days |
| 61_90 | 61–90 days |
| 91_120 | 91–120 days |
| over_120 | 120+ days |

---

## Security Rules

The dashboard never exposes:
- `access_token`
- `pin_token`
- `Authorization`
- `password`
- `JWT_SECRET`
- `DATABASE_URL`
- `ANTHROPIC_API_KEY`
- `BALANCE_API_KEY`
- `VAULT_ENCRYPTION_KEY`

`_strip_forbidden()` is applied to the final output before returning.

---

## API

```
GET /reports/cfo-dashboard
GET /reports/cfo-dashboard?as_of=2026-08-31
GET /reports/cfo-dashboard?date_from=2026-08-01&date_to=2026-08-31
```

Permission required: `reports:read`

---

## Production-Ready vs Partial Metrics

| Section | Status | Note |
|---|---|---|
| Cash position | Production-ready | Reads from 1110/1120 |
| Profitability | Production-ready | Via financial_statements_service |
| VAT position | Production-ready | Via 3311/3310 trial balance |
| AR/AP aging | Production-ready when AR/AP data passed | |
| Inventory value | Production-ready | Account 1310 |
| Low-stock count | Partial — always 0 | No min-stock rules implemented |
| RS.ge summary | Production-ready | Queries rsge_* tables |
| Workflow counts | Production-ready | journal_drafts table |
| Fixed assets | Production-ready | 1510/1520 accounts |
| Payroll | Production-ready when payroll_data passed | |
| Period lock | Production-ready | period_locks table |

---

## Safety

- No RS.ge live calls
- No production DB mutations
- No Balance.ge activation
- No env vars changed
- Immutable core files untouched
- `_strip_forbidden()` applied on every response
