# Reports Ledger Integrity Audit

## A) Purpose

Task 11C-H1: Audit-only investigation of current report data sources.

This document:

- Defines report ledger integrity requirements for Bridge Hub.
- Audits current report source tables across all report services.
- Establishes the contract that official financial reports must use
  posted `journal_entries` only.
- Identifies the critical gap: Bridge Hub currently has no separate
  immutable `journal_entries` table — reports source from `journal_drafts`
  with a `status = 'posted'` filter.
- Classifies risk for each report endpoint.
- Defines the required future behavior and implementation sequence.

**This task does not change runtime report behavior.**
**No migrations are created.**
**No SQL is executed.**
**No production DB is touched.**
**No Balance.ge activation.**

Cross-reference:
- `docs/accounting-truth-schema-contract.md` (Task 10E-D)
- `docs/trust-foundation-runtime-implementation-sequence.md` (Task 11C)
- `app/storage/migrations/010_evidence_bundle_schema.sql` (Task 11C-G1)

---

## B) Accounting Truth Definitions

### journal_drafts

The working table. Contains AI-proposed, human-edited, and pending-approval
accounting records. Status lifecycle:

```
drafted → approved → posted → (reversal/correction)
         ↓
       rejected
```

A `journal_drafts` row, even when `status = 'posted'`, is **not** an
immutable official ledger fact until it is written to a separate, append-only
`journal_entries` table (future state).

The `journal_entries` column inside `journal_drafts` is a **JSONB array**
holding the debit/credit line pairs for that draft. It is **not** a separate
table.

### approved journal_drafts

An approved draft is an accounting candidate that passed human review.
It is **not** official ledger truth. It must not appear in official financial
reports unless clearly labeled as "preview" or "pending posting."

### journal_entries (target — not yet a separate table)

In the target architecture, `journal_entries` is a **separate, immutable,
append-only table** populated only by the posting service after a successful
connector write (or a manual approve-and-lock step for non-connector tenants).

**Current state:** `journal_entries` exists only as a JSONB column within
`journal_drafts`, not as an independent table.

### journal_entry_lines / ledger lines

The individual debit/credit account movements. In the target architecture,
these are rows in a `journal_entry_lines` (or `journal_lines`) table linked
to the `journal_entries` table. Currently they are embedded as JSONB
within `journal_drafts.journal_entries`.

### reversal/correction entries

Future required model. When a posted entry must be corrected, the process
must:
1. Create a reversal entry (mirror debit/credit) referencing the original.
2. Create a new corrected entry.
3. Never modify a previously posted entry in place.

No reversal table or workflow exists yet. This is a blocker for full
accounting truth compliance.

### official reports

Reports that represent official accounting state to management,
auditors, tax authorities, or regulators:

- Trial Balance
- Profit and Loss (P&L / Income Statement)
- Balance Sheet
- Cash Flow Statement
- VAT Register / VAT Summary
- Payroll Summary (when used for tax reporting)

These must source from posted `journal_entries` only.

---

## C) Current Report Source Audit

### C1. financial_statements_service.py — `_get_trial_balance` (internal)

| Item | Value |
|---|---|
| File | `app/api/services/financial_statements_service.py` |
| Function | `_get_trial_balance(tenant_id, date_from, date_to)` |
| Source table | `journal_drafts` |
| Reads JSONB column | `journal_entries` (inside `journal_drafts`) |
| Status filter | `status = 'posted'` |
| Uses `journal_drafts`? | **YES** |
| Uses separate `journal_entries` table? | NO — JSONB column only |
| Risk level | **HIGH** |
| Reason | Draft table used as accounting truth; no immutable posting ledger. Status filter is the only guard. |
| Recommended future change | Migrate to query `journal_entry_lines` (separate table) once 11C-H3 migration is executed. |

### C2. financial_statements_service.py — `build_profit_and_loss`

| Item | Value |
|---|---|
| File | `app/api/services/financial_statements_service.py` |
| Function | `build_profit_and_loss(tenant_id, date_from, date_to)` |
| Source | Calls `_get_trial_balance` → `journal_drafts` |
| Status filter | `status = 'posted'` (inherited) |
| Uses `journal_drafts`? | **YES** (via `_get_trial_balance`) |
| Risk level | **HIGH** |
| Recommended future change | Source from separate `journal_entries` / `journal_entry_lines` table. |

### C3. financial_statements_service.py — `build_balance_sheet`

| Item | Value |
|---|---|
| File | `app/api/services/financial_statements_service.py` |
| Function | `build_balance_sheet(tenant_id, as_of)` |
| Source | Calls `_get_trial_balance` → `journal_drafts` |
| Status filter | `status = 'posted'` (inherited) |
| Uses `journal_drafts`? | **YES** |
| Risk level | **HIGH** |
| Recommended future change | Source from separate `journal_entries` / `journal_entry_lines` table. |

### C4. ledger_service.py — `get_trial_balance`

| Item | Value |
|---|---|
| File | `app/api/services/ledger_service.py` |
| Function | `get_trial_balance(tenant_id, date_from, date_to)` |
| Source | `journal_drafts` CROSS JOIN LATERAL `journal_entries` JSONB |
| Status filter | `status = 'posted'` |
| Uses `journal_drafts`? | **YES** |
| Risk level | **CRITICAL** |
| Reason | This is the primary trial balance function used in `/reports/trial-balance`. Sources from draft table. |
| Recommended future change | Migrate to query `journal_entry_lines` from separate `journal_entries` table. |

### C5. ledger_service.py — `get_account_ledger`

| Item | Value |
|---|---|
| File | `app/api/services/ledger_service.py` |
| Function | `get_account_ledger(tenant_id, account_code, ...)` |
| Source | `journal_drafts` CROSS JOIN LATERAL `journal_entries` JSONB |
| Status filter | `status = 'posted'` |
| Uses `journal_drafts`? | **YES** |
| Risk level | **HIGH** |
| Note | Opening balance also sourced from `journal_drafts`. |
| Recommended future change | Migrate to `journal_entry_lines` once posting writes there. |

### C6. ledger_service.py — `get_counterparty_ledger`

| Item | Value |
|---|---|
| File | `app/api/services/ledger_service.py` |
| Function | `get_counterparty_ledger(tenant_id, counterparty_inn, ...)` |
| Source | `journal_drafts` with `status = 'posted'` |
| Uses `journal_drafts`? | **YES** |
| Risk level | **HIGH** |
| Note | Returns `journal_entries` JSONB array from the draft row. |
| Recommended future change | Migrate to `journal_entries` + `journal_entry_lines` tables. |

### C7. ledger_service.py — `get_payroll_ledger`

| Item | Value |
|---|---|
| File | `app/api/services/ledger_service.py` |
| Function | `get_payroll_ledger(tenant_id, employee_id, year)` |
| Source | `journal_drafts` CROSS JOIN LATERAL `journal_entries` JSONB |
| Status filter | `status = 'posted'` |
| Uses `journal_drafts`? | **YES** |
| Risk level | **HIGH** |
| Note | Used for payroll tax reporting — elevated sensitivity. |
| Recommended future change | Migrate to `journal_entry_lines` from separate ledger table. |

### C8. ledger_service.py — `get_journal_entries`

| Item | Value |
|---|---|
| File | `app/api/services/ledger_service.py` |
| Function | `get_journal_entries(tenant_id, date, limit, offset)` |
| Source | `journal_drafts` with `status = 'posted'` |
| Uses `journal_drafts`? | **YES** |
| Risk level | **HIGH** |
| Note | Returns `draft_id` as the identifier — exposes draft provenance in what should be a ledger view. |
| Recommended future change | Should return `journal_entry_id` from a separate `journal_entries` table. |

### C9. routes_reports.py — `/reports/pnl/detail` — **CRITICAL**

| Item | Value |
|---|---|
| File | `app/api/routes_reports.py` |
| Endpoint | `GET /reports/pnl/detail` |
| Source | `journal_drafts` |
| Status filter | `status IN ('posted', 'simulated_success')` |
| Uses `journal_drafts`? | **YES** |
| Risk level | **CRITICAL** |
| Reason | Treats `simulated_success` entries as accounting truth alongside `posted`. Simulation is a preview, not official state. This drills down into P&L but mixes simulated results with posted results. |
| Recommended future change | Remove `simulated_success` from the filter. Migrate source to `journal_entry_lines`. |

### C10. routes_reports.py — `/reports/bs/detail` — **CRITICAL**

| Item | Value |
|---|---|
| File | `app/api/routes_reports.py` |
| Endpoint | `GET /reports/bs/detail` |
| Source | `journal_drafts` |
| Status filter | **NONE** — no status filter applied |
| Uses `journal_drafts`? | **YES** |
| Risk level | **CRITICAL** |
| Reason | Balance Sheet drill-down returns ALL journal drafts regardless of status — including drafted, approved, and rejected entries. Unposted drafts appear as if they were accounting facts. |
| Recommended future change | Add `status = 'posted'` filter immediately (minimal fix). Migrate to `journal_entry_lines` in 11C-H4. |

### C11. routes_tax.py — `/tax/vat-register`

| Item | Value |
|---|---|
| File | `app/api/routes_tax.py` |
| Endpoint | `GET /tax/vat-register` |
| Source | `journal_drafts` |
| Status filter | `status = 'posted'` |
| Uses `journal_drafts`? | **YES** |
| Risk level | **HIGH** |
| Note | Used for VAT reporting obligations. Sources from draft table. |
| Recommended future change | Migrate to `journal_entry_lines` or dedicated VAT ledger table. |

### C12. routes_reports.py — `/reports/cashflow` and `/reports/cashflow/detail`

| Item | Value |
|---|---|
| File | `app/api/routes_reports.py` |
| Endpoints | `GET /reports/cashflow`, `GET /reports/cashflow/detail` |
| Source | `bank_transactions` |
| Status filter | N/A (bank_transactions) |
| Uses `journal_drafts`? | NO |
| Risk level | **MEDIUM** |
| Note | Cash flow sourced from raw bank transactions only — not GL-mapped. Does not distinguish between bank movements and their accounting classification. Not IAS 7 compliant for official reporting. |
| Recommended future change | Link `bank_transactions` to posted `journal_entry_lines` via reconciliation. Classify into operating/investing/financing activities. |

### C13. routes_reports.py — `/reports/monthly`, `/reports/annual`, `/reports/audit-trail`

| Item | Value |
|---|---|
| File | `app/api/routes_reports.py` |
| Endpoints | `/reports/monthly`, `/reports/annual`, `/reports/audit-trail` |
| Source | `pipeline_runs` (operational table) |
| Uses `journal_drafts`? | NO |
| Risk level | **INFO** |
| Note | Operational/dashboard metrics only. Not financial statements. Low risk. |

### C14. routes_reports.py — `/reports/ledger/{account_code}`, `/reports/counterparty/{inn}`, `/reports/payroll`, `/reports/journal`

These are wrappers around `ledger_service.py` functions (see C5–C8 above). Risk inherited.

---

## D) Risk Classification Summary

| Risk Level | Count | Endpoints / Functions |
|---|---|---|
| **CRITICAL** | 3 | `ledger_service.get_trial_balance`, `routes_reports./reports/pnl/detail`, `routes_reports./reports/bs/detail` |
| **HIGH** | 8 | `financial_statements._get_trial_balance`, `build_profit_and_loss`, `build_balance_sheet`, `get_account_ledger`, `get_counterparty_ledger`, `get_payroll_ledger`, `get_journal_entries`, `vat-register` |
| **MEDIUM** | 1 | Cash flow (bank_transactions only, not GL-mapped) |
| **LOW** | 0 | No report explicitly sources from a separate immutable `journal_entries` table |
| **INFO** | 3 | Monthly/annual summary, audit trail (pipeline_runs) |

### Risk Definitions

- **CRITICAL**: Official report reads `journal_drafts` without a proper status filter,
  or includes non-posted statuses (`simulated_success`) as accounting truth.
- **HIGH**: Official report reads `journal_drafts` filtered by `status = 'posted'`
  but from the mutable draft table, not an immutable posting ledger.
- **MEDIUM**: Report source is not a posted ledger (uses bank_transactions or
  operational tables without GL linkage).
- **LOW**: Report explicitly uses a separate immutable `journal_entries` table.
- **INFO**: Operational/dashboard metric, not a financial statement.

---

## E) Required Future Behavior

Official reports MUST:

1. **Default to posted `journal_entries` only** — sourced from a separate,
   immutable, append-only table populated by the posting service.
2. **Never treat approved drafts as posted ledger truth** — approved status
   means ready-to-post, not posted.
3. **Never treat `simulated_success` as posted truth** — simulation is a
   payload preview, not an accounting fact.
4. **Expose draft-based reports only under explicit preview/draft mode** —
   with a clear `"data_source": "draft_preview"` label in the response.
5. **Clearly label preview reports as non-official** — UI and API response
   must indicate the data is not final.
6. **Apply tenant_id filter** — every query must be scoped to the
   requesting tenant.
7. **Apply period/date filters** — reports must support date-range and
   period-lock checks.
8. **Use posted status or immutable posted entry table** — not `simulated_success`,
   not `approved`, not `drafted`.
9. **Link to evidence bundle when available** — posted entries should carry
   `evidence_bundle_id` for auditability.
10. **Support reversals/corrections instead of editing posted truth** —
    no in-place update of posted entries.
11. **Fix `/reports/bs/detail` immediately** — add `status = 'posted'` filter
    as a minimal safety patch (separate minimal-fix commit before migration).

---

## F) Report-by-Report Future Requirements

### Trial Balance

- **Source table**: `journal_entry_lines` (target) / `journal_entries` (target)
- **Required filters**: `tenant_id`, `date_range`, `period_lock_check`
- **Forbidden draft usage**: must not include `status != 'posted'` entries
- **Expected output**: balanced debit/credit turnover per account code;
  opening/closing balances; `data_source: "posted"` field in response
- **Current gap**: sources from `journal_drafts.journal_entries` JSONB

### Profit and Loss

- **Source table**: aggregated from `journal_entry_lines` per account classification
- **Required filters**: `tenant_id`, `date_from`, `date_to`
- **Forbidden draft usage**: no `simulated_success`; no unapproved drafts
- **Expected output**: revenue/COGS/opex/EBIT; `data_source: "posted"` field
- **Current gap**: same as trial balance (calls `_get_trial_balance`)

### Balance Sheet

- **Source table**: aggregated from `journal_entry_lines` as-of date
- **Required filters**: `tenant_id`, `as_of` date
- **Forbidden draft usage**: no unfiltered `journal_drafts` drill-down
- **Expected output**: assets/liabilities/equity; balanced check; `data_source: "posted"` field
- **Current critical gap**: `/reports/bs/detail` has NO status filter — returns all drafts

### Cash Flow

- **Source table**: `journal_entry_lines` classified by activity type
  (operating/investing/financing) — linked to `bank_transactions` via reconciliation
- **Required filters**: `tenant_id`, `period`, activity classification
- **Forbidden draft usage**: no unreconciled bank transactions as cash flow
- **Expected output**: IAS 7 indirect/direct method; `data_source: "posted"` field
- **Current gap**: uses `bank_transactions` only without GL classification

### VAT Summary

- **Source table**: `journal_entry_lines` for VAT accounts (1760, 3310, 3311, etc.)
- **Required filters**: `tenant_id`, `year`, `month`, VAT account codes
- **Forbidden draft usage**: must not include unapproved VAT entries
- **Expected output**: input VAT / output VAT / net VAT payable;
  `data_source: "posted"` field; tax period lock check
- **Current gap**: sources from `journal_drafts` with `status = 'posted'`

### Payroll Summary

- **Source table**: `journal_entry_lines` for payroll accounts (7110-7130, 3370/3380)
- **Required filters**: `tenant_id`, `year`, `employee_id`, payroll account codes
- **Forbidden draft usage**: payroll entries for tax reporting must be posted
- **Expected output**: wages/deductions/employer contributions per employee;
  `data_source: "posted"` field
- **Current gap**: sources from `journal_drafts` with `status = 'posted'`

---

## G) Implementation Plan for 11C-H2 through 11C-H6

### 11C-H1 (current task)
- Audit document: this file.
- Contract tests: `tests/unit/test_reports_ledger_integrity_contract.py`
- No runtime behavior changes.
- No migrations.
- No SQL executed.

### 11C-H2 — Contract tests for posted journal_entries fixtures
- Create read-only contract tests using fixture data.
- Define expected output format for each official report.
- Define `data_source` field contract.
- No runtime behavior changes.
- No migrations.

### 11C-H3 — Migrate trial balance and P&L read path
- Add `data_source` field to trial balance and P&L responses.
- Add posted filter as required; remove `simulated_success` from P&L detail.
- Fix `/reports/bs/detail` missing status filter (minimal patch).
- Prerequisite: separate `journal_entries` table migration (planned DDL).
- Tests: trial balance and P&L return `data_source: "posted"`.

### 11C-H4 — Migrate balance sheet / cash flow / VAT read path
- Fix balance sheet to source from posted entries only.
- Classify cash flow by GL account movement type.
- Fix VAT register to require explicit posted status.
- Tests per report.

### 11C-H5 — Compatibility / draft preview mode
- Add explicit `?mode=draft` query parameter for draft-preview access.
- Label draft preview responses with `"data_source": "draft_preview"`.
- Confirm `mode=draft` is never the default.
- Tests: default returns posted; `mode=draft` returns labeled preview.

### 11C-H6 — Live verification
- Deploy and verify all official report endpoints.
- Confirm `/health` and `/version` match.
- Confirm static pages and protected endpoints.
- Confirm Balance.ge is still demo_mode/inactive.

---

## H) Stop Conditions

This task (11C-H1) and Codex must stop if:

- Report behavior change is required in this task.
- Migration creation is required.
- Production DB access is required.
- Source table meaning is ambiguous and cannot be resolved by code inspection.
- Tests fail.
- Files outside the allowed set (docs + tests only) need changes.

---

## I) Commercial Pilot Gate

Bridge Hub is **not commercial-pilot ready** until:

1. Official reports use separate immutable `journal_entries` table (not `journal_drafts`).
2. `/reports/bs/detail` has a `status = 'posted'` filter.
3. `simulated_success` is removed from all official report queries.
4. Draft/preview reports are labeled non-official (`data_source: "draft_preview"`).
5. Reversal/correction model is planned and tested.
6. Evidence bundle link is planned for each posted entry.
7. Opening balance / import strategy is planned.
8. VAT reporting uses posted entries with period-lock check.
9. Balance.ge activation gates are all met (currently none are).

---

## J) Non-goals

- No runtime report behavior change in this task.
- No SQL execution.
- No migration creation or execution.
- No production DB access.
- No Balance.ge activation.
- No connector behavior change.
- No approval/posting business logic change.
- No Cloud Run / Cloud SQL / GitHub Actions changes.
