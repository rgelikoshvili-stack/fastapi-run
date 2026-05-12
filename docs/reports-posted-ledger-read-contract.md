# Bridge Hub — Reports Posted-Ledger Read Contract

**Task:** 11C-H7
**Type:** Contract document and tests only — no runtime code change, no SQL, no migration execution.
**Date:** 2026-05-12
**Follows:** 11C-H6 `tests/unit/test_posting_service_ledger_write_mock_contract.py`

---

## 1. Purpose

This contract defines the **future behavior** for all official financial reports to read from immutable posted ledger tables:

- `journal_entry_headers`
- `journal_entry_lines`

`journal_drafts` JSONB **is not official accounting truth**. All current report queries that source from `journal_drafts` are reading unconfirmed working data. This contract defines the target state that runtime report services must eventually reach.

`financial_statements_service.py`, `ledger_service.py`, and `routes_reports.py` are **not modified by this task**. No runtime behavior changes in H7. This document is the read contract that H8 will mock-test against, and that H12 will implement once the migration is executed and the posting ledger write path is live.

**No SQL is executed in this task. No production DB is touched. No migration is executed. No runtime report behavior is changed.**

---

## 2. Background

The H1–H6 foundation that makes this contract necessary:

| Task | Deliverable |
|---|---|
| H1 | Reports ledger integrity audit — CRITICAL: all reports source from `journal_drafts` JSONB; no immutable `journal_entries` table; `/reports/bs/detail` has no status filter; `/reports/pnl/detail` treats `simulated_success` as truth |
| H2 | Posted journal entries schema contract — defined `journal_entry_headers` + `journal_entry_lines` target schema, all required fields, 13 invariants, accounting truth principles |
| H3 | Safe migration plan — defined constraint requirements, index requirements, soft-link strategy, H4–H8 rollout sequence, safe backfill policy |
| H4 | SQL migration file `011_posted_journal_entries_schema.sql` created but **not executed** — additive-only DDL awaiting approved production execution |
| H5 | Posting service ledger write contract — defined when and how `posting_service` must write immutable ledger entries after successful real ERP connector posting |
| H6 | Posting service ledger write mock tests — 59 mock-based tests encoding all future ledger write policy rules without touching runtime code |
| H7 (this task) | Reports posted-ledger read contract — defines how all official reports must read from `journal_entry_headers` + `journal_entry_lines` in future H8 and H12 implementations |

Until H12 is implemented and the migration is executed, reports continue to read from `journal_drafts`. H7 prepares the read contract so H8 can be mock-tested safely and H12 can be implemented without ambiguity.

---

## 3. Background — Current Report Problem (from H1 Audit)

The H1 audit confirmed the following active problems in current reports:

| Report | Current Source | Problem |
|---|---|---|
| `/reports/trial-balance` | `journal_drafts` JSONB | Includes unapproved drafts in trial balance |
| `/reports/pnl/summary` | `journal_drafts` JSONB | No status filter |
| `/reports/bs/summary` | `journal_drafts` JSONB | No status filter |
| `/reports/pnl/detail` | `journal_drafts` JSONB | Treats `simulated_success` as truth |
| `/reports/bs/detail` | `journal_drafts` JSONB | No status filter at all |
| `/reports/vat` | `journal_drafts` JSONB | Tax data from unposted drafts |
| `/reports/account-ledger` | `journal_drafts` JSONB | Non-immutable ledger data |
| `/reports/counterparty-ledger` | `journal_drafts` JSONB | Non-immutable data |
| `/reports/payroll-ledger` | `journal_drafts` JSONB | Payroll from draft entries |

These problems are not corrected by H7. They are corrected only after H10 migration is executed and H12 implements the runtime report migration.

---

## 4. Official Report Truth Rule

The following principles define what constitutes official report truth in Bridge Hub. These rules apply to all future report read behavior.

| Source | Is official report truth? | Reason |
|---|---|---|
| `journal_drafts` JSONB | **NO** | Unconfirmed working data — not ERP-confirmed |
| Draft status entries | **NO** | Not yet reviewed or approved |
| `approved` status entries | **NO** | Approved for execution — not yet ERP-confirmed |
| `auto_approved` entries | **NO** | Automated approval — not ERP-confirmed |
| `simulated_success` entries | **NO** | Test/simulation state — no real ERP write occurred |
| `mock_posting` entries | **NO** | Development connector — no real ERP entry |
| `dry_run` entries | **NO** | Preview mode — explicitly not a real posting |
| Failed connector attempts | **NO** | Connector returned failure — no real ERP entry |
| `journal_entry_headers` where `status='posted'` | **YES** | ERP connector confirmed — immutable ledger entry |
| `journal_entry_headers` where `status='correction'` | **YES** | Correction of posted entry — immutable |
| `journal_entry_headers` where `status='reversed'` | **YES (with caveats)** | Reversal row exists — must be excluded from net totals unless reversal history view is requested |
| `journal_entry_headers` where `status='voided'` | **NO** | Explicitly voided — excluded from all official totals |

**Only immutable posted ledger entries in `journal_entry_headers` + `journal_entry_lines` are official report truth.**

---

## 5. Target Report Sources

When H12 is implemented and the migration is executed, each official report must read from the following sources:

### 5.1 Trial Balance
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `journal_entry_headers.status = 'posted'` (or `'correction'` for correction entries)
- **Group by:** `account_code`, `currency`, `period`
- **Tenant filter:** `journal_entry_headers.tenant_id = :tenant_id` and `journal_entry_lines.tenant_id = :tenant_id`
- **Period filter:** `journal_entry_headers.period = :period` or `entry_date` range
- **Exclude:** `status = 'voided'`; reversed entries excluded from net unless reversal history view
- **Output:** debit total, credit total, net movement per account per period

### 5.2 P&L Summary
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; account_code filtered to income and expense chart of accounts ranges
- **Tenant filter:** required
- **Period filter:** required (selected period only — P&L is a flow statement, not cumulative)
- **Never include:** `simulated_success`, `auto_approved`, drafts, `dry_run`

### 5.3 P&L Detail
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; account_code in income/expense ranges
- **Tenant filter:** required
- **Period filter:** required
- **Line-level detail:** `account_code`, `description`, `amount_gel`, `entry_date`, `source_type`, `posting_date`
- **Never include:** `simulated_success`, drafts, `mock_posting`, `dry_run`

### 5.4 Balance Sheet Summary
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; account_code filtered to asset, liability, equity chart of accounts ranges
- **Tenant filter:** required
- **Date filter:** as-of date — cumulative to the given date (balance sheet is a position statement)
- **Opening balance support:** must calculate running balance from earliest posted entry to as-of date

### 5.5 Balance Sheet Detail
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; account_code in asset/liability/equity ranges
- **Tenant filter:** required
- **Date filter:** required
- **Period filter:** required
- **Line-level detail:** same fields as P&L detail
- **Never include:** `simulated_success`, drafts

### 5.6 VAT Register
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; lines where `tax_code IS NOT NULL` or `vat_amount IS NOT NULL`
- **Tenant filter:** required
- **Period filter:** required
- **Output:** `tax_code`, `vat_amount`, `account_code`, `entry_date`, `posting_date`, `source_type`

### 5.7 Account Ledger
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; `account_code = :account_code`
- **Tenant filter:** required
- **Date/period filter:** required
- **Output:** chronological debit/credit movements per account with opening and closing balances

### 5.8 Counterparty Ledger
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; `counterparty_id = :counterparty_id`
- **Tenant filter:** required
- **Period filter:** required
- **Output:** all posted lines linked to a given counterparty

### 5.9 Payroll Ledger
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; `source_type = 'payroll'` or payroll-specific account codes
- **Tenant filter:** required
- **Period filter:** required
- **Output:** payroll-linked posted lines with employee/cost center linkage where available

### 5.10 Journal Entries List
- **Source:** `journal_entry_headers` with nested `journal_entry_lines`
- **Filter:** `status IN ('posted', 'correction', 'reversed')` depending on view
- **Tenant filter:** required
- **Period/date filter:** required
- **Output:** one row per header with all associated line details

### 5.11 Cashflow Statement
- **Source:** `journal_entry_lines` joined to `journal_entry_headers`
- **Filter:** `status = 'posted'`; cash and bank account codes from chart of accounts
- **Tenant filter:** required
- **Period filter:** required
- **Reconciliation:** posted cash/bank lines or ledger-linked bank transactions
- **Output:** operating/investing/financing categories derived from account classification

---

## 6. Required Filters

Every official report query against `journal_entry_headers` and `journal_entry_lines` **must** include all applicable filters:

| Filter | Required on | Rule |
|---|---|---|
| `tenant_id` | All queries | Must match authenticated request tenant — no cross-tenant data |
| `period` or date range | All flow reports (P&L, VAT, cashflow) | P&L and VAT are period-specific; balance sheet uses as-of-date |
| `status = 'posted'` | All standard report queries | `journal_entry_headers.status` must be `'posted'` |
| Account code filter | Trial balance, P&L, BS, VAT, account ledger | Filter to report-relevant account ranges |
| Counterparty filter | Counterparty ledger only | `counterparty_id` filter on lines |
| Exclude voided | All reports | `status != 'voided'` |
| Reversal handling | Net-view reports | Reversed entries excluded from net unless reversal history view |
| Correction inclusion | All net-view reports | Correction entries (`status='correction'`) count as posted truth |

**No report may omit the `tenant_id` filter. No report may silently fall back to `'default'` tenant.**

---

## 7. Reversal / Correction Handling

Official reports must handle reversal and correction entries as follows:

1. **Reversed entries:** A header with `status='reversed'` has been offset by a subsequent reversal entry. For net-view reports (trial balance, P&L, balance sheet), reversed entries must be **excluded from active posted totals** unless the user has requested reversal history view.
2. **Reversal entries:** A header that is itself a reversal (containing offsetting lines) has `status='posted'` but references `correction_of_entry_id` or is linked via `reversed_by_entry_id`. These must be **included** in net totals as they are real ERP-confirmed offsets.
3. **Correction entries:** Headers with `status='correction'` are new corrective postings. They must be **included** as active posted entries in all net-view reports.
4. **Original corrected entries:** The original entry that was corrected remains immutable — its status does not change. Reports must not double-count both the original and correction if the correction supersedes the original.
5. **Void:** Headers with `status='voided'` must be **excluded** from all official report totals.
6. **No destructive edits:** No report implementation may `UPDATE` or `DELETE` from `journal_entry_headers` or `journal_entry_lines`. All corrections and reversals are append-only new rows.

---

## 8. Opening Balances and Period Boundaries

Official reports must support opening balance and period boundary logic:

1. **Trial balance opening balance:** The trial balance must support a three-column view: opening balance (cumulative to period start), period movement (debits/credits within selected period), and closing balance (opening + movement).
2. **Balance sheet as-of-date:** The balance sheet calculates cumulative net position from the earliest posted entry to the given as-of date. It is not limited to a single period.
3. **P&L period-only:** The P&L report covers only the selected period. It must not include movements from prior periods unless an explicit year-to-date view is requested.
4. **Cashflow period-only:** The cashflow statement covers the selected period. Opening and closing cash positions come from posted balance sheet cash/bank accounts.
5. **Cross-period comparison:** Reports supporting multi-period comparison must repeat the `tenant_id` + `status='posted'` filter for each period column independently.
6. **Period boundary definition:** Period is defined as `journal_entry_headers.period` (e.g., `'2026-05'`) or `entry_date` range, depending on report type. Both must be supported.

---

## 9. Tenant Isolation

All official report queries must enforce strict tenant isolation:

1. **Mandatory tenant_id filter:** Every query against `journal_entry_headers` and `journal_entry_lines` must include `WHERE tenant_id = :tenant_id`.
2. **No silent default fallback:** No report may fall back to `tenant_id = 'default'` if the authenticated tenant is not set.
3. **No cross-tenant aggregation:** No report may aggregate data across multiple tenants unless an explicit future consolidation feature is designed and approved.
4. **All joins must preserve tenant_id:** Every join between `journal_entry_headers` and `journal_entry_lines` must preserve the tenant context on both sides of the join.
5. **Authenticated request tenant:** Tenant must be derived from `request.state.tenant_id` (set by tenant middleware from JWT), not from query parameters or user input.

---

## 10. Non-Goals for H7

This task explicitly does **not**:

- Change any runtime report behavior.
- Modify `financial_statements_service.py`.
- Modify `ledger_service.py`.
- Modify `routes_reports.py` or any route handler.
- Modify `posting_service.py`.
- Modify `approval_service.py`.
- Execute any SQL.
- Create any new SQL migration file.
- Execute any migration.
- Access any database (production or otherwise).
- Touch the production database.
- Change any connector behavior.
- Activate Balance.ge.
- Change any credentials or secrets.
- Change any production infrastructure or deployment configuration.
- Start H8, H9, H10, H11, or H12 work.

This task produces two files only:
- `docs/reports-posted-ledger-read-contract.md` (this document)
- `tests/unit/test_reports_posted_ledger_read_contract.py`

---

## 11. Future Task Sequence

| Task | Description |
|---|---|
| **H7** (this task) | Reports posted-ledger read contract / tests only — no runtime change |
| **H8** | Report query implementation tests with mocks — mock-test the future `financial_statements_service` read queries against `journal_entry_headers` + `journal_entry_lines` using `MagicMock` for DB; no production DB write |
| **H9** | Reversal / correction contract — define append-only reversal and correction flow, including API and UI contract |
| **H10** | Evidence / audit export linkage contract — define how `evidence_bundle_id` links to posted entries and how audit export should work |
| **H11** | Controlled local/test migration execution plan — if explicitly approved, run `011_posted_journal_entries_schema.sql` against a local or test DB only; never production without separate approval |
| **H12** | Runtime report migration — after migration is executed and posting ledger write path is live, migrate `financial_statements_service` and `ledger_service` to read from `journal_entry_headers` + `journal_entry_lines` |

Each task follows the same protocol: branch → docs/tests → PR → merge → deploy → live verification → confirmed before starting the next task.

---

*Bridge Hub — Task 11C-H7. Contract only. No runtime changes. No SQL. No migration execution. No production DB touch. Balance.ge remains inactive.*
