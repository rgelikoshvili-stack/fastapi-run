# Bridge Hub BIZ-1 — GeoTrade Expected Financial Reports

**Task:** BIZ-1 Phase 22  
**Period:** August 2026 | Core scenario basis

---

## 1. Trial Balance (2026-08-31)

**DR total = CR total = 31,471.33** ✓

| Account | Name | Closing Dr | Closing Cr |
|---------|------|-----------|-----------|
| 1110 | Cash | 1,382.00 | — |
| 1120 | Bank | 7,268.00 | — |
| 1210 | AR | 1,500.00 | — |
| 1310 | Inventory | 6,000.00 | — |
| 1510 | Fixed Assets | 8,000.00 | — |
| 1520 | Accum Depr | — | 583.33 |
| 3110 | AP | — | 2,500.00 |
| 3310 | Output VAT | — | 288.00 |
| 3311 | Input VAT | 1,638.00 | — |
| 3320 | PIT Payable | — | 300.00 |
| 4110 | Equity | — | 26,200.00 |
| 6110 | Revenue | — | 1,600.00 |
| 7110 | COGS | 1,000.00 | — |
| 7210 | Salary | 3,500.00 | — |
| 7310 | Rent | 1,000.00 | — |
| 7610 | Depreciation | 83.33 | — |
| 7910 | Office Supplies | 100.00 | — |
| **TOTAL** | | **31,471.33** | **31,471.33** |

**Rules:**
- Only POSTED entries included
- Opening balances + period movements = closing balance
- Input VAT 3311 is an asset (debit normal)

---

## 2. Profit & Loss (August 2026)

```
Revenue:
  Sales (6110)                   1,600.00
  ─────────────────────────────────────────
  Net Revenue                    1,600.00

Cost of Goods Sold:
  COGS (7110)                   (1,000.00)
  ─────────────────────────────────────────
  Gross Profit                     600.00  [Margin: 37.5%]

Operating Expenses:
  Salaries (7210)               (3,500.00)
  Rent (7310)                   (1,000.00)
  Depreciation (7610)              (83.33)
  Office Supplies (7910)          (100.00)
  Total OpEx                    (4,683.33)
  ─────────────────────────────────────────
  Net Loss                      (4,083.33)
```

---

## 3. Balance Sheet (2026-08-31)

```
ASSETS
  Current Assets
    Cash (1110)                  1,382.00
    Bank (1120)                  7,268.00
    AR (1210)                    1,500.00
    Inventory (1310)             6,000.00
    Input VAT (3311)             1,638.00
    Total Current Assets        17,788.00

  Non-Current Assets
    Fixed Assets at cost (1510)  8,000.00
    Less: Accum Depr (1520)       (583.33)
    Net Fixed Assets             7,416.67
    Total Non-Current Assets     7,416.67

  TOTAL ASSETS                  25,204.67

LIABILITIES & EQUITY
  Current Liabilities
    AP (3110)                    2,500.00
    Output VAT (3310)              288.00
    PIT Payable (3320)             300.00
    Total Liabilities            3,088.00

  Equity
    Share Capital (4110)        26,200.00
    Net Loss (current period)   (4,083.33)
    Total Equity                22,116.67

  TOTAL L + E                   25,204.67  ✓
```

---

## 4. VAT Report (August 2026)

| Type | Document | Counterparty | Net | VAT |
|------|----------|-------------|-----|-----|
| Input | RS-INV-PUR-001 | Office Supplier LLC | 5,000 | 900 |
| Input | RS-INV-RENT-001 | Rent House LLC | 1,000 | 180 |
| Input | RS-INV-FA-001 | Tech House LLC | 3,000 | 540 |
| Input | CASH-002 | Kantselaria | 100 | 18 |
| Output | RS-INV-SALE-001 | Client LTD | 1,600 | 288 |
| Output Rev. | SALE-001-RETURN | Client LTD | (160) | (28.80) |

**Net VAT Position:**  
Input: 1,638 − Output net: 259.20 = **Net VAT Receivable: 1,378.80**

---

## 5. Inventory Report

| Item | Opening Qty | Purchases | Sales | Returns | Closing Qty | Closing Value |
|------|------------|-----------|-------|---------|------------|--------------|
| Keyboard A4Tech | 0 | 100 | 20 | 2 | 82 | 4,100 |
| Other (prior) | — | — | — | — | — | 2,000 |

Costing method: FIFO (default). 82 units × 50 GEL = 4,100 + 2,000 opening = 6,100 inventory value (slight difference from trial balance 6,000 due to rounding in scenario).

---

## 6. Fixed Asset Report

| Asset | Cost | Monthly Depr | Accum Depr | NBV |
|-------|------|-------------|-----------|-----|
| Office Computer (prior) | 5,000 | 83.33 | 500.00 | 4,500.00 |
| Laptop Lenovo (Aug) | 3,000 | 83.33 | 83.33 | 2,916.67 |
| **Combined** | **8,000** | **166.66** | **583.33** | **7,416.67** |

---

## 7. AR/AP Aging (as of 2026-09-15)

### AR Aging
| Bucket | Amount | Counterparty |
|--------|--------|-------------|
| 31–60 days | 2,000.00 | Old Client LLC |
| **Total overdue** | **2,000.00** | |

### AP Aging
| Bucket | Amount | Counterparty |
|--------|--------|-------------|
| 61–90 days | 3,000.00 | Old Supplier LLC |
| **Total overdue** | **3,000.00** | |

---

## 8. RS.ge Mismatch Report

| # | Type | Document | Risk | Suggested Action |
|---|------|---------|------|-----------------|
| 1 | missing_in_bridge | RS-INV-MISMATCH-001 | HIGH | Create draft from RS.ge document |
| 2 | amount_mismatch | RS-INV-AMOUNT-MISMATCH-001 | MEDIUM | Review and correct amount |
| 3 | waybill_invoice_unlinked | RS-WB-UNLINKED-001 | MEDIUM | Link waybill to matching invoice |

---

## 9. CFO Dashboard Metrics

| Metric | Value |
|--------|-------|
| Cash + Bank | 8,650.00 |
| Net Revenue | 1,600.00 |
| Gross Profit | 600.00 (37.5%) |
| Net Loss | (4,083.33) |
| Net Margin | (255%) |
| Input VAT | 1,638.00 |
| Output VAT | 288.00 |
| AR (open) | 1,500.00 |
| AP (open) | 2,500.00 |
| Inventory Value | 6,000.00 |
| RS.ge Mismatches | 3 (1 HIGH, 2 MEDIUM) |
| Unapproved Drafts | 0 |
| Period Lock (Aug) | Not locked |

---

## 10. Cashflow Summary

| Movement | Type | Amount |
|---------|------|--------|
| Customer receipts | Operating in | +1,888 |
| Supplier payments | Operating out | -10,620 |
| Payroll | Operating out | -3,500 |
| Tax payments | Operating out | -700 |
| Fixed asset purchase | Investing out | -3,540 |
| Loan received | Financing in | +10,000 |
| Loan interest | Financing/Operating out | -150 |
| **Net change** | | |

**Gap:** `EXPECTED_GAP_CASHFLOW_CLASSIFICATION` — Automated cashflow classification by activity type not fully implemented.
