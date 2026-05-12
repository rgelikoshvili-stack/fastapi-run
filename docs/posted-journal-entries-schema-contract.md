# Bridge Hub — Posted Journal Entries Schema Contract

**Task:** 11C-H2
**Status:** Schema contract and design only — no SQL, no migration, no runtime change.
**Date:** 2026-05-12
**Follows:** 11C-H1 Reports Ledger Integrity Audit (`docs/reports-ledger-integrity-audit.md`)

---

## 1. Purpose

`journal_drafts` JSONB is **not accounting truth.**

The current Bridge Hub data model stores all journal content — including both unposted drafts and posted entries — inside the `journal_drafts` table. Accounting reports that read from `journal_drafts` conflate pending drafts with confirmed ledger entries. This violates the accounting truth principle: *only posted journal entries are official ledger truth.*

This contract defines the target accounting truth model for Bridge Hub:

- An immutable `journal_entry_headers` + `journal_entry_lines` table structure must be created.
- All official accounting reports must eventually source exclusively from **posted journal entries** in these tables.
- `journal_drafts` remains the working/approval layer only — a staging area, never a ledger source.
- This document is the design contract. Migration, runtime, and reporting tasks follow in H3–H7.

**No SQL is executed in this task. No runtime behavior is changed. No migration is created or executed. No production DB is touched.**

---

## 2. Background / H1 Findings

The H1 audit (`docs/reports-ledger-integrity-audit.md`) identified the following critical and high-risk findings:

### CRITICAL

1. **`/reports/bs/detail` has no status filter.** It queries `journal_drafts` without filtering by `status = 'posted'`, returning all drafts regardless of posting status. Balance Sheet detail currently includes unposted, rejected, and draft entries as if they were accounting truth.

2. **`/reports/pnl/detail` treats `simulated_success` as accounting truth.** The query uses `status IN ('posted', 'simulated_success')`. `simulated_success` is a test/simulation status, not a real ERP posting. Profit and Loss detail is corrupted by simulated entries.

3. **No separate immutable `journal_entries` table exists.** The production schema stores journal lines as a JSONB column (`journal_entries`) inside `journal_drafts`. There is no append-only ledger table. All reports must read from this JSONB column, which mixes draft and posted state.

### HIGH

The following official reports all source from `journal_drafts` JSONB (acceptable as interim, but must migrate before commercial pilot):

- Trial Balance (`financial_statements_service.py` — `_get_trial_balance`)
- Profit & Loss summary
- Balance Sheet summary
- VAT register (`routes_tax.py` — `/tax/vat-register`)
- Account ledger (`ledger_service.py` — `get_account_ledger`)
- Counterparty ledger (`get_counterparty_ledger`)
- Payroll ledger (`get_payroll_ledger`)
- Journal entries list (`get_journal_entries`)

### MEDIUM

- **`/reports/cashflow`** queries `bank_transactions` only with no journal linkage. Cash flow does not reconcile with the ledger.

---

## 3. Accounting Truth Principles

The following principles define what constitutes accounting truth in Bridge Hub. These principles must be enforced in all future official report implementations.

| Status | Is accounting truth? | Reason |
|---|---|---|
| `draft` | **NO** | Unreviewed, may be incorrect |
| `approved` | **NO** | Approved for posting, not yet posted |
| `auto_approved` | **NO** | Automated approval, not ERP-confirmed |
| `simulated_success` | **NO** | Test/simulation only, never a real ERP write |
| `mock_posting` | **NO** | Development/test artifact |
| `posted` | **YES** | ERP connector confirmed, immutable ledger entry |

**Governing rules:**

1. **Draft is not truth.** A journal draft is a work-in-progress entry pending human review.
2. **Approved is not truth.** An approved draft is a candidate for posting, not a confirmed ledger entry.
3. **`auto_approved` is not truth.** Automated approval bypasses human confirmation and must not feed official reports.
4. **`simulated_success` is not truth.** Simulation is a test state. No official report may treat `simulated_success` as posted ledger truth.
5. **Mock posting is not truth.** Development/test connectors do not produce real ERP entries.
6. **Only posted journal entries are official accounting truth.** A journal entry becomes accounting truth only after the ERP connector confirms the post and the entry is written to the immutable ledger table.
7. **Official reports must be posted-only.** No official report may mix drafted, approved, or simulated entries with posted entries unless it is explicitly labeled as a preview/draft report.
8. **Reversal and correction must be append-only.** Posted entries are never destructively edited. A reversal creates a new offsetting entry. A correction creates a new correction entry referencing the original.
9. **Posted entries must not be destructively edited.** Once a journal entry is posted, its lines are immutable. Only clearly defined metadata fields (e.g., `notes`) may be updated.
10. **Every official report must filter by `tenant_id`.** No cross-tenant ledger data may appear in any report.
11. **Every official report must filter by period or date range.** Unscoped queries across all time are forbidden in official reports.
12. **Every posted entry should link back to source/evidence where applicable.** Where an `evidence_bundle_id` exists, it must be stored on the header. Where a `posting_log_id` exists, it must be stored on the header.

---

## 4. Target Conceptual Schema

This section defines the target schema conceptually. **No SQL migration is created in this task.** The migration will be designed in 11C-H3.

The accounting truth layer consists of four logical structures:

| Structure | Purpose |
|---|---|
| `journal_entry_headers` | One row per posted journal entry — the header record |
| `journal_entry_lines` | Debit/credit lines belonging to a header (double-entry) |
| `journal_entry_sources` | Source/evidence linkage (draft, document, OCR, bank transaction) |
| `journal_entry_reversals` | Reversal and correction linkage between related entries |

All tables must include `tenant_id`. All tables must be indexed by `tenant_id`. Ledger tables must be insert-only for posted content (reversals/corrections create new rows, never update existing ones).

---

## 5. `journal_entry_headers` — Required Fields

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | Generated, immutable |
| `tenant_id` | TEXT NOT NULL | Required on every row |
| `source_draft_id` | UUID / TEXT | Reference to originating `journal_drafts.id` |
| `posting_batch_id` | TEXT | Groups entries posted together in one batch |
| `posting_log_id` | TEXT | Links to `posting_logs` — the connector execution record |
| `evidence_bundle_id` | UUID nullable | Links to `evidence_bundles` if available |
| `entry_date` | DATE NOT NULL | The accounting date of the entry |
| `posting_date` | TIMESTAMPTZ NOT NULL | When the ERP connector confirmed the post |
| `period` | TEXT NOT NULL | Accounting period (e.g., `2026-01`) |
| `status` | TEXT NOT NULL | One of: `posted`, `reversed`, `correction`, `voided` |
| `source_type` | TEXT | Origin: `bank_transaction`, `document`, `manual`, `payroll`, etc. |
| `source_hash` | TEXT | Hash of the source content at time of posting |
| `currency` | TEXT NOT NULL | ISO 4217 currency code |
| `exchange_rate` | NUMERIC | Rate to GEL at time of posting |
| `total_debit` | NUMERIC NOT NULL | Sum of all debit lines — must equal `total_credit` |
| `total_credit` | NUMERIC NOT NULL | Sum of all credit lines — must equal `total_debit` |
| `created_by` | TEXT | Actor who created the originating draft |
| `approved_by` | TEXT | Actor who approved the draft |
| `posted_by` | TEXT | Actor or system that triggered posting |
| `created_at` | TIMESTAMPTZ NOT NULL | Header record creation time |
| `posted_at` | TIMESTAMPTZ NOT NULL | ERP confirmation time |
| `reversed_by_entry_id` | UUID nullable | Points to the reversing entry if this entry was reversed |
| `correction_of_entry_id` | UUID nullable | Points to the original entry if this is a correction |
| `metadata_json` | JSONB | Non-financial metadata (connector response summary, etc.) |

**Invariants for `journal_entry_headers`:**

- `total_debit = total_credit` — required on every posted entry.
- `status` must be one of `posted`, `reversed`, `correction`, `voided` — drafts, approved, auto_approved, simulated_success are forbidden.
- `tenant_id` is required and must not be empty.
- `entry_date` and `posting_date` must be set on post.
- `reversed_by_entry_id` and `correction_of_entry_id` are mutually informative (a reversed entry points forward to its reversal; a correction entry points back to the original).

---

## 6. `journal_entry_lines` — Required Fields

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | Generated, immutable |
| `tenant_id` | TEXT NOT NULL | Required on every row, must match header |
| `journal_entry_id` | UUID NOT NULL | FK → `journal_entry_headers.id` |
| `line_no` | INT NOT NULL | Order of this line within the entry (1-based) |
| `account_code` | TEXT NOT NULL | Chart of accounts code |
| `account_name` | TEXT | Human-readable account name |
| `debit` | NUMERIC NOT NULL DEFAULT 0 | Debit amount in entry currency |
| `credit` | NUMERIC NOT NULL DEFAULT 0 | Credit amount in entry currency |
| `currency` | TEXT NOT NULL | Line currency (may differ from header if multi-currency) |
| `exchange_rate` | NUMERIC | Rate to GEL for this line |
| `amount_gel` | NUMERIC NOT NULL | Functional currency amount (GEL) |
| `counterparty_id` | TEXT nullable | Counterparty reference if applicable |
| `document_id` | TEXT nullable | Source document reference |
| `bank_transaction_id` | TEXT nullable | Bank transaction reference |
| `tax_code` | TEXT nullable | Tax classification code |
| `vat_amount` | NUMERIC nullable | VAT portion of this line if applicable |
| `description` | TEXT | Line-level description |
| `line_hash` | TEXT | Hash of immutable line fields for integrity verification |
| `created_at` | TIMESTAMPTZ NOT NULL | Line creation time |

**Invariants for `journal_entry_lines`:**

- `debit >= 0` and `credit >= 0`.
- At least one of `debit` or `credit` must be non-zero per line.
- `tenant_id` must match the parent header's `tenant_id`.
- Lines are immutable once posted. Corrections and reversals create new lines in new headers — they never update existing lines.
- `line_hash` covers `journal_entry_id`, `line_no`, `account_code`, `debit`, `credit`, `amount_gel` — to detect any tampering.

---

## 7. Required Invariants

All future ledger implementations must enforce these invariants:

1. **`tenant_id` is required on every ledger table.** No tenant-scoped ledger query may omit `WHERE tenant_id = $N`.
2. **Every official report must filter by `tenant_id`.** No cross-tenant data in any report.
3. **Every official report must filter by period or date range.** Open-ended full-history queries are forbidden in official reports.
4. **`total_debit` must equal `total_credit`.** Every posted journal entry is balanced. This is a hard invariant enforced at write time.
5. **Entry status must be one of `posted`, `reversed`, `correction`, `voided`.** No other status may represent accounting truth. Draft, approved, auto_approved, simulated_success, and mock posting statuses must never appear in the immutable ledger tables.
6. **`draft`, `approved`, `auto_approved`, `simulated_success`, and mock posting are not accounting truth.** No official report may source from these statuses.
7. **No official report may treat `simulated_success` as posted ledger truth.** This is an explicit prohibition arising from the H1 CRITICAL finding in `/reports/pnl/detail`.
8. **Reversals must be append-only.** A reversal of entry X creates a new entry Y that offsets X. Entry X remains in the ledger as `reversed`, pointing to Y. Y points back to X.
9. **Corrections must create new correction entries, not mutate posted lines.** A correction entry has `correction_of_entry_id` set to the original entry's `id`.
10. **Posted journal lines must be immutable** except for clearly defined metadata fields (e.g., `metadata_json` on the header).
11. **Every posted entry should be linkable to `evidence_bundle_id` or source document** when an evidence bundle was created during the approval/posting flow.
12. **Every posted entry should be linkable to `posting_log_id`** when a connector execution occurred during posting.
13. **No official report should read `journal_drafts` JSONB** after the migration to the immutable ledger table is complete.

---

## 8. Report Migration Targets

The table below defines the target data source for each official report after migration is complete. **These are future targets. No runtime report code is changed in this task.**

| Report | Current source (H1 finding) | Target source |
|---|---|---|
| Trial Balance | `journal_drafts.journal_entries` JSONB (HIGH) | `journal_entry_lines` JOIN `journal_entry_headers` WHERE `status = 'posted'` |
| Profit & Loss summary | `journal_drafts` JSONB (HIGH) | `journal_entry_lines` JOIN `journal_entry_headers` WHERE `status = 'posted'`, account class filter |
| Profit & Loss detail | `journal_drafts` WHERE `status IN ('posted','simulated_success')` (CRITICAL) | `journal_entry_lines` JOIN `journal_entry_headers` WHERE `status = 'posted'` only |
| Balance Sheet summary | `journal_drafts` JSONB (HIGH) | `journal_entry_lines` JOIN `journal_entry_headers` WHERE `status = 'posted'`, account class filter |
| Balance Sheet detail | No status filter — all drafts (CRITICAL) | `journal_entry_lines` JOIN `journal_entry_headers` WHERE `status = 'posted'` only |
| VAT register | `journal_drafts` WHERE `status = 'posted'` (HIGH) | `journal_entry_lines` WHERE `tax_code IS NOT NULL` JOIN `journal_entry_headers` WHERE `status = 'posted'` |
| Account ledger | `journal_drafts` WHERE `status = 'posted'` (HIGH) | `journal_entry_lines` WHERE `account_code = $code` JOIN `journal_entry_headers` WHERE `status = 'posted'` |
| Counterparty ledger | `journal_drafts` WHERE `status = 'posted'` (HIGH) | `journal_entry_lines` WHERE `counterparty_id = $id` JOIN `journal_entry_headers` WHERE `status = 'posted'` |
| Payroll ledger | `journal_drafts` WHERE `status = 'posted'` (HIGH) | `journal_entry_lines` with payroll/source linkage JOIN `journal_entry_headers` WHERE `status = 'posted'` |
| Journal entries list | `journal_drafts` WHERE `status = 'posted'` (HIGH) | `journal_entry_headers` + `journal_entry_lines` WHERE `status = 'posted'` |
| Cash flow | `bank_transactions` only, no journal linkage (MEDIUM) | Ledger-linked bank transactions OR `journal_entry_lines` WHERE account class is cash/bank, `status = 'posted'` |

---

## 9. Future Task Sequence

| Task | Description |
|---|---|
| **11C-H2** (this task) | Posted Journal Entries Schema / Contract Plan — design contract only, no SQL |
| **11C-H3** | Posted Journal Entries Migration Contract / Migration Plan — SQL schema definition, additive migration design, contract tests |
| **11C-H4** | Posting Service Ledger Write Plan / Contract Tests — define how `posting_service.py` will write to `journal_entry_headers` + `journal_entry_lines` after ERP confirmation |
| **11C-H5** | Reports Posted-Ledger Read Plan / Contract Tests — define how report services will query the new tables; contract tests for correct query patterns |
| **11C-H6** | Reversal / Correction Contract — define the append-only reversal and correction flow, including UI and API contract |
| **11C-H7** | Evidence Bundle Ledger Linkage + Audit Export Contract — define how `evidence_bundle_id` links to posted entries and how audit export should work |

Each task follows the same protocol: branch → docs/tests → PR → merge → deploy → live verification → confirmed before starting the next task.

---

## 10. Non-Goals for H2

This task explicitly does **not**:

- Execute any SQL.
- Touch the production database.
- Create any database migration file.
- Execute any migration.
- Change any runtime report behavior.
- Modify `routes_reports.py`, `financial_statements_service.py`, or `ledger_service.py`.
- Change any approval or posting business logic.
- Modify `approval_service.py` or `posting_service.py`.
- Change any connector behavior.
- Activate Balance.ge.
- Change any credentials or secrets.
- Change any production infrastructure or deployment configuration.

This task produces two files only:
- `docs/posted-journal-entries-schema-contract.md` (this document)
- `tests/unit/test_posted_journal_entries_schema_contract.py`

---

*Bridge Hub — Task 11C-H2. Schema contract only. No runtime changes. No SQL. No production DB touch. Balance.ge remains inactive.*
