# Bridge Hub BIZ-1 — GeoTrade Full Accounting Scenario

**Task:** BIZ-1 — GeoTrade Full Accounting & Financial Controller Test Pack  
**Company:** GeoTrade Test LLC | INN: 400000001 | VAT payer: yes  
**Period:** August 2026 | Currency: GEL | Basis: Accrual  
**Branch:** `codex/geotrade-full-accounting-test-pack`

---

## Scope

End-to-end test of Bridge Hub as accounting, financial controller, RS.ge-connected, and audit-safe system using fixtures and mocks only. No real DB, no live RS.ge, no production credentials.

---

## Account Code Reference (Bridge Hub COA)

| Account | Name | Type |
|---------|------|------|
| 1110 | სალარო (ნაღდი) | Asset — Cash |
| 1120 | საბანკო ანგ. | Asset — Bank |
| 1210 | მოთხ. კლ-ზე | Asset — AR |
| 1310 | მარ. / საქ. | Asset — Inventory |
| 1420 | გადახ. ავ. | Asset — Supplier Advances |
| 1430 | წინ. გადახ. ხ. | Asset — Prepaid Expenses |
| 1510 | ძირ. საშ. | Asset — Fixed Assets |
| 1520 | დარ. ამ. (კ.) | Contra-asset — Accumulated Depreciation |
| 3110 | კრ. დავ. | Liability — AP |
| 3120 | მიღ. ავ. | Liability — Customer Advances |
| 3130 | გად. ხ. | Liability — Salaries Payable |
| 3310 | დღგ გად. | Liability — Output VAT |
| 3311 | ჩათვ. დღგ | Asset — Input VAT |
| 3320 | PIT / საშ. | Liability — PIT Payable |
| 3330 | დასაქ. საპ. | Liability — Employee PAYG |
| 3335 | დამ. საპ. | Liability — Employer PAYG |
| 3410 | სასეხ.ვ.მ. | Liability — Short-term Loan |
| 3420 | გ.თ. | Liability — Interest/Accrued Payable |
| 4110 | საწ.კაპ. | Equity — Share Capital |
| 4210 | გ.მ.(RE) | Equity — Retained Earnings |
| 6110 | გ-ვ. შემ. | Revenue — Sales |
| 7110 | COGS | Expense — Cost of Goods |
| 7210 | ხ.ხ. | Expense — Salaries |
| 7310 | ქ.ხ. | Expense — Rent |
| 7410 | კ.ხ. | Expense — Utilities/Insurance |
| 7510 | სბ.სკ. | Expense — Bank Fees |
| 7520 | სბ.პ. | Expense — Interest |
| 7610 | ამ.ხ. | Expense — Depreciation |
| 7910 | სხვ.ხ. | Expense — Other (Office Supplies) |
| 7920 | გ.კ.ზ. | Expense — FX Exchange |

---

## Core Transaction Journal Summary

### Phase 2 — Purchase (100 Keyboards from Office Supplier LLC)
```
Dr 1310  Inventory        5,000.00
Dr 3311  Input VAT          900.00
  Cr 3110  AP                      5,900.00
```

### Phase 3 — Supplier Payment
```
Dr 3110  AP               5,900.00
  Cr 1120  Bank                    5,900.00
```

### Phase 4a — Sale (20 Keyboards to Client LTD)
```
Dr 1210  AR               1,888.00
  Cr 6110  Revenue                 1,600.00
  Cr 3310  Output VAT                288.00
```

### Phase 4b — COGS (FIFO: 20 × 50 GEL)
```
Dr 7110  COGS             1,000.00
  Cr 1310  Inventory               1,000.00
```

### Phase 5 — Customer Payment
```
Dr 1120  Bank             1,888.00
  Cr 1210  AR                      1,888.00
```

### Phase 6 — Rent
```
Dr 7310  Rent             1,000.00
Dr 3311  Input VAT          180.00
  Cr 3110  AP                      1,180.00
```

### Phase 7 — Payroll
```
Dr 7210  Salary           3,500.00
  Cr 3130  Net Salary Payable       2,730.00
  Cr 3320  PIT Payable                700.00
  Cr 3330  Employee PAYG               70.00
```

### Phase 8 — Fixed Asset (Laptop Lenovo)
```
Dr 1510  Fixed Assets     3,000.00
Dr 3311  Input VAT          540.00
  Cr 3110  AP                      3,540.00
```

### Phase 8 — Monthly Depreciation
```
Dr 7610  Depreciation        83.33
  Cr 1520  Accumulated Depr           83.33
```

### Phase 9 — Petty Cash
```
Dr 7910  Office Supplies    100.00
Dr 3311  Input VAT           18.00
  Cr 1110  Cash                       118.00
```

---

## Opening Balance (2026-08-01)

| Account | Debit | Credit |
|---------|-------|--------|
| 1110 Cash | 1,000 | |
| 1120 Bank | 20,000 | |
| 1210 AR | 1,500 | |
| 1310 Inventory | 2,000 | |
| 1510 Fixed Assets | 5,000 | |
| 1520 Accum Depr | | 500 |
| 3110 AP | | 2,500 |
| 3320 PIT Payable | | 300 |
| 4110 Equity | | 26,200 |
| **Total** | **29,500** | **29,500** |

---

## Expected P&L (August 2026 — Core Scenario)

| Item | Amount |
|------|--------|
| Sales Revenue | 1,600.00 |
| COGS | (1,000.00) |
| **Gross Profit** | **600.00** |
| Salary Expense | (3,500.00) |
| Rent Expense | (1,000.00) |
| Depreciation | (83.33) |
| Office Supplies | (100.00) |
| **Net Loss** | **(4,083.33)** |

---

## Expected Balance Sheet (2026-08-31)

**Assets = 25,204.67** | **Liabilities + Equity = 25,204.67**

| Assets | | Liabilities & Equity | |
|--------|---|---------------------|---|
| Cash | 1,382 | AP | 2,500 |
| Bank | 7,268 | Output VAT | 288 |
| AR | 1,500 | PIT Payable | 300 |
| Inventory | 6,000 | **Total Liabilities** | **3,088** |
| Input VAT | 1,638 | Equity | 26,200 |
| Fixed Assets (net) | 7,417 | Net Loss | (4,083) |
| | | **Total Equity** | **22,117** |
| **Total Assets** | **25,205** | **Total L+E** | **25,205** |

---

## VAT Summary

| | Amount |
|--|--------|
| Input VAT (3311) | 1,638.00 |
| Output VAT (3310) | 288.00 |
| **Net VAT Receivable** | **1,350.00** |
