# Bridge Hub — Migration 011 Disposable Dry-Run Evidence

**Task:** 11C-H69-PRE-R2
**Type:** Operational gate — disposable dry-run evidence. No production DB connection.
**Date:** 2026-05-20
**Follows:** 11C-H68 dry-run prerequisites (DRY_RUN_REQUIRED_BEFORE_PRODUCTION)

---

## 1. Purpose

This document records the evidence from running migration 011 against a disposable
Docker-based PostgreSQL instance. Production DB was not used. The dry-run proves:

- Migration 011 applies cleanly (exit 0).
- Migration 011 is idempotent (second run also exit 0).
- All three tables are created with correct columns and indexes.
- The `ck_jeh_balanced` constraint is enforced.
- No destructive side effects.

---

## 2. Dry-Run Environment

| Field | Value |
|---|---|
| Target | Disposable Docker container (`postgres:15-alpine`) |
| Production DB used | NO — FORBIDDEN |
| Container name | `migration011-dryrun` |
| Local port | 5434 (host-only, not exposed externally) |
| Database name | `dryrun_db` |
| DB user | `postgres` (local container only) |
| Container credentials | Local ephemeral — NOT production credentials |
| Container lifecycle | Started → dry-run → stopped → removed |

---

## 3. Migration File Identity

| Field | Value |
|---|---|
| File | `app/storage/migrations/011_posted_journal_entries_schema.sql` |
| Expected SHA-256 | `3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0` |
| Computed SHA-256 | `3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0` |
| SHA match | **YES** ✓ |

---

## 4. Step 1 — Container Start

```
docker run --rm -d --name migration011-dryrun \
  -e POSTGRES_PASSWORD=[local-container-only] \
  -e POSTGRES_DB=dryrun_db \
  -p 5434:5432 \
  postgres:15-alpine
```

Result: Container started. `pg_isready` confirmed: `accepting connections`.

---

## 5. Step 2 — SHA-256 Verification

```
sha256sum app/storage/migrations/011_posted_journal_entries_schema.sql
```

Output:
```
3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0 *app/storage/migrations/011_posted_journal_entries_schema.sql
```

**Result: SHA VERIFIED ✓**

---

## 6. Step 3 — First Run

Command template (credentials not recorded; container-local only):
```
docker exec -i migration011-dryrun psql -U postgres -d dryrun_db \
  -v ON_ERROR_STOP=1 < app/storage/migrations/011_posted_journal_entries_schema.sql
```

Output (truncated):
```
CREATE TABLE
COMMENT   [×10 — journal_entry_headers columns]
CREATE TABLE
COMMENT   [×4  — journal_entry_lines columns]
CREATE TABLE
COMMENT   [×1  — journal_entry_sources]
CREATE INDEX   [×16 — all idempotent indexes]
```

Exit code: **0** ✓

---

## 7. Step 4 — Second Run (Idempotency)

Same command repeated immediately after the first run.

Output (truncated):
```
CREATE TABLE
NOTICE: relation "journal_entry_headers" already exists, skipping
NOTICE: relation "journal_entry_lines" already exists, skipping
NOTICE: relation "journal_entry_sources" already exists, skipping
CREATE INDEX
NOTICE: relation "idx_jeh_tenant" already exists, skipping
NOTICE: relation "idx_jeh_tenant_period" already exists, skipping
[... all 16 indexes: already exist, skipping ...]
```

Exit code: **0** ✓

**Idempotency verified — safe to re-run without side effects.**

---

## 8. Step 5 — Table Verification

```sql
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('journal_entry_headers','journal_entry_lines','journal_entry_sources')
ORDER BY table_name;
```

Output:
```
      table_name
-----------------------
 journal_entry_headers
 journal_entry_lines
 journal_entry_sources
(3 rows)
```

**All 3 tables present ✓**

---

## 9. Step 6 — Column Verification

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'journal_entry_lines'
  AND column_name IN ('account_type', 'cashflow_category')
ORDER BY column_name;
```

Output:
```
    column_name    | data_type
-------------------+-----------
 account_type      | text
 cashflow_category | text
(2 rows)
```

**H66 columns `account_type` and `cashflow_category` confirmed ✓**

---

## 10. Step 7 — Index Verification

```sql
SELECT COUNT(*) FROM pg_indexes
WHERE tablename IN ('journal_entry_headers','journal_entry_lines','journal_entry_sources');
```

Output:
```
 count
-------
    20
(1 row)
```

20 indexes present (16 named + 3 primary key indexes + 1 `journal_entry_sources` index) ✓

---

## 11. Step 8 — Accounting Constraint Verification

### Balanced entry (must succeed):

```sql
INSERT INTO journal_entry_headers
  (tenant_id, entry_date, period, source_type, total_debit, total_credit, status)
VALUES
  ('dryrun_tenant', '2026-05-20', '2026-05', 'manual_dryrun', 1000.00, 1000.00, 'posted');
```

Result: `INSERT 0 1` — exit 0 ✓

### Unbalanced entry (must fail `ck_jeh_balanced`):

```sql
INSERT INTO journal_entry_headers
  (tenant_id, entry_date, period, source_type, total_debit, total_credit, status)
VALUES
  ('dryrun_tenant', '2026-05-20', '2026-05', 'manual_dryrun', 1000.00, 999.00, 'posted');
```

Result:
```
ERROR: new row for relation "journal_entry_headers" violates check constraint "ck_jeh_balanced"
```

**Constraint enforced ✓ — double-entry invariant is active.**

---

## 12. Step 9 — Destructive Side Effects Check

No DROP TABLE, TRUNCATE, DELETE, or UPDATE statements were executed by migration 011.
The `ON DELETE CASCADE` on foreign keys is a constraint definition, not a DML statement.
No fixture data was inserted by the migration. Only DDL (`CREATE TABLE IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`) and `COMMENT` statements were executed.

**No destructive side effects ✓**

---

## 13. Step 10 — Cleanup

```
docker stop migration011-dryrun
```

Result: Container stopped and removed (`--rm` flag). No local database state persists.
No production DB was touched. No credentials were logged or stored.

**Cleanup complete ✓**

---

## 14. Dry-Run Evidence Summary

| Step | Status |
|---|---|
| SHA-256 verified | PASS ✓ |
| First run — exit 0 | PASS ✓ |
| Second run (idempotency) — exit 0 | PASS ✓ |
| All 3 tables present | PASS ✓ |
| `account_type` column present | PASS ✓ |
| `cashflow_category` column present | PASS ✓ |
| 20 indexes present | PASS ✓ |
| `ck_jeh_balanced` enforced | PASS ✓ |
| No destructive side effects | PASS ✓ |
| Container cleaned up | PASS ✓ |

```
DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE
Executed by  : Claude Sonnet 4.6 (automated verification, 11C-H69-PRE-R2)
Target       : Disposable Docker postgres:15-alpine container (NOT production)
Date         : 2026-05-20
SHA verified : 3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0
```

---

## 15. Decision

**Decision: `DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE`**

All 10 dry-run steps passed. Migration 011 is safe to apply to the production database
once backup/PITR, approval signatures, and maintenance window gates are also closed.

---

*Bridge Hub — Task 11C-H69-PRE-R2. Disposable dry-run completed.
No production DB connection. No production SQL. No secrets exposed. Dry-run PASSED.*
