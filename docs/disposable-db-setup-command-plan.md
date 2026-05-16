# Bridge Hub — Disposable DB Setup Contract / Command Plan

## 1. Purpose

Task 11C-H23 defines the exact future command plan and safety contract for
creating and using a disposable local or test PostgreSQL database for
posted-ledger schema verification.

**H23 is docs and contract tests only.**

- H23 does not create a database.
- H23 does not connect to any database.
- H23 does not execute SQL.
- H23 does not run migrations.
- H23 does not execute `011_posted_journal_entries_schema.sql`.
- H23 does not touch production DB or Cloud Run DB.
- H23 does not enable any feature flag.
- H23 does not activate Balance.ge.
- H23 does not change credentials, connector behavior, or infrastructure.

All commands in this document are future plans only.  No command is executed as
part of H23.  Actual DB creation and migration dry-run must happen in a later
explicit task after human approval.

---

## 2. Background / H1–H22 Chain

| Task | Description |
|---|---|
| H1  | Found report ledger integrity risks — `journal_drafts` includes unposted entries |
| H2  | Defined posted-ledger schema contract (`journal_entry_headers`, `journal_entry_lines`) |
| H3  | Defined safe schema migration plan |
| H4  | Created SQL migration contract; not executed |
| H5  | Defined posting service ledger write contract |
| H6  | Added posting ledger write mock tests |
| H7  | Defined report posted-ledger read contract |
| H8  | Added report query mock tests |
| H9  | Defined reversal/correction contract |
| H10 | Defined evidence/audit export linkage |
| H11 | Defined controlled local/test migration execution plan |
| H12 | Attempted local/test migration; blocked — disposable PostgreSQL unavailable |
| H13 | Defined runtime report migration plan with feature flag gate |
| H14 | Added report service query mock tests |
| H15 | Added feature-flagged posted-ledger path; production default OFF |
| H16 | Verified posted-ledger behavior with local/test fixture data |
| H17 | Verified UI/API drill-down contracts |
| H18 | Defined controlled non-production switch plan and production guard |
| H19 | Defined production migration approval plan |
| H20 | Defined staging environment readiness plan |
| H21 | Made staging infrastructure / test data readiness decision — verdict NO-GO |
| H22 | Defined disposable/staging DB readiness plan |
| H23 | Defines future DB setup command plan only (this document) |

---

## 3. Non-Action Statement

H23 takes no action beyond producing this command plan document:

- No database is created.
- No database is connected.
- No SQL is executed.
- No migration is executed.
- `011_posted_journal_entries_schema.sql` is not executed.
- No production DB connection.
- No Cloud Run DB connection.
- No staging Cloud Run service created.
- No feature flag enablement anywhere.
- No Balance.ge activation.
- No credentials changed.
- No connector behavior changed.
- No infrastructure changed.
- No runtime code changes.
- No UI or static file changes.
- H23 does not start H24.

---

## 4. Disposable DB Safety Principles

All future disposable DB work must satisfy every principle below:

- **Disposable only** — the DB is created for testing and dropped after verification.
  It must never be treated as a persistent staging or production resource.
- **Non-production only** — the DB host must be `localhost` or an explicitly
  approved non-production host.  Never a Cloud SQL production instance.
- **No production host** — if `DATABASE_URL` contains a known production host,
  the command must refuse and abort.
- **No production credentials** — the disposable DB role must be a new,
  isolated role.  Production DB passwords must never be reused.
- **No customer data** — no real customer financial rows may be loaded.
  Synthetic or approved anonymized data only.
- **Explicit DB name** — the disposable DB name must contain `bridgehub_disposable`
  or `bridgehub_test` as a prefix.  Any other name must be rejected by the
  preflight guard.
- **Explicit owner** — one named engineer is the designated owner of the
  disposable DB for the session.  The owner is responsible for cleanup.
- **Explicit teardown** — the cleanup command to drop the disposable DB must be
  reviewed before creation begins.  No DB is left running after verification.
- **Full transcript capture** — all commands and their stdout/stderr must be
  captured to a local transcript file before any command runs.
- **No live connector credentials** — `BALANCE_API_KEY` and ERP connector
  credentials must be absent or placeholder during disposable DB work.
- **No Balance.ge live credentials** — Balance.ge must remain `demo_mode`
  throughout disposable DB work.

---

## 5. Required Preflight Before Future Execution

Before any future disposable DB setup is attempted, all of the following must be
confirmed and documented:

- [ ] Human approval granted — named approver has explicitly authorised this task
- [ ] Machine/environment confirmed — local machine or CI, not production Cloud Run
- [ ] `psql`, `createdb`, `dropdb`, `pg_isready` available on the machine
- [ ] PostgreSQL version confirmed — 14 or higher recommended
- [ ] DB host confirmed as `localhost` or approved non-production host
- [ ] DB name confirmed — contains `bridgehub_disposable` or `bridgehub_test`
- [ ] `DATABASE_URL` confirmed — does not contain production host
- [ ] `POSTED_LEDGER_REPORTS_ENABLED` confirmed empty or absent before setup
- [ ] Migration file path confirmed: `app/storage/migrations/011_posted_journal_entries_schema.sql`
- [ ] No production credentials in environment
- [ ] Rollback/cleanup commands reviewed before creation begins
- [ ] Transcript capture confirmed — output file path agreed

---

## 6. Future Environment Template — PLACEHOLDERS ONLY

The following template uses placeholder values only.  No real credentials.
No production host.  Values in `<angle brackets>` must be replaced before use.

```bash
# PLACEHOLDER TEMPLATE ONLY — NOT EXECUTED IN H23
# Replace all <PLACEHOLDER> values before running in future task

export BRIDGE_HUB_DB_ENV="disposable-local"
export BRIDGE_HUB_DB_NAME="bridgehub_disposable_h23_<date>"
export BRIDGE_HUB_DB_USER="bridgehub_disposable_user"
export BRIDGE_HUB_DB_HOST="localhost"
export BRIDGE_HUB_DB_PORT="5432"
export DATABASE_URL="postgresql://<NON_PROD_USER>:<NON_PROD_PASSWORD>@localhost:5432/<DISPOSABLE_DB>"
export POSTED_LEDGER_REPORTS_ENABLED=""
export BALANCE_API_KEY=""
export ENVIRONMENT="disposable-local"
```

Rules for this template:

- Never commit `.env` files containing real passwords.
- Never use a production host in `DATABASE_URL`.
- Never set `POSTED_LEDGER_REPORTS_ENABLED=1` in this template.
- Never set `BALANCE_API_KEY` to a real value in this template.
- The `BRIDGE_HUB_DB_NAME` must include the `bridgehub_disposable` prefix.
- The `DATABASE_URL` must resolve to `localhost` or a confirmed non-production host.

---

## 7. Future Command Plan — NOT EXECUTED IN H23

The following commands are documented for future reference only.
**None of these commands are executed in H23.**
Execution requires explicit human approval in a future task.

```bash
# ============================================================
# FUTURE COMMAND PLAN — NOT EXECUTED IN H23
# All commands below are for documentation / planning only.
# Execution requires explicit human approval.
# ============================================================

# Step 1 — Preflight environment check
echo "BRIDGE_HUB_DB_HOST=${BRIDGE_HUB_DB_HOST}"
echo "BRIDGE_HUB_DB_NAME=${BRIDGE_HUB_DB_NAME}"
echo "DATABASE_URL contains production? [manual check]"

# Step 2 — Confirm PostgreSQL is reachable (non-production host only)
pg_isready -h "${BRIDGE_HUB_DB_HOST}" -p "${BRIDGE_HUB_DB_PORT}"

# Step 3 — Create disposable DB
createdb -h "${BRIDGE_HUB_DB_HOST}" -p "${BRIDGE_HUB_DB_PORT}" \
  -U postgres "${BRIDGE_HUB_DB_NAME}"

# Step 4 — Create isolated role (if needed)
psql -h "${BRIDGE_HUB_DB_HOST}" -U postgres -c \
  "CREATE ROLE bridgehub_disposable_user LOGIN PASSWORD '<PLACEHOLDER>';"

# Step 5 — Apply 011 migration to disposable DB only
psql -h "${BRIDGE_HUB_DB_HOST}" -p "${BRIDGE_HUB_DB_PORT}" \
  -U "${BRIDGE_HUB_DB_USER}" -d "${BRIDGE_HUB_DB_NAME}" \
  -f app/storage/migrations/011_posted_journal_entries_schema.sql

# Step 6 — Inspect tables
psql -h "${BRIDGE_HUB_DB_HOST}" -U "${BRIDGE_HUB_DB_USER}" \
  -d "${BRIDGE_HUB_DB_NAME}" -c "\dt"

# Step 7 — Inspect indexes and constraints
psql -h "${BRIDGE_HUB_DB_HOST}" -U "${BRIDGE_HUB_DB_USER}" \
  -d "${BRIDGE_HUB_DB_NAME}" -c "\di"

# Step 8 — Run schema contract tests (local, no DB connection needed)
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/test_posted_journal_entries_schema_contract.py -v

# Step 9 — Load synthetic fixture data (future fixture loader script)
python tools/load_disposable_fixtures.py \
  --db "${BRIDGE_HUB_DB_NAME}" --host "${BRIDGE_HUB_DB_HOST}"

# Step 10 — Run report query tests
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/test_report_service_posted_ledger_query_mock_contract.py -v

# Step 11 — Capture evidence (save transcript)
# [transcript file saved to: disposable_db_run_<date>.txt]

# Step 12 — Teardown: drop disposable DB
dropdb -h "${BRIDGE_HUB_DB_HOST}" -p "${BRIDGE_HUB_DB_PORT}" \
  -U postgres "${BRIDGE_HUB_DB_NAME}"

# Step 13 — Drop disposable role (if created)
psql -h "${BRIDGE_HUB_DB_HOST}" -U postgres -c \
  "DROP ROLE IF EXISTS bridgehub_disposable_user;"
```

---

## 8. Production Guard Commands

The following guard checks must be run before any future disposable DB command.
If any guard fails, the command must refuse and abort.

```bash
# PRODUCTION GUARDS — must all pass before any DB command executes

# Guard 1: DATABASE_URL must not contain production host
if echo "$DATABASE_URL" | grep -q "<PRODUCTION_HOST_PLACEHOLDER>"; then
  echo "GUARD FAILED: DATABASE_URL contains production host. Aborting."; exit 1
fi

# Guard 2: DB name must contain disposable/test/staging prefix
if ! echo "$BRIDGE_HUB_DB_NAME" | grep -qE "bridgehub_disposable|bridgehub_test|bridgehub_staging"; then
  echo "GUARD FAILED: DB name does not contain approved prefix. Aborting."; exit 1
fi

# Guard 3: ENVIRONMENT must not be production
if [ "$ENVIRONMENT" = "production" ]; then
  echo "GUARD FAILED: ENVIRONMENT=production detected. Aborting."; exit 1
fi

# Guard 4: POSTED_LEDGER_REPORTS_ENABLED must be off before setup
if [ "$POSTED_LEDGER_REPORTS_ENABLED" = "1" ] || [ "$POSTED_LEDGER_REPORTS_ENABLED" = "true" ]; then
  echo "GUARD FAILED: POSTED_LEDGER_REPORTS_ENABLED is enabled. Must be off for DB setup. Aborting."; exit 1
fi

# Guard 5: BALANCE_API_KEY must be absent for dry-run DB task
if [ -n "$BALANCE_API_KEY" ]; then
  echo "GUARD FAILED: BALANCE_API_KEY is present. Must not be set during disposable DB task. Aborting."; exit 1
fi

# Guard 6: DB host must not match Cloud Run / production host
if echo "$BRIDGE_HUB_DB_HOST" | grep -qE "<CLOUD_SQL_HOST_PATTERN>"; then
  echo "GUARD FAILED: DB host matches known production pattern. Aborting."; exit 1
fi

# Guard 7: Target must not be Cloud Run DB
if echo "$DATABASE_URL" | grep -q "cloudsql"; then
  echo "GUARD FAILED: Cloud SQL connection string detected. Never run against Cloud Run DB."; exit 1
fi
```

---

## 9. 011 Migration Execution Plan — FUTURE ONLY

The posted-ledger schema migration is defined in:

```
app/storage/migrations/011_posted_journal_entries_schema.sql
```

**This migration is not executed in H23.**  Execution is planned for a future
explicitly approved task (H24 or equivalent).

Future execution rules:

- Migration must be applied against the disposable/staging DB only — never production.
- Capture full stdout and stderr to transcript before declaring success.
- Stop on first error — use `psql` with `-v ON_ERROR_STOP=1` flag.
- No production execution under any circumstance.
- Migration must be additive-only — confirmed by H22 inspection:
  `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, no `DROP TABLE`,
  no `DELETE FROM`, no `TRUNCATE`.
- After migration, run schema inspection commands (Section 11) to confirm tables
  and constraints are present.
- Migration idempotency must be verified: run the migration a second time and
  confirm no error and no data corruption.

Future execution command (placeholder — not run in H23):

```bash
# FUTURE ONLY — NOT EXECUTED IN H23
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_h23_<date> \
  -v ON_ERROR_STOP=1 \
  -f app/storage/migrations/011_posted_journal_entries_schema.sql \
  2>&1 | tee disposable_db_migration_transcript.txt
```

---

## 10. Schema Inspection Commands — FUTURE ONLY

After applying the migration, the following read-only inspection commands must
be run to confirm the schema is correct.  **Not executed in H23.**

```bash
# FUTURE ONLY — NOT EXECUTED IN H23

# List all tables in disposable DB
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> -c "\dt"

# Describe journal_entry_headers
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> -c "\d journal_entry_headers"

# Describe journal_entry_lines
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> -c "\d journal_entry_lines"

# Describe journal_entry_sources
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> -c "\d journal_entry_sources"

# List all indexes in disposable DB
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> -c "\di"

# Confirm status check constraint (posted, reversed, correction, voided)
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> \
  -c "SELECT conname, consrc FROM pg_constraint WHERE conrelid = 'journal_entry_headers'::regclass;"

# Confirm tenant_id NOT NULL on journal_entry_headers
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> \
  -c "SELECT column_name, is_nullable FROM information_schema.columns
      WHERE table_name='journal_entry_headers' AND column_name='tenant_id';"

# Confirm debit/credit balance constraint
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> \
  -c "SELECT conname FROM pg_constraint
      WHERE conrelid='journal_entry_headers'::regclass AND contype='c'
      AND conname LIKE '%debit%' OR conname LIKE '%credit%';"

# Confirm evidence_bundle_id, posting_log_id, source_draft_id columns
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> \
  -c "SELECT column_name FROM information_schema.columns
      WHERE table_name='journal_entry_headers'
      AND column_name IN ('evidence_bundle_id','posting_log_id','source_draft_id');"

# Confirm FK from journal_entry_lines to journal_entry_headers
psql -h localhost -U bridgehub_disposable_user \
  -d bridgehub_disposable_<date> \
  -c "SELECT conname, confrelid::regclass FROM pg_constraint
      WHERE conrelid='journal_entry_lines'::regclass AND contype='f';"
```

---

## 11. Synthetic Fixture Load Plan — FUTURE ONLY

After schema validation, synthetic fixture data must be loaded into the disposable
DB.  **Not executed in H23.**  No production data, no real customer PII unless
explicitly anonymized and approved.

Fixture categories required (minimum one row per test tenant per category):

- Posted income entries — `status='posted'`, income account codes
- Posted expense entries — `status='posted'`, expense account codes
- Posted asset entries — `status='posted'`, asset account codes
- Posted liability entries — `status='posted'`, liability account codes
- Posted equity entries — `status='posted'`, equity account codes
- Cash/bank entries — cashflow-classifiable account codes
- VAT/tax entries — VAT-relevant account codes, VAT amounts
- Payroll entries — payroll account codes
- Counterparty/document links — `counterparty_id` and `document_id` populated
- Correction entries — `status='correction'`, `correction_of_id` populated
- Reversal entries — `status='reversed'`, `reversal_of_id` populated
- Forbidden non-posted states — `draft`, `approved`, `auto_approved`,
  `simulated_success`, `mock_posting`, `dry_run` must NOT be present
  in the posted-ledger tables
- Multi-tenant negative rows — at least two distinct test tenants; rows from
  tenant A must not appear in tenant B report responses
- `source_draft_id` — populated on at least one posted entry per tenant
- `posting_log_id` — populated on at least one posted entry per tenant
- `evidence_bundle_id` — populated on at least one posted entry per tenant

Fixture load method (future, not H23):

- Fixtures are loaded via a future approved fixture loader script.
- Loader script must validate that no real production data is included.
- Loader script output must be captured to the evidence transcript.

---

## 12. Future Verification Commands

After loading synthetic fixtures, the following test suites must be run against
the local/disposable environment.  **Not executed in H23** — these are planned
for the future approved execution task.

```bash
# FUTURE ONLY — NOT EXECUTED IN H23

# Schema contract tests (no DB required — unit tests)
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/test_posted_journal_entries_schema_contract.py -v

# Posted-ledger fixture verification tests
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/test_report_service_posted_ledger_fixture_verification.py -v

# Report service query mock tests
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/test_report_service_posted_ledger_query_mock_contract.py -v

# Old-vs-new report comparison preparation tests
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/test_reports_posted_ledger_read_contract.py -v

# No production DB used — DATABASE_URL remains empty for all unit tests above
# No Balance.ge connector tests — balance remains demo_mode
```

---

## 13. Evidence Collection Template

For each future disposable DB setup execution, the following evidence must be
recorded and archived before declaring any readiness milestone:

| Evidence Item | Required |
|---|---|
| Date and time of execution | yes |
| Operator name | yes |
| Machine / environment description | yes |
| DB name used | yes |
| DB host classification (localhost / non-production) | yes |
| Approval reference (who approved, when) | yes |
| Full command transcript (all commands + stdout/stderr) | yes |
| Migration output — stdout and stderr | yes |
| Schema inspection output | yes |
| Test results — pass/fail counts | yes |
| Fixture manifest — categories loaded | yes |
| Cleanup confirmation — DB dropped after verification | yes |
| Final GO/NO-GO declaration | yes |
| Any deviations from this plan | yes |

Evidence transcript file naming convention:

```
disposable_db_run_<YYYY-MM-DD>_<operator>.txt
```

---

## 14. Cleanup / Teardown Plan

Teardown must occur after verification is complete, whether successful or not.

Teardown steps (future — not executed in H23):

1. Drop the disposable DB:
   ```bash
   dropdb -h localhost -U postgres bridgehub_disposable_<date>
   ```
2. Drop the disposable role if it was created:
   ```bash
   psql -h localhost -U postgres -c "DROP ROLE IF EXISTS bridgehub_disposable_user;"
   ```
3. Unset `DATABASE_URL`:
   ```bash
   unset DATABASE_URL
   ```
4. Verify `POSTED_LEDGER_REPORTS_ENABLED` is off or absent:
   ```bash
   echo "${POSTED_LEDGER_REPORTS_ENABLED:-NOT_SET}"
   ```
5. Verify no lingering credentials in shell environment:
   ```bash
   env | grep -iE "password|secret|api_key" || echo "CLEAN"
   ```
6. Archive the transcript file to a secure local location.
7. Document cleanup result in the evidence record.

Rules:
- Never drop a production or persistent staging DB as part of this teardown.
- If the DB name does not contain `bridgehub_disposable` or `bridgehub_test`,
  do not drop it — abort and investigate.
- Teardown is the named owner's responsibility.

---

## 15. Go / No-Go

**GO criteria** — all must be true before future execution begins:

- Human approval explicitly granted by named approver
- DB host is `localhost` or confirmed non-production host
- DB name contains `bridgehub_disposable` or `bridgehub_test`
- Credentials are non-production (new role, placeholder password)
- Rollback and cleanup commands reviewed before execution starts
- Migration file present: `app/storage/migrations/011_posted_journal_entries_schema.sql`
- Synthetic test data fixture plan reviewed
- `BALANCE_API_KEY` absent from environment
- `POSTED_LEDGER_REPORTS_ENABLED` absent or empty before setup
- Transcript capture confirmed

**NO-GO criteria** — any one of these blocks execution:

- DB identity unclear — cannot confirm host is non-production
- Production host or credentials detected in environment
- Cloud Run DB or Cloud SQL production instance detected as target
- No cleanup/teardown plan reviewed
- No transcript capture planned
- Safe synthetic test data unavailable
- Operator uncertain about any guard condition
- `BALANCE_API_KEY` present in environment
- `POSTED_LEDGER_REPORTS_ENABLED=1` or `true` in environment before setup

**Current verdict: NO-GO** — this is a planning document only; no execution
has been approved as of H23.

---

## 16. Non-Goals for H23

This task does **not**:

- Create a disposable or staging database
- Connect to any database
- Execute any SQL
- Run any migration
- Execute `011_posted_journal_entries_schema.sql`
- Enable any feature flag
- Enable `POSTED_LEDGER_REPORTS_ENABLED` anywhere
- Execute any production switch
- Touch production DB or Cloud Run DB
- Change any Cloud Run environment variables
- Activate Balance.ge or any ERP connector
- Change any connector behavior or credentials
- Change any infrastructure
- Change any runtime code
- Change any UI or static files
- Change posting or approval logic
- Start H24

---

## 17. Next Task

Only after PR merge, deploy, and live verification:

**Preferred (if human explicitly approves DB creation):**
**11C-H24 — Disposable DB Setup Dry-Run Execution**

This task applies the command plan in Section 8 against a confirmed disposable
local/test PostgreSQL, captures evidence, and documents readiness per H21
Section 6.

**Alternative (if DB creation approval is not yet granted):**
**SEC-1 — Hardcoded Secrets / Legacy Migration Scripts Cleanup**

H23 does not start H24.  H24 begins only after this PR is merged, deployed to
Cloud Run, and live-verified via `/version` and `/health`, and only after
explicit human approval for DB creation is granted.
