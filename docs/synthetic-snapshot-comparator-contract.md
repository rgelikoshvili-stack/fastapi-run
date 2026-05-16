# Bridge Hub - H29 Synthetic Snapshot Comparator Contract

## 1. Title

Bridge Hub - H29 Synthetic Snapshot Comparator Contract

Task: 11C-H29 - Synthetic Snapshot Comparator Contract / Mismatch Classifier Helper Design
Branch: `codex/synthetic-snapshot-comparator-contract`
Starting SHA: `ab914cbb01e07e8a7371f4ff92cdc6f1f7fbdad8` (H28 live verified)

## 2. Purpose

H29 defines the comparator and mismatch classifier contract used after H28 normalization. It specifies how two canonical report snapshots are compared, how mismatches are classified, which mismatches are hard failures, and what future helper signatures should look like.

H29 is docs/tests only.
H29 does not create DB.
H29 does not connect to DB.
H29 does not execute SQL.
H29 does not run migrations.
H29 does not load fixtures into DB.
H29 does not call runtime report APIs.
H29 does not modify runtime report behavior.
H29 does not implement app/runtime helpers.
H29 does not enable feature flags.
H29 does not activate Balance.ge.

All examples use synthetic local snapshots only. No production or customer data is used.

## 3. H28 Context

H28 defined the canonical snapshot shape, canonical row shape, normalization rules, money and rounding rules, stable row keys, report name mapping, missing/null field policy, and normalization error codes.

H29 starts after those normalized snapshots exist. It does not normalize raw runtime output. H29 defines how already-normalized snapshots are compared and how deterministic mismatch classifications are emitted for accountant and engineering review.

## 4. Comparator Input Contract

The future comparator accepts two canonical snapshots and a comparison context:

```json
{
  "left": {"report_name": "Trial Balance", "rows": [], "totals": {}},
  "right": {"report_name": "Trial Balance", "rows": [], "totals": {}},
  "comparison_context": {
    "comparison_name": "legacy_vs_posted_ledger_trial_balance",
    "left_label": "legacy|current|expected_fixture",
    "right_label": "posted_ledger|expected_fixture",
    "report_name": "Trial Balance",
    "tenant_id": "tenant_alpha",
    "period": {"from": "2026-01-01", "to": "2026-01-31"},
    "currency": "GEL",
    "tolerance": "0.01"
  }
}
```

Input rules:
- `left` and `right` must already conform to the H28 canonical snapshot contract.
- `comparison_context.report_name`, `tenant_id`, `period`, `currency`, and `tolerance` are required.
- `currency` must be `GEL` for the synthetic fixture comparison path.
- `tolerance` must be a decimal string and defaults to `0.01` GEL.
- Labels identify the compared source only; labels do not affect accounting results.

## 5. Comparator Output Contract

The comparator returns a machine-readable result:

```json
{
  "ok": true,
  "comparison_name": "legacy_vs_posted_ledger_trial_balance",
  "report_name": "Trial Balance",
  "tenant_id": "tenant_alpha",
  "period": {"from": "2026-01-01", "to": "2026-01-31"},
  "currency": "GEL",
  "summary": {
    "total_mismatches": 0,
    "critical": 0,
    "high": 0,
    "medium": 0,
    "low": 0,
    "rounding_only": 0
  },
  "mismatches": [],
  "metadata": {}
}
```

Output rules:
- `ok` is `false` when any critical, high, or medium mismatch exists.
- In `strict_accounting` mode, `ROUNDING_ONLY_DIFFERENCE` items are reported but do not block by themselves.
- `summary.total_mismatches` equals the length of `mismatches`.
- Severity counters must sum to `summary.total_mismatches`.
- `metadata` may include local comparison details, but no secrets or production data.

## 6. Mismatch Item Shape

Each mismatch item must use this canonical shape:

```json
{
  "code": "REPORT_TOTAL_MISMATCH",
  "severity": "high",
  "report_name": "Trial Balance",
  "tenant_id": "tenant_alpha",
  "row_key": null,
  "field": "total_dr",
  "expected_value": "14480.00",
  "actual_value": "14481.00",
  "difference": "1.00",
  "tolerance": "0.01",
  "path": "totals.total_dr",
  "message": "Report total differs outside tolerance",
  "evidence": {},
  "classification_notes": []
}
```

Required mismatch item fields:
- `code`
- `severity`
- `report_name`
- `tenant_id`
- `row_key`
- `field`
- `expected_value`
- `actual_value`
- `difference`
- `tolerance`
- `path`
- `message`
- `evidence`
- `classification_notes`

## 7. Severity Rules

Severity levels are deterministic:

| Severity | Rule |
|---|---|
| `critical` | Tenant leakage, status policy mismatch, missing required row, missing required total, currency mismatch |
| `high` | Report total mismatch outside tolerance, row value mismatch outside tolerance, missing drilldown/evidence when required |
| `medium` | Row count mismatch, optional metadata mismatch, category mismatch |
| `low` | Ordering-only difference after normalization, optional extra fields |
| `rounding_only` | Numeric difference within tolerance |

Critical and high mismatches block production switch gates. Medium mismatches require engineering/accountant review. Low mismatches are informational unless repeated. Rounding-only mismatches are grouped separately for accountant visibility.

## 8. Mismatch Codes

H29 keeps all H27 mismatch codes and adds comparator-specific hard-fail codes where needed:

| Code | Severity | Meaning |
|---|---|---|
| `SNAPSHOT_SHAPE_MISMATCH` | critical | Snapshot shape, duplicate row key, or required structural field differs |
| `REPORT_TOTAL_MISMATCH` | high | Report-level total differs outside tolerance |
| `ROW_COUNT_MISMATCH` | medium | Row counts differ after key matching |
| `ROW_VALUE_MISMATCH` | high | Row-level value differs outside tolerance |
| `ROUNDING_ONLY_DIFFERENCE` | rounding_only | Numeric difference is within configured tolerance |
| `TENANT_LEAKAGE` | critical | Row or snapshot tenant differs from expected tenant |
| `STATUS_POLICY_MISMATCH` | critical | Included/excluded status policy differs |
| `CORRECTION_REVERSAL_MISMATCH` | critical | Correction/reversal inclusion or linkage differs |
| `DRILLDOWN_LINK_MISSING` | high | Required drilldown link is absent |
| `EVIDENCE_LINK_MISSING` | high | Required evidence link is absent |
| `CASHFLOW_CLASSIFICATION_MISMATCH` | high | Cashflow category or direct-method classification differs |
| `VAT_CLASSIFICATION_MISMATCH` | high | VAT input/output/net classification differs |
| `PAYROLL_CLASSIFICATION_MISMATCH` | high | Payroll gross/net/tax classification differs |
| `CURRENCY_MISMATCH` | critical | Snapshot or context currency differs |
| `PERIOD_MISMATCH` | critical | Snapshot period differs |
| `REPORT_NAME_MISMATCH` | critical | Snapshot report name differs |
| `ROW_KEY_MISSING` | critical | A row lacks a deterministic key |
| `REQUIRED_TOTAL_MISSING` | critical | Required total is absent |
| `REQUIRED_ROW_MISSING` | critical | Required row is absent on the right side |
| `UNEXPECTED_ROW_PRESENT` | medium | Extra row is present on the right side |

## 9. Numeric Comparison Rules

Numeric comparison rules:
- Use `Decimal` only.
- Decimal only arithmetic is allowed.
- Default tolerance is `0.01` GEL.
- Default tolerance is `0.01` GEL for every synthetic fixture report unless a later contract narrows it.
- Values must be canonical money strings from H28 before comparison.
- If `abs(left - right) <= tolerance`, classify as `ROUNDING_ONLY_DIFFERENCE` in strict mode or pass silently in smoke mode.
- If `abs(left - right) > tolerance`, classify as `REPORT_TOTAL_MISMATCH` for totals or `ROW_VALUE_MISMATCH` for row values.
- No tolerance for sign mismatch.
- There is no tolerance for sign mismatch if the sign changes report meaning.
- Float comparisons are forbidden.
- Difference is reported as a canonical decimal string.

## 10. Row Matching Rules

Row matching rules:
- Match rows by `row_key` first.
- If `row_key` is missing, use the H28 stable-key fallback only when deterministic.
- Missing row on right side produces `REQUIRED_ROW_MISSING`.
- Extra row on right side produces `UNEXPECTED_ROW_PRESENT`.
- Duplicate row key produces `SNAPSHOT_SHAPE_MISMATCH`.
- Sorted order is not a mismatch when normalized rows match by key.
- Row comparison must be order-independent.
- Row value comparison uses each row's `values` object.

## 11. Hard-Fail Rules

The comparator emits hard failures for:
- `tenant_id` mismatch
- tenant_id mismatch
- tenant leakage
- currency mismatch
- report_name mismatch
- period mismatch
- status policy mismatch
- missing required drilldown link
- missing required evidence link
- correction/reversal policy mismatch
- missing required totals

Hard failures are always blocking for pre-production switch gates.

## 12. Report-by-Report Comparator Rules

| Report | Required totals | Rows to match | Hard-fail fields | Drilldown/evidence | Tolerance | Special codes |
|---|---|---|---|---|---|---|
| Trial Balance | `total_dr`, `total_cr` | account rows by `row_key`/`account_code` | tenant, period, currency, status_policy | evidence optional at summary level | `0.01` | `REPORT_TOTAL_MISMATCH`, `ROW_VALUE_MISMATCH` |
| P&L Summary | `total_income`, `total_expense`, `net_profit_loss` | single summary row when present | tenant, period, currency, status_policy | evidence optional at summary level | `0.01` | `REPORT_TOTAL_MISMATCH` |
| P&L Detail | income/expense rollups, `net_profit_loss` | account rows by `row_key`/`account_code` | tenant, period, currency, status_policy | drilldown required for detail rows | `0.01` | `ROW_VALUE_MISMATCH` |
| Balance Sheet Summary | `total_assets`, `total_liabilities`, `total_equity` | category rows | tenant, period, currency, status_policy | evidence optional at summary level | `0.01` | `REPORT_TOTAL_MISMATCH` |
| Balance Sheet Detail | asset/liability/equity detail totals | account rows by `row_key`/`account_code` | tenant, period, currency, status_policy | drilldown required for detail rows | `0.01` | `ROW_VALUE_MISMATCH` |
| VAT Register | `vat_input_reclaimable`, `vat_output_payable`, `net_vat_position` | VAT category rows | tenant, period, currency, status_policy | evidence required where fixture requires it | `0.01` | `VAT_CLASSIFICATION_MISMATCH` |
| Account Ledger | `total_dr`, `total_cr`, net balance fields | ledger rows by `ledger_line_id`/`row_key` | tenant, period, currency, status_policy | journal_entry_id required | `0.01` | `DRILLDOWN_LINK_MISSING` |
| Counterparty Ledger | invoiced/purchased/paid/received/outstanding totals | counterparty rows by `counterparty_id`/`row_key` | tenant, period, currency, status_policy | source_draft_id and journal_entry_id required where present in fixture | `0.01` | `ROW_VALUE_MISMATCH` |
| Payroll Ledger | `gross_salary_expense`, `net_salary_payable`, `income_tax_payg` | period rows by `period`/`row_key` | tenant, period, currency, status_policy | payroll source evidence required for fixture-linked entries | `0.01` | `PAYROLL_CLASSIFICATION_MISMATCH` |
| Journal Entries List | `standard_net_count`, `total_volume_dr`, `total_volume_cr` | entries by `journal_entry_id`/`row_key` | tenant, period, currency, status_policy, correction/reversal policy | posting_log_id and evidence link required where fixture requires them | `0.01` | `CORRECTION_REVERSAL_MISMATCH` |
| Cashflow | `inflows`, `outflows`, `net_cash_movement`, `closing_balance_bank_1010` | cashflow categories by `row_key` | tenant, period, currency, status_policy | evidence optional at summary level | `0.01` | `CASHFLOW_CLASSIFICATION_MISMATCH` |

## 13. Comparison Modes

| Mode | Behavior |
|---|---|
| `strict_accounting` | Default Bridge Hub pre-production switch mode. Rounding differences are reported. Critical/high/medium mismatches fail. |
| `accountant_review` | Rounding differences are grouped separately. Accountant-facing summary highlights affected accounts, counterparties, journal entries, and evidence links. |
| `smoke` | Shape and totals only. Row-level detail is skipped unless a hard-fail field differs. |

Default for Bridge Hub: `strict_accounting` for pre-production switch gates.

## 14. Future Helper Design

These signatures are documentation only. H29 does not implement app/runtime helpers.

```python
from decimal import Decimal

def compare_snapshots(left: dict, right: dict, *, context: dict) -> dict:
    """Compare two H28-normalized snapshots and return the H29 output contract."""
    ...

def compare_totals(left_totals: dict, right_totals: dict, *, tolerance: Decimal) -> list[dict]:
    """Compare canonical money totals and return mismatch items."""
    ...

def compare_rows(left_rows: list[dict], right_rows: list[dict], *, report_name: str, tolerance: Decimal) -> list[dict]:
    """Match rows by stable key and compare canonical row values."""
    ...

def classify_mismatch(code: str, *, field: str | None = None, difference=None) -> dict:
    """Return deterministic severity and display metadata for a mismatch code."""
    ...
```

## 15. Accountant Review Output

The future accountant-facing summary must include:
- pass/fail
- report name
- total mismatches
- critical/high/medium/low counts
- affected accounts
- affected counterparties
- affected journal entries
- affected evidence links
- recommended action
- sign-off checkbox/future approval note

Recommended actions:
- `approve_comparison` when no blocking mismatch exists.
- `review_rounding` when only rounding-only differences exist.
- `investigate_report_logic` when totals or row values differ outside tolerance.
- `block_switch` when critical/high mismatches exist.

## 16. Future Old-vs-New Comparator Flow

Future flow, not executed in H29:

1. Normalize legacy/current output.
2. Normalize posted-ledger output.
3. Compare normalized snapshots.
4. Classify mismatches.
5. Produce machine-readable JSON.
6. Produce accountant-readable summary.
7. Block production if critical/high mismatches exist.
8. Require sign-off before feature flag promotion.

## 17. Safety Rules

- No DB in H29.
- No runtime API calls.
- No feature flag.
- No Balance.ge.
- No connector changes.
- No production data.
- No credentials.
- No infrastructure.
- No UI/static changes.
- No runtime report behavior changes.
- No approval or posting behavior changes.

## 18. H29 Results

| Check | Result |
|---|---|
| H29 targeted tests | 31 passed |
| H28 + H29 tests | 67 passed |
| Related report/fixture tests | 287 passed |
| Full unit suite | 4126 passed, 2 skipped |
| Fixture changes | none |
| Comparator contract green | yes |

## 19. Non-Goals

H29 does not do any of the following:
- no DB
- no SQL
- no migration
- no fixture load
- no runtime API calls
- no runtime implementation
- no app service helper implementation
- no production data
- no connector
- no Balance.ge
- no UI/static

## 20. Next Task

Only after PR merge, deploy, and live verification:

H30 - Accountant Review Report Contract / Snapshot Comparison Result UX Plan
