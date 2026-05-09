# Bridge Hub Migration Stabilization Plan

This plan follows Task 10A and Task 10B. It is intentionally non-destructive and
does not introduce production migrations yet.

## Stabilization Principles

- Do not mutate production schema from application startup once formal
  migrations exist.
- Do not remove existing runtime `ensure_*` compatibility code until migration
  replay and existing-database upgrade tests pass.
- Prefer additive migrations first: create missing tables, add nullable columns,
  add indexes concurrently where the database supports it, then backfill in
  controlled batches.
- Keep approval-first accounting behavior unchanged.
- Keep posted ledger truth separate from pending drafts.
- Treat credential/secret tables as security-sensitive schema.

## Task 10C: Non-Destructive Migration Replay Tests

Goal: prove the current schema can be described and replayed safely without
touching production data.

Planned work:

1. Add a test-only schema manifest loader for `tests/fixtures/schema_manifest.json`.
2. Add tests that verify the manifest is valid JSON and has required fields for
   every documented table.
3. Add a dry-run ordering test for existing SQL/script/startup schema sources.
4. Add a fresh test database bootstrap test only if the existing test harness has
   a safe ephemeral database path.
5. Add a schema drift report that compares expected table ownership to runtime
   DDL sources.

Safety notes:

- No production database connections.
- No destructive commands.
- No runtime behavior changes.
- Runtime `ensure_*` functions remain in place.

Exit criteria:

- Manifest validation passes in unit tests.
- Fresh-schema replay risks are documented.
- Existing full unit suite still passes.

## Task 10D: Move ERP Runtime DDL To Ordered Migrations

Goal: convert runtime-created ERP tables into formal ordered migrations without
changing API behavior.

Recommended order:

1. Inventory:
   - `inventory_categories`
   - `warehouses`
   - `inventory_items`
   - `stock_movements`
   - `purchase_orders`
   - `purchase_order_lines`
2. Payroll and employees:
   - `employees`
   - `pension_transfers`
   - `payroll_runs`
   - `payroll_run_lines`
3. Trade/sales consolidation:
   - `customers`
   - `customer_interactions`
   - `outgoing_invoices`
   - `invoice_counters`
   - legacy `invoices` and `invoice_lines` compatibility notes
4. Reporting/closing support:
   - `period_locks`
   - `exchange_rates`
   - `bank_reconciliations`

Rollback safety:

- Additive table creation can be rolled back by leaving unused tables in place.
- Column additions should be nullable or have safe defaults first.
- Index additions should be separately deployable.
- Backfills should be idempotent and batchable.
- No column drops, table drops, or type narrowing in this task.

Exit criteria:

- Ordered migrations exist for ERP runtime DDL.
- Runtime `ensure_*` functions can detect existing schema without altering it in
  normal environments.
- Inventory/payroll/trade/reporting regression tests pass.

## Task 10E: Harden Core Accounting, Auth, And Credential Schemas

Goal: stabilize the schemas that carry real accounting truth, auth, and secrets.

Core accounting:

- Canonicalize `journal_drafts`, `journal_entries`, `posting_logs`,
  `draft_comments`, and audit tables.
- Confirm idempotency fields and unique constraints around approval/posting.
- Confirm posted reports use only posted ledger tables where appropriate.
- Add missing indexes for `tenant_id`, date, status, account, and source draft.

Auth and tenant:

- Quarantine or replace `scripts/run_users_migration.py` because it contains
  destructive `DROP TABLE IF EXISTS users`.
- Canonicalize `users`, `tenants`, `tenant_settings`, and `tenant_secrets`.
- Review tenant ID type consistency and DB-level isolation strategy.

Credentials and connectors:

- Canonicalize `tenant_balance_credentials`, `tenant_email_credentials`,
  `tenant_secrets`, `webhooks`, and `webhook_deliveries`.
- Require security review for encryption, masking, rotation, and audit events.
- Do not add connector behavior during schema stabilization.

Rollback safety:

- Use additive migrations and non-destructive constraints first.
- Add NOT NULL constraints only after data backfill validation.
- Add foreign keys in a controlled phase after orphan detection.
- Keep runtime behavior unchanged until all tests pass.

## Required Reviews Before Real Accounting Use

Accountant review:

- Chart of accounts mapping for inventory, payroll, trade, VAT, and banking.
- VAT register classification assumptions.
- Payroll PIT and pension handling.
- Period closing workflow and reversal policy.
- Balance sheet and trial balance source-of-truth rules.

Security review:

- Tenant isolation guarantees at app and database layers.
- Credential encryption and rotation.
- Auth/RBAC permissions on accounting, payroll, trade, and reporting routes.
- Audit log completeness for approval, posting, connector access, and settings.

Operations review:

- Migration execution process.
- Backup/restore plan.
- Rollback plan.
- Deployment ordering.
- Monitoring for migration failures and schema drift.

## What Must Not Be Done Yet

- Do not run migrations against production.
- Do not remove runtime schema compatibility code yet.
- Do not drop or rename production tables.
- Do not add connector features.
- Do not alter approval/posting behavior.
- Do not introduce new ERP transactional modules.
- Do not enforce new NOT NULL or foreign key constraints until orphan data and
  backfills are tested.

## Recommended Next Step

Task 10C should be next: add non-destructive validation around the manifest and
migration replay assumptions. It should be test-focused and should not create
production migrations yet.
