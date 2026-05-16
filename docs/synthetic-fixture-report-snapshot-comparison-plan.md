# Bridge Hub — H27 Synthetic Fixture Report Snapshot Comparison Plan

## 1. Title

Bridge Hub — H27 Synthetic Fixture Report Snapshot Comparison Plan

Task: 11C-H27 — Synthetic Fixture Report Snapshot Contract / Old-vs-New Comparison Plan
Branch: `codex/synthetic-fixture-report-snapshot-comparison`
Starting SHA: `3619817e0a8fd20a25910f8a315bcf1b395bf34e` (H26 merge)

---

## 2. Purpose

H27 defines the old-vs-new report snapshot comparison contract using the H25/H26 synthetic fixture.

H27 **does not** create a DB.
H27 **does not** connect to a DB.
H27 **does not** execute SQL.
H27 **does not** run migrations.
H27 **does not** load fixtures into any DB.
H27 **does not** call runtime report APIs.
H27 **does not** modify runtime report behavior.
H27 **does not** enable feature flags.
H27 **does not** activate Balance.ge.

All snapshot comparison rules are defined as local contracts read from the H25 fixture JSON and validated
in pure Python with no external dependencies. The future runtime comparison (old path vs. posted-ledger
path) is defined as a plan only — it is not executed in H27.

---

## 3. H25/H26 Context

| Property | Value |
|---|---|
| H25 | Created synthetic fixture pack (docs/tests/JSON only) |
| H26 | Validated expected totals; corrected account_ledger.1010_bank gross totals |
| Tenants | 2 (`tenant_alpha`, `tenant_beta`) |
| Headers | 15 (12 standard net + 1 reversed + 1 voided + 1 tenant_beta) |
| Lines | 33 |
| Sources | 4 |
| Invalid rows | 4 (draft, approved, auto_approved, unbalanced) |
| Report snapshots | 11 types defined in expected_reports.tenant_alpha |
| DB/SQL/migration | None — fixture JSON only |
| H26 correction | account_ledger.1010_bank total_dr 12360→11180; total_cr 7885→6705 |

---

## 4. Comparison Scope

H27 defines snapshot comparison rules for the following 11 report types:

1. **Trial Balance** — net debit/credit by account; total_dr = total_cr invariant
2. **P&L Summary** — total income, total expense, net profit/loss
3. **P&L Detail** — income and expense line items rolling up to summary
4. **Balance Sheet Summary** — total assets, liabilities, equity; equation: A = L + E
5. **Balance Sheet Detail** — asset, liability, equity line items rolling up to summary
6. **VAT Register** — VAT input reclaimable, VAT output payable, net VAT position
7. **Account Ledger** — gross DR/CR and net balance per account
8. **Counterparty Ledger** — invoiced, received/paid, net outstanding per counterparty
9. **Payroll Ledger** — gross salary, income tax, net salary payable
10. **Journal Entries List** — count, volume, status policy
11. **Cashflow** — inflows, outflows, net movement, closing balance

---

## 5. Snapshot Shape Requirements

Every report snapshot must carry the following metadata to be comparable:

| Field | Requirement |
|---|---|
| `report_name` | Identifies which of the 11 report types this snapshot represents |
| Tenant context | `tenant_id` or equivalent scoping; no cross-tenant leakage |
| Period / date range | `period` field or equivalent (e.g., `2026-01`) |
| Currency | Must be `GEL` for all synthetic fixture snapshots |
| `generated_from` or source marker | References fixture version, task, or synthetic origin |
| Totals | At least one top-level numeric total per report (e.g., `total_dr`, `total_income`) |
| Detail rows | Row-level breakdown where applicable (accounts, counterparties, line items) |
| Stable row keys | Account code, counterparty ID, journal_entry_id, or equivalent |
| Status policy | Which statuses are included/excluded from this snapshot |
| Drilldown/evidence links | `posting_log_id`, `evidence_bundle_id`, `source_draft_id` where applicable |
| Comparison tolerance | Default 0.01 GEL for numeric rounding; zero tolerance for structural fields |

---

## 6. Stable Identity Keys

The following keys must be stable across snapshot comparisons. If any key changes between old-path and
new-path outputs, it indicates a structural regression rather than a rounding difference.

| Key | Used In |
|---|---|
| `account_code` | Trial balance, P&L, balance sheet, account ledger |
| `account_name` | All account-based reports (secondary, non-sorting key) |
| `counterparty_id` | Counterparty ledger |
| `journal_entry_id` | Journal entries list, account ledger drilldown, sources |
| `ledger_line_id` | Account ledger detail rows |
| `source_draft_id` | Drilldown from journal entry to originating draft |
| `posting_log_id` | Drilldown from journal entry to posting audit record |
| `evidence_bundle_id` | Drilldown from journal entry to evidence package |
| `correction_of_id` | Correction chain: links correction entry to original entry |
| `reversal_of_id` / `reversed_by_entry_id` | Reversal chain: links reversal to original |
| `period` | Period-scoping key for all reports |
| `tenant_id` | Tenant-isolation key — must match exactly |

---

## 7. Comparison Rules

| Rule | Specification |
|---|---|
| Numeric comparison | Use `Decimal` arithmetic; never compare floats directly |
| Currency | Must match exactly; no implicit conversion |
| Row count | Must match between snapshots; row count mismatch → `ROW_COUNT_MISMATCH` |
| Account/category grouping | Account codes and categories must be grouped identically |
| Signs | DR/CR sign convention must be consistent (debit positive for DR-normal accounts) |
| Tenant isolation | `tenant_id` must be identical; cross-tenant rows → `TENANT_LEAKAGE` |
| Row ordering | Sort by stable key before comparison; order must not affect outcome |
| Rounding tolerance | Default 0.01 GEL; applies only to numeric totals, not keys or counts |
| Status policy | Included/excluded status sets must match; divergence → `STATUS_POLICY_MISMATCH` |
| Evidence links | `evidence_bundle_id`, `posting_log_id`, `source_draft_id` must not be null on required rows |
| Correction/reversal | Links must be preserved; missing link → `CORRECTION_REVERSAL_MISMATCH` |
| Tenant leakage | Zero tolerance; any cross-tenant value → `TENANT_LEAKAGE` (hard fail) |
| Missing drilldown | Zero tolerance; required link absent → `DRILLDOWN_LINK_MISSING` (hard fail) |

---

## 8. Mismatch Classification

| Code | Description | Tolerance |
|---|---|---|
| `SNAPSHOT_SHAPE_MISMATCH` | Report JSON shape differs from expected schema | None — hard fail |
| `REPORT_TOTAL_MISMATCH` | Top-level total differs beyond rounding tolerance | None — hard fail |
| `ROW_COUNT_MISMATCH` | Number of rows/accounts in report differs | None — hard fail |
| `ROW_VALUE_MISMATCH` | Individual row value differs beyond tolerance | None — hard fail |
| `ROUNDING_ONLY_DIFFERENCE` | Numeric difference ≤ 0.01 GEL per field | Acceptable — log, do not fail |
| `TENANT_LEAKAGE` | Cross-tenant data present in report output | None — hard fail, block production |
| `STATUS_POLICY_MISMATCH` | Different statuses included/excluded than expected | None — hard fail |
| `CORRECTION_REVERSAL_MISMATCH` | Correction or reversal chain broken or wrong | None — hard fail |
| `DRILLDOWN_LINK_MISSING` | Required `posting_log_id` / `evidence_bundle_id` absent | None — hard fail |
| `EVIDENCE_LINK_MISSING` | `evidence_bundle_id` absent where fixture requires it | None — hard fail |
| `CASHFLOW_CLASSIFICATION_MISMATCH` | Bank account movements classified differently | None — hard fail |
| `VAT_CLASSIFICATION_MISMATCH` | VAT input/output accounts classified differently | None — hard fail |
| `PAYROLL_CLASSIFICATION_MISMATCH` | Payroll accounts classified differently | None — hard fail |

---

## 9. Standard Net Status Policy

All 11 report snapshots apply the same standard net status policy unless explicitly noted:

| Status | Included | Notes |
|---|---|---|
| `posted` | Yes | Core ledger status |
| `correction` | Yes | Adjustments; must have `correction_of_entry_id` |
| `reversed` | No | Excluded from standard net; reversal chain tracked in history view |
| `voided` | No | Excluded from all standard net reports |
| `draft` | Never | Forbidden in posted ledger by DB constraint |
| `approved` | Never | Forbidden in posted ledger by DB constraint |
| `auto_approved` | Never | Forbidden in posted ledger by DB constraint |
| `simulated_success` | Never | Forbidden in posted ledger by DB constraint |

Correction entries are included in all standard net reports. The original entry being corrected retains
`reversed_by_entry_id` if fully reversed, but stays in standard net if only partially corrected.

A reversal entry (status=`reversed`) is excluded from standard net. The reversal chain (`correction_of_entry_id`
pointing to the original) must be preserved in drilldown and history views.

---

## 10. Report-by-Report Snapshot Criteria

### Trial Balance

| Criterion | Requirement |
|---|---|
| Required totals | `total_dr`, `total_cr` |
| Required rows | One row per account code with DR/CR or net balance |
| Required drilldown | `account_code` as stable key |
| Status behavior | Standard net only (`posted` + `correction`) |
| Failure mode if mismatch | `REPORT_TOTAL_MISMATCH` or `ROW_VALUE_MISMATCH` |
| Invariant | `total_dr` must equal `total_cr` |

### P&L Summary

| Criterion | Requirement |
|---|---|
| Required totals | `total_income`, `total_expense`, `net_profit_loss` |
| Required rows | Income total, expense total, net |
| Status behavior | Standard net |
| Failure mode | `REPORT_TOTAL_MISMATCH` |
| Invariant | `net_profit_loss` = `total_income` - `total_expense` |

### P&L Detail

| Criterion | Requirement |
|---|---|
| Required rows | Per-account income and expense lines |
| Required totals | Sum of income rows = `pl_summary.total_income`; sum of expense rows = `pl_summary.total_expense` |
| Stable key | `account_code` |
| Failure mode | `ROW_COUNT_MISMATCH` or `ROW_VALUE_MISMATCH` |

### Balance Sheet Summary

| Criterion | Requirement |
|---|---|
| Required totals | `total_assets`, `total_liabilities`, `total_equity` |
| Invariant | `total_assets` = `total_liabilities` + `total_equity` |
| Failure mode | `REPORT_TOTAL_MISMATCH` |

### Balance Sheet Detail

| Criterion | Requirement |
|---|---|
| Required rows | Assets, liabilities, equity line items |
| Rollup | Detail sums must match summary totals |
| Stable key | `account_code` |
| Failure mode | `ROW_COUNT_MISMATCH` or `ROW_VALUE_MISMATCH` |

### VAT Register

| Criterion | Requirement |
|---|---|
| Required totals | `vat_input_reclaimable`, `vat_output_payable`, `net_vat_position` |
| Invariant | `net_vat_position` = `vat_output_payable` - `vat_input_reclaimable` |
| Excluded | Reversed, voided entries |
| Failure mode | `VAT_CLASSIFICATION_MISMATCH` or `REPORT_TOTAL_MISMATCH` |

### Account Ledger

| Criterion | Requirement |
|---|---|
| Required per account | `total_dr`, `total_cr`, `net_balance_dr` or `net_balance_cr` |
| Stable key | `account_code` |
| Drilldown | `journal_entry_id` at line level |
| Failure mode | `ROW_VALUE_MISMATCH` or `DRILLDOWN_LINK_MISSING` |

### Counterparty Ledger

| Criterion | Requirement |
|---|---|
| Required per counterparty | `total_invoiced` or `total_purchased`, `total_received` or `total_paid`, `net_outstanding` |
| Stable key | `counterparty_id` |
| Drilldown | `journal_entry_id`, `source_draft_id` |
| Failure mode | `ROW_VALUE_MISMATCH` |

### Payroll Ledger

| Criterion | Requirement |
|---|---|
| Required totals | `gross_salary_expense`, `net_salary_payable`, `income_tax_payg` |
| Invariant | `gross_salary_expense` = `net_salary_payable` + `income_tax_payg` (simplified, no pension) |
| Stable key | `period` |
| Failure mode | `PAYROLL_CLASSIFICATION_MISMATCH` or `REPORT_TOTAL_MISMATCH` |

### Journal Entries List

| Criterion | Requirement |
|---|---|
| Required totals | `standard_net_count`, `total_volume_dr`, `total_volume_cr` |
| Status policy | `statuses_included` and `statuses_excluded` both required |
| Invariant | `total_volume_dr` = `total_volume_cr` |
| Stable key | `journal_entry_id` at row level |
| Failure mode | `STATUS_POLICY_MISMATCH` or `ROW_COUNT_MISMATCH` |

### Cashflow

| Criterion | Requirement |
|---|---|
| Required totals | `inflows`, `outflows`, `net_cash_movement`, `closing_balance_bank_1010` |
| Invariant | `net_cash_movement` = `inflows` - `outflows` |
| Classification | Only bank account (1010) movements in simplified direct method |
| Failure mode | `CASHFLOW_CLASSIFICATION_MISMATCH` or `REPORT_TOTAL_MISMATCH` |

---

## 11. Old-vs-New Future Runtime Comparison Plan

The following plan defines how the old (current/legacy) report path and the new (posted-ledger) report
path will be compared in a future non-production controlled environment. **This plan is not executed in H27.**

Steps:

1. **Load synthetic fixture into disposable/staging DB** — using approved H24/H23 setup plan; local
   PostgreSQL or Docker `postgres:16` required; no production DB.
2. **Run legacy/current report path with feature flag OFF** — `POSTED_LEDGER_REPORTS_ENABLED=false`;
   capture output JSON for all 11 report types for `tenant_alpha`.
3. **Run posted-ledger report path with feature flag ON in non-production only** — `POSTED_LEDGER_REPORTS_ENABLED=true`
   on disposable/staging DB only; capture output JSON for all 11 report types.
4. **Normalize both outputs** — apply the snapshot normalizer (H28 task) to produce comparable structures:
   sort by stable key, convert floats to Decimal, strip runtime-only metadata.
5. **Compare to expected snapshot** — diff normalized old-path output and normalized new-path output
   against `expected_reports.tenant_alpha` from the H25 fixture.
6. **Classify mismatches** — apply the mismatch classification table (Section 8); distinguish
   `ROUNDING_ONLY_DIFFERENCE` (acceptable) from structural or value mismatches (blocking).
7. **Produce accountant review report** — summarize mismatches, totals, and delta for human review.
8. **Do not enable production feature flag unless all gates pass** (Section 12).

---

## 12. Approval Gates

| Gate | Description | Required Before |
|---|---|---|
| G1 | Fixture contract green (H25/H26 tests pass) | All subsequent gates |
| G2 | DB migration dry-run green (H24 — disposable only) | G3 |
| G3 | Fixture load into disposable DB green | G4 |
| G4 | Old-path report output captured from disposable DB | G5 |
| G5 | Posted-ledger output captured from disposable DB | G6 |
| G6 | Snapshot comparison green (all 11 reports; mismatches classified) | G7 |
| G7 | Accountant sign-off on comparison report | G8 |
| G8 | Rollback plan confirmed (dropdb + feature flag reset) | G9 |
| G9 | Production feature flag approval from stakeholder | G10 |
| G10 | Post-switch monitoring plan approved (dashboards, alerts, circuit breaker) | Production enablement |

No production feature flag enablement until G1–G10 are all confirmed.

---

## 13. Safety Rules

- No production data is used in any fixture or comparison in H27.
- No DB is created or connected to in H27.
- No runtime report endpoints are called in H27.
- No feature flag is enabled in H27 (`POSTED_LEDGER_REPORTS_ENABLED` stays OFF).
- Balance.ge remains `demo_mode`; `BALANCE_API_KEY` absent.
- No connector behavior is changed.
- No infrastructure is changed.
- No credentials are changed.
- No UI/static files are changed.
- No runtime business logic code is modified.

---

## 14. H27 Results

| Test group | Result |
|---|---|
| H27 targeted (28 tests) | 28/28 passed |
| H26 + H27 combined (55 tests) | 55/55 passed |
| Related report/fixture tests | all passed |
| Full unit suite | 4031+ passed / 0 failed / 2 skipped |
| Fixture corrections | none — fixture JSON unchanged in H27 |
| Comparison contract green | yes |

---

## 15. Non-Goals

H27 does **not**:

- Create a DB.
- Connect to a DB.
- Execute SQL.
- Run migrations.
- Load fixture data into any DB.
- Use production data.
- Call runtime report APIs.
- Modify runtime report code.
- Modify connector or posting behavior.
- Activate Balance.ge.
- Enable `POSTED_LEDGER_REPORTS_ENABLED`.
- Change UI/static files.
- Change infrastructure.
- Change credentials.

---

## 16. Next Task

Only after PR merge, deploy, and live verification of H27:

**H28 — Synthetic Snapshot Normalizer Contract / Comparison Helper Design**

or, if local PostgreSQL becomes available:

**Controlled Disposable DB Fixture Load Dry Run** (H24 unblocking path)
