# Bridge Hub — H28 Synthetic Snapshot Normalizer Contract

## 1. Title

Bridge Hub — H28 Synthetic Snapshot Normalizer Contract / Comparison Helper Design

Task: 11C-H28 — Synthetic Snapshot Normalizer Contract / Comparison Helper Design
Branch: `codex/synthetic-snapshot-normalizer-contract`
Starting SHA: `c8070910ba2a80575a5d760fa32155d4033557d4` (H27 merge)

---

## 2. Purpose

H28 defines the canonical shape for normalized report snapshots and specifies the contract for the
future comparison helper functions. All normalization rules, canonical money format, stable row key
priority, report name mapping, and mismatch classification behavior are defined here as a local
contract and validated in pure Python with no external dependencies.

H28 **does not** create a DB.
H28 **does not** connect to a DB.
H28 **does not** execute SQL.
H28 **does not** run migrations.
H28 **does not** load fixtures into any DB.
H28 **does not** call runtime report APIs.
H28 **does not** modify runtime report behavior.
H28 **does not** enable feature flags.
H28 **does not** activate Balance.ge.
H28 **does not** implement runtime helpers in app code.

All helper function signatures and normalization rules are defined as local contract prototypes
inside the test file only — they are not added to any app service, module, or package. The future
runtime implementation of these helpers (in a production-facing module) is deferred to H29 or later.

---

## 3. H25–H27 Context

| Property | Value |
|---|---|
| H25 | Created synthetic fixture pack (docs/tests/JSON only) |
| H26 | Validated expected totals; corrected account_ledger.1010_bank gross totals |
| H27 | Defined old-vs-new snapshot comparison contract; 13 mismatch codes; G1–G10 gates |
| Tenants | 2 (`tenant_alpha`, `tenant_beta`) |
| Headers | 15 (12 standard net + 1 reversed + 1 voided + 1 tenant_beta) |
| Lines | 33 |
| Report types | 11 |
| DB/SQL/migration | None — fixture JSON only |
| H27 comparison codes | 13 (SNAPSHOT_SHAPE_MISMATCH … PAYROLL_CLASSIFICATION_MISMATCH) |

---

## 4. Canonical Snapshot Shape

Every normalized report snapshot must conform to the following top-level structure:

```json
{
  "report_name": "...",
  "tenant_id": "...",
  "period": {"from": "2026-01-01", "to": "2026-01-31"},
  "currency": "GEL",
  "generated_from": "legacy|posted_ledger|expected_fixture",
  "status_policy": {
    "included": ["posted", "correction"],
    "excluded": ["reversed", "voided", "draft", "pending_approval", "rejected"]
  },
  "totals": {...},
  "rows": [...],
  "metadata": {...}
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `report_name` | string | Yes | Canonical name from Section 8 (e.g., "Trial Balance") |
| `tenant_id` | string | Yes | Must be non-empty; normalization fails without it |
| `period` | object | Yes | `{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}`; both dates required |
| `currency` | string | Yes | Must be `"GEL"` for all synthetic fixture snapshots |
| `generated_from` | string | Yes | One of: `"legacy"`, `"posted_ledger"`, `"expected_fixture"` |
| `status_policy` | object | Yes | Both `included` and `excluded` lists required; must not be empty |
| `totals` | object | Yes | At least one key; all values are canonical money strings |
| `rows` | array | Yes | May be empty array `[]`; must be array (not null) |
| `metadata` | object | Yes | May be empty object `{}`; must be object (not null) |

---

## 5. Canonical Row Shape

Each element of the `rows` array must conform to:

```json
{
  "row_key": "...",
  "tenant_id": "...",
  "account_code": "...",
  "account_name": "...",
  "values": {...}
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `row_key` | string | Yes | Stable, opaque key; derived by canonical_row_key(); must be non-empty |
| `tenant_id` | string | Yes | Must match snapshot-level `tenant_id`; cross-tenant rows → TENANT_LEAKAGE |
| `account_code` | string | Conditional | Required for account-based reports (trial balance, P&L, balance sheet, account ledger) |
| `account_name` | string | No | Secondary, descriptive; not used as sort or comparison key |
| `counterparty_id` | string | Conditional | Required for counterparty ledger rows |
| `journal_entry_id` | string | Conditional | Required for journal entries list rows and drilldown rows |
| `ledger_line_id` | string | Conditional | Required for account ledger detail-level rows |
| `values` | object | Yes | Key-value pairs; all monetary values are canonical money strings |

---

## 6. Canonical Money Format

All monetary values in normalized snapshots must be represented as decimal strings in `"GEL"` using
exactly two decimal places. This eliminates float precision errors before comparison.

| Rule | Specification |
|---|---|
| Type | String, not float or int |
| Precision | Always exactly 2 decimal places (e.g., `"1300.00"`, `"0.00"`, `"-1225.00"`) |
| Rounding | `Decimal.quantize(Decimal("0.01"))` with `ROUND_HALF_UP` |
| Negative values | Allowed; represent credit balances or net losses (e.g., `"-1225.00"`) |
| Zero | `"0.00"` (never `"0"` or `"0.0"`) |
| Null input | Treated as `"0.00"` |
| Unparseable input | Raises `ValueError` with code `NORMALIZATION_MONEY_PARSE_ERROR` |
| Currency | Must be `"GEL"`; mismatch → `NORMALIZATION_CURRENCY_MISMATCH` |

Example conversions:

| Input | Output |
|---|---|
| `1300` (int) | `"1300.00"` |
| `1300.0` (float) | `"1300.00"` |
| `"1300.00"` (str) | `"1300.00"` |
| `"-1225"` (str) | `"-1225.00"` |
| `None` | `"0.00"` |
| `"abc"` | raises `ValueError` |

---

## 7. Stable Row Key Priority

The `canonical_row_key()` function derives a stable, opaque key from the most specific identifier
available in the row. Priority order (highest to lowest):

| Priority | Field | Report types |
|---|---|---|
| 1 | `ledger_line_id` | Account ledger (detail rows) |
| 2 | `journal_entry_id` | Journal entries list, account ledger drilldown |
| 3 | `counterparty_id` | Counterparty ledger |
| 4 | `account_code` | Trial balance, P&L, balance sheet, account ledger (summary rows) |
| 5 | `period` | Payroll ledger (period-keyed) |
| 6 | Composite | `report_name|tenant_id|all_non_null_fields` — fallback only |

Rules:
- The key must be non-empty; an empty or all-null row raises `ValueError` with `NORMALIZATION_UNSTABLE_ROW_KEY`.
- The key must not contain runtime-only fields (timestamps, UUIDs generated at request time) that differ between old-path and new-path runs.
- Keys are deterministic — the same logical row always produces the same key.
- Row ordering before comparison must use the stable key, not insertion order.

---

## 8. Report Name Mapping

All 11 report types must be mapped from their fixture/API snake_case key to a canonical display name:

| Snake Case Key | Canonical Name |
|---|---|
| `trial_balance` | `Trial Balance` |
| `pl_summary` | `P&L Summary` |
| `pl_detail` | `P&L Detail` |
| `balance_sheet_summary` | `Balance Sheet Summary` |
| `balance_sheet_detail` | `Balance Sheet Detail` |
| `vat_register` | `VAT Register` |
| `account_ledger` | `Account Ledger` |
| `counterparty_ledger` | `Counterparty Ledger` |
| `payroll_ledger` | `Payroll Ledger` |
| `journal_entries_list` | `Journal Entries List` |
| `cashflow` | `Cashflow` |

An unrecognized snake_case key raises `ValueError` with `NORMALIZATION_UNKNOWN_REPORT`.

---

## 9. Report-by-Report Normalization Rules

### Trial Balance

| Rule | Specification |
|---|---|
| Stable key | `account_code` (required) |
| Required totals | `total_dr`, `total_cr` |
| Money fields | `total_dr`, `total_cr`, `net_balance` |
| Sort order | By `account_code` ascending |
| Invariant | `total_dr == total_cr` (checked post-normalization) |

### P&L Summary

| Rule | Specification |
|---|---|
| Stable key | `report_name` (single summary row) |
| Required totals | `total_income`, `total_expense`, `net_profit_loss` |
| Money fields | `total_income`, `total_expense`, `net_profit_loss` |
| Invariant | `net_profit_loss == total_income - total_expense` |

### P&L Detail

| Rule | Specification |
|---|---|
| Stable key | `account_code` |
| Required totals | Sum of income rows = `pl_summary.total_income`; sum of expense rows = `pl_summary.total_expense` |
| Money fields | `net_balance` per row |
| Sort order | By `account_code` ascending |

### Balance Sheet Summary

| Rule | Specification |
|---|---|
| Stable key | Category label (assets / liabilities / equity) |
| Required totals | `total_assets`, `total_liabilities`, `total_equity` |
| Invariant | `total_assets == total_liabilities + total_equity` |

### Balance Sheet Detail

| Rule | Specification |
|---|---|
| Stable key | `account_code` |
| Required totals | Rollup sums must match balance sheet summary |
| Sort order | By `account_code` ascending |

### VAT Register

| Rule | Specification |
|---|---|
| Stable key | VAT category label (input / output) |
| Required totals | `vat_input_reclaimable`, `vat_output_payable`, `net_vat_position` |
| Invariant | `net_vat_position == vat_output_payable - vat_input_reclaimable` |

### Account Ledger

| Rule | Specification |
|---|---|
| Stable key | `account_code` for summary rows; `ledger_line_id` for detail rows |
| Required per account | `total_dr`, `total_cr`, `net_balance_dr` or `net_balance_cr` |
| Sort order | By `account_code` ascending, then by `ledger_line_id` |
| Drilldown | `journal_entry_id` must be present on each detail row |

### Counterparty Ledger

| Rule | Specification |
|---|---|
| Stable key | `counterparty_id` |
| Required per row | `total_invoiced` or `total_purchased`, `total_received` or `total_paid`, `net_outstanding` |
| Sort order | By `counterparty_id` ascending |
| Drilldown | `journal_entry_id`, `source_draft_id` |

### Payroll Ledger

| Rule | Specification |
|---|---|
| Stable key | `period` |
| Required totals | `gross_salary_expense`, `net_salary_payable`, `income_tax_payg` |
| Invariant | `gross_salary_expense == net_salary_payable + income_tax_payg` |

### Journal Entries List

| Rule | Specification |
|---|---|
| Stable key | `journal_entry_id` at row level |
| Required totals | `standard_net_count`, `total_volume_dr`, `total_volume_cr` |
| Status policy | `statuses_included` and `statuses_excluded` must both appear |
| Invariant | `total_volume_dr == total_volume_cr` |
| Sort order | By `journal_entry_id` ascending |

### Cashflow

| Rule | Specification |
|---|---|
| Stable key | Direction label (inflows / outflows) |
| Required totals | `inflows`, `outflows`, `net_cash_movement`, `closing_balance_bank_1010` |
| Invariant | `net_cash_movement == inflows - outflows` |
| Classification | Only bank account (1010) movements in simplified direct method |

---

## 10. Missing and Null Field Policy

| Scenario | Behavior |
|---|---|
| Required top-level field absent | Raise `ValueError` with `NORMALIZATION_REQUIRED_FIELD_MISSING` |
| `tenant_id` is None or empty string | Raise `ValueError` with `NORMALIZATION_TENANT_MISSING` |
| `currency` absent | Default to `"GEL"`; do not raise |
| `currency` is not `"GEL"` | Raise `ValueError` with `NORMALIZATION_CURRENCY_MISMATCH` |
| `totals` is empty dict | Raise `ValueError` with `NORMALIZATION_REQUIRED_FIELD_MISSING` |
| `rows` is None | Normalize to `[]`; do not raise |
| `metadata` is None | Normalize to `{}`; do not raise |
| Money value is None | Treat as `"0.00"` |
| Money value is unparseable | Raise `ValueError` with `NORMALIZATION_MONEY_PARSE_ERROR` |
| Row missing stable key field | Raise `ValueError` with `NORMALIZATION_UNSTABLE_ROW_KEY` |
| Required drilldown link absent | Raise `ValueError` with `NORMALIZATION_DRILLDOWN_LINK_MISSING` |
| Required evidence link absent | Raise `ValueError` with `NORMALIZATION_EVIDENCE_LINK_MISSING` |
| Unknown report name key | Raise `ValueError` with `NORMALIZATION_UNKNOWN_REPORT` |
| Date field unparseable | Raise `ValueError` with `NORMALIZATION_DATE_PARSE_ERROR` |
| Status policy missing | Raise `ValueError` with `NORMALIZATION_STATUS_POLICY_MISSING` |

---

## 11. Normalization Error Codes

| Code | Trigger |
|---|---|
| `NORMALIZATION_REQUIRED_FIELD_MISSING` | Required top-level field absent from snapshot or totals is empty |
| `NORMALIZATION_MONEY_PARSE_ERROR` | A monetary value cannot be parsed to Decimal |
| `NORMALIZATION_DATE_PARSE_ERROR` | A date field (period.from / period.to) cannot be parsed to ISO 8601 |
| `NORMALIZATION_UNSTABLE_ROW_KEY` | A row has no usable stable identifier; row_key cannot be derived |
| `NORMALIZATION_TENANT_MISSING` | `tenant_id` is absent, None, or empty string |
| `NORMALIZATION_CURRENCY_MISMATCH` | `currency` is present but is not `"GEL"` |
| `NORMALIZATION_STATUS_POLICY_MISSING` | `status_policy` object is absent or lacks `included` / `excluded` lists |
| `NORMALIZATION_DRILLDOWN_LINK_MISSING` | A required `journal_entry_id`, `posting_log_id`, or `source_draft_id` is absent |
| `NORMALIZATION_EVIDENCE_LINK_MISSING` | A required `evidence_bundle_id` is absent where the fixture requires it |
| `NORMALIZATION_UNKNOWN_REPORT` | The `report_name` snake_case key is not in the canonical mapping |

---

## 12. Future Helper Function Signatures

The following signatures define the contract for the future runtime normalization helpers. **These
functions are not implemented in app code in H28.** They are defined as prototypes inside the test
file for contract validation only. The production implementation is deferred to H29 or later.

```python
def normalize_report_snapshot(
    raw: dict,
    *,
    source: str,
    report_name: str,
    tenant_id: str,
) -> dict:
    """
    Produce a canonical normalized snapshot from a raw report output dict.

    Parameters:
        raw         Raw report output from legacy or posted-ledger path (dict).
        source      One of: "legacy", "posted_ledger", "expected_fixture".
        report_name Snake-case report key, e.g. "trial_balance".
        tenant_id   Required; normalization fails if empty.

    Returns:
        Normalized snapshot dict conforming to the canonical shape (Section 4).

    Raises:
        ValueError  With a NORMALIZATION_* error code prefix on any contract violation.
    """
    ...


def normalize_report_rows(
    rows: list[dict],
    *,
    report_name: str,
    tenant_id: str,
) -> list[dict]:
    """
    Normalize a list of raw report rows to canonical row shape (Section 5).

    Rows are sorted by stable key (canonical_row_key) before return.
    Cross-tenant rows raise ValueError with NORMALIZATION_TENANT_MISSING.

    Parameters:
        rows        List of raw row dicts from a report output.
        report_name Snake-case report key.
        tenant_id   Expected tenant; each row is validated against this.

    Returns:
        Sorted list of normalized row dicts conforming to canonical row shape.
    """
    ...


def canonical_money(value) -> str:
    """
    Convert any numeric or string money value to a canonical 2-decimal-place string.

    None → "0.00"
    int / float / Decimal / str → quantized to 0.01 with ROUND_HALF_UP.
    Unparseable → raises ValueError with NORMALIZATION_MONEY_PARSE_ERROR prefix.
    """
    ...


def canonical_row_key(row: dict, *, report_name: str) -> str:
    """
    Derive a stable, opaque row key using the priority hierarchy (Section 7).

    Raises ValueError with NORMALIZATION_UNSTABLE_ROW_KEY if no stable key can be derived.
    """
    ...
```

---

## 13. Normalization Flow

The following 8-step flow describes how a raw report output is normalized for comparison. This flow
is the contract for the future runtime implementation. **It is not executed in H28.**

1. **Receive raw output** — collect raw JSON dicts from old-path and new-path report runs.
2. **Validate required fields** — check `tenant_id`, `report_name`, `currency`, `status_policy`;
   raise `NORMALIZATION_*` errors on any violation.
3. **Normalize money values** — apply `canonical_money()` to every monetary field in `totals`
   and row `values`; reject floats after conversion.
4. **Derive stable row keys** — apply `canonical_row_key()` to each row; raise on unstable rows.
5. **Sort rows** — sort by stable key ascending; comparison must be order-independent.
6. **Map report name** — convert snake_case key to canonical display name using `REPORT_NAME_MAPPING`.
7. **Strip runtime-only metadata** — remove timestamps, request IDs, and other fields that differ
   between runs and are not part of the comparison contract.
8. **Return canonical snapshot** — conforming to the shape in Section 4, ready for diff.

---

## 14. Comparison Flow (Future — Not Executed in H28)

After normalization, the comparison proceeds as follows (defined for context; executed in a later task):

1. Normalize old-path output → `snap_old`.
2. Normalize new-path output → `snap_new`.
3. Normalize expected fixture snapshot → `snap_expected`.
4. Diff `snap_old` vs. `snap_expected` — classify any mismatches using H27 mismatch codes.
5. Diff `snap_new` vs. `snap_expected` — classify any mismatches.
6. Diff `snap_old` vs. `snap_new` — detect regressions introduced by the new path.
7. Log `ROUNDING_ONLY_DIFFERENCE` entries (≤ 0.01 GEL) as acceptable.
8. Fail on any structural mismatch code (all codes except `ROUNDING_ONLY_DIFFERENCE`).

---

## 15. Approval Gates

This task does not gate on G1–G10 directly. The normalizer contract (H28) is a prerequisite for
the snapshot comparison step (G6 in H27). The H28 contract tests must pass before G6 can be
satisfied.

| Dependency | Status |
|---|---|
| H25 — Fixture created | Merged |
| H26 — Expected totals validated | Merged |
| H27 — Comparison contract defined | Merged |
| H28 — Normalizer contract defined | This task |
| H29 — Runtime normalizer implementation | Future |
| G6 — Snapshot comparison green | Requires H28 + H29 |

---

## 16. Safety Rules

- No production data is used in any normalizer contract test or example in H28.
- No DB is created or connected to in H28.
- No runtime report endpoints are called in H28.
- No feature flag is enabled in H28 (`POSTED_LEDGER_REPORTS_ENABLED` stays OFF).
- Balance.ge remains `demo_mode`; `BALANCE_API_KEY` absent.
- No helper function is added to any `app/` module in H28.
- No connector behavior is changed.
- No infrastructure is changed.
- No credentials are changed.
- No UI/static files are changed.
- No runtime business logic code is modified.

---

## 17. H28 Results

| Test group | Result |
|---|---|
| H28 targeted (27 tests) | 27/27 passed |
| H27 + H28 combined (55 tests) | 55/55 passed |
| Related report/fixture tests | all passed |
| Full unit suite | 4086+ passed / 0 failed / 2 skipped |
| App code modified | none |
| Fixture JSON modified | none |

---

## 18. Non-Goals

H28 does **not**:

- Create a DB.
- Connect to a DB.
- Execute SQL.
- Run migrations.
- Load fixture data into any DB.
- Use production data.
- Call runtime report APIs.
- Implement runtime helpers in app code.
- Modify any file under `app/`.
- Modify connector or posting behavior.
- Activate Balance.ge.
- Enable `POSTED_LEDGER_REPORTS_ENABLED`.
- Change UI/static files.
- Change infrastructure.
- Change credentials.
- Start H29.

---

## 19. Next Task

Only after PR merge, deploy, and live verification of H28:

**H29 — Synthetic Snapshot Normalizer Runtime Implementation**

or, if local PostgreSQL becomes available:

**Controlled Disposable DB Fixture Load Dry Run** (H24 unblocking path)
