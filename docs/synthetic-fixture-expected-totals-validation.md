# Bridge Hub — H26 Synthetic Fixture Expected Totals Validation

## 1. Title

Bridge Hub — H26 Synthetic Fixture Expected Totals Validation

Task: 11C-H26 — Synthetic Fixture Validation / Report Expected Totals Contract
Branch: `codex/synthetic-fixture-expected-totals-contract`
Starting SHA: `ca25588d92f833931714b69056e51b1e83f8650e` (H25 merge)

---

## 2. Purpose

H26 validates the H25 synthetic posted-ledger fixture expected totals using pure local tests.

H26 **does not** create a DB.
H26 **does not** connect to a DB.
H26 **does not** execute SQL.
H26 **does not** run migrations.
H26 **does not** load fixtures into any DB.
H26 **does not** modify runtime report behavior.
H26 **does not** enable feature flags.
H26 **does not** activate Balance.ge.

All validation is performed by reading `tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json`
into memory in pure Python and computing report totals from the raw line data using `Decimal` arithmetic.
Calculated totals are compared against `expected_reports.tenant_alpha` snapshots.

---

## 3. H25 Fixture Context

H25 created a fully synthetic posted-ledger fixture pack:

| Property | Value |
|---|---|
| Tenants | 2 (`tenant_alpha`, `tenant_beta`) |
| Journal entry headers | 15 (14 tenant_alpha + 1 tenant_beta) |
| Journal entry lines | 33 (31 tenant_alpha + 2 tenant_beta) |
| Sources | 4 |
| Invalid rows | 4 (draft, approved, auto_approved, unbalanced) |
| Expected report types | 11 |
| Real PII | None |
| Real tax IDs | None |
| Real bank accounts | None |
| DB load | None — fixture JSON only |

Standard net filter: `status IN ('posted', 'correction')` — excludes `reversed` and `voided`.

tenant_alpha standard net entries: 12 headers (H001–H012), all posted or correction status.

---

## 4. Validation Methodology

1. Load `synthetic_posted_ledger_fixture_pack.json` from disk (read-only, no DB).
2. Select `tenant_alpha` as the primary reporting tenant.
3. Exclude all `tenant_beta` rows from tenant_alpha calculations.
4. Apply standard net filter: `status IN ('posted', 'correction')`.
5. Excluded statuses: `reversed`, `voided`, `draft`, `approved`, `auto_approved`.
6. Collect all `journal_entry_lines` whose `journal_entry_id` belongs to a standard-net header.
7. Use `Decimal` arithmetic throughout to avoid floating-point error.
8. Group lines by `account_code` and sum `debit` and `credit` columns.
9. Derive account net balances using normal-balance direction (debit-normal: assets, expenses; credit-normal: liabilities, equity, income).
10. Compare calculated totals against `expected_reports.tenant_alpha` snapshots.
11. Validate structural links: `correction_of_entry_id`, `reversed_by_entry_id`, `evidence_bundle_id`, `posting_log_id`, `source_draft_id`.

---

## 5. Expected Status Behavior

| Status | Standard Net | Notes |
|---|---|---|
| `posted` | **Included** | Core ledger status |
| `correction` | **Included** | Corrective adjustments; must have `correction_of_entry_id` |
| `reversed` | **Excluded** | Net-out entries; excluded from standard reports |
| `voided` | **Excluded** | Cancelled entries; excluded from standard reports |
| `draft` | **Never included** | Forbidden by DB constraint; in `invalid_rows` only |
| `approved` | **Never included** | Forbidden by DB constraint; in `invalid_rows` only |
| `auto_approved` | **Never included** | Forbidden by DB constraint; in `invalid_rows` only |

Correction entries (`status='correction'`) are included in standard net but must carry a non-null `correction_of_entry_id`.

Reversal entries (`status='reversed'`) are excluded. The original entry (`status='posted'`) that was reversed retains its `reversed_by_entry_id` reference but stays in standard net — only the reversal itself is excluded.

---

## 6. Trial Balance Validation

Method: sum debit and credit columns by account code for all standard-net tenant_alpha lines.
Compute net balance per account (debit minus credit for debit-normal accounts; credit minus debit for credit-normal).

| Account | Normal | Net Balance | Derivation |
|---|---|---|---|
| 1010 Bank | DR | 4,475.00 | DR: H007(1180)+H009(10000)=11180; CR: H002(500)+H004(5000)+H008(1180)+H010(25)=6705; Net=4475 |
| 1200 AR | DR | 1,300.00 | DR: H001(1000)+H006(1180)+H011(500)=2680; CR: H007(1180)+H012(200)=1380; Net=1300 |
| 1211 VAT Input | DR | 180.00 | DR: H005(180); Net=180 |
| 1500 Fixed Assets | DR | 5,000.00 | DR: H004(5000); Net=5000 |
| 2100 AP | CR | 0.00 | CR: H005(1180); DR: H008(1180); Net=0 |
| 2200 VAT Payable | CR | 180.00 | CR: H006(180); Net=180 |
| 2300 Salary Payable | CR | 1,600.00 | CR: H003(1600); Net=1600 |
| 2310 Tax Payable | CR | 400.00 | CR: H003(400); Net=400 |
| 3000 Share Capital | CR | 10,000.00 | CR: H009(10000); Net=10000 |
| 4100 Service Revenue | CR | 1,800.00 | CR: H001(1000)+H006(1000)=2000; DR: H012(200); Net=1800 |
| 4200 Product Revenue | CR | 500.00 | CR: H011(500); Net=500 |
| 5100 Office Expense | DR | 1,500.00 | DR: H002(500)+H005(1000)=1500; Net=1500 |
| 5200 Salary Expense | DR | 2,000.00 | DR: H003(2000); Net=2000 |
| 5300 Bank Fees | DR | 25.00 | DR: H010(25); Net=25 |

Sum of debit-normal net balances: 4475+1300+180+5000+1500+2000+25 = **14,480.00**
Sum of credit-normal net balances: 180+1600+400+10000+1800+500 = **14,480.00**

Trial balance is balanced: total_dr = total_cr = **14,480.00 GEL**

---

## 7. P&L Validation

Standard net status filter applies. Income accounts have credit-normal balances; expense accounts have debit-normal balances.

| Category | Account | Net Balance |
|---|---|---|
| Income | 4100 Service Revenue | 1,800.00 |
| Income | 4200 Product Revenue | 500.00 |
| **Total Income** | | **2,300.00** |
| Expense | 5100 Office Expense | 1,500.00 |
| Expense | 5200 Salary Expense | 2,000.00 |
| Expense | 5300 Bank Fees | 25.00 |
| **Total Expense** | | **3,525.00** |
| **Net Profit / (Loss)** | | **-1,225.00** |

H012 correction reduces 4100 Service Revenue by 200 (DR 4100 200) and is included in standard net.

P&L summary: total_income=2,300.00; total_expense=3,525.00; net_profit_loss=-1,225.00

---

## 8. Balance Sheet Validation

Method: net balances from trial balance grouped by category.

**Assets** (debit-normal net balances):

| Account | Balance |
|---|---|
| 1010 Bank | 4,475.00 |
| 1200 AR | 1,300.00 |
| 1211 VAT Input | 180.00 |
| 1500 Fixed Assets | 5,000.00 |
| **Total Assets** | **10,955.00** |

**Liabilities** (credit-normal net balances):

| Account | Balance |
|---|---|
| 2100 AP | 0.00 |
| 2200 VAT Payable | 180.00 |
| 2300 Salary Payable | 1,600.00 |
| 2310 Tax Payable | 400.00 |
| **Total Liabilities** | **2,180.00** |

**Equity**:

| Component | Balance |
|---|---|
| 3000 Share Capital | 10,000.00 |
| Retained earnings (P&L net) | -1,225.00 |
| **Total Equity** | **8,775.00** |

Balance sheet equation: Assets = Liabilities + Equity
10,955.00 = 2,180.00 + 8,775.00 ✓

---

## 9. VAT Register Validation

| Item | Account | Amount |
|---|---|---|
| VAT Input (reclaimable) | 1211 | 180.00 |
| VAT Output (payable) | 2200 | 180.00 |
| Net VAT position | | 0.00 |

VAT input comes from H005 (purchase invoice with 18% VAT on 1,000 expense = 180).
VAT output comes from H006 (sales invoice with 18% VAT on 1,000 revenue = 180).
Net VAT payable = 0.00 for period 2026-01.

Invalid/excluded rows (reversed, voided, draft) do not contribute to VAT register.

---

## 10. Ledger and Drilldown Validation

**Account Ledger (gross movements, standard net entries only):**

| Account | Total DR | Total CR | Net Balance |
|---|---|---|---|
| 1010 Bank | 11,180.00 | 6,705.00 | 4,475.00 DR |
| 1200 AR | 2,680.00 | 1,380.00 | 1,300.00 DR |

Note: H25 fixture originally had 1010_bank gross totals as 12,360/7,885 — these were corrected in H26 to 11,180/6,705 to match line-by-line calculation. Net balance (4,475) was already correct.

**Counterparty Ledger (from metadata_json.counterparty_id):**

| Counterparty | Total Invoiced | Total Received | Net Outstanding |
|---|---|---|---|
| synthetic_customer_alpha | 1,680.00 | 1,180.00 | 500.00 |
| synthetic_supplier_alpha | 1,180.00 | 1,180.00 | 0.00 |

Customer invoiced: H006 (1,180) + H011 (500) = 1,680 (entries tagged with counterparty_id in metadata).
Customer received: H007 (1,180).
Supplier purchased: H005 (1,180). Supplier paid: H008 (1,180).

**Drilldown fields present on headers:**

- `posting_log_id`: present on H001–H012 (all standard net entries except H013 reversal which has one, H014 voided has null)
- `source_draft_id`: present on most headers except H013 (reversal has null)
- `evidence_bundle_id`: present on H003, H005, H006, H012 (payroll, VAT, correction — high-evidence entries)

**Sources table:** 4 entries linking H001 (draft source), H003 (payroll doc), H005 (purchase invoice), H006 (sales invoice).

---

## 11. Cashflow Validation

Simplified direct method from account 1010 (Bank) movements, standard net entries only.

| Item | Amount |
|---|---|
| Opening balance | 0.00 |
| Cash inflows (1010 DR movements) | 11,180.00 |
| Cash outflows (1010 CR movements) | 6,705.00 |
| Net cash movement | 4,475.00 |
| Closing balance (1010 net) | 4,475.00 |

Inflows: H007 cash receipt (1,180) + H009 equity contribution (10,000) = 11,180.
Outflows: H002 office expense (500) + H004 fixed asset (5,000) + H008 AP payment (1,180) + H010 bank fee (25) = 6,705.

H010 (bank fee, status=posted) is included in standard net. H013 (reversal of H010, status=reversed) is excluded.

---

## 12. Tenant Isolation Validation

`tenant_beta` has one posted entry (B001) with total_debit = total_credit = 9,999.00 GEL.

All tenant_alpha expected report totals must be computed using only tenant_alpha lines. The 9,999.00 figure must not appear in any tenant_alpha expected report total.

Cross-tenant leakage contract: if a test inadvertently includes tenant_beta lines in tenant_alpha totals, the trial balance total would become 14,480 + (9,999×2) = 33,478 — a clearly wrong value that the contract test detects.

tenant_beta has its own `expected_reports.tenant_beta` section documenting the isolation requirement.

---

## 13. No Real Data Validation

- No real personal identification numbers (Georgian 11-digit PIDs).
- No real company tax registration numbers (Georgian 9-digit company IDs).
- No real IBAN or bank account numbers.
- No real company names (LLC, Ltd., Inc., GmbH, სს, შპს, etc.).
- No real email addresses (gmail, yahoo, hotmail).
- All counterparty IDs are `SYN-CUST-0001` / `SYN-SUPP-0001` format — clearly synthetic.
- All tenant IDs are `tenant_alpha` / `tenant_beta` — clearly synthetic.
- All UUIDs use `00000000-0000-4000-8000-...` or `00000000-ffff-...` pattern — clearly synthetic.

---

## 14. H26 Results

| Test group | Result |
|---|---|
| H26 targeted (27 tests) | 27/27 passed |
| H25 + H26 combined (47 tests) | 47/47 passed |
| Related report/fixture tests | all passed |
| Full unit suite | 4004+ passed / 0 failed / 2 skipped |
| Fixture corrections | yes — account_ledger.1010_bank gross totals corrected |
| All totals consistent | yes — after correction |

**Fixture correction made in H26:**

File: `tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json`

Section: `expected_reports.tenant_alpha.account_ledger.1010_bank`

| Field | Old value | New value | Reason |
|---|---|---|---|
| `total_dr` | 12,360.00 | 11,180.00 | Computed from lines: H007(1180)+H009(10000)=11,180 |
| `total_cr` | 7,885.00 | 6,705.00 | Computed from lines: H002(500)+H004(5000)+H008(1180)+H010(25)=6,705 |
| `net_balance_dr` | 4,475.00 | 4,475.00 | Already correct; unchanged |

The original gross totals were inconsistent with both the line-by-line calculation and the cashflow section (which already showed the correct 11,180/6,705 values). No accounting logic changed; only the incorrect snapshot numbers were corrected.

---

## 15. Non-Goals

H26 does **not**:

- Create a DB.
- Connect to a DB.
- Execute SQL.
- Run migrations.
- Load fixture data into any DB.
- Use production data.
- Use real PII, tax IDs, or bank accounts.
- Modify runtime report service code.
- Modify connector or posting behavior.
- Activate Balance.ge.
- Enable POSTED_LEDGER_REPORTS_ENABLED.
- Change UI/static files.
- Change infrastructure.
- Change credentials.

---

## 16. Next Task

Only after PR merge, deploy, and live verification of H26:

**H27 — Synthetic Fixture Report Snapshot Contract / Old-vs-New Comparison Plan**

or, if local PostgreSQL becomes available:

**H27 — Controlled Disposable DB Fixture Load Dry Run**
