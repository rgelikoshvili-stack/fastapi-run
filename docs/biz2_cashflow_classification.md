# BIZ-2: Cashflow Classification — Implementation

**Service:** `app/api/services/cashflow_classification_service.py`  
**Route:** `GET /reports/cashflow`  
**Standard:** IAS 7 — Statement of Cash Flows  
**Decision:** BIZ2_CASHFLOW_CLASSIFICATION_PASS

---

## Classification Rules

### Cash Accounts

Accounts `1110` (cash register) and `1120` (bank) are the only cash accounts. A line is a cash movement only when at least one side is `1110` or `1120`.

### Operating Activities

**Inflows (DR=cash, CR=counterpart):**

| Counterpart | Meaning |
|---|---|
| 1210 | Customer receipt (AR cleared) |
| 3120 | Customer advance received |
| 6110/6120/6130 | Direct revenue receipt |

**Outflows (CR=cash, DR=counterpart):**

| Counterpart | Meaning |
|---|---|
| 3110 | Supplier payment (AP cleared) |
| 7310 | Rent paid directly |
| 3130 | Accrued expenses paid (salary, benefits) |
| 3360 | Net salary payment |
| 3320 | PIT payment to tax authority |
| 3330/3335 | PAYG (employee/employer pension) |
| 3340 | CIT payment |
| 1420 | Supplier advance (prepayment to supplier) |
| 1430 | Prepaid expense payment (insurance etc.) |
| 3420 | Interest payment (**operating per IAS 7.33 policy**) |
| 7520 | Interest paid directly |

### Investing Activities

**Outflows:**

| Counterpart | Meaning |
|---|---|
| 1510 | Fixed asset purchase |
| 1610 | Intangible asset purchase |
| 1620 | Long-term investment |

### Financing Activities

**Inflows:**

| Counterpart | Meaning |
|---|---|
| 3410/3510 | Loan received |
| 4110/4120 | Equity/capital contribution |

**Outflows:**

| Counterpart | Meaning |
|---|---|
| 3410/3510 | Loan principal repayment |
| 3370 | Dividend payment |

---

## Exclusions

### Internal Transfers
- `1110 ↔ 1120` (bank-to-cash, cash-to-bank) → category: `internal`, excluded from totals
- These do not change net cash position, so they must not inflate any section

### Non-Cash Items
- `7610` (depreciation): non-cash, excluded
- `1520` (accumulated depreciation): non-cash, excluded
- `7920` (unrealised FX revaluation): non-cash, excluded
- Any entry with no cash account on either side → non-cash, excluded

### Accrual vs Cash
- Accrual entry (e.g., Dr 7410 / Cr 3420 — utility accrual): no cash → excluded
- When the accrual is paid (Dr 3420 / Cr 1120): becomes operating outflow
- Monthly prepaid recognition (Dr 7410 / Cr 1430): non-cash, excluded
- Initial prepaid payment (Dr 1430 / Cr 1120): operating outflow (cash leaves)

---

## Policy Decisions

| Policy | Decision | Basis |
|---|---|---|
| Interest paid | Operating | IAS 7.33 (allowed alternative) |
| Dividends paid | Financing | IAS 7.34 |
| Internal bank↔cash | Excluded | Not a cash flow |
| Depreciation | Excluded | Non-cash |
| Unrealised FX | Excluded | Non-cash |

---

## GeoTrade Scenario Classification

| Movement | Amount | Category |
|---|---|---|
| Client payment (AR 1210 → bank) | 1,888 GEL | Operating inflow |
| Customer advance (3120 → bank) | 1,000 GEL | Operating inflow |
| Supplier payment (AP 3110 ← bank) | 5,900 GEL | Operating outflow |
| Rent (7310 ← bank) | 1,180 GEL | Operating outflow |
| Salary payment (3130 ← bank) | 2,730 GEL | Operating outflow |
| PIT payment (3320 ← bank) | 700 GEL | Operating outflow |
| Interest payment (3420 ← bank) | 150 GEL | Operating outflow |
| Insurance prepaid (1430 ← bank) | 1,200 GEL | Operating outflow |
| Fixed asset purchase (1510 ← bank) | 3,540 GEL | Investing outflow |
| Loan received (bank ← 3410) | 10,000 GEL | Financing inflow |
| Loan repayment (3410 ← bank) | 1,000 GEL | Financing outflow |
| Bank-to-cash (1110 ← 1120) | 500 GEL | Internal — excluded |
| Petty cash expense (supplier ← 1110) | 118 GEL | Operating outflow |
| Depreciation (7610 / 1520) | 83.33 GEL | Non-cash — excluded |
| Accrued utility (7410 / 3420) | 300 GEL | Non-cash until paid — excluded |
| Prepaid recognition (7410 / 1430) | 100 GEL | Non-cash — excluded |

---

## API

```
GET /reports/cashflow?date_from=2026-08-01&date_to=2026-08-31
GET /financial-statements/cashflow?date_from=...&date_to=...
```

**Response:** Standard `ok_response` envelope with:
- `operating`: `{inflows, outflows, net, lines}`
- `investing`: `{inflows, outflows, net, lines}`
- `financing`: `{inflows, outflows, net, lines}`
- `internal_transfers`: `{amount, lines}`
- `non_cash`: `{count}`
- `net_change_in_cash`: float
- `policy_notes`: list of policy documentation strings

---

## Safety

- No RS.ge calls
- No production DB mutations
- No live flags changed
- Immutable core files untouched
