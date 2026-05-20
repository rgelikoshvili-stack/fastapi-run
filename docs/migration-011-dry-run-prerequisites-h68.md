# Bridge Hub — Migration 011 Dry-Run Prerequisites

**Task:** 11C-H68
**Type:** Staging/disposable dry-run prerequisites — docs only.
**Date:** 2026-05-20
**Branch:** codex/h68-migration-011-production-execution-plan

---

## 1. Purpose

A staging or disposable database dry-run of migration 011 is required before any
production execution. This document defines exactly what the dry-run must demonstrate.

**Decision: `DRY_RUN_REQUIRED_BEFORE_PRODUCTION`**

---

## 2. Dry-Run Environment Options

| Option | Description | Preferred |
|---|---|---|
| Disposable local PostgreSQL | `createdb bridge_hub_h68_dryrun` on developer workstation | Yes |
| Staging Cloud SQL clone | Point-in-time clone of production (no production data flows) | Yes |
| CI PostgreSQL service | GitHub Actions or local CI postgres service container | Yes |
| Production directly | **FORBIDDEN** — never use production as dry-run target | Never |

The dry-run must use a **separate database instance** from production.
The production `DATABASE_URL` must never be used during the dry-run.

---

## 3. Dry-Run Steps

### Step 1 — Create Disposable Database

```bash
# Example for local PostgreSQL:
createdb bridge_hub_h68_dryrun
echo "Disposable DB created: bridge_hub_h68_dryrun"
```

### Step 2 — Verify Migration File Integrity

```bash
python - <<'PYEOF'
import hashlib, pathlib
p = pathlib.Path("app/storage/migrations/011_posted_journal_entries_schema.sql")
digest = hashlib.sha256(p.read_bytes()).hexdigest()
expected = "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0"
assert digest == expected, f"Hash mismatch: {digest}"
print("SHA-256 verified:", digest)
PYEOF
```

### Step 3 — First Execution (idempotency run 1)

```bash
# Use disposable DB URL — NOT production
psql "[DISPOSABLE_DB_URL]" \
  -f app/storage/migrations/011_posted_journal_entries_schema.sql \
  -v ON_ERROR_STOP=1
echo "First run exit code: $?"
```

### Step 4 — Second Execution (idempotency run 2)

```bash
# Re-run to confirm IF NOT EXISTS guards work
psql "[DISPOSABLE_DB_URL]" \
  -f app/storage/migrations/011_posted_journal_entries_schema.sql \
  -v ON_ERROR_STOP=1
echo "Second run (idempotency) exit code: $?"
```

### Step 5 — Verify Tables Exist

```bash
psql "[DISPOSABLE_DB_URL]" -c "
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('journal_entry_headers','journal_entry_lines','journal_entry_sources')
ORDER BY table_name;"
```

Expected output:
```
       table_name
-----------------------
 journal_entry_headers
 journal_entry_lines
 journal_entry_sources
(3 rows)
```

### Step 6 — Verify Columns

```bash
psql "[DISPOSABLE_DB_URL]" -c "
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('journal_entry_headers','journal_entry_lines','journal_entry_sources')
  AND column_name IN ('tenant_id','status','total_debit','total_credit','debit','credit',
                      'account_type','cashflow_category')
ORDER BY table_name, column_name;"
```

### Step 7 — Verify Indexes

```bash
psql "[DISPOSABLE_DB_URL]" -c "
SELECT indexname FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('journal_entry_headers','journal_entry_lines','journal_entry_sources')
ORDER BY tablename, indexname;"
```

Expected: 16 indexes total (7 + jeh, 8 + jel including H66 additions, 1 + jes).

### Step 8 — Verify Accounting Constraints

```bash
psql "[DISPOSABLE_DB_URL]" -c "
SELECT conname, contype, conrelid::regclass
FROM pg_constraint
WHERE conrelid::regclass::text IN
  ('journal_entry_headers','journal_entry_lines','journal_entry_sources')
ORDER BY conrelid::regclass, conname;"
```

Expected: All CHECK constraints and UNIQUE constraint present.

### Step 9 — Insert Test Row (accounting invariant verification)

```bash
psql "[DISPOSABLE_DB_URL]" <<'SQL'
-- Valid balanced entry
INSERT INTO journal_entry_headers
  (tenant_id, entry_date, period, status, source_type, total_debit, total_credit)
VALUES
  ('test-tenant', '2026-05-20', '2026-05', 'posted', 'test', 100.00, 100.00);

-- This must FAIL (unbalanced: debit ≠ credit)
INSERT INTO journal_entry_headers
  (tenant_id, entry_date, period, status, source_type, total_debit, total_credit)
VALUES
  ('test-tenant', '2026-05-20', '2026-05', 'posted', 'test', 100.00, 99.00);
SQL
```

Expected: First INSERT succeeds. Second INSERT fails with `ck_jeh_balanced` violation.

### Step 10 — Cleanup

```bash
dropdb bridge_hub_h68_dryrun
echo "Disposable DB dropped."
```

---

## 4. Dry-Run Pass Criteria

All items must pass before production execution is approved:

| Item | Pass Criterion |
|---|---|
| SHA-256 match | `3077cec...35d0` confirmed |
| First run (exit code) | 0 |
| Second run (idempotency) | 0 |
| All 3 tables exist | Yes |
| `account_type` column exists | Yes |
| `cashflow_category` column exists | Yes |
| All 16 indexes exist | Yes |
| `ck_jeh_balanced` blocks unbalanced entry | Yes (INSERT fails) |
| Valid balanced entry succeeds | Yes |
| Disposable DB cleaned up | Yes |

---

## 5. Dry-Run Evidence Template

Attach dry-run evidence to the approval packet (APPROVAL-2026-H68-001):

```
Dry-run environment:         ___________________________
Executed by:                 ___________________________
Date/time (UTC):             ___________________________
SHA-256 verified:            ___________________________
First run exit code:         ___________________________
Idempotency run exit code:   ___________________________
Tables verified:             [ ] jeh  [ ] jel  [ ] jes
account_type column:         [ ] Present
cashflow_category column:    [ ] Present
ck_jeh_balanced enforced:    [ ] Yes
Disposable DB cleaned up:    [ ] Yes
Evidence file/URL:           ___________________________
Dry-run decision:            DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE / PENDING
```

---

## 6. H12 Context

Task 11C-H12 previously attempted a disposable-DB dry-run but was blocked
(`H12 Verdict: BLOCKED`) because `psql`, `pg_isready`, and `createdb` were
not found in the execution environment. The H68 dry-run must be performed
in an environment where PostgreSQL tooling is available.

---

## 7. Decision

**Decision: `DRY_RUN_REQUIRED_BEFORE_PRODUCTION`**

Status: PENDING — dry-run has not yet been completed.
Dry-run must be completed and evidence attached to APPROVAL-2026-H68-001
before H69 production execution may begin.

---

*Bridge Hub — Task 11C-H68. Dry-run prerequisites documented.
DRY_RUN_REQUIRED_BEFORE_PRODUCTION. No SQL executed in H68.*
