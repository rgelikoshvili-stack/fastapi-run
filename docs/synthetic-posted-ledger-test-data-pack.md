# Bridge Hub — Synthetic Posted-Ledger Test Data Pack / Fixture Load Plan

## 1. Title

Bridge Hub — Synthetic Posted-Ledger Test Data Pack / Fixture Load Plan
Task: 11C-H25

---

## 2. Purpose

H25 defines a safe, fully synthetic fixture data pack intended for future disposable/staging DB verification of posted-ledger reports.

**H25 is docs + contract tests + fixture JSON design only.**

- H25 does **not** create a DB.
- H25 does **not** connect to a DB.
- H25 does **not** execute SQL.
- H25 does **not** run migrations.
- H25 does **not** load fixture data into any DB.
- H25 does **not** touch the production DB or Cloud Run DB.
- H25 does **not** enable feature flags (POSTED_LEDGER_REPORTS_ENABLED remains off).
- H25 does **not** activate Balance.ge.
- H25 does **not** change runtime report, posting, or approval behavior.
- H25 does **not** start H26.

The fixture pack is committed as a local JSON file only:
`tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json`

It is intended for a future H26 or H27 controlled DB fixture load dry-run, once a disposable PostgreSQL instance is available.

---

## 3. Background — H1–H24 Chain

| Task | Purpose |
|---|---|
| H1 | Found report ledger integrity risks — reports reading journal_drafts instead of immutable posted ledger |
| H2 | Defined posted-ledger schema contract (journal_entry_headers, lines, sources) |
| H3 | Defined posted-ledger migration plan |
| H4 | Authored migration 011_posted_journal_entries_schema.sql — additive only, not executed |
| H5–H10 | Covered posting service write, report migration, reversal/correction, evidence, backfill plan |
| H11–H12 | Local/test migration blocked by unavailable disposable PostgreSQL |
| H13–H17 | Feature-flagged runtime/report tests, drilldown contract, fixture verification framework |
| H18–H23 | Staging readiness, nonprod runtime switch, disposable DB setup planning |
| SEC-1 | Removed hardcoded production credentials from legacy scripts |
| ENC-1 | Cleaned Georgian mojibake from 4 backend files |
| H24 | Attempted disposable DB dry-run — BLOCKED safely (local PostgreSQL unavailable) |
| **H25** | **Define synthetic fixture pack before future DB execution (this task)** |

---

## 4. Non-Action Statement

H25 does NOT:

- Create any DB.
- Connect to any DB.
- Execute any SQL.
- Run any migration.
- Load fixture data into any DB.
- Use production data.
- Use customer data.
- Enable POSTED_LEDGER_REPORTS_ENABLED.
- Activate Balance.ge.
- Change any connector behavior.
- Change any runtime behavior.
- Change any infrastructure.
- Change UI/static files.
- Start H26.

---

## 5. Fixture Safety Rules

All fixture data must be:

- **Synthetic only** — entirely fictional, no real-world data.
- **No real person names** — use synthetic identifiers like `syn_user_alpha`.
- **No real company identifiers** — use `SYNTHETIC COMPANY ALPHA (test only)`.
- **No real tax IDs** — use synthetic codes like `SYN-CUST-0001`.
- **No real bank account numbers** — use synthetic account codes only.
- **No real payroll identities** — use `syn_employee_alpha` etc.
- **No real customer / supplier data** — use `SYNTHETIC CUSTOMER ALPHA`.
- **No live ERP identifiers** — no Balance.ge IDs, no RS.ge submission IDs.
- **All tenants synthetic** — `tenant_alpha`, `tenant_beta` only.
- **All evidence IDs synthetic UUIDs** — `00000000-0000-4003-8000-...`.
- **All posting log IDs synthetic UUIDs** — `00000000-0000-4004-8000-...`.
- **All source draft IDs synthetic UUIDs** — `00000000-0000-4005-8000-...`.
- **All dates clearly test-period** — period `2026-01` (fictional accounting period).
- **All amounts small and deterministic** — no amounts above 10 000 GEL except opening equity.
- **Safe to commit** — no PII, no secrets, no real data.

---

## 6. Synthetic Tenants

| Tenant ID | Name | Role |
|---|---|---|
| `tenant_alpha` | SYNTHETIC COMPANY ALPHA (test only) | Primary reporting tenant — all expected report totals computed for this tenant |
| `tenant_beta` | SYNTHETIC COMPANY BETA (test only) | Negative isolation tenant — its rows must never appear in `tenant_alpha` reports |

**Isolation rule:** Any report filtered to `tenant_alpha` must exclude all `tenant_beta` rows. Cross-tenant leakage must fail contract tests.

---

## 7. Fixture Categories

### Income
- H001: Posted service revenue — 1 000.00 GEL (plain, no VAT)
- H006: Posted service revenue with VAT output — 1 180.00 GEL (inclusive)
- H011: Posted product revenue — 500.00 GEL
- H012: Revenue correction (status=correction) — reduces H001 revenue by 200.00 GEL

### Expenses
- H002: Office expense — 500.00 GEL
- H005: Purchase with office expense + VAT input — 1 000.00 + 180.00 GEL
- H010: Bank fee — 25.00 GEL (reversed by H013)

### Assets
- H007: Cash receipt (bank inflow from customer) — 1 180.00 GEL
- H004: Fixed asset acquisition — 5 000.00 GEL
- H001/H006/H011: Accounts receivable movement

### Liabilities
- H005: Accounts payable (AP) credit from supplier purchase — 1 180.00 GEL
- H008: AP payment to supplier — 1 180.00 GEL (clears AP)
- H006: VAT Payable credit — 180.00 GEL
- H003: Salary payable — 1 600.00 GEL; Tax payable (PAYG) — 400.00 GEL

### Equity
- H009: Opening equity / owner capital contribution — 10 000.00 GEL

### VAT / Tax
- H005: VAT Input reclaimable — 180.00 GEL
- H006: VAT Output payable — 180.00 GEL
- Net VAT position: 0.00 GEL (VAT input = VAT output in this fixture)

### Payroll
- H003 (3 lines): Gross salary expense (5200) 2 000.00; Salary payable (2300) 1 600.00; Tax payable PAYG (2310) 400.00

### Cash / Bank
- H007: Bank receipt — debit 1 010 +1 180.00
- H008: Bank payment to supplier — credit 1 010 −1 180.00
- H009: Opening capital — debit 1 010 +10 000.00
- H002: Office expense payment — credit 1 010 −500.00
- H004: Fixed asset purchase — credit 1 010 −5 000.00
- H010: Bank fee — credit 1 010 −25.00
- Net bank balance: 4 475.00 GEL

### Counterparty / Document Links
- `synthetic_customer_alpha` — linked to H001, H006, H007, H011 via metadata / sources
- `synthetic_supplier_alpha` — linked to H005, H008 via metadata / sources
- Document `doc_syn_invoice_001` — synthetic sales invoice
- Document `doc_syn_payroll_002` — synthetic payroll sheet
- Document `doc_syn_purchase_003` — synthetic purchase invoice

### Evidence / Audit
- `evidence_bundle_id` present on H003, H005, H006, H012
- `posting_log_id` present on all standard entries except H014 (voided)
- `source_draft_id` present on all entries (H013 is reversal, source_draft_id null)
- `journal_entry_sources` table links 4 entries to draft/doc/payroll source objects

### Corrections / Reversals
- **H012** (status=correction, correction_of_entry_id=H001): Revenue correction — reduces service revenue by 200.00 GEL. **Included in standard net.**
- **H013** (status=reversed, correction_of_entry_id=H010): Bank fee reversal entry. **Excluded from standard net.**
- H010 carries `reversed_by_entry_id=H013` to document the reversal linkage.

### Forbidden States (invalid_rows)
- status=`draft` — forbidden by ck_jeh_status constraint
- status=`approved` — forbidden by ck_jeh_status constraint
- status=`auto_approved` — forbidden by ck_jeh_status constraint
- Unbalanced entry (total_debit ≠ total_credit) — violates ck_jeh_balanced constraint

### Multi-Tenant Negative
- B001 (tenant_beta): 9 999.00 GEL service revenue — must never appear in tenant_alpha reports

---

## 8. Expected Report Impact Matrix

Standard net filter: `status IN ('posted', 'correction')` — excludes `reversed` and `voided`.

| Fixture | Trial Balance | P&L | Balance Sheet | VAT Register | Account Ledger | Counterparty Ledger | Payroll Ledger | Journal List | Cashflow |
|---|---|---|---|---|---|---|---|---|---|
| H001 service revenue | 1200 dr / 4100 cr | Income +1000 | AR +1000 | — | AR, 4100 | customer_alpha | — | ✓ | — |
| H002 office expense | 5100 dr / 1010 cr | Expense +500 | Bank −500 | — | 5100, 1010 | — | — | ✓ | Outflow |
| H003 payroll | 5200 dr / 2300,2310 cr | Expense +2000 | Liability +2000 | — | 5200, 2300, 2310 | — | ✓ | ✓ | — |
| H004 fixed asset | 1500 dr / 1010 cr | — | Asset +5000, Bank −5000 | — | 1500, 1010 | — | — | ✓ | Outflow |
| H005 purchase+VAT | 5100+1211 dr / 2100 cr | Expense +1000 | AP +1180, VAT Input +180 | VAT Input | 5100, 1211, 2100 | supplier_alpha | — | ✓ | — |
| H006 revenue+VAT | 1200 dr / 4100+2200 cr | Income +1000 | AR +1180, VAT Pay +180 | VAT Output | 1200, 4100, 2200 | customer_alpha | — | ✓ | — |
| H007 cash receipt | 1010 dr / 1200 cr | — | Bank +1180, AR −1180 | — | 1010, 1200 | customer_alpha | — | ✓ | Inflow |
| H008 AP payment | 2100 dr / 1010 cr | — | AP −1180, Bank −1180 | — | 2100, 1010 | supplier_alpha | — | ✓ | Outflow |
| H009 equity | 1010 dr / 3000 cr | — | Bank +10000, Equity +10000 | — | 1010, 3000 | — | — | ✓ | Inflow |
| H010 bank fee | 5300 dr / 1010 cr | Expense +25 | Bank −25 | — | 5300, 1010 | — | — | ✓ | Outflow |
| H011 product revenue | 1200 dr / 4200 cr | Income +500 | AR +500 | — | 1200, 4200 | customer_alpha | — | ✓ | — |
| H012 correction | 4100 dr / 1200 cr | Income −200 | AR −200, Revenue −200 | — | 4100, 1200 | — | — | ✓ | — |
| H013 reversed | **excluded** | **excluded** | **excluded** | **excluded** | drilldown only | — | — | detail only | **excluded** |
| H014 voided | **excluded** | **excluded** | **excluded** | **excluded** | drilldown only | — | — | detail only | **excluded** |
| B001 tenant_beta | **isolated** | **isolated** | **isolated** | **isolated** | **isolated** | **isolated** | — | **isolated** | **isolated** |

---

## 9. Expected Accounting Invariants

The following invariants must hold for all standard-net entries (posted + correction):

1. **Balance invariant:** `total_debit = total_credit` for every header.
2. **Line integrity:** No line has both `debit > 0` and `credit > 0`.
3. **Non-zero lines:** Every line has `debit > 0 OR credit > 0`.
4. **Tenant isolation:** `tenant_id` present and non-empty on every header and line.
5. **Status constraint:** `status IN ('posted', 'reversed', 'correction', 'voided')`.
6. **Standard net include:** posted + correction entries contribute to report totals.
7. **Standard net exclude:** reversed + voided entries excluded from standard report totals.
8. **Drilldown preservation:** `source_draft_id`, `posting_log_id`, `evidence_bundle_id` available in detail views.
9. **Multi-tenant isolation:** No `tenant_beta` rows appear in `tenant_alpha` reports.
10. **Trial balance:** Total DR = Total CR = 14 480.00 GEL across all 12 standard-net entries for `tenant_alpha`.
11. **Correction linkage:** `correction_of_entry_id` present on correction and reversal entries.
12. **Reversal linkage:** `reversed_by_entry_id` present on the original reversed entry.

---

## 10. Suggested Fixture JSON Schema

```json
{
  "metadata": {
    "version": "string",
    "task": "string",
    "description": "string — must state synthetic/no-PII",
    "period": "YYYY-MM",
    "currency": "GEL",
    "fixture_categories": ["list of categories"],
    "standard_net_filter_rule": "string",
    "accounting_invariants": ["list"]
  },
  "tenants": [
    {"id": "tenant_alpha", "name": "...", "role": "primary reporting tenant"},
    {"id": "tenant_beta",  "name": "...", "role": "negative isolation tenant"}
  ],
  "accounts": [{"code": "...", "name": "...", "category": "...", "normal_balance": "debit|credit"}],
  "counterparties": [{"id": "...", "name": "...", "type": "customer|supplier", "tax_id": "SYN-..."}],
  "documents": [{"id": "doc_syn_...", "type": "...", "counterparty_id": "..."}],
  "journal_entry_headers": [
    {
      "id": "UUID",
      "tenant_id": "string",
      "status": "posted|reversed|correction|voided",
      "source_draft_id": "UUID|null",
      "posting_log_id": "UUID|null",
      "evidence_bundle_id": "UUID|null",
      "total_debit": "number",
      "total_credit": "number",
      "reversed_by_entry_id": "UUID|null",
      "correction_of_entry_id": "UUID|null"
    }
  ],
  "journal_entry_lines": [
    {
      "id": "UUID",
      "journal_entry_id": "UUID",
      "tenant_id": "string",
      "line_no": "integer",
      "account_code": "string",
      "debit": "number >= 0",
      "credit": "number >= 0"
    }
  ],
  "journal_entry_sources": [
    {
      "id": "UUID",
      "journal_entry_id": "UUID",
      "tenant_id": "string",
      "source_type": "string",
      "source_id": "string"
    }
  ],
  "expected_reports": {
    "tenant_alpha": {
      "standard_net_filter": "string",
      "trial_balance": {"total_dr": "number", "total_cr": "number", "accounts": {}},
      "pl_summary": {"total_income": "number", "total_expense": "number", "net_profit_loss": "number"},
      "pl_detail": {},
      "balance_sheet_summary": {"total_assets": "number", "total_liabilities": "number", "total_equity": "number"},
      "balance_sheet_detail": {},
      "vat_register": {"vat_input_reclaimable": "number", "vat_output_payable": "number", "net_vat_position": "number"},
      "account_ledger": {},
      "counterparty_ledger": {},
      "payroll_ledger": {},
      "journal_entries_list": {"standard_net_count": "integer"},
      "cashflow": {"net_cash_movement": "number"}
    }
  },
  "invalid_rows": [
    {"status": "draft",    "note": "forbidden — ck_jeh_status violation"},
    {"status": "approved", "note": "forbidden — ck_jeh_status violation"},
    {"total_debit": "!= total_credit", "note": "forbidden — ck_jeh_balanced violation"}
  ]
}
```

---

## 11. Future Load Order

When a disposable PostgreSQL instance is available (H26 or later), the fixture must be loaded in this order to satisfy FK constraints:

1. **Tenants** — ensure tenant IDs exist (if tenants table is a dependency)
2. **Accounts** — chart-of-accounts reference rows (if accounts table exists)
3. **Counterparties** — reference entities (if counterparties table exists)
4. **Documents / Evidence placeholders** — source document reference rows
5. **Posting logs / Source draft placeholders** — posting log reference rows
6. **`journal_entry_headers`** — parent rows (FK target for lines and sources)
7. **`journal_entry_lines`** — FK references `journal_entry_headers(id)`
8. **`journal_entry_sources`** — FK references `journal_entry_headers(id)`
9. **Expected report snapshots** — store expected totals for automated report verification

**Load constraint:** Lines and sources must be loaded after headers. All other reference tables before headers.

---

## 12. Future Validation Plan

After fixture load into a disposable DB, the following must be verified:

| Validation | Check |
|---|---|
| Schema shape | All required tables and columns exist per migration 011 |
| Balancing | SELECT header_id, SUM(debit), SUM(credit) per entry — all must match total_debit/total_credit |
| Tenant isolation | Query tenant_alpha reports — assert no tenant_beta rows appear |
| Status rules | All headers have status IN ('posted', 'reversed', 'correction', 'voided') |
| Report expected totals | Trial Balance DR = CR = 14 480.00 for tenant_alpha standard net |
| Drilldown links | source_draft_id, posting_log_id, evidence_bundle_id accessible per header |
| Correction behavior | H012 appears in P&L; total revenue reduced by 200 |
| Reversal behavior | H013 excluded from standard net totals; H010's reversed_by_entry_id points to H013 |
| No real data | No patterns matching real Georgian personal IDs, tax IDs, or bank accounts |
| Deterministic totals | All report totals are exact, reproducible, and match expected_reports in fixture JSON |

---

## 13. Current H25 Output

- Fixture pack created as local synthetic JSON: `tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json`
- No DB load occurred.
- No SQL executed.
- No migration executed.
- No DB connection made.
- Intended for future H26 / H27 controlled DB fixture load dry-run, contingent on a disposable PostgreSQL instance becoming available.

---

## 14. Go / No-Go Criteria

**GO** to future fixture load only if ALL of the following are met:

- Disposable / staging PostgreSQL instance exists and is confirmed non-production
- Migration 011 applied successfully to the disposable DB
- Fixture pack passes all H25 contract tests (`test_synthetic_posted_ledger_fixture_pack_contract.py`)
- No real data present in fixture
- All fixture entries balance (total_debit = total_credit)
- Expected report totals are deterministic and documented
- Explicit operator approval for DB creation exists

**NO-GO** if ANY of the following:

- No disposable/staging DB available (result: BLOCKED, as in H24)
- Fixture contains real PII, company identifiers, or tax IDs
- Any fixture entry is unbalanced
- Fixture lacks multi-tenant isolation test rows
- Fixture lacks expected report totals
- POSTED_LEDGER_REPORTS_ENABLED would be enabled in production
- Feature flag would affect production behavior

---

## 15. Non-Goals for H25

H25 does NOT:

- Create any DB.
- Execute any SQL or migration.
- Connect to any DB.
- Load fixture data into any DB.
- Use production data or customer data.
- Use live ERP data or Balance.ge.
- Change runtime code behavior.
- Change UI/static files.
- Change approval or posting logic.
- Enable any feature flag in production.
- Start H26.

---

## 16. Next Task

Only after PR merge, deploy, and live verification of H25:

**Preferred:**
H26 — Synthetic Fixture Validation / Report Expected Totals Contract
(Validates fixture totals, report impact matrix, and invariants — docs + tests only, no DB)

**Alternative (if PostgreSQL becomes available):**
H26 — Controlled Disposable DB Fixture Load Dry Run
(Requires: disposable DB confirmed, migration applied, fixture load approved by operator)
