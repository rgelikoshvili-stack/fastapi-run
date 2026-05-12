# Bridge Hub — Posted Journal Entries Migration Plan

**Task:** 11C-H3
**Type:** Migration contract and implementation plan only — no SQL, no migration file, no DB access.
**Date:** 2026-05-12
**Follows:** 11C-H2 `docs/posted-journal-entries-schema-contract.md`

---

## 1. Purpose

This document prepares the future SQL migration strategy for immutable posted journal entry tables (`journal_entry_headers` and `journal_entry_lines`), based on the H2 schema contract.

**H3 does not create or execute any migration.** No SQL file is created in this task. No database is accessed. This document defines what a future migration must contain, how it must be validated, how it must be rolled out safely, and what the rollback strategy is — so that future tasks (H4–H8) can implement each phase in a controlled, reviewable, and reversible way.

**No SQL is executed in this task. No production DB is touched. No runtime behavior is changed.**

---

## 2. Inputs

This plan is grounded in three prior deliverables:

| Input | Description |
|---|---|
| `docs/reports-ledger-integrity-audit.md` (H1) | Identified CRITICAL bugs: no status filter on BS detail, `simulated_success` as P&L truth, no immutable `journal_entries` table. Also identified HIGH findings across all report routes. |
| `docs/posted-journal-entries-schema-contract.md` (H2) | Defined the target schema: `journal_entry_headers` + `journal_entry_lines`, all required fields, 13 invariants, accounting truth principles, and the H3–H7 task sequence. |
| Current blocker | `journal_drafts.journal_entries` JSONB is not accounting truth. All official reports currently source from this column, conflating pending drafts with confirmed ledger entries. |

The migration planned here is the structural prerequisite for H4 (posting service writes) and H5 (reports read from new tables).

---

## 3. Migration Scope for Future H4/H5

The future migration (to be created in H4, NOT in H3) must create the following objects. This section defines the conceptual scope only.

### 3.1 New tables

| Table | Purpose |
|---|---|
| `journal_entry_headers` | One immutable row per posted journal entry — the header record with audit fields, status, totals, and all linkage references |
| `journal_entry_lines` | Immutable debit/credit lines belonging to a header; the double-entry ledger detail |
| `journal_entry_sources` | Source/evidence linkage table — maps a posted header to its source objects (draft, document, bank transaction, OCR result) |

### 3.2 Linkage fields (on `journal_entry_headers`)

The header table includes soft-link columns (TEXT/UUID, no hard FK by default to avoid cross-table coupling):

- `source_draft_id` — reference to originating `journal_drafts.id`
- `posting_log_id` — reference to `posting_logs` record (connector execution)
- `evidence_bundle_id` — reference to `evidence_bundles.id` (nullable)
- `posting_batch_id` — groups entries posted in one batch

### 3.3 Reversal and correction linkage (on `journal_entry_headers`)

- `reversed_by_entry_id` — UUID nullable — points forward to the reversing entry
- `correction_of_entry_id` — UUID nullable — points back to the original entry being corrected

### 3.4 Required indexes

| Index | Table | Columns | Condition |
|---|---|---|---|
| `idx_jeh_tenant` | `journal_entry_headers` | `tenant_id` | — |
| `idx_jeh_tenant_period` | `journal_entry_headers` | `(tenant_id, period)` | — |
| `idx_jeh_tenant_status` | `journal_entry_headers` | `(tenant_id, status)` | `WHERE status = 'posted'` preferred |
| `idx_jeh_tenant_entry_date` | `journal_entry_headers` | `(tenant_id, entry_date)` | — |
| `idx_jeh_source_draft` | `journal_entry_headers` | `source_draft_id` | `WHERE source_draft_id IS NOT NULL` |
| `idx_jeh_evidence_bundle` | `journal_entry_headers` | `evidence_bundle_id` | `WHERE evidence_bundle_id IS NOT NULL` |
| `idx_jel_tenant` | `journal_entry_lines` | `tenant_id` | — |
| `idx_jel_header` | `journal_entry_lines` | `journal_entry_id` | — |
| `idx_jel_account` | `journal_entry_lines` | `(tenant_id, account_code)` | — |
| `idx_jel_counterparty` | `journal_entry_lines` | `(tenant_id, counterparty_id)` | `WHERE counterparty_id IS NOT NULL` |
| `idx_jes_header` | `journal_entry_sources` | `journal_entry_id` | — |

### 3.5 Required constraints

| Constraint | Table | Rule |
|---|---|---|
| `ck_jeh_tenant_nonempty` | `journal_entry_headers` | `tenant_id <> ''` |
| `ck_jeh_status` | `journal_entry_headers` | `status IN ('posted', 'reversed', 'correction', 'voided')` |
| `ck_jeh_balanced` | `journal_entry_headers` | `total_debit = total_credit` |
| `ck_jeh_debit_nonneg` | `journal_entry_headers` | `total_debit >= 0` |
| `ck_jeh_credit_nonneg` | `journal_entry_headers` | `total_credit >= 0` |
| `ck_jel_tenant_nonempty` | `journal_entry_lines` | `tenant_id <> ''` |
| `ck_jel_account_nonempty` | `journal_entry_lines` | `account_code <> ''` |
| `ck_jel_debit_nonneg` | `journal_entry_lines` | `debit >= 0` |
| `ck_jel_credit_nonneg` | `journal_entry_lines` | `credit >= 0` |
| `ck_jel_nonzero` | `journal_entry_lines` | `debit > 0 OR credit > 0` |
| `uq_jel_line_no` | `journal_entry_lines` | `UNIQUE (journal_entry_id, line_no)` |

---

## 4. Future Table Design Requirements

These requirements are confirmed from the H2 schema contract and must be enforced by the future migration and service implementations.

### 4.1 Mandatory on every row

- `tenant_id` NOT NULL on both `journal_entry_headers` and `journal_entry_lines`
- `tenant_id` on `journal_entry_lines` must match the parent header's `tenant_id`
- No cross-tenant rows may exist in any ledger query result

### 4.2 Posted-only official ledger states

Allowed values for `journal_entry_headers.status`:

| Status | Meaning |
|---|---|
| `posted` | Confirmed by ERP connector — accounting truth |
| `reversed` | Original posted entry that has been offset by a reversal |
| `correction` | Correction entry referencing the original entry |
| `voided` | Voided before ERP confirmation (rare, operationally defined) |

**These statuses must never appear in `journal_entry_headers`:**

| Forbidden status | Why |
|---|---|
| `draft` | Not yet reviewed — not accounting truth |
| `approved` | Approved for posting, not yet ERP-confirmed — not accounting truth |
| `auto_approved` | Automated approval, not human-confirmed — not accounting truth |
| `simulated_success` | Test/simulation status — not a real ERP write — not accounting truth |
| `mock_posting` | Development artifact — not accounting truth |

### 4.3 Balanced entry invariant

Every row inserted into `journal_entry_headers` must satisfy `total_debit = total_credit`. This is enforced by:

1. A `CHECK` constraint at the database level.
2. Application-level validation in the posting service before write.
3. A contract test that verifies the constraint is present in the migration SQL (in H4).

### 4.4 Append-only reversal and correction

- Reversals and corrections never mutate existing rows.
- A reversal creates a new header row with `status = 'reversed'` and sets `reversed_by_entry_id` on the original.
- A correction creates a new header row with `status = 'correction'` and sets `correction_of_entry_id` to the original's `id`.
- Lines within a posted entry are immutable. Only clearly scoped metadata fields on the header (e.g., `metadata_json`) may be updated post-posting.

### 4.5 Audit linkage fields

Every posted header should carry:

- `source_draft_id` — traceability back to the approved journal draft
- `posting_log_id` — traceability to the connector execution record
- `evidence_bundle_id` — traceability to the evidence bundle (nullable; populated when available)
- `source_hash` — hash of source content at time of posting (integrity)
- `line_hash` on each line — hash of immutable line fields (integrity verification)
- `created_at` and `posted_at` — audit timestamps

### 4.6 No simulated_success as accounting truth

`simulated_success` and `mock_posting` must not:

- Be inserted into `journal_entry_headers`.
- Be used as a filter in any official report query.
- Be backfilled into the immutable ledger table.

This is the direct remediation for the H1 CRITICAL finding in `/reports/pnl/detail`.

---

## 5. Future Constraints Required

The future migration must include these constraints. Each is documented here for the H4 SQL author to implement. **These are descriptions only — no SQL is created in H3.**

### 5.1 NOT NULL constraints

- `journal_entry_headers.tenant_id` — NOT NULL
- `journal_entry_headers.entry_date` — NOT NULL
- `journal_entry_headers.posting_date` — NOT NULL
- `journal_entry_headers.period` — NOT NULL
- `journal_entry_headers.status` — NOT NULL
- `journal_entry_headers.currency` — NOT NULL
- `journal_entry_headers.total_debit` — NOT NULL
- `journal_entry_headers.total_credit` — NOT NULL
- `journal_entry_headers.created_at` — NOT NULL
- `journal_entry_headers.posted_at` — NOT NULL
- `journal_entry_lines.tenant_id` — NOT NULL
- `journal_entry_lines.journal_entry_id` — NOT NULL
- `journal_entry_lines.line_no` — NOT NULL
- `journal_entry_lines.account_code` — NOT NULL
- `journal_entry_lines.currency` — NOT NULL
- `journal_entry_lines.amount_gel` — NOT NULL
- `journal_entry_lines.created_at` — NOT NULL

### 5.2 CHECK constraints

- `ck_jeh_tenant_nonempty`: `tenant_id <> ''`
- `ck_jeh_status`: `status IN ('posted', 'reversed', 'correction', 'voided')`
- `ck_jeh_balanced`: `total_debit = total_credit`
- `ck_jeh_debit_nonneg`: `total_debit >= 0`
- `ck_jeh_credit_nonneg`: `total_credit >= 0`
- `ck_jel_account_nonempty`: `account_code <> ''`
- `ck_jel_debit_nonneg`: `debit >= 0`
- `ck_jel_credit_nonneg`: `credit >= 0`
- `ck_jel_nonzero`: `debit > 0 OR credit > 0`

### 5.3 UNIQUE constraints

- `UNIQUE (journal_entry_id, line_no)` on `journal_entry_lines` — ensures unique line ordering within each entry

### 5.4 FK / soft-link strategy

All cross-table references (`source_draft_id`, `posting_log_id`, `evidence_bundle_id`) use soft links (TEXT or UUID columns without hard FOREIGN KEY constraints) to:

- Avoid cascading delete complications across audit tables.
- Allow `posting_logs` and `evidence_bundles` to evolve independently.
- Enable queries to join on these columns without enforcing FK-level integrity at the DB layer.

Hard FK from `journal_entry_lines.journal_entry_id → journal_entry_headers.id` with `ON DELETE CASCADE` is appropriate and should be included.

### 5.5 Index requirements

Indexes must cover every query pattern used by official reports (defined in H2 Section 8):

- `(tenant_id)` — base tenant isolation
- `(tenant_id, period)` — period-scoped report queries
- `(tenant_id, entry_date)` — date-range report queries
- `(tenant_id, status)` — posted-only filter
- `(tenant_id, account_code)` — trial balance and account ledger
- `(tenant_id, counterparty_id)` WHERE NOT NULL — counterparty ledger
- `journal_entry_id` on lines — join from header to lines
- `source_draft_id` WHERE NOT NULL — reverse-lookup from draft
- `evidence_bundle_id` WHERE NOT NULL — reverse-lookup from bundle

---

## 6. Future Migration Safety Gates

Before any migration SQL file is merged or executed against any database, the following gates must all be satisfied. These are the required conditions for H4 PR approval.

| Gate | Requirement |
|---|---|
| Additive only | Migration must use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`. No `DROP`, `ALTER ... DROP COLUMN`, `TRUNCATE`, or destructive DDL. |
| No journal_drafts changes | Migration must not modify, drop, or alter the `journal_drafts` table or its columns. |
| No report changes in same PR | The migration SQL must not be bundled with runtime report query changes in the same PR. Schema and read changes are separate tasks. |
| No backfill in initial migration | The initial H4 migration creates empty tables only. No `INSERT INTO journal_entry_headers SELECT ...` in H4. |
| No production execution in H4 | H4 migration file is reviewed and tested locally/in CI only. Production execution requires explicit approval in a later task. |
| Schema tests pass | A dedicated schema test file must validate the migration SQL file for all required constraints, indexes, and fields before merge. |
| Contract tests pass | All H2 and H3 contract tests must continue to pass after H4 is merged. |
| No Balance.ge activation | Migration must not reference, activate, or require the Balance.ge connector. |
| No credential changes | Migration must not reference secrets, API keys, passwords, or credentials. |

---

## 7. Future Rollout Plan

The safe rollout sequence for posted journal entries is:

| Phase | Task | Deliverable | DB touched? |
|---|---|---|---|
| H3 (this task) | Migration plan | `docs/posted-journal-entries-migration-plan.md` | **NO** |
| H4 | SQL migration + schema tests | `app/storage/migrations/011_posted_journal_entries.sql` + schema test | local CI only |
| H5 | Posting service ledger write | `posting_service.py` writes to `journal_entry_headers` + lines on confirmed ERP post | local CI only |
| H6 | Reports read from posted ledger | `financial_statements_service.py`, `ledger_service.py`, `routes_reports.py` migrated to new tables | local CI only |
| H7 | Reversal/correction + evidence/audit export | reversal flow, correction flow, audit export endpoint | local CI only |
| H8 | Optional safe backfill | dry-run backfill strategy for historical `posted` drafts only | **explicit production approval required** |

**Production database execution** for each phase requires:
1. The migration file to pass all local schema tests.
2. Explicit PR approval by the project owner.
3. A separate production execution task with its own live verification step.
4. No destructive operations at any phase.

---

## 8. Future Backfill Policy

Backfill (migrating historical `posted` data from `journal_drafts.journal_entries` JSONB into the new immutable tables) is **not part of H3, H4, H5, H6, or H7**. It is an optional H8 activity subject to separate approval.

**Backfill rules (for H8 or equivalent):**

1. **No backfill in H3.** This task creates no data.
2. **No production backfill without separate explicit approval.** A backfill PR must be reviewed independently, never bundled with schema or runtime changes.
3. **Backfill must distinguish real postings from non-truth states.** Only rows from `journal_drafts` where `status = 'posted'` (confirmed real ERP posting) may be candidates for backfill.
4. **`simulated_success` and `mock_posting` must not be backfilled** into the immutable ledger table. These are test/simulation artifacts and are not accounting truth.
5. **`auto_approved` and `draft` rows must not be backfilled.** Only confirmed real postings may enter the immutable ledger.
6. **Backfill must run in `dry_run` mode first**, producing a candidate row count and a sample diff before any real insertion.
7. **Backfill must be reversible.** Either by using a transaction with explicit rollback on failure, or by running in a staging environment first.
8. **Backfill must produce an audit report** listing: rows attempted, rows inserted, rows skipped (with skip reason), errors.
9. **Backfill must be idempotent.** Re-running backfill must not create duplicate entries.

---

## 9. Verification Plan for Future Migration

For each future migration phase (H4–H8), the verification sequence is:

### 9.1 Local / CI verification (before merge)

- **Schema tests**: Read the SQL migration file as text; assert all required tables, columns, constraints, and indexes are present. No DB connection required.
- **Contract tests**: Run all H1–H3 contract tests (and H4+ tests as they are created). All must pass.
- **Local test DB**: If a test DB is available, run the migration against it and verify the schema. Never against production.
- **No production SQL** in the planning or CI phase. All test DB runs are in `TEST_MODE` or equivalent isolated environment.

### 9.2 Live verification (after merge and deploy)

Live verification for H4+ migration tasks checks only:

- `GET /version` — confirms the new commit SHA is live.
- `GET /health` — confirms 200 and `balance: demo_mode`.
- Static pages — confirms 200.
- Protected endpoints — confirms 401 without token.
- **No DB writes during live verification.** No direct DB access. No SQL execution.

### 9.3 What live verification does NOT include

- No direct DB connection.
- No schema inspection against production DB.
- No `SELECT` or `SHOW TABLES` against production.
- No data validation queries.
- No report output validation (done in integration tests only).

---

## 10. Non-Goals for H3

This task explicitly does **not**:

- Execute any SQL.
- Create any SQL migration file (`app/storage/migrations/*.sql`).
- Execute any migration.
- Access any database (production or otherwise).
- Touch the production database.
- Change any runtime report behavior.
- Modify `routes_reports.py`.
- Modify `financial_statements_service.py` or `ledger_service.py`.
- Change any posting or approval service logic.
- Modify `posting_service.py` or `approval_service.py`.
- Change any connector behavior.
- Activate Balance.ge.
- Change any credentials or secrets.
- Change any production infrastructure or deployment configuration.
- Start H4, H5, H6, H7, or H8 work.

This task produces two files only:
- `docs/posted-journal-entries-migration-plan.md` (this document)
- `tests/unit/test_posted_journal_entries_migration_plan_contract.py`

---

*Bridge Hub — Task 11C-H3. Migration plan only. No SQL. No migration file. No DB access. No runtime changes. Balance.ge remains inactive.*
