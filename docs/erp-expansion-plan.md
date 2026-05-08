# Bridge Hub ERP Expansion Technical Plan

## Scope And Non-Implementation Rules

Task 5 is a planning-only task. This document does not add production code, API routes, database tables, migrations, frontend pages, auth rules, or business behavior.

ERP implementation must follow these rules:

- All accounting-impacting ERP actions create `journal_drafts` and never post directly.
- Posting remains approval-first through the existing approval and posting flow.
- All queries must be tenant-scoped with the current request tenant.
- New schemas must use the existing project `tenant_id` type consistently.
- Do not assume `tenant_id` is an integer.
- Preserve auth, RBAC, tenant isolation, idempotency, audit trail, approval workflow, and posting behavior.

## Existing System Reuse Baseline

Inspected files:

- `app/api/routes_inventory.py`
- `app/api/services/inventory_service.py`
- `app/api/routes_payroll.py`
- `app/api/services/payroll_service.py`
- `app/api/routes_reports.py`
- `app/api/routes_documents.py`
- `app/api/routes_approval.py`
- `app/api/services/posting_service.py`
- `app/api/services/ledger_service.py`
- `app/core/router_registry.py`
- `docs/`
- `migrations/`
- `app/storage/migrations/`
- `app/startup/migrations.py`
- `app/startup/migrations_tables.py`
- `app/startup/migrations_indexes.py`

Current reusable capabilities:

- Inventory routes already exist under `/inventory`.
- Payroll routes already exist under `/payroll`.
- Reporting routes already include ledger, trial balance, counterparty ledger, payroll ledger, journal, P&L detail, balance sheet detail, and cash flow detail under `/reports`.
- Document ingestion already covers generic uploads, waybills, tax invoices, commercial invoices, triangle matches, and document file retrieval under `/documents`.
- Approval routes already cover queue, approve, reject, correct, audit, preview, stats, batch action, attachments, and CFO approval under `/approval`.
- Posting routes already cover approved drafts, payload preview, posting logs, connector statuses, posting preview, and posting apply under `/posting`.
- Router registration is centralized in `app/core/router_registry.py`.
- Startup migrations and SQL migrations use additive `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, indexes, and row-level-security support.

## Tenant ID Type And Isolation Rule

The existing project treats `tenant_id` as string-like:

- Python services and routes pass `tenant_id: str`.
- Startup migrations use `tenant_id TEXT NOT NULL DEFAULT 'default'` in multiple tables.
- SQL migrations use `tenant_id TEXT NOT NULL` for tenant-scoped tables.
- User model uses `tenant_id VARCHAR(100)`.
- Startup migration code explicitly converts old UUID tenant IDs to TEXT for some legacy tables.

ERP schema work must therefore use the same string/TEXT tenant identifier pattern. New schema plans should use `tenant_id TEXT NOT NULL` unless they are extending a table that already uses `VARCHAR(100)`, in which case they must remain compatible with the existing column type. Every route and service must filter by tenant and every unique business key must be unique within tenant boundaries.

## Dependency Order

1. Schema inventory: confirm existing tables, tenant column types, indexes, and RLS policies.
2. Shared ERP primitives: counterparties, items, warehouses, journal-draft helpers, status enums, audit events.
3. Reporting read models: account card, trial balance, counterparty card, VAT register, and period-close previews.
4. Inventory implementation hardening.
5. Purchase management.
6. Sales management.
7. Payroll ERP persistence and Georgian compliance exports.
8. Period closing execution and controls.
9. Advanced reporting workbench.
10. Connector export/import refinements after internal workflows are stable.

The first implementation task after this plan should be inventory hardening because inventory routes and services already exist and purchase receiving already has journal draft integration.

## Implementation Phases

### Phase 1: Schema And Contract Review

- Build a table inventory from current migrations and production schema.
- Verify `tenant_id` type per table.
- Identify existing tables that can be reused before proposing new tables.
- Define response envelope and permission expectations for each planned endpoint.
- Define module-level audit events without logging sensitive document content.

### Phase 2: Read-Only Reporting And UI Foundations

- Implement read-only account card, trial balance, counterparty card, VAT register, and period closing previews first.
- Reuse `ledger_service` and existing `/reports` routes where possible.
- Avoid write behavior until read surfaces match accounting expectations.

### Phase 3: Inventory And Purchase Flow

- Harden inventory item, movement, valuation, reorder, and purchase order flows.
- Ensure every accounting-impacting movement creates journal drafts.
- Keep approval as the only route into posting.

### Phase 4: Sales Flow

- Extend outgoing invoice and customer/counterparty workflows.
- Generate receivable and revenue journal drafts from finalized sales documents.
- Keep PDF/email flows separate from posting.

### Phase 5: Payroll ERP

- Add durable payroll runs and employee payroll lines only after formulas and current payroll routes are locked by tests.
- Preserve Georgian PIT and pension formulas.
- Create journal drafts for salary, PIT, employee pension, and employer pension.

### Phase 6: Closing, VAT, And Advanced Reporting

- Add period close controls and VAT register workflows.
- Add management reporting and export surfaces.
- Keep close actions guarded by preview, approval, and audit logging.

## Schema Plan

Schema changes must be additive, tenant-scoped, and reversible where practical. Do not add tables until each module reaches implementation.

Planned schema groups:

- Inventory: reuse or confirm `inventory_items`, `stock_movements`, `warehouses`, `inventory_categories`, `purchase_orders`, and purchase order lines.
- Payroll ERP: `employees`, `payroll_runs`, `payroll_run_lines`, `payroll_exports`, and optional `payroll_pension_transfers` if existing employee portal tables are insufficient.
- Purchases: `purchase_orders`, `purchase_order_lines`, `supplier_invoices`, `supplier_payments`, and links to `processed_documents` and `journal_drafts`.
- Sales: reuse `outgoing_invoices` and `invoice_counters`; add sales invoice lines or status history only if existing structures are insufficient.
- Reporting: prefer views or service-layer read models over materialized tables until performance requires caching.
- Period closing: reuse existing period lock and closing routes; add `period_closing_runs` and `period_closing_entries` only if current closing tables cannot preserve audit history.
- VAT register: build initially from posted journal entries and document tables; add `vat_register_snapshots` only for filed/frozen reporting periods.

Every table must include:

- `tenant_id` using existing string/TEXT-compatible type.
- `created_at` and `updated_at` where state changes.
- Tenant-scoped indexes on common filters.
- Tenant-scoped uniqueness for document numbers, codes, and external IDs.
- Audit linkage fields where relevant, such as `source_document_id`, `journal_draft_id`, or `posted_log_id`.

## Endpoint Plan

Endpoint expansion should reuse existing routers where the domain already exists. New endpoints should be added only during implementation tasks, not in this planning task.

General rules:

- Read endpoints require module read permissions.
- Write endpoints require module write permissions.
- Accounting-impact endpoints return journal draft references, not posted-entry results.
- Batch endpoints return per-item results with `succeeded`, `failed`, `skipped`, and `items` where applicable.
- All endpoints return standard response envelopes.

## UI Plan

New UI work should be full workflow pages, not landing pages. Pages should use existing frontend helpers where applicable:

- `window.BHApi`
- `window.BHToast`
- `window.BHModal`
- `window.BHDebounce`

Planned UI pages:

- Inventory management page.
- Purchase management page.
- Sales management page.
- Payroll ERP page.
- Account card / ledger page.
- Trial balance page.
- Counterparty card page.
- VAT register page.
- Period closing page.
- Reporting workbench page.

Each write-capable UI must preview accounting impact before submitting approval-impacting actions.

## Testing Plan

Each module must include:

- Unit tests for validation, formulas, status transitions, and ledger mapping.
- Route tests for auth, RBAC, tenant isolation, response envelopes, and error codes.
- Service tests for journal draft creation and idempotency.
- Reporting tests for posted-only behavior and tenant filtering.
- Migration tests for tenant type consistency and index presence.
- UI syntax/loadability checks for changed frontend pages.
- Manual smoke tests for approval-first workflows before deployment.

## Migration Plan

1. Inspect production schema and current migrations before writing any migration.
2. Confirm each existing table's `tenant_id` type.
3. Add tables only with `CREATE TABLE IF NOT EXISTS`.
4. Add columns only with `ADD COLUMN IF NOT EXISTS`.
5. Add indexes concurrently where production constraints require it.
6. Backfill in idempotent batches.
7. Verify tenant-scoped uniqueness and RLS policy compatibility.
8. Deploy migrations before code paths that depend on them.
9. Add rollback notes to every migration PR.

## Rollback Plan

- Prefer additive schemas so rollback can disable routes/UI without dropping data.
- Gate new routers or pages until module acceptance tests pass.
- Keep old reporting routes intact until new reports are validated.
- For write modules, disable new entry points first, then leave data for reconciliation.
- Do not delete ERP tables in emergency rollback unless data retention and audit requirements have been reviewed.
- If a module creates incorrect journal drafts, stop the module, leave drafts unposted, and correct or reject through approval workflow.

## Module Plans

### Inventory Management

Existing backend routes to reuse:

- `/inventory/items`
- `/inventory/items/{item_id}`
- `/inventory/items/create`
- `/inventory/movements`
- `/inventory/valuation`
- `/inventory/purchase-orders`
- `/inventory/purchase-orders/{po_id}`
- `/inventory/purchase-orders/{po_id}/receive`
- `/inventory/warehouses`
- `/inventory/categories`
- `/inventory/reorder-report`
- `/inventory/export`
- Services in `app/api/services/inventory_service.py`

Missing routes:

- Stock adjustment approval preview.
- Inventory count session routes.
- Inventory transfer route between warehouses.
- Item status archive/reactivation route.
- Valuation detail by item and warehouse if current report is insufficient.

Database tables needed:

- Reuse or confirm `inventory_items`, `stock_movements`, `warehouses`, `inventory_categories`, `purchase_orders`, and purchase order lines.
- Add `inventory_counts`, `inventory_count_lines`, and `inventory_transfers` only if warehouse/count workflows are implemented.

Tenant isolation rules:

- Every item, warehouse, category, movement, purchase order, and count query must filter by `tenant_id`.
- Item codes and warehouse codes must be unique per tenant.
- Movement history must never join by item ID alone without tenant match.

Approval workflow integration:

- Stock adjustments with accounting impact require preview and approval.
- Purchase order receiving that creates financial impact must create journal drafts and stay pending approval.

Journal draft integration:

- Inventory purchases debit inventory/expense accounts and credit payable or clearing accounts through `create_journal_draft`.
- Adjustments create valuation-delta drafts.
- No inventory route may directly call posting apply.

Frontend page needed:

- `static/inventory.html` or an updated existing inventory page with item table, movement form, valuation report, reorder alerts, and purchase receiving workflow.

Tests needed:

- Tenant-scoped item CRUD.
- Movement validation and stock prevention for negative on-hand where applicable.
- Valuation methods.
- Reorder report.
- Purchase receiving creates journal drafts only when accounting impact exists.
- Unauthorized access returns 401/403.

Rollout risk:

- Medium. Inventory changes affect valuation and cost of goods sold.

Rollback plan:

- Disable new write controls and leave read-only inventory views active.
- Reject incorrect inventory journal drafts before posting.

### Payroll ERP / Georgian Compliance

Existing backend routes to reuse:

- `/payroll/calculate`
- `/payroll/calculate/single`
- `/payroll/generate-drafts`
- `/payroll/rs-ge-xml`
- `/payroll/history`
- `/payroll/ledger`
- `/payroll/payslip-pdf`
- `/payroll/status`
- `/reports/payroll`
- Employee portal routes under `/employees` where appropriate.

Missing routes:

- Payroll run create/list/detail/finalize.
- Employee compensation history.
- Payroll adjustment route.
- Payroll export history.
- Payroll approval preview route if current draft generation is insufficient.

Database tables needed:

- Reuse existing employee tables where present.
- Add `payroll_runs`, `payroll_run_lines`, `payroll_adjustments`, and `payroll_exports` only during payroll ERP implementation.

Tenant isolation rules:

- Employees, runs, run lines, payslips, and exports must filter by `tenant_id`.
- Employee personal IDs must be unique only within tenant or as legally required by the tenant context.

Approval workflow integration:

- Payroll run finalization creates draft entries and does not post.
- Payroll corrections create reversing or adjustment drafts through approval.

Journal draft integration:

- Net salary, PIT, employee pension, employer pension, and payable clearing entries create balanced journal drafts.
- Formulas must be locked by tests before any persistence changes.

Frontend page needed:

- Payroll ERP page with employees, run calculation, review, draft generation, payslip export, RS.ge export, and payroll ledger links.

Tests needed:

- Georgian PIT 20%.
- Employee pension 2%.
- Employer pension 2%.
- Net/gross calculations.
- Payroll run tenant isolation.
- Draft generation balanced entries.
- RS.ge XML shape and export audit.

Rollout risk:

- High. Payroll errors affect employees, tax, pension, and statutory filings.

Rollback plan:

- Keep calculation read paths stable.
- Disable run finalization if errors occur.
- Leave generated drafts pending and reject/correct through approval.

### Purchase Management

Existing backend routes to reuse:

- Inventory purchase order routes under `/inventory/purchase-orders`.
- Document ingestion routes for supplier documents under `/documents`.
- Approval queue and posting preview under `/approval` and `/posting`.
- Counterparty/customer infrastructure under `/crm/counterparties`.

Missing routes:

- Supplier invoice create/list/detail.
- Purchase order match to waybill/tax invoice/commercial invoice.
- Three-way match approval preview.
- Supplier payment schedule and payment application.
- Purchase return and credit note routes.

Database tables needed:

- Reuse `purchase_orders` and related inventory tables if sufficient.
- Add `supplier_invoices`, `supplier_invoice_lines`, `supplier_payments`, `purchase_matches`, and `purchase_returns` only as implementation requires.

Tenant isolation rules:

- Supplier invoices, matches, payments, and purchase returns must filter by `tenant_id`.
- Supplier document numbers must be unique per tenant, supplier, and fiscal period where required.

Approval workflow integration:

- Matched supplier invoice acceptance creates draft entries.
- Payment application creates draft entries and requires approval.
- Purchase returns create reversal or credit drafts.

Journal draft integration:

- Goods receipt, supplier invoice recognition, VAT input, payable, and payment clearing create journal drafts.
- Matching differences should create correction-needed status, not automatic posting.

Frontend page needed:

- Purchase management page with purchase orders, supplier invoices, document match status, payment status, and draft links.

Tests needed:

- Tenant-scoped supplier invoice CRUD.
- Three-way match status.
- Invoice acceptance creates balanced draft.
- Payment application creates draft.
- Duplicate supplier invoice detection.

Rollout risk:

- High. Purchases affect inventory, VAT input, payables, and cash.

Rollback plan:

- Disable purchase write endpoints/pages.
- Keep imported source documents and reject unposted drafts.

### Sales Management

Existing backend routes to reuse:

- `/outgoing/drafts`
- `/outgoing/drafts/{invoice_id}`
- `/outgoing/drafts/{invoice_id}/finalize`
- `/outgoing/list`
- `/outgoing/{invoice_id}`
- `/outgoing/{invoice_id}/send-email`
- `/outgoing/{invoice_id}/pdf`
- `/invoices/create`, `/invoices/list`, `/invoices/{invoice_id}`, and invoice status routes if compatible.
- CRM customer and counterparty routes.

Missing routes:

- Sales order create/list/detail.
- Delivery/fulfillment status.
- Customer payment application.
- Credit note and cancellation workflow.
- Sales invoice accounting preview if current finalize flow is insufficient.

Database tables needed:

- Reuse `outgoing_invoices`, `invoice_counters`, `invoices`, and `invoice_lines` where compatible.
- Add `sales_orders`, `sales_order_lines`, `customer_payments`, and `sales_credit_notes` only if needed.

Tenant isolation rules:

- Invoice numbers, sales orders, customer payments, and credit notes must be tenant-scoped.
- Customer joins must include tenant scope.

Approval workflow integration:

- Finalized sales documents create journal drafts.
- Credit notes and cancellations create reversal drafts.

Journal draft integration:

- Revenue, VAT output, receivable, cash receipt, and discount entries must be balanced drafts.
- No sales finalization should post directly.

Frontend page needed:

- Sales management page with invoice drafts, finalized invoices, customer balances, payments, PDFs, and email status.

Tests needed:

- Tenant-scoped invoice list/detail.
- Invoice finalization creates draft.
- Credit note reversal draft.
- Duplicate invoice number prevention.
- Unauthorized access checks.

Rollout risk:

- High. Sales affect revenue, VAT output, receivables, and customer statements.

Rollback plan:

- Disable new sales write pages.
- Preserve generated PDFs/documents.
- Reject/correct unposted sales drafts through approval.

### Advanced Reporting

Existing backend routes to reuse:

- `/reports/monthly`
- `/reports/annual`
- `/reports/audit-trail`
- `/reports/cashflow`
- `/reports/journal`
- `/reports/pnl/detail`
- `/reports/bs/detail`
- `/reports/cashflow/detail`
- `/reports/pnl`
- `/reports/balance-sheet`
- `/dashboard/live/*`
- `app/api/services/ledger_service.py`

Missing routes:

- Consolidated reporting workbench metadata.
- Saved report layouts.
- Export queue/status for larger reports.
- Report drilldown links to source drafts/documents.

Database tables needed:

- Prefer no new tables initially.
- Add `saved_reports`, `report_exports`, or `report_cache_snapshots` only after performance and UX requirements are proven.

Tenant isolation rules:

- Every report must filter by tenant before aggregation.
- Cached report rows must include tenant_id in keys and indexes.

Approval workflow integration:

- Reporting is read-only except saved layouts and exports.
- Reports should link to approval and posting records, not modify them.

Journal draft integration:

- Reports read posted entries where accounting statements require posted-only data.
- Draft-aware reports must clearly label pending, approved, simulated, and posted states.

Frontend page needed:

- Reporting workbench with filters, export actions, drilldowns, and saved views.

Tests needed:

- Posted-only P&L.
- Balance sheet equation.
- Cash flow structure.
- Tenant-scoped report filters.
- Drilldown source links.
- Export response envelope.

Rollout risk:

- Medium. Incorrect reports mislead decision-making even when journal data is correct.

Rollback plan:

- Keep existing reports available.
- Disable new workbench routes/UI if calculations fail validation.

### Account Card / Ledger UI

Existing backend routes to reuse:

- `/reports/ledger/{account_code}`
- `/reports/journal`
- `get_account_ledger` and `get_journal_entries` in `ledger_service`.

Missing routes:

- Account search/filter metadata if COA routes are insufficient.
- Export account card route if existing export routes do not fit.

Database tables needed:

- No new tables initially.
- Optional saved filter table later.

Tenant isolation rules:

- Ledger query must filter `journal_drafts` and entries by tenant.
- Account drilldown must never expose another tenant's draft/document IDs.

Approval workflow integration:

- Read-only UI links to approval details for non-posted entries when allowed.

Journal draft integration:

- Posted-only mode should be default for statutory ledger.
- Draft-inclusive mode must be explicitly labeled.

Frontend page needed:

- Account card page with account selector, date filters, opening balance, debit turnover, credit turnover, closing balance, and line drilldown.

Tests needed:

- Tenant-scoped account ledger.
- Opening and closing balance calculation.
- Posted-only filter.
- Export shape.

Rollout risk:

- Medium. Account cards are core accountant review surfaces.

Rollback plan:

- Fall back to existing `/reports/ledger/{account_code}` endpoint and disable only the new UI.

### Trial Balance UI

Existing backend routes to reuse:

- `/reports/trial-balance`
- `get_trial_balance` in `ledger_service`.

Missing routes:

- Trial balance export if existing export routes are insufficient.
- Comparative period trial balance route.

Database tables needed:

- No new tables initially.
- Optional report snapshot table only for locked/filed periods.

Tenant isolation rules:

- Trial balance must filter by tenant and date range.
- Cached/snapshotted balances must include tenant_id and period.

Approval workflow integration:

- Read-only. Trial balance can show warnings for unapproved drafts but cannot approve/post.

Journal draft integration:

- Statutory trial balance reads posted entries.
- Management mode may include simulated/approved drafts only with explicit labels.

Frontend page needed:

- Trial balance page with period filters, account grouping, debit/credit totals, imbalance warnings, and export.

Tests needed:

- Total debit equals total credit for balanced posted data.
- Tenant-scoped aggregation.
- Date range filtering.
- Empty period shape.

Rollout risk:

- Medium to high because trial balance is a primary control report.

Rollback plan:

- Keep existing report route and disable new UI/export only.

### Counterparty Card

Existing backend routes to reuse:

- `/reports/counterparty/{inn}`
- `/crm/counterparties`
- `/crm/counterparties/create`
- Document routes for source documents.

Missing routes:

- Counterparty statement export.
- Counterparty reconciliation summary.
- Counterparty aging by open items if aging routes are insufficient.

Database tables needed:

- Reuse `counterparties`, `customers`, invoices, outgoing invoices, and journal entries.
- Add `counterparty_open_items` only if open-item accounting is implemented.

Tenant isolation rules:

- Counterparty INN queries must include tenant.
- Same INN can exist across tenants without data overlap.

Approval workflow integration:

- Read-only card links to source drafts, documents, and approvals.
- Corrections must create drafts through approval.

Journal draft integration:

- Card reads receivable/payable and payment journal entries.
- Draft-inclusive view must separate pending from posted movements.

Frontend page needed:

- Counterparty card page with balances, invoices, payments, documents, aging, and ledger movements.

Tests needed:

- Tenant-scoped counterparty card.
- Same INN across tenants stays isolated.
- Aging totals match ledger lines.
- Document links respect permissions.

Rollout risk:

- Medium. Counterparty balances drive collections and payment decisions.

Rollback plan:

- Keep `/reports/counterparty/{inn}` available and disable new UI.

### Period Closing

Existing backend routes to reuse:

- `/accounting/periods`
- `/accounting/periods/lock`
- `/accounting/periods/unlock`
- `/accounting/close-period/preview`
- `/accounting/close-period`
- Posting period-lock checks.

Missing routes:

- Period close run history.
- Reopen request workflow.
- Close checklist route.
- Close exception report.

Database tables needed:

- Reuse period locks and closing routes where possible.
- Add `period_closing_runs`, `period_closing_checklist_items`, and `period_reopen_requests` only if existing history is insufficient.

Tenant isolation rules:

- Period locks and closing runs must be tenant-scoped.
- Close/reopen permissions must never apply globally.

Approval workflow integration:

- Period close execution should require preview and explicit approval if closing entries create accounting impact.
- Reopening a locked period should be audited and permissioned.

Journal draft integration:

- Closing entries create journal drafts or use existing close flow only after preview.
- No closing entry should bypass approval unless an explicit audited exception is approved.

Frontend page needed:

- Period closing page with checklist, preview, warnings, lock state, close action, and reopen request status.

Tests needed:

- Locked period blocks approve/posting.
- Close preview is read-only.
- Close execution is tenant-scoped.
- Reopen permissions.
- Closing entry balance.

Rollout risk:

- High. Period close controls protect filed financial statements.

Rollback plan:

- Disable close execution and leave locks intact.
- Reverse bad closing drafts through approval before posting.

### VAT Register

Existing backend routes to reuse:

- `/documents/tax-invoices`
- `/documents/waybills`
- `/documents/triangle-matches`
- `/reports/journal`
- `/reports/pnl/detail`
- Tax routes registered in `router_registry`.

Missing routes:

- VAT register list by period.
- VAT input/output detail.
- VAT filing snapshot.
- VAT discrepancy report between documents and journal entries.
- VAT export for Georgian compliance needs.

Database tables needed:

- Reuse `tax_invoices`, `waybills`, `commercial_invoices`, `triangle_matches`, `outgoing_invoices`, and journal entries.
- Add `vat_register_snapshots` and `vat_register_snapshot_lines` only when filing/freeze workflow is implemented.

Tenant isolation rules:

- VAT source documents and register rows must filter by tenant.
- Filing snapshots must be tenant and period scoped.

Approval workflow integration:

- VAT adjustments create journal drafts.
- VAT filing snapshot is approval-controlled if it locks accounting interpretation.

Journal draft integration:

- VAT input/output entries must map to posted journal lines.
- Document-only differences should appear as reconciliation exceptions, not posted entries.

Frontend page needed:

- VAT register page with input VAT, output VAT, document links, journal links, discrepancy warnings, and export.

Tests needed:

- VAT input/output classification.
- Tenant-scoped VAT period report.
- Document-to-journal discrepancy detection.
- Snapshot immutability after filing.
- Georgian VAT rate assumptions covered by tests.

Rollout risk:

- High. VAT errors affect statutory filings.

Rollback plan:

- Disable filing snapshot creation.
- Keep read-only register available.
- Correct VAT adjustment drafts through approval.

