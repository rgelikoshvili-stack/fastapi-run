# Bridge Hub BIZ-1 — GeoTrade Full Coverage Scenarios

**Task:** BIZ-1 Phases 9-20  
**Covers:** Cash, Advances, Partial Payments, Returns, FIFO/WACG, FX, Loan, Accruals, Period Lock, Reversal

---

## Phase 9 — Cash Register / Petty Cash

**Bank to Cash:**
```
Dr 1110  Cash                500.00
  Cr 1120  Bank                       500.00
```

**Cash Expense (office supplies with VAT):**
```
Dr 7910  Office Supplies     100.00
Dr 3311  Input VAT            18.00
  Cr 1110  Cash                       118.00
```
Cash opening 1,000 + 500 in - 118 out = **1,382 closing**. Cash cannot go negative.

---

## Phase 10 — Advances

### Customer Advance (Client LTD pre-pays 1,000)
```
Dr 1120  Bank              1,000.00
  Cr 3120  Customer Advances          1,000.00
```
**Not revenue until invoice issued.**

**Advance Application (when invoice created):**
```
Dr 3120  Customer Advances 1,000.00
  Cr 1210  AR                        1,000.00
```

### Supplier Advance (pay 1,200 before invoice)
```
Dr 1420  Supplier Advances 1,200.00
  Cr 1120  Bank                      1,200.00
```
**Not expense/inventory until invoice arrives.**

**Advance Application:**
```
Dr 3110  AP               1,200.00
  Cr 1420  Supplier Advances         1,200.00
```

---

## Phase 11 — Partial Payments

Invoice: 2,400 GEL from supplier.
```
Payment 1 (1,000):  Dr 3110 AP 1,000 / Cr 1120 Bank 1,000  →  AP remaining: 1,400
Payment 2 (1,400):  Dr 3110 AP 1,400 / Cr 1120 Bank 1,400  →  AP remaining: 0
```
Aging uses remaining balance only. No overpayment allowed without explicit advance treatment.

---

## Phase 12 — Returns / Corrections

### Revenue Reversal (2 keyboards returned)
```
Dr 6110  Revenue            160.00
Dr 3310  Output VAT          28.80
  Cr 1210  AR                        188.80
```

### COGS Reversal (2 × 50 = 100)
```
Dr 1310  Inventory          100.00
  Cr 7110  COGS                       100.00
```

**Rules:**
- Correction document links to original invoice
- RS.ge correction action preview created — no automatic live mutation
- Original entries preserved in audit trail
- Inventory quantity increases by 2 after return

---

## Phase 13 — FIFO vs WACG

**Setup:** Layer 1: 100 units × 50 GEL = 5,000. Layer 2: 50 units × 60 GEL = 3,000. Sell 120 units.

| Method | COGS | Ending Inventory | Ending Value |
|--------|------|-----------------|-------------|
| FIFO | 100×50 + 20×60 = **6,200** | 30 units × 60 | **1,800** |
| WACG | 120 × (8000/150) = **6,400** | 30 × 53.33 | **1,600** |

**WACG avg cost:** 8,000 ÷ 150 = 53.3333 GEL/unit

Negative stock is blocked — `fifo_cogs` returns `unmatched_qty > 0` when demand exceeds supply.

---

## Phase 14 — FX Gain/Loss

**Invoice in USD (1,000 USD × 2.70 = 2,700 GEL):**
```
Dr 1310  Inventory        2,700.00
  Cr 3110  AP                        2,700.00
```

**Payment (1,000 USD × 2.75 = 2,750 GEL → FX loss 50):**
```
Dr 3110  AP              2,700.00
Dr 7920  FX Loss            50.00
  Cr 1120  Bank                      2,750.00
```

Month-end: unpaid FX balances revalued at closing rate. FX gain/loss recognized once.

---

## Phase 15 — Loan and Interest

```
Loan Receipt:       Dr 1120 Bank 10,000 / Cr 3410 Loan 10,000
Interest Accrual:   Dr 7520 Interest 150 / Cr 3420 Accrued Payable 150
Interest Payment:   Dr 3420 Payable 150 / Cr 1120 Bank 150
Principal Payment:  Dr 3410 Loan 1,000 / Cr 1120 Bank 1,000
```

**Gap:** `EXPECTED_GAP_LOAN_ACCOUNT_MAPPING` — loan amortisation schedule not automated. Manual journal workflow used.

---

## Phase 16 — Accruals and Prepaids

**Utility Accrual (invoice not yet received):**
```
Dr 7410  Utility Expense   300.00
  Cr 3420  Accrued Liabilities       300.00
```

**Prepaid Insurance (12 months, 1,200 total):**
```
Initial:  Dr 1430 Prepaid 1,200 / Cr 1120 Bank 1,200
Monthly:  Dr 7410 Insurance 100 / Cr 1430 Prepaid 100
```
Expense recognised once per month. No duplicate month-close.

---

## Phase 17 — Profit Tax / Dividend

**Gap:** `EXPECTED_GAP_PROFIT_TAX_DIVIDEND`

Georgian rates exist in `taxation_engine.py`:
- `DIVIDEND_WHT = 5%`
- `CIT_RATE = 15%`

Automated dividend journal generation not implemented. Manual journal required.

---

## Phase 18 — Period Lock

**Bridge Hub implementation:** `routes_period_lock.py` + `period_locks` table.

After period close:
- New postings blocked
- Adjustments/reversals create separate entries with audit trail
- Reports remain stable

**Gap (DB-dependent):** `EXPECTED_GAP_PERIOD_LOCK` — requires live DB for full enforcement test.

---

## Phase 19 — Reversal / Adjustment

**Wrong rent entry posted. Reversal process:**

1. Original entry (Dr 7310, Dr 3311, Cr 3110) — **preserved, not deleted**
2. Reversal entry (Cr 7310, Cr 3311, Dr 3110) — cancels original
3. Corrected entry — new correct amounts

All three entries linked in audit trail. Trial balance remains balanced after reversal.
