# Database Migrations

## Overview

All DDL migrations are fully idempotent — every statement uses
`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` guards so re-running is safe.

Migration modules live in `app/startup/`:

| Module | Responsibility |
|--------|---------------|
| `migrations.py` | Column additions on core tables; delegates to the three modules below |
| `migrations_tables.py` | `CREATE TABLE IF NOT EXISTS` for expenses, invoices, chat, bank, pipeline, etc. |
| `migrations_indexes.py` | Indexes, FX columns, constraints, data backfills |
| `migrations_vault.py` | Credential vault schema (`credential_vault_*` tables) |

---

## Running migrations manually

```bash
DATABASE_URL="postgresql://user:pw@host/db" python scripts/migrate.py
```

The script requires `DATABASE_URL` and delegates to `run_db_migrations()` in
`app/startup/migrations.py`, which chains all four modules in order.

---

## Dry-run (no DB connection)

```bash
python scripts/migrate.py --dry-run
```

Validates all module imports and prints the migration plan.
Exits 0; makes no database changes.

---

## CI/CD integration

The `.github/workflows/deploy.yml` `deploy` job runs **before** `gcloud run deploy`:

```
python scripts/migrate.py --dry-run
```

This validates all migration module imports and prints the full execution plan.
It exits non-zero if any import is broken, blocking the deploy before a bad
container is pushed.

**Live pre-deploy migrations** (future): to promote to a live DB run, add
Cloud SQL Auth Proxy to the deploy job and set `DATABASE_URL` in GitHub Actions
Secrets (Repository → Settings → Secrets → Actions → New repository secret).
The `scripts/migrate.py` (without `--dry-run`) will then run DDL against the
production DB before the new container starts.

Until then, live DDL migrations run at app startup via `run_db_migrations()`
called from the FastAPI lifespan hook in `main.py`.

---

## Adding a new migration

1. Add idempotent SQL to the appropriate module:
   - New table → `app/startup/migrations_tables.py`
   - New column / index → `app/startup/migrations_indexes.py`
   - Vault schema → `app/startup/migrations_vault.py`
   - Everything else → `app/startup/migrations.py`
2. Add a one-line description to `MIGRATION_GROUPS` in `scripts/migrate.py`
3. Validate locally: `python scripts/migrate.py --dry-run`

---

## Rollback

All migrations are **additive only** — no destructive DDL is ever applied
automatically. To revert a change connect to the database directly:

```sql
-- Remove a column (destructive — back up first)
ALTER TABLE <table> DROP COLUMN IF EXISTS <column>;

-- Drop a table (destructive — back up first)
DROP TABLE IF EXISTS <table>;
```

If a migration step fails at startup, `app/startup/migrations.py` logs a
WARNING and continues — the application still starts with the schema from the
last successful run.

To remove the migration step from CI/CD while preserving startup safety:

```bash
# Comment out the migration step in deploy.yml
# The startup shim in migrations.py will still run at container start
```
