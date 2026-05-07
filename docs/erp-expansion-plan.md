# Bridge Hub ERP Expansion Plan

## Scope

This document is planning only. It does not change database schema, add API routes, or modify production behavior.

## Current Repo Reality

- Core accounting and approval flows already exist.
- Inventory routes and services already exist in the repo.
- Payroll routes and services already exist in the repo.
- Reporting routes already cover ledger, trial balance, counterparty ledger, payroll ledger, and cash flow.
- The tenant model in the repo uses the existing project tenant identifier type consistently; do not assume a different type when planning schema.

## Implementation Phases

1. Inventory hardening and gap closure.
2. Payroll ERP completion and Georgian compliance alignment.
3. Purchases and sales workflow expansion.
4. Reporting workbench consolidation.
5. Period closing and tax workflow refinement.

## Module Plan

### Inventory Management

Existing backend routes to reuse:

- `app/api/routes_inventory.py`
- `app/api/services/inventory_service.py`

Missing routes:

- Product CRUD if not fully complete.
- Stock movement history and adjustment routes.
- Low-stock alert endpoint.
- Valuation report endpoint.

Database tables needed:

- `products`
- `stock_movements`
- Optional supporting table for inventory thresholds if the current schema lacks one.

Tenant isolation rules:

- Every query must filter by `tenant_id`.
- Product codes must be tenant-scoped and unique per tenant.

Approval workflow integration:

- Stock movements that affect accounting should create journal drafts.
- Journal drafts must flow through approval rather than direct posting.

Journal draft integration:

- Positive or negative inventory valuation deltas should map to draft entries.

Frontend page needed:

- `static/inventory.html`

Tests needed:

- Tenant-scoped product CRUD.
- Stock movement updates on-hand inventory.
- Low-stock alerts.
- Valuation report structure.
- Draft creation when accounting impact exists.

Rollout risk:

- Medium. Inventory affects valuation and accounting entries.

Rollback plan:

- Disable new routes behind the existing router registration and preserve read-only inventory views.

### Payroll ERP / Georgian Compliance

Existing backend routes to reuse:

- `app/api/routes_payroll.py`
- `app/api/services/payroll_service.py`
- `app/api/routes_reports.py` payroll ledger route

Missing routes:

- Employee CRUD if not fully complete.
- Periodized payroll run persistence if not already tenant-safe.
- Export endpoints for RS.ge-compatible output if needed.

Database tables needed:

- `employees`
- `payroll_runs`
- `payroll_run_lines`

Tenant isolation rules:

- Employee and payroll run queries must remain tenant-scoped.

Approval workflow integration:

- Payroll journal impacts must be drafted, then approved.

Journal draft integration:

- Net salary, PIT, employer pension, and employee pension entries should generate journal drafts.

Frontend page needed:

- Payroll management page or extension of the current payroll ledger surface.

Tests needed:

- PIT 20% calculation.
- Employee pension 2%.
- Employer pension 2%.
- Net salary formula.
- Tenant-scoped payroll reporting.

Rollout risk:

- Medium to high because payroll formula changes affect financial reporting.

Rollback plan:

- Keep payroll calculation read paths stable and gate persistence changes until outputs match existing tests.

### Purchases and Sales

Existing backend routes to reuse:

- Document ingestion and approval routes for source documents.
- Ledger and counterparty reporting routes.

Missing routes:

- Supplier CRUD.
- Customer CRUD.
- Purchase order CRUD and status transitions.
- Sales invoice CRUD.
- Payment tracking if not already covered.

Database tables needed:

- `suppliers`
- `customers`
- `purchase_orders`
- `sales_invoices`
- `payments`

Tenant isolation rules:

- Every business entity must be tenant-scoped and unique only within tenant boundaries.

Approval workflow integration:

- Purchase and sales financial impact should draft journal entries, not post directly.

Journal draft integration:

- Purchase order receipt, invoice issuance, and payment application should create draft entries when accounting impact exists.

Frontend page needed:

- Supplier/customer management.
- Purchase order workflow.
- Sales invoice workflow.
- Payment tracking and credit status views.

Tests needed:

- Tenant-scoped CRUD.
- Purchase order status flow.
- Sales invoice creates draft.
- Unauthorized access blocked.

Rollout risk:

- High because these surfaces affect revenue, receivables, and payables.

Rollback plan:

- Ship the new routes behind router inclusion only after the supporting tables are migrated and verified.

### Reporting Workbench

Existing backend routes to reuse:

- `app/api/routes_reports.py`
- `app/api/services/ledger_service.py`
- `app/api/services/financial_statements_service.py`

Missing routes:

- Add only missing reporting routes if they do not already exist.

Required UI pages:

- Account card / ledger.
- Trial balance.
- Posted journal.
- Counterparty card.
- Balance sheet.
- Profit and loss.
- Cash flow.
- VAT register.
- Period closing dashboard.

Accounting requirements:

- Reports should use posted entries where appropriate.
- Trial balance must show opening balance, debit turnover, credit turnover, and closing balance.
- Balance sheet must still verify Assets = Liabilities + Equity.
- VAT register must follow Georgian tax reporting expectations.

Tests needed:

- Balance sheet equation.
- Trial balance structure.
- Tenant-scoped account ledger.
- Posted-only P&L.
- Cash flow structure.
- VAT report structure.

Rollout risk:

- Medium.

Rollback plan:

- Keep the legacy report routes intact until new report screens are validated in staging.

## Migration Plan

1. Inspect existing schema and migrations before adding tables.
2. Add tenant-scoped tables only where missing.
3. Backfill data in an idempotent migration step.
4. Verify reports and approval flows against production-like data.

## Testing Plan

- Unit tests for formulas, validation, and tenant filters.
- Route-level tests for response envelopes and permission checks.
- Integration tests for journal draft creation and idempotency where applicable.
- Smoke tests for all affected UI surfaces.

## Rollback Strategy

- Prefer additive schema changes.
- Keep new tables and routes isolated so they can be disabled without breaking the core approval/posting flow.
- Use feature flags or router registration only when a module is not yet fully ready.
