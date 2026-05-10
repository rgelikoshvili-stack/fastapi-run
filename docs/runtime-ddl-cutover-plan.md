# Runtime DDL Cutover Plan

## A) Purpose

Runtime DDL cutover is required before production-grade commercial pilot. Currently,
Bridge Hub applies schema changes (CREATE TABLE, ALTER TABLE ADD COLUMN, CREATE INDEX,
data migrations) at application startup via Python startup scripts. This approach
was appropriate during rapid early development but introduces risk at scale:

- Schema changes are hidden inside application code rather than reviewed migration files.
- A failed startup migration can silently skip schema changes, leaving the DB in a
  partial state.
- There is no ordered, versioned history of schema changes.
- Rollback is not structured — it requires reverting application code.
- Explicit migrations allow peer review, CI gate checks, and DBA sign-off before
  schema touches production.

This plan defines:

- An inventory of runtime DDL currently executed at startup.
- Classification of DDL by risk and migration coverage status.
- A phased cutover approach.
- Domain priority order for migration coverage.
- Safety gates required before any startup DDL is removed.
- Rollback and no-op strategy.

**This task defines the cutover plan only.**

No runtime code is changed in this task. No startup files were edited. No migration
files are created. No SQL is executed. Production DB is untouched. Balance.ge remains
inactive.

---

## B) Current State

### Completed prior work

- `docs/trust-foundation-implementation-plan.md` — Pillar 4 defines runtime DDL cutover
  as a required trust foundation step.
- `docs/core-schema-hardening-plan.md` — defines schema ownership rules for auth,
  credential, and accounting truth tables.
- `docs/db-schema-inventory.md` — baseline schema ownership and migration risk profile.
- `tests/fixtures/schema_manifest.json` — existing schema manifest used by contract tests.
- `tests/unit/test_schema_manifest.py` — schema manifest contract tests.

### Runtime DDL status

Runtime DDL still exists and executes in three startup files:

| File | Type | Risk |
|---|---|---|
| `app/startup/migrations.py` | ALTER TABLE ADD COLUMN + CREATE TABLE + data migration | High |
| `app/startup/migrations_tables.py` | CREATE TABLE | Medium–High |
| `app/startup/migrations_indexes.py` | CREATE INDEX + ALTER TABLE + constraints + data mutations | High |

Runtime DDL removal is **not changed in this task**. Startup files are **not edited
in this task**. No migration creation is performed in this task.

### Explicit SQL migration files

Eight explicit SQL migration files exist in `app/storage/migrations/`:

| File | Domain | Coverage Status |
|---|---|---|
| `001_multi_tenant_schema.sql` | Core multi-tenant schema | Active |
| `002_row_level_security.sql` | Row-level security policies | Active |
| `003_triangle_schema.sql` | Triangle matching schema | Active |
| `004_outgoing_invoices.sql` | Outgoing invoice schema | Active |
| `005_inventory_erp_schema.sql` | Inventory ERP schema | Active |
| `006_payroll_employee_schema.sql` | Payroll employee schema | Active |
| `007_trade_partner_schema.sql` | Trade partner schema | Active |
| `008_outgoing_invoice_columns.sql` | Outgoing invoice column additions | Active |

**Balance.ge activation status: inactive — Balance.ge must stay inactive.**
**Production DB status: untouched in this task.**

---

## C) Runtime DDL Inventory

### C1) CREATE TABLE at startup

Tables created via `app/startup/migrations.py`:

| Table | File | Migration Coverage |
|---|---|---|
| `customers` | migrations.py | None — runtime only |
| `customer_interactions` | migrations.py | None — runtime only |
| `contracts` | migrations.py | None — runtime only |
| `contract_milestones` | migrations.py | None — runtime only |

Tables created via `app/startup/migrations_tables.py`:

| Table | File | Migration Coverage |
|---|---|---|
| `expense_articles` | migrations_tables.py | None — runtime only |
| `expenses` | migrations_tables.py | None — runtime only |
| `invoices` | migrations_tables.py | None — runtime only |
| `invoice_lines` | migrations_tables.py | None — runtime only |
| `comments` | migrations_tables.py | None — runtime only |
| `attachments` | migrations_tables.py | None — runtime only |
| `chat_sessions` | migrations_tables.py | None — runtime only |
| `idempotency_keys` | migrations_tables.py | None — runtime only |
| `search_index` | migrations_tables.py | None — runtime only |
| `bank_reconciliations` | migrations_tables.py | None — runtime only |

### C2) ALTER TABLE ADD COLUMN at startup

| Table | Columns Added | Source File |
|---|---|---|
| `outgoing_invoices` | sent_at, invoice_date, delivery_date, seller_name, seller_inn, seller_address, seller_phone, seller_bank, seller_swift, seller_account, buyer_address, buyer_phone (12 cols) | migrations.py |
| `tenants` | company_inn, company_name_legal, company_name_aliases, owner_personal_id, company_type, is_vat_payer, subscription_tier, trial_ends_at, signature_b64, stamp_b64, submit_token (11 cols) | migrations.py |
| `processed_documents` | gcs_path, status, approved_by, approved_at, source_document_id (5 cols) | migrations.py |
| `journal_drafts` | attached_file_path, attached_file_name, attached_file_size, autopilot_suggested, confidence_score, effective_threshold, review_required, partner, autopilot_flag, engine_metadata, doc_set_score, doc_set_summary, doc_matrix, provider_type, tax_detail, triangle_match_id, completeness_alerts, journal_entries, raw_extraction (19 cols) | migrations.py |
| `learning_patterns` | weighted_success_score, weighted_failure_score, usage_count, last_used_at (4 cols) | migrations.py |
| `exchange_rates` | from_code, to_code, source, fetched_at (4 cols) | migrations_indexes.py |
| `journal_drafts` | currency (1 col FX) | migrations_indexes.py |
| `journal_entries` | currency, amount_gel, exchange_rate (3 cols FX) | migrations_indexes.py |
| `journal_entries` | entry_hash (1 col) | migrations_indexes.py |
| `posting_logs` | entry_hash, source_draft_id (2 cols) | migrations_indexes.py |
| `invoices` | original_rate, exchange_rate (2 cols FX) | migrations_tables.py |
| `chat_sessions` | tenant_id, user_id, messages, context, updated_at (5 cols) | migrations_tables.py |
| `pipeline_runs` | tenant_id (1 col) | migrations_indexes.py |
| `search_history` | tenant_id (1 col) | migrations_indexes.py |

Total runtime ALTER TABLE ADD COLUMN statements: approximately 60 columns across 14 tables.

### C3) CREATE INDEX at startup

Indexes created via `migrations_indexes.py`:

- 5 core performance indexes (journal_drafts, processed_documents, tenants)
- 1 unique index on journal_entries.entry_hash
- 1 exchange rate lookup index
- 1 unique posting_logs.entry_hash index
- 6 domain indexes (expenses, contracts, customers, bank, pipeline, search)
- 18 speed phase indexes across journal_drafts, journal_entries, audit_log, audit_events, bank_transactions, posting_logs, outgoing_invoices, learning_patterns, pipeline_runs
- 1 bank reconciliation unique index and 1 tenant index (migrations_tables.py)
- 1 chat session index (migrations_tables.py)
- 1 idempotency key index (migrations_tables.py)

Total: approximately 37 indexes created at startup.

### C4) Constraints at startup

- `ALTER TABLE outgoing_invoices DROP CONSTRAINT IF EXISTS outgoing_invoices_status_check` — **risky pattern**: destructive constraint drop at startup, followed by re-add with updated values. Documented as `requires_deeper_audit`.
- `ALTER TABLE outgoing_invoices ADD CONSTRAINT IF NOT EXISTS outgoing_invoices_status_check` — constraint re-add (additive intent).
- Data quality constraints on journal_drafts, expenses, invoices, learning_patterns — additive.
- Unique constraint on invoices (tenant_id, invoice_number) — additive.

### C5) Data mutations at startup

The following data mutations execute at startup — these are high-risk patterns in a migration tool:

| Mutation | Source File | Risk |
|---|---|---|
| `UPDATE tenants SET submit_token = ... WHERE submit_token IS NULL` | migrations.py | Medium — data backfill, idempotent |
| `ALTER TABLE {tbl} ALTER COLUMN tenant_id TYPE TEXT USING tenant_id::text` | migrations.py | High — type coercion on production tables |
| `UPDATE {tbl} SET tenant_id = t.tenant_id FROM tenants t ...` (tenant normalization, 6 tables) | migrations_indexes.py | High — data mutation on every startup |
| `UPDATE exchange_rates SET from_code / to_code / fetched_at ...` (backfill) | migrations_indexes.py | Medium — data backfill, idempotent |
| `SELECT ... FROM journal_drafts WHERE ... / UPDATE journal_drafts SET debit_account ...` (auto-classify) | migrations_indexes.py | High — AI classification at startup on production data |

The auto-classify drafts mutation is especially risky: it reads up to 500 journal_drafts
with missing accounts and updates them using AI classification logic at startup. This runs
on every deployment restart.

---

## D) Cutover Principles

1. **Migrations first** — explicit reviewed SQL files are the source of truth for schema.
2. **Tests first** — migration coverage tests must pass before startup DDL is removed.
3. **Additive-only until explicitly approved** — no DROP TABLE, no DROP COLUMN, no TRUNCATE, no destructive ALTER in any new migration without explicit review and approval gate.
4. **No destructive SQL** — DROP TABLE, TRUNCATE, and DROP COLUMN are forbidden in all new migration files. DROP CONSTRAINT is permitted only with documented reason and a matching re-add.
5. **No production DB manual SQL** — all schema changes go through versioned migration files.
6. **No startup behavior removal until migration coverage is proven** — removing a runtime DDL block requires: explicit migration exists, migration tests pass, schema manifest updated, deploy verified.
7. **One schema slice per PR** — each PR covers at most one domain's migration coverage. No bulk removals.
8. **Deploy and verify after each slice** — live /version must match, /health must be stable, protected endpoints must remain authorized.
9. **Rollback / no-op strategy required** — every startup DDL removal must have a rollback path.
10. **Schema manifest remains the coverage authority** — `tests/fixtures/schema_manifest.json` must be updated when new migration coverage is added.

---

## E) Migration Coverage Strategy

### Required coverage rules

- Every runtime-created table must have explicit migration coverage or a documented deferral reason in this plan.
- Every runtime-added column must have explicit migration coverage or a documented deferral reason.
- Every runtime-created index must have explicit migration coverage or a documented deferral reason.
- Schema manifest must describe ownership, source, and risk for each table/column group.
- Read-only tests must confirm migration files do not contain destructive SQL.

### Coverage gap summary

| Domain | Tables with no explicit migration | Priority |
|---|---|---|
| CRM | customers, customer_interactions | Medium |
| Contracts | contracts, contract_milestones | Medium |
| Expenses | expense_articles, expenses | Medium |
| Invoices | invoices, invoice_lines | Medium |
| Collaboration | comments, attachments | Low |
| Chat | chat_sessions | Low |
| Idempotency | idempotency_keys | Medium |
| Search | search_index | Low |
| Bank reconciliation | bank_reconciliations | High |
| FX / multi-currency | exchange_rates columns, journal FX columns | Medium |
| Posting logs | posting_logs columns | Medium |
| Tenant columns | tenants 11-column runtime ADD | High |
| Auth/identity tables | No explicit migration for users-related changes | High |

---

## F) Runtime DDL Classification

Runtime DDL is classified into these categories:

### already_covered_by_explicit_migration

DDL for which an explicit SQL migration file already exists in `app/storage/migrations/`:

- `outgoing_invoices` table structure → covered by `004_outgoing_invoices.sql`
- `outgoing_invoices` column additions → partially covered by `008_outgoing_invoice_columns.sql`
- inventory ERP tables → covered by `005_inventory_erp_schema.sql`
- payroll employee tables → covered by `006_payroll_employee_schema.sql`
- trade partner tables → covered by `007_trade_partner_schema.sql`
- triangle matching tables → covered by `003_triangle_schema.sql`
- core multi-tenant schema → covered by `001_multi_tenant_schema.sql`

### safe_additive_pending_migration

DDL that is additive (ADD COLUMN IF NOT EXISTS, CREATE TABLE IF NOT EXISTS) and has no
explicit migration yet. Safe to add as a new migration without risk of data loss:

- `customers`, `customer_interactions` CREATE TABLE
- `contracts`, `contract_milestones` CREATE TABLE
- `expense_articles`, `expenses`, `invoices`, `invoice_lines` CREATE TABLE
- `comments`, `attachments`, `chat_sessions` CREATE TABLE
- `idempotency_keys`, `search_index`, `bank_reconciliations` CREATE TABLE
- `journal_drafts` column additions (19 columns)
- `tenants` column additions (11 columns)
- `processed_documents` column additions (5 columns)
- `learning_patterns` column additions (4 columns)
- FX columns on exchange_rates, journal_drafts, journal_entries, invoices

### index_only_pending_migration

Indexes with no explicit migration. These can be added as separate index-only migrations
with low risk (CREATE INDEX IF NOT EXISTS is non-destructive):

- All 37 startup indexes in `migrations_indexes.py` and `migrations_tables.py`

### requires_deeper_audit

DDL requiring deeper review before migration coverage or removal:

- `ALTER TABLE outgoing_invoices DROP CONSTRAINT IF EXISTS outgoing_invoices_status_check` — destructive constraint drop at startup (then re-added). Must be reviewed before creating an equivalent migration.
- `ALTER TABLE {tbl} ALTER COLUMN tenant_id TYPE TEXT USING tenant_id::text` — type coercion on production tables (expenses, invoices, contracts, customers). High risk, must be audited before migration equivalent.
- Data mutations at startup (tenant normalization UPDATE, exchange_rates backfill) — require explicit one-time migration with careful idempotency design.
- Auto-classify journal_drafts at startup — should become a background job, not a startup mutation.

### forbidden_destructive

These patterns are forbidden in any new migration file or startup addition:

- `DROP TABLE` (any table) without explicit deprecation plan and full data export
- `TRUNCATE` (any table)
- `DROP COLUMN` without explicit schema contract update
- `DROP CONSTRAINT` without a matching ADD CONSTRAINT in the same migration
- Destructive `ALTER TABLE` (e.g., shrinking column type, adding NOT NULL to nullable column with data)

### temporary_runtime_only

DDL that should remain runtime-only for now with documented reason:

- `tenant_settings` table creation via `ensure_tenant_settings_table()` — used by per-tenant config service; requires app service context. Pending service-level migration ownership.

---

## G) Cutover Phases

### Phase 0 — Inventory and Contract Tests (this task)

- Docs and tests only.
- No runtime change, no startup edit, no migration creation.
- Deliverable: `docs/runtime-ddl-cutover-plan.md`, `tests/unit/test_runtime_ddl_cutover_contract.py`.

### Phase 1 — Migration Coverage Gap Map

- Read-only audit of each startup DDL statement vs existing migration files.
- Produce a per-table/column gap map documenting covered, uncovered, deferred.
- No migration files created yet.
- Deliverable: updated `docs/db-schema-inventory.md` or gap-map addendum.

### Phase 2 — Additive Migration Slices

- One migration file per domain, additive-only (CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS).
- Start with highest-priority gaps: tenants columns, bank_reconciliations, CRM tables.
- Read-only migration tests for each slice.
- Startup DDL not removed yet.
- Deliverable: new migration files, new migration contract tests.

### Phase 3 — Shadow Verification

- Compare schema manifest vs explicit migrations vs runtime DDL output.
- Ensure no divergence between migration-applied schema and runtime-applied schema.
- Startup still unchanged.
- Deliverable: shadow diff report, schema manifest update.

### Phase 4 — Runtime DDL No-op Mode Planning

- Design feature flag / environment gate: `STARTUP_DDL_MODE=apply | log_only | skip`.
- Log-only mode records which DDL would fire without applying.
- No production removal.
- Deliverable: no-op mode design document, feature flag spec.

### Phase 5 — Controlled Startup DDL Disablement

- Only after Phase 2–3 migrations deployed and verified on production.
- Staged by domain: disable one domain's startup DDL block after its migration is live.
- Rollback switch must be in place before disabling.
- Each disable must be a separate PR with live verification.

### Phase 6 — Cleanup

- Remove disabled/dead startup DDL blocks only after live verification confirms no regression.
- Keep schema manifest tests and migration contract tests permanently.

---

## H) Domain Priority Order

Priority for migration coverage, highest risk first:

1. **Inventory** — `005_inventory_erp_schema.sql` exists; verify full coverage and add missing columns/indexes.
2. **Payroll** — `006_payroll_employee_schema.sql` exists; verify full coverage.
3. **Trade** — `007_trade_partner_schema.sql` exists; verify full coverage.
4. **Outgoing invoice** — `004_outgoing_invoices.sql` + `008_outgoing_invoice_columns.sql` exist; verify sent_at/seller/buyer columns are covered.
5. **Credential/security** — tenant_secrets, tenant_balance_credentials, tenant_rsge_credentials, tenant_email_credentials; requires vault encryption context.
6. **Auth/tenant/subscription** — tenants 11-column runtime ADD; subscription_tier, trial_ends_at, company_inn, submit_token; aligns with subscription enforcement contract.
7. **Accounting truth** — journal_drafts 19-column runtime ADD; journal_entries FX columns; posting_logs idempotency columns.
8. **Document/OCR/evidence** — processed_documents 5-column runtime ADD; bank_reconciliations CREATE TABLE.
9. **Connector/audit/posting logs** — audit_log, audit_events, posting_logs columns; tenant normalization data migration.
10. **Indexes** — all 37 startup indexes; lowest risk, can be added as index-only migration slices.

---

## I) Safety Gates

Before any startup DDL block is removed or disabled:

| Gate | Description |
|---|---|
| `explicit_migration_exists` | A reviewed SQL migration file covers all DDL in the block being removed |
| `migration_tests_pass` | Contract tests asserting migration content pass in CI |
| `schema_manifest_updated` | `tests/fixtures/schema_manifest.json` updated to reflect new migration ownership |
| `local_tests_pass` | Full unit test suite passes locally |
| `pr_checks_pass` | All CI checks pass on the PR removing the startup DDL |
| `deploy_succeeds` | Cloud Run deploy completes without error |
| `live_version_matches` | `/version` commit SHA matches deployed commit |
| `health_stable` | `/health` returns 200 with no new warnings post-deploy |
| `protected_endpoints_unauthorized` | Protected endpoints still return 401/403 for unauthenticated requests |
| `rollback_switch_exists` | A documented rollback path exists to re-enable the disabled startup DDL |
| `no_production_manual_sql` | No manual SQL was executed against production DB outside migration files |

All 11 gates must be met before any startup DDL disablement PR is merged.

---

## J) Rollback / No-op Strategy

1. **Startup DDL disablement must be reversible.** The environment gate `STARTUP_DDL_MODE` allows quick re-enablement without a code deploy.
2. **No-op mode must log skipped DDL.** Every skipped startup DDL statement must produce a log entry at INFO level: `action=startup_ddl_skipped table=X statement_type=ALTER`.
3. **Failure must not corrupt DB.** Each startup DDL block must remain wrapped in try/except with rollback. No DDL block failure should abort the entire startup.
4. **Production rollout must be gradual.** Domain-by-domain disablement, not bulk removal.
5. **Previous runtime DDL path must remain restorable.** Until Phase 5 is stable across all domains, the startup DDL code must not be deleted — only disabled via flag.

---

## K) Forbidden Work in This Task

- No runtime code change.
- No startup file edit (`migrations.py`, `migrations_tables.py`, `migrations_indexes.py` not changed).
- No migration creation (no new SQL files in `app/storage/migrations/`).
- No SQL execution.
- No production DB touch.
- No Balance.ge activation.
- No Task 10F-G or Task 11C implementation.

**Balance.ge activation remains blocked** until all 12 gates in
`docs/balance-ge-activation-gate.md` are MET. All gates are currently NOT MET.

---

## L) Test Strategy

Task 10F-F tests in `tests/unit/test_runtime_ddl_cutover_contract.py` validate this
contract using only:

- Reading doc files and asserting required content is present.
- Reading startup Python files as text to confirm runtime DDL indicators exist.
- Scanning explicit SQL migration files for forbidden destructive patterns.
- Local test-only set definitions (phases, gates, classifications, domains).
- No DB access, no runtime imports, no SQL execution, no startup module imports.

Tests must not:

- Import `app.startup.*` modules.
- Connect to any database.
- Execute SQL.
- Use psycopg2 or asyncpg connect patterns.
- Change any runtime behavior.

---

## M) Future Implementation Scope

### Task 10F-F1 — Runtime DDL Inventory and Gap Map

- Read-only audit producing a per-table/column gap map.
- Update `docs/db-schema-inventory.md` with full coverage status.

### Task 10F-F2 — Migration Coverage Map

- Map each startup DDL statement to: covered, uncovered, deferred.
- Produce per-domain migration readiness score.

### Task 10F-F3 — Additive Migration Slice Planning

- Draft migration SQL for highest-priority gaps (tenants columns, bank_reconciliations, CRM).
- Read-only migration content tests.
- No startup removal.

### Task 10F-F4 — Startup DDL No-op Flag Design

- Design `STARTUP_DDL_MODE` environment gate.
- Define log format for skipped DDL.
- Define metric: `startup_ddl.skipped_count`, `startup_ddl.applied_count`.

### Task 10F-F5 — Shadow Verification Tests

- Compare migration-applied schema vs runtime DDL output.
- Schema manifest diff validation.

### Task 10F-F6 — Staged Disablement Plan

- Per-domain disablement checklist.
- Rollback runbook for each domain.

### Task 10F-F7 — Live Verification Playbook

- End-to-end: deploy with startup DDL disabled for one domain, verify schema intact, verify app healthy.
