# Bridge Hub — Controlled Local/Test Migration Execution Plan

**Task:** 11C-H11
**Type:** Contract document and tests only — no SQL, no migration execution, no DB connection.
**Date:** 2026-05-14
**Follows:** 11C-H10 `docs/evidence-audit-export-linkage-contract.md`

---

## 1. Purpose

This plan defines how `011_posted_journal_entries_schema.sql` may be tested in **local or test environments only**. It specifies the preflight checks, execution steps, validation checks, and rollback/restore expectations that must be followed in a future explicitly approved task (H12).

**H11 does not execute SQL. H11 does not execute the migration. H11 does not connect to any database. H11 does not touch the production database.** This document is a readiness specification only — no migration occurs until H12 is explicitly approved.

---

## 2. Background

The H1–H10 foundation that makes this plan necessary:

| Task | Deliverable |
|---|---|
| H1 | Reports ledger integrity audit — CRITICAL: reports source from `journal_drafts` JSONB; no immutable ledger; `simulated_success` treated as truth |
| H2 | Posted journal entries schema contract — defined `journal_entry_headers` + `journal_entry_lines` + `journal_entry_sources` with all required fields and 13 invariants |
| H3 | Safe migration plan — defined constraint requirements, index requirements, soft-link strategy, additive-only DDL rules |
| H4 | SQL migration file `011_posted_journal_entries_schema.sql` created but **not executed** — awaiting approved local/test execution |
| H5 | Posting service ledger write contract — defined write rules after real ERP connector posting |
| H6 | Posting service ledger write mock tests — 59 tests encoding future write rules |
| H7 | Reports posted-ledger read contract — defined how reports must read from `journal_entry_headers` + `journal_entry_lines` |
| H8 | Report query mock tests — 89 tests for future query rules |
| H9 | Reversal / correction contract — defined append-only reversal and correction model |
| H10 | Evidence / audit export linkage contract — defined how `evidence_bundle_id` links to posted entries and how audit export packages must work |
| H11 (this task) | Controlled local/test migration execution plan — defines how the migration may be tested safely before any production execution |

Until H12 is explicitly approved, `011_posted_journal_entries_schema.sql` remains unexecuted. H11 prepares the readiness specification so H12 can proceed safely when approved.

---

## 3. Migration Target

The migration file to be executed in a future approved task is:

```
app/storage/migrations/011_posted_journal_entries_schema.sql
```

This file was created in H4 and contains **additive-only DDL**. It is expected to create the following database objects:

| Object | Type | Purpose |
|---|---|---|
| `journal_entry_headers` | Table | Immutable posted ledger entry headers |
| `journal_entry_lines` | Table | Immutable posted ledger entry lines (one row per line) |
| `journal_entry_sources` | Table | Source linkage table connecting entries to drafts, evidence bundles, and posting logs |
| Constraints | `CHECK`, `UNIQUE`, `FK` | Enforce accounting invariants and data integrity |
| Indexes | `CREATE INDEX IF NOT EXISTS` | Tenant-scoped query performance |
| Comments | `COMMENT ON TABLE/COLUMN` | Schema documentation |

No `DROP`, `DELETE`, `UPDATE`, `TRUNCATE`, or data backfill is expected in this migration. Any deviation from additive-only DDL must cause the migration to be rejected and replanned.

---

## 4. Environment Rules

The following rules govern where and when this migration may be executed:

1. **Local/test DB only** — the migration may only be executed against a local development database or a dedicated, disposable test database. No production execution in H11 or H12 without a separately approved production migration task.

2. **Production DB is forbidden** — `DATABASE_URL` must never point to the production database during local/test execution. The migration runner must verify the connection target before executing any DDL.

3. **`DATABASE_URL` must not point to production** — before any migration step, the executor must confirm that `DATABASE_URL` does not contain the production host, production project ID, or any Cloud SQL production instance identifier.

4. **Migration execution requires explicit future approval** — local/test execution may only proceed after H11 is live-verified and H12 is explicitly approved by a human stakeholder. No automated or unattended migration execution is permitted.

5. **Migration runner must fail closed if environment is production** — if the migration runner detects that `DATABASE_URL` points to a production database, it must abort immediately with a clear error. It must never prompt for confirmation or continue in degraded mode.

6. **Cloud Run production must not be used for execution** — the Cloud Run production service must not be used as the execution environment for this migration. Execution must occur in a local terminal or a dedicated CI/non-production environment.

7. **No automatic startup migration** — `011_posted_journal_entries_schema.sql` must not be added to the automatic startup migration list in `app/startup/migrations.py` or equivalent until a separate production migration task is explicitly approved. Adding it to startup would silently execute it against production on the next deploy.

---

## 5. Preflight Checklist

The following checks must be completed and recorded **before** any future local/test migration execution:

| # | Check | Pass condition |
|---|---|---|
| 1 | Confirm current git SHA | Local HEAD matches the expected H11 or later SHA |
| 2 | Confirm branch and task | Working on an approved H12 migration execution branch |
| 3 | Confirm DB target is local/test | `DATABASE_URL` host is `localhost`, `127.0.0.1`, or a named test instance — not production |
| 4 | Confirm backup/snapshot exists for test DB | A restorable snapshot of the test DB state is available before migration |
| 5 | Confirm migration file checksum | SHA-256 of `011_posted_journal_entries_schema.sql` matches the H4-committed file |
| 6 | Confirm migration is additive-only | File contains no `DROP`, `DELETE`, `UPDATE`, `TRUNCATE`, or destructive DDL |
| 7 | Confirm no data backfill | File does not modify existing rows or insert synthetic data |
| 8 | Confirm test DB is disposable or restorable | The test DB can be dropped and recreated or restored from snapshot without data loss risk |
| 9 | Confirm Balance.ge is inactive | `BALANCE_API_KEY` is not set; `balance` connector is `demo_mode` |
| 10 | Confirm credentials are not changed | No API keys, passwords, or secrets are modified by the migration or execution procedure |

All 10 checks must pass before execution proceeds. Any failed check is a blocking condition — migration execution must not begin until the failed check is resolved.

---

## 6. Local/Test Execution Plan

The following steps define the future local/test execution procedure for H12. **These steps are not executed in H11.**

### Step 1 — Create disposable local/test database
```sql
-- Future H12 step (not executed in H11)
CREATE DATABASE bridge_hub_migration_test;
```

### Step 2 — Apply baseline schema if needed
Apply any prerequisite migrations (001–010) that the test DB does not already have, if starting from an empty database.

### Step 3 — Run migration file once
```bash
# Future H12 step (not executed in H11)
psql $DATABASE_URL -f app/storage/migrations/011_posted_journal_entries_schema.sql
```

### Step 4 — Run migration file a second time (idempotency check)
`CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` constructs must not error on a second execution. The second run must produce no errors.

### Step 5 — Inspect created tables
```sql
-- Future H12 step (not executed in H11)
\dt journal_entry_*
SELECT table_name FROM information_schema.tables
  WHERE table_name IN ('journal_entry_headers','journal_entry_lines','journal_entry_sources');
```

### Step 6 — Inspect constraints
```sql
-- Future H12 step (not executed in H11)
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name IN ('journal_entry_headers','journal_entry_lines');
```

### Step 7 — Inspect indexes
```sql
-- Future H12 step (not executed in H11)
SELECT indexname, tablename FROM pg_indexes
WHERE tablename IN ('journal_entry_headers','journal_entry_lines','journal_entry_sources');
```

### Step 8 — Insert safe synthetic rows (local/test only, if explicitly approved)
Only in the local/test environment and only if separately approved: insert one synthetic `posted` entry and one synthetic `journal_entry_lines` row to verify constraints hold. No real data. No production data.

### Step 9 — Validate tenant isolation and balanced constraints
Verify that the `tenant_id NOT NULL` constraint, `status CHECK` constraint, and debit/credit balance constraint enforce correctly against synthetic rows.

### Step 10 — Drop disposable local/test database if applicable
```sql
-- Future H12 step (not executed in H11)
DROP DATABASE bridge_hub_migration_test;
```

---

## 7. Validation Checks After Future Local/Test Execution

After the migration runs in H12, the following validation checks must all pass:

| Check | Expected result |
|---|---|
| `journal_entry_headers` exists | Table present in information_schema |
| `journal_entry_lines` exists | Table present in information_schema |
| `journal_entry_sources` exists | Table present in information_schema |
| `tenant_id` NOT NULL on all three tables | Constraint present and enforced |
| `status` CHECK constraint excludes non-truth values | `draft`, `approved`, `auto_approved`, `simulated_success`, `mock_posting`, `dry_run` are rejected |
| Balanced header constraint exists | `total_debit = total_credit` enforced at insert |
| Debit/credit non-negative constraints exist | `debit >= 0` and `credit >= 0` enforced |
| Unique `(journal_entry_id, line_no)` constraint on lines | Duplicate line numbers per entry rejected |
| FK `journal_entry_lines.journal_entry_id → journal_entry_headers.id` exists | Orphan lines rejected |
| Required indexes exist | Tenant-scoped indexes on `tenant_id`, `period`, `status` present |
| Schema comments present | `COMMENT ON TABLE` entries exist for all three tables |
| Second migration run is safe | No errors on re-execution |
| No `journal_drafts` mutation | `journal_drafts` table is unchanged; no rows inserted, updated, or deleted |
| No data backfill occurred | All three new tables are empty after migration (no data inserted by DDL) |

---

## 8. Rollback / Restore Policy

### Local/test rollback
Because the migration is additive-only (no existing data modified), rollback in a local/test environment is straightforward:
- **Option A:** Drop the disposable test database entirely and recreate from scratch.
- **Option B:** Restore the pre-migration snapshot taken during preflight check #4.
- **Option C:** Drop the three new tables directly: `DROP TABLE IF EXISTS journal_entry_sources, journal_entry_lines, journal_entry_headers;` — acceptable in a local/test context only.

### Production rollback
Production rollback is **not in scope for H11 or H12**. Before any production execution:
- A dedicated production rollback script must be designed, reviewed, and approved separately.
- The rollback script must be tested against a production-equivalent clone before the production migration.
- No destructive rollback (`DROP TABLE`) may be run in production without explicit human approval.
- PostgreSQL PITR (point-in-time recovery) must be confirmed available before production migration.

---

## 9. Production Approval Gate

Production execution of `011_posted_journal_entries_schema.sql` requires **all** of the following conditions to be met and recorded:

1. **H11 live verification passed** — this plan document is merged, deployed, and live-verified.
2. **H12 local/test execution completed successfully** — migration executed against disposable local/test DB; all validation checks passed; evidence recorded.
3. **Dedicated production migration task explicitly approved** — a separate task (H17 or later) must be created, reviewed, and approved by a human stakeholder. Production migration is not implied by H12 approval.
4. **Backup/PITR confirmed** — PostgreSQL PITR is available and a recent backup is confirmed before production execution begins.
5. **Maintenance window approved if needed** — if the migration requires a table lock or brief downtime, a maintenance window must be scheduled and communicated.
6. **Migration dry-run/local/test evidence reviewed** — the H12 execution log, validation check results, and any issues discovered must be reviewed and accepted.
7. **Explicit human approval recorded** — a human stakeholder must record approval in a PR, task, or audit log before the production migration command is issued.
8. **Rollback plan reviewed** — the production rollback procedure must be reviewed and confirmed available before execution.
9. **No Balance.ge activation coupled to migration** — Balance.ge must remain inactive and must not be activated as part of or alongside the production migration.
10. **No runtime report migration in same task** — migrating reports to read from the new tables (H13) must be a separate, separately approved task. The schema migration and the report migration must not be bundled.

---

## 10. Non-Goals for H11

This task explicitly does **not**:

- Execute any SQL.
- Execute the migration.
- Connect to any database.
- Touch the production database.
- Change any runtime behavior.
- Modify `posting_service.py`.
- Modify `approval_service.py`.
- Modify `ledger_service.py`.
- Modify `financial_statements_service.py`.
- Modify `routes_reports.py` or `routes_posting.py` or any route handler.
- Modify `evidence_bundle_service.py` or `evidence_bundle_repository.py`.
- Activate Balance.ge.
- Change any credentials or secrets.
- Change any connector behavior.
- Change any production infrastructure or deployment configuration.
- Add `011_posted_journal_entries_schema.sql` to the automatic startup migration list.
- Start H12, H13, H14, H15, H16, or H17 work.

This task produces two files only:
- `docs/controlled-local-test-migration-execution-plan.md` (this document)
- `tests/unit/test_controlled_local_test_migration_execution_plan_contract.py`

---

## 11. Future Task Sequence

| Task | Description |
|---|---|
| **H11** (this task) | Controlled local/test migration execution plan only — no SQL, no execution |
| **H12** | Controlled local/test migration execution with disposable DB — only if explicitly approved; run `011_posted_journal_entries_schema.sql` against disposable local/test DB; record evidence |
| **H13** | Runtime report migration plan — define how `financial_statements_service` and `ledger_service` must be migrated to read from `journal_entry_headers` + `journal_entry_lines` after H12 is confirmed |
| **H14** | Posting service ledger write implementation tests with mocks or local/test DB only — move from contract tests to implementation tests |
| **H15** | Reversal/correction implementation tests with mocks — mock-test the future `_write_reversal_entry` and `_write_correction_entry` functions |
| **H16** | Evidence/audit export implementation tests with mocks — mock-test future export package builder functions |
| **H17** | Production migration execution plan — only after H12 evidence reviewed and explicit production approval; design and review production-safe execution procedure with backup/PITR confirmation |

Each task follows the same protocol: branch → docs/tests → PR → merge → deploy → live verification → confirmed before starting the next task.

---

*Bridge Hub — Task 11C-H11. Plan only. No SQL. No migration execution. No DB connection. No production DB touch. Balance.ge remains inactive.*
