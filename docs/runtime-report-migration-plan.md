# Bridge Hub — Runtime Report Migration Plan

**Task:** 11C-H13
**Type:** Contract document and tests only — no runtime code change, no SQL, no migration execution.
**Date:** 2026-05-14
**Follows:** 11C-H12 `docs/controlled-local-test-migration-execution-results.md`

---

## 1. Purpose

This plan defines how Bridge Hub's official reports must migrate from their current
source — `journal_drafts` JSONB — to the immutable posted ledger tables:
`journal_entry_headers` and `journal_entry_lines`.

**H13 does not change runtime report behavior. H13 does not modify
`financial_statements_service.py`, `ledger_service.py`, or `routes_reports.py`.
H13 does not execute SQL. H13 does not execute any migration. H13 does not connect
to any database. H13 does not touch the production database or Cloud Run database.**

This document is the behavioral specification that H14–H19 will implement in sequence,
each requiring explicit human approval before proceeding.

---

## 2. Background

The H1–H12 foundation that makes this plan necessary:

| Task | Deliverable |
|---|---|
| H1 | Reports ledger integrity audit — CRITICAL: reports read from `journal_drafts` JSONB; no immutable ledger; `simulated_success` treated as truth |
| H2 | Posted journal entries schema contract — defined `journal_entry_headers` + `journal_entry_lines` + `journal_entry_sources` with all required fields and invariants |
| H3 | Safe migration plan — defined constraint requirements, index requirements, additive-only DDL rules |
| H4 | SQL migration file `011_posted_journal_entries_schema.sql` created but **not executed** |
| H5 | Posting service ledger write contract — defined write rules after real ERP connector posting |
| H6 | Posting service ledger write mock tests — 59 tests encoding future write rules |
| H7 | Reports posted-ledger read contract — defined how reports must read from `journal_entry_headers` + `journal_entry_lines` |
| H8 | Report query mock tests — 89 tests for future query rules |
| H9 | Reversal / correction contract — defined append-only reversal and correction model |
| H10 | Evidence / audit export linkage contract — defined how `evidence_bundle_id` links to posted entries |
| H11 | Controlled local/test migration execution plan — defined preflight, execution, validation, and rollback rules |
| H12 | Controlled local/test migration execution — **BLOCKED**: no disposable local/test PostgreSQL available; static analysis passed; production not touched |
| H13 (this task) | Runtime report migration plan — defines how official reports must migrate to posted ledger truth; docs and contract tests only |

Until H14–H19 are explicitly approved and executed in sequence, official report
runtime behavior is **unchanged**. Reports continue to read from their current sources.

---

## 3. Current Risk

The H1 audit identified the following risks that this migration plan addresses:

1. **`journal_drafts` is not accounting truth** — `journal_drafts` contains draft,
   approved, and submitted records that have not been confirmed by a real ERP connector.
   Using draft data as the source for official financial reports is a ledger integrity risk.

2. **`simulated_success`, `mock_posting`, `dry_run` treated as truth** — any report
   that reads entries with these status values is reporting simulated data as real
   accounting. This is a critical integrity violation.

3. **`approved` and `auto_approved` are not posted** — approval gates the entry for
   posting but does not confirm it was posted to the ERP. An approved-but-not-posted
   entry must not appear in official balance sheet, P&L, or trial balance totals.

4. **No immutable ledger** — without `journal_entry_headers`, there is no source of
   truth that is guaranteed immutable after a confirmed ERP posting. `journal_drafts`
   rows can be updated, corrected, or deleted.

5. **Report runtime behavior must not change until tested and explicitly approved** —
   the current report behavior, while risky, is what production depends on. Migration
   must happen only after posted ledger tables exist in the target environment and
   integration tests confirm correctness.

6. **Report migration must happen only after posted ledger tables exist** — if
   `journal_entry_headers` and `journal_entry_lines` do not exist in the database,
   any report service that tries to query them will fail. Migration requires the schema
   migration (H11/H12) to have been successfully executed in the target environment.

---

## 4. Target Report Truth Model

After migration, all official reports must read exclusively from the posted ledger:

### 4.1 Primary source tables

| Table | Role |
|---|---|
| `journal_entry_headers` | One row per confirmed ERP posting; status, dates, totals, tenant, audit actors |
| `journal_entry_lines` | Double-entry lines per header; account_code, debit, credit, tax, counterparty |

### 4.2 Mandatory filters

Every report query must apply all of the following filters unless a named exception is
explicitly documented:

| Filter | Rule |
|---|---|
| `tenant_id` | Must equal `request.state.tenant_id` from authenticated JWT — never from user input |
| `status = 'posted'` | Standard official totals must include only `status = 'posted'` entries |
| `status NOT IN (...)` | `draft`, `approved`, `auto_approved`, `simulated_success`, `mock_posting`, `dry_run` must never appear in official totals |
| No default tenant | If `tenant_id` is missing from authenticated context, query must fail closed — never fall back to `'default'` |

### 4.3 Correction and reversal handling

| View type | Rule |
|---|---|
| Net official totals | Include `status = 'posted'`; exclude `status = 'reversed'` originals from net totals; include `status = 'correction'` as final net value |
| History view | Include all statuses including `reversed`, `correction`, `voided` with explicit labels |
| Voided entries | Excluded from all net totals; included in history view with `voided` label |
| Double counting | Reversed originals and their reversal entries must not both appear in net totals |

### 4.4 Cross-tenant isolation

- No report may aggregate across multiple `tenant_id` values unless a future
  consolidation feature is explicitly designed and approved.
- No report endpoint may accept `tenant_id` as a query parameter or request body
  field — tenant must come from `request.state.tenant_id` (set by auth middleware).

---

## 5. Report Migration Targets

### 5a. Trial Balance

**Current risk:** reads from `journal_drafts`; approved/simulated entries counted.

**Target source:** `journal_entry_lines` joined to `journal_entry_headers`

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| `status = 'posted'` | mandatory for net totals |
| Period/date filter | mandatory — must be user-supplied or current-period default |
| Opening balance | Aggregate from entries before period start |
| Movement | Aggregate from entries within period (debits and credits) |
| Closing balance | Opening + movement |
| Debit/credit balance | total debits must equal total credits across all accounts (double-entry invariant) |
| `journal_drafts` | forbidden as truth source |
| `simulated_success` | excluded |

### 5b. Profit & Loss Summary

**Current risk:** income/expense totals may include unapproved or simulated entries.

**Target source:** `journal_entry_lines` filtered to income and expense `account_code` ranges,
joined to `journal_entry_headers`

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| `status = 'posted'` | mandatory |
| Period filter | mandatory |
| Income accounts | Filter by chart-of-accounts income code range |
| Expense accounts | Filter by chart-of-accounts expense code range |
| `journal_drafts` | forbidden as truth source |
| `simulated_success` | excluded |

### 5c. Profit & Loss Detail

**Target source:** `journal_entry_lines` joined to `journal_entry_headers` — full
line-level detail

| Requirement | Rule |
|---|---|
| All P&L Summary requirements | inherited |
| Line rows | Individual `journal_entry_lines` rows with account_code, description, debit, credit |
| `source_draft_id` | exposed where available — enables drill-down to originating draft |
| `posting_log_id` | exposed where available — enables drill-down to connector execution |
| `evidence_bundle_id` | exposed where available — enables drill-down to evidence package |

### 5d. Balance Sheet Summary

**Current risk:** asset/liability/equity totals may include unapproved entries; no
explicit status filter documented in H1.

**Target source:** `journal_entry_lines` filtered to balance sheet `account_code` ranges,
joined to `journal_entry_headers`

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| `status = 'posted'` | mandatory |
| As-of-date | cumulative — sum all `entry_date <= as_of_date` |
| Opening balance support | aggregate from entries before reporting start date |
| Asset/liability/equity classification | by chart-of-accounts range |
| `journal_drafts` | forbidden as truth source |

### 5e. Balance Sheet Detail

**Current risk (H1):** balance sheet detail had no explicit `status` filter — the H1
audit flagged this as a critical integrity gap. Draft and approved entries could
appear in BS detail rows.

**Target source:** `journal_entry_lines` joined to `journal_entry_headers`

| Requirement | Rule |
|---|---|
| All BS Summary requirements | inherited |
| `status = 'posted'` | mandatory — this fixes the H1 gap |
| `draft` | explicitly excluded |
| `approved` | explicitly excluded |
| `auto_approved` | explicitly excluded |
| `simulated_success` | explicitly excluded |
| Detail rows | Individual `journal_entry_lines` with account_code, counterparty, amounts |

### 5f. VAT Register

**Target source:** `journal_entry_lines` where `tax_code IS NOT NULL` or
`vat_amount IS NOT NULL`, joined to `journal_entry_headers`

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| `status = 'posted'` | mandatory |
| Period filter | mandatory — regulatory reporting requires exact period |
| `tax_code` / `vat_amount` filter | lines without tax fields excluded from VAT register |
| `journal_drafts` | forbidden as truth source |
| `simulated_success` | excluded |
| Format | must be reproducible for the same period — regulatory compliance |

### 5g. Account Ledger

**Target source:** `journal_entry_lines` filtered by `account_code`, joined to
`journal_entry_headers`

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| `account_code` filter | mandatory — user-supplied account scope |
| Date range filter | mandatory |
| Opening balance | aggregate from entries before date range start |
| Running balance | per-row cumulative balance |
| Closing balance | opening + movement |
| `journal_drafts` | forbidden as truth source |

### 5h. Counterparty Ledger

**Target source:** `journal_entry_lines` filtered by `counterparty_id`, joined to
`journal_entry_headers`

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| `counterparty_id` filter | mandatory — user-supplied counterparty scope |
| Date range filter | mandatory |
| Opening / closing balance | same logic as account ledger |
| `journal_drafts` | forbidden as truth source |

### 5i. Payroll Ledger

**Target source:** `journal_entry_lines` or `journal_entry_headers` filtered by
`source_type = 'payroll'` or payroll account code range

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| Period filter | mandatory |
| Payroll identification | by `source_type` or account range — must be defined in config |
| `journal_drafts` payroll entries | forbidden as truth source after migration |
| `simulated_success` | excluded |

### 5j. Journal Entries List

**Target source:** `journal_entry_headers` with optional `journal_entry_lines` join

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| Standard view | `status = 'posted'` only |
| History view | `status IN ('posted','reversed','correction','voided')` with explicit labels |
| Reversal/correction chains | must not double-count — label originals as `reversed`, label reversals as `reversal`, label corrections as `correction` |
| Pagination | required for large result sets |
| Date/period filter | available |

### 5k. Cash Flow

**Target source:** `journal_entry_lines` filtered to cash and bank `account_code`
ranges, joined to `journal_entry_headers`

| Requirement | Rule |
|---|---|
| `tenant_id` filter | mandatory |
| Period filter | mandatory |
| `status = 'posted'` | mandatory |
| Operating / investing / financing | classified by account code or `source_type` |
| Opening / closing cash positions | aggregate positions before and after period |
| `journal_drafts` | forbidden as truth source |
| Bank transaction linkage | `bank_transaction_id` on lines links to bank records, but journal entry remains truth |

---

## 6. Reversal and Correction Handling in Reports

All official reports must handle reversal and correction chains explicitly:

1. **Standard official totals** — use `status = 'posted'` net accounting rules.
   A reversed entry (`status = 'reversed'`) must not appear in net totals.
   A correction entry (`status = 'correction'`) represents the final corrected value
   and must be included in net totals.

2. **History view** — may include `reversed`, `correction`, and `voided` entries with
   explicit status labels so the reader can trace the full accounting history.

3. **No double counting** — both the reversed original and its reversing entry must
   not simultaneously appear in net totals. The reversing entry zeroes out the original.

4. **Correction chain integrity** — where a correction follows a reversal, the net
   official position is the correction entry value. The original and reversal cancel
   each other out.

5. **UI/API labeling** — the API response and UI must clearly distinguish between
   the net official view and the full history view. Mixing both without labels is a
   contract violation.

6. **Report support export** — export packages for reports must include the full
   reversal/correction chain in the history section, separate from the net totals section.

---

## 7. Evidence and Audit Linkage in Reports

Report detail rows must expose audit linkage fields where available:

1. **`evidence_bundle_id`** — where set on `journal_entry_headers`, detail report rows
   must expose this ID to enable drill-down to the full evidence package.

2. **`posting_log_id`** — where set, must be exposed to enable drill-down to the
   connector execution log confirming the ERP write.

3. **`source_draft_id`** — where set, must be exposed to enable drill-down to the
   originating `journal_drafts` row and its approval history.

4. **Full drill-down chain** — the API must support: report total → ledger line →
   header → evidence bundle → posting log → source draft → approval events.

5. **No raw secrets in reports** — `_strip_unsafe` or equivalent sanitization must be
   applied to any connector response metadata before it is included in a report row
   or export. API keys, passwords, tokens, and encrypted values must never appear.

---

## 8. Tenant Isolation and Permissions

Every report operation must enforce:

1. **`tenant_id` is mandatory** — derive from `request.state.tenant_id` (set by
   tenant middleware from JWT). Never accept `tenant_id` from query params or body.

2. **Missing `tenant_id` fails closed** — if `request.state.tenant_id` is absent,
   the report endpoint must return 401/403 and must not fall back to `'default'`.

3. **No cross-tenant aggregation** — no report may JOIN or aggregate across multiple
   tenants unless a future consolidation feature is explicitly approved.

4. **Permission required** — each report endpoint must require an appropriate
   `report:read` or scoped permission. Unauthenticated or unpermissioned requests
   must receive HTTP 401 or 403.

5. **No user-controlled tenant** — if a user can set `tenant_id` in the request
   body and receive data from a different tenant, that is a security vulnerability.
   Tenant must come from auth middleware only.

---

## 9. Migration Rollout Sequence

| Task | Description |
|---|---|
| **H13** (this task) | Runtime report migration plan/tests only — no runtime change |
| **H14** | Report service query tests with mocks/local fakes — encode future query rules as tests without changing runtime code |
| **H15** | Report service implementation behind feature flag — implement new report queries against posted ledger, gated by feature flag; default behavior unchanged |
| **H16** | Local/test verification with posted ledger fixture data — run H15 implementation against disposable local/test DB with synthetic posted entries; validate all report types |
| **H17** | Report UI/API drill-down tests — test that report detail rows expose evidence_bundle_id, posting_log_id, source_draft_id and support full audit chain navigation |
| **H18** | Controlled runtime switch for non-production — enable posted-ledger report reading in a non-production environment; compare output against current behavior; document any discrepancies |
| **H19** | Production report migration approval plan — only after H18 is confirmed; design production switch with rollback plan, monitoring requirements, and explicit human approval gate |

Each task follows the same protocol: branch → docs/tests → PR → merge → deploy →
live verification → confirmed before starting the next task.

No task in this sequence may be started without explicit human approval and
confirmation that all prior tasks are live-verified.

---

## 10. Feature Flag and Compatibility Rule

1. **Feature flag required** — the runtime switch from `journal_drafts` to posted
   ledger reads must be controlled by a feature flag (e.g., an environment variable
   `POSTED_LEDGER_REPORTS_ENABLED=true`) or explicit configuration. The flag must
   default to `false` (legacy behavior) in production until H19 is approved.

2. **Default behavior unchanged** — until the feature flag is enabled, report
   services must continue reading from their current source. No behavior change is
   permitted by merely deploying H15 code.

3. **Fail closed if tables missing** — if the feature flag is enabled but
   `journal_entry_headers` does not exist in the database, the report service must
   fail closed with a clear error rather than silently querying `journal_drafts`.
   A missing table must never be silently ignored.

4. **No silent fallback to `journal_drafts`** — once a report query is configured
   to read from the posted ledger, it must not silently fall back to `journal_drafts`
   if the posted ledger is empty. An empty `journal_entry_headers` table in a
   production environment likely means the migration has not been executed — not that
   there are legitimately zero posted entries. Falling back would produce a misleading
   non-empty report from draft data.

5. **Explicit compatibility mode only** — if a temporary compatibility mode is needed
   during migration (reading from both sources), it must be explicitly designed,
   approved, and labeled in the API response to indicate it is in compatibility mode.

---

## 11. Non-Goals for H13

This task explicitly does **not**:

- Change any runtime report behavior.
- Modify `financial_statements_service.py`.
- Modify `ledger_service.py`.
- Modify `routes_reports.py`.
- Modify `posting_service.py`.
- Modify `approval_service.py`.
- Modify `evidence_bundle_service.py`.
- Execute any SQL.
- Execute any migration.
- Connect to any database (production or otherwise).
- Touch the production database.
- Touch the Cloud Run database.
- Activate Balance.ge.
- Change any credentials or secrets.
- Change any connector behavior.
- Change any production infrastructure or deployment configuration.
- Add `011_posted_journal_entries_schema.sql` to the automatic startup migration list.
- Change any UI or static files.
- Start H14 work.

This task produces two files only:
- `docs/runtime-report-migration-plan.md` (this document)
- `tests/unit/test_runtime_report_migration_plan_contract.py`

---

## 12. Success Criteria for Future Runtime Migration

A future migration is complete only when all of the following are confirmed:

1. All official reports read exclusively from `journal_entry_headers` + `journal_entry_lines`.
2. Every report query requires `tenant_id` from authenticated context.
3. Every standard total requires `status = 'posted'`.
4. `draft`, `approved`, `auto_approved`, `simulated_success`, `mock_posting`, `dry_run`
   are excluded from all official totals.
5. Reversal and correction net/history behavior is tested and confirmed correct.
6. Evidence and audit drill-down is available and exposed in report detail rows.
7. No double counting of reversal/correction chains.
8. No raw secrets appear in report rows or exports.
9. No report endpoint accepts `tenant_id` from user input.
10. No cross-tenant aggregation occurs.
11. Feature flag is required to enable posted-ledger reports.
12. No silent fallback from posted ledger to `journal_drafts`.
13. Production switch requires explicit human approval and a documented rollback plan.

---

*Bridge Hub — Task 11C-H13. Plan only. No runtime code change. No SQL. No migration
execution. No DB connection. No production DB touch. Balance.ge remains inactive.*
