# Bridge Hub Database Schema Inventory

Task 10B records the current schema ownership and migration risk profile without
changing runtime behavior. This is a stabilization manifest, not an executable
migration.

## Scope And Ground Rules

- Source branch: `main`
- Baseline HEAD: `3b5aafa2371fd657c94e386785facc50ed3b93c8`
- Production database was not touched.
- No application runtime code was changed.
- No migration files were created.
- Known allowed untracked path: `.venv.broken-20260507-235411/`

## Migration And Schema Systems Found

| Source | Purpose | Tables affected | Risk |
| --- | --- | --- | --- |
| `app/storage/migrations/001_multi_tenant_schema.sql` | Multi-tenant document/counterparty expansion | `tenants`, `counterparties`, `processed_documents`, `journal_drafts` | Medium |
| `app/storage/migrations/002_row_level_security.sql` | Row-level security policies | `counterparties`, `processed_documents`, `journal_drafts` | High |
| `app/storage/migrations/003_triangle_schema.sql` | Waybill/tax/commercial invoice triangle matching | `waybills`, `tax_invoices`, `commercial_invoices`, `triangle_matches`, `document_corrections` | Medium |
| `app/storage/migrations/004_outgoing_invoices.sql` | Outgoing invoice schema | `outgoing_invoices`, `invoice_counters` | Medium |
| `app/api/migrations/add_draft_comments.sql` | Approval comments and assignment fields | `draft_comments`, `journal_drafts` | Medium |
| `migrations/upgrade_v2.sql` | Journal draft metadata and indexes | `journal_drafts`, `bank_accounts`, `budgets` | Medium |
| `app/startup/migrations.py` | Startup schema patching | `tenants`, `processed_documents`, `journal_drafts`, `learning_patterns`, `customers`, `contracts`, `contract_milestones`, `outgoing_invoices` | High |
| `app/startup/migrations_tables.py` | Startup table creation | `expense_articles`, `expenses`, `invoices`, `invoice_lines`, `comments`, `attachments`, `chat_sessions`, `idempotency_keys`, `search_index`, `bank_reconciliations` | High |
| `app/startup/migrations_indexes.py` | Startup indexes, constraints, and schema patching | `journal_drafts`, `journal_entries`, `posting_logs`, `expenses`, `invoices`, `outgoing_invoices`, `exchange_rates`, audit/search/pipeline tables | High |
| `scripts/run_tenant_tables_migration.py` | Tenant table bootstrap | `tenants`, `tenant_settings`, `tenant_secrets` | High |
| `scripts/run_tenant_migration.py` | Tenant columns and indexes on existing tables | `journal_drafts`, `bank_transactions`, `learning_patterns`, `audit_events`, `posting_logs`, `transaction_memory`, `erp_posting_memory` | Medium |
| `scripts/run_bank_files_migration.py` | Bank file tenant columns | `processed_bank_files`, `journal_drafts`, `bank_transactions`, `posting_logs` | Medium |
| `scripts/run_audit_migration.py` | Audit event tenant column | `audit_events` | Medium |
| `scripts/run_contracts_migration.py` | Contract tenant columns | `contracts`, `contract_milestones` | Medium |
| `scripts/run_learning_tenant_migration.py` | Learning table tenant columns | `learning_feedback`, `learning_patterns`, `transaction_memory`, `erp_posting_memory`, `async_queue` | Medium |
| `scripts/run_learning_pattern_upgrade_migration.py` | Learning pattern score columns | `learning_patterns` | Medium |
| `scripts/run_llm_connectors_migration.py` | LLM/tax support tables and indexes | `tax_rules`, `llm_cost_log`, `journal_drafts`, `learning_patterns` | Medium |
| `scripts/run_users_migration.py` | Users table recreation | `users` | Critical |

## Runtime CREATE/ALTER Sources

These files currently create or alter schema from application or helper code.
They should be treated as compatibility shims until formal migrations replace
them.

| Runtime source | Function or area | Schema affected | Move to formal migration? | Risk |
| --- | --- | --- | --- | --- |
| `main.py` | startup lifecycle | Runs startup migrations and service `ensure_*` calls | Yes | High |
| `app/startup/migrations.py` | `_run_db_migrations` | Broad `ALTER TABLE`, `CREATE TABLE`, and backfills | Yes | High |
| `app/startup/migrations_tables.py` | startup table creation | Core app tables and invoice/expense support | Yes | High |
| `app/startup/migrations_indexes.py` | startup indexes/constraints | Core accounting indexes, constraints, FX fields | Yes | High |
| `app/api/services/inventory_service.py` | `ensure_inventory_tables` | Inventory and purchase order tables | Yes | High |
| `app/api/services/payroll_service.py` | `ensure_payroll_erp_tables` | Payroll run tables | Yes | High |
| `app/api/routes_employee_portal.py` | `_ensure_tables` | Employee and pension transfer tables | Yes | High |
| `app/api/routes_period_lock.py` | period lock table ensure | `period_locks` | Yes | Medium |
| `app/api/services/email_collector.py` | email ingestion table ensure | `tenant_email_credentials`, `email_documents` | Yes | High |
| `app/api/services/balance_credentials_service.py` | `ensure_table` | `tenant_balance_credentials` | Yes | High |
| `app/api/services/tenant_config_service.py` | tenant settings ensure | `tenant_settings` | Yes | Medium |
| `app/api/services/webhook_service.py` | webhook table ensure | `webhooks`, `webhook_deliveries` | Yes | Medium |
| `app/api/services/invoice_creator.py` | outgoing invoice ALTER | `outgoing_invoices` | Yes | Medium |
| `app/api/services/reconciliation_service.py` | reconciliation ALTER | `journal_drafts` | Yes | Medium |
| `app/api/services/totp_service.py` | TOTP ALTER | `users` | Yes | High |

## Table Ownership By Module

### Core Tenant/Auth/Settings

| Table | Owner module | Current creation source | Tenant ID | Indexes | Audit fields | FK gaps | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `tenants` | Tenant/auth | `scripts/run_tenant_tables_migration.py`, `app/startup/migrations.py`, storage SQL alters | Partial/self | Partial | Partial | N/A | High | Canonicalize once in formal migration |
| `tenant_settings` | Tenant config | script and runtime service ensure | Yes | Partial | Partial | Missing tenant FK | Medium | Merge duplicate definitions |
| `tenant_secrets` | Tenant credentials | `scripts/run_tenant_tables_migration.py` | Yes | Partial | Partial | Missing tenant FK | High | Review encryption and access controls |
| `users` | Auth | `scripts/run_users_migration.py`, `totp_service.py` ALTER | Unknown/partial | Unknown | Partial | Tenant/user role links unclear | Critical | Quarantine destructive script |

### Approval, Posting, And Ledger Truth

| Table | Owner module | Current creation source | Tenant ID | Indexes | Audit fields | FK gaps | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `journal_drafts` | Approval/accounting | Base schema plus many SQL/startup/script ALTERs | Yes | Partial/good | Partial | Source document links partial | High | Freeze canonical draft schema |
| `draft_comments` | Approval | `app/api/migrations/add_draft_comments.sql` | Yes | Yes | Created only | `draft_id` FK exists | Medium | Add to ordered migration chain |
| `posting_logs` | Posting/audit | scripts and startup ALTER/indexes | Yes | Partial | Partial | Draft FK partial/unclear | High | Canonicalize with posting idempotency fields |
| `journal_entries` | Posted ledger | startup ALTER/indexes | Yes | Partial | Partial | Draft/source FK partial | High | Formalize posted-ledger schema and indexes |
| `audit_events` / `audit_log` | Audit | scripts/startup indexes | Partial | Partial | Partial | Tenant FK absent | Medium | Normalize table naming and tenant indexes |

### Documents, OCR, And Triangle Matching

| Table | Owner module | Current creation source | Tenant ID | Indexes | Audit fields | FK gaps | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `processed_documents` | Documents/OCR | `001_multi_tenant_schema.sql`, startup ALTERs | Yes | Yes | Partial | Source links partial | Medium | Keep in formal chain, remove startup ALTERs later |
| `counterparties` | Documents/CRM reference | `001_multi_tenant_schema.sql` | Yes | Yes | Partial | Tenant FK absent | Medium | Confirm relation to `customers` |
| `waybills` | Georgian documents | `003_triangle_schema.sql` | Yes | Yes | Partial | Cross-doc FKs partial | Medium | Keep formal migration |
| `tax_invoices` | Georgian documents/VAT | `003_triangle_schema.sql` | Yes | Yes | Partial | Cross-doc FKs partial | Medium | Keep formal migration |
| `commercial_invoices` | Georgian documents | `003_triangle_schema.sql` | Yes | Yes | Partial | Cross-doc FKs partial | Medium | Keep formal migration |
| `triangle_matches` | Document matching | `003_triangle_schema.sql` | Yes | Yes | Partial | Document FKs present/partial | Medium | Keep formal migration |
| `document_corrections` | Document corrections | `003_triangle_schema.sql` | Yes | Yes | Partial | Polymorphic doc link | Medium | Review FK strategy |

### Inventory And Purchases

| Table | Owner module | Current creation source | Tenant ID | Indexes | Audit fields | FK gaps | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `inventory_categories` | Inventory | Runtime `inventory_service.py` | Yes | Unknown/partial | Created only | Tenant FK absent | High | Move to ordered ERP migration |
| `warehouses` | Inventory | Runtime `inventory_service.py` | Yes | Unknown/partial | Created only | Tenant FK absent | High | Move to ordered ERP migration |
| `inventory_items` | Inventory | Runtime `inventory_service.py` | Yes | Yes | Partial | Category FK partial/warehouse relation unclear | High | Move to ordered ERP migration |
| `stock_movements` | Inventory | Runtime `inventory_service.py` | Yes | Yes | Partial | Item FK exists/partial | High | Move to ordered ERP migration |
| `purchase_orders` | Inventory/trade | Runtime `inventory_service.py` | Yes | Yes | Partial | Supplier FK absent | High | Move to ordered ERP migration |
| `purchase_order_lines` | Inventory/trade | Runtime `inventory_service.py` | Via order plus own tenant | Partial | Created only | PO FK exists, item FK partial | High | Move to ordered ERP migration |

### Payroll

| Table | Owner module | Current creation source | Tenant ID | Indexes | Audit fields | FK gaps | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `employees` | Employee/payroll | Runtime `routes_employee_portal.py` | Yes | Unique tenant/person only | Created only | Tenant FK absent | High | Move to ordered payroll migration |
| `pension_transfers` | Payroll compliance | Runtime `routes_employee_portal.py` | Yes | Unknown | Created only | Tenant FK absent | High | Move to ordered payroll migration |
| `payroll_runs` | Payroll ERP | Runtime `payroll_service.py` | Yes | Unknown/partial | Created/updated | Tenant FK absent | High | Move to ordered payroll migration |
| `payroll_run_lines` | Payroll ERP | Runtime `payroll_service.py` | Yes | Unknown/partial | Created only | Run FK exists, employee FK soft | High | Move to ordered payroll migration |

### Trade And Sales

| Table | Owner module | Current creation source | Tenant ID | Indexes | Audit fields | FK gaps | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `customers` | CRM/trade | Runtime startup migration | Yes | Yes | Partial | Tenant FK absent | High | Move to ordered trade migration |
| `customer_interactions` | CRM | Runtime startup migration | Yes | Unknown/partial | Partial | Customer FK unclear | Medium | Move to ordered migration |
| `outgoing_invoices` | Sales invoices | `004_outgoing_invoices.sql` plus runtime ALTERs | Yes | Yes | Partial | Customer FK absent | Medium | Consolidate schema definition |
| `invoice_counters` | Sales invoices | `004_outgoing_invoices.sql` | Yes | Partial | Unknown/partial | Tenant FK absent | Medium | Keep in formal chain |
| `invoices` | Legacy invoice/reporting | Runtime startup tables | Yes | Partial | Partial | Customer FK absent | High | Clarify relation to outgoing invoices |
| `invoice_lines` | Legacy invoice lines | Runtime startup tables | Via invoice/partial | Unknown | Partial | Invoice FK expected | High | Clarify canonical invoice model |

### Reporting, Tax, Closing, And FX

| Table | Owner module | Current creation source | Tenant ID | Indexes | Audit fields | FK gaps | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `period_locks` | Period closing | Runtime `routes_period_lock.py` | Yes | Unknown/partial | Partial | Tenant FK absent | Medium | Move to formal migration |
| `tax_rules` | Tax/LLM support | `scripts/run_llm_connectors_migration.py` | Unknown/partial | Unknown | Unknown | N/A | Medium | Add to formal chain if used |
| `exchange_rates` | FX | Startup ALTER/indexes | No/unknown | Yes | Partial | N/A | Medium | Canonicalize FX schema |
| `bank_accounts` | Bank/accounting | Root migration indexes | Yes | Partial | Unknown | Tenant FK absent | Medium | Confirm base creation source |
| `budgets` | Reporting | Root migration indexes | Yes | Partial | Unknown | Tenant FK absent | Medium | Confirm base creation source |

### Bank, Email, Connectors, And Webhooks

| Table | Owner module | Current creation source | Tenant ID | Indexes | Audit fields | FK gaps | Risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `processed_bank_files` | Bank ingestion | Existing base plus script tenant ALTER | Yes | Partial | Partial | Tenant FK absent | Medium | Formalize base schema |
| `bank_transactions` | Bank/reconciliation | Existing base plus scripts/startup indexes | Yes | Partial | Partial | Account FK partial | Medium | Formalize indexes and tenant fields |
| `bank_reconciliations` | Reconciliation | Runtime startup tables | Yes | Yes | Partial | Bank/journal FKs unclear | High | Move to formal migration |
| `tenant_email_credentials` | Email ingestion credentials | Runtime `email_collector.py` | Yes | Unknown | Partial | Tenant FK absent | High | Formal migration plus security review |
| `email_documents` | Email ingestion | Runtime `email_collector.py` | Yes | Unknown | Partial | Credential/source FK unclear | High | Move to formal migration |
| `tenant_balance_credentials` | Balance connector credentials | Runtime `balance_credentials_service.py` | Yes | Unknown | Partial | Tenant FK absent | High | Formal migration plus secret review |
| `webhooks` | Integrations | Runtime `webhook_service.py` | Yes | Yes | Partial | Tenant FK absent | Medium | Move to formal migration |
| `webhook_deliveries` | Integrations | Runtime `webhook_service.py` | Via webhook/partial | Unknown | Partial | Webhook FK expected | Medium | Move to formal migration |
| `llm_cost_log` | AI/connector metering | `scripts/run_llm_connectors_migration.py` | Unknown/partial | Unknown | Partial | Tenant FK should be confirmed | Medium | Add to canonical map |

## Foreign Key And Audit Gaps

- Tenant-owned tables usually store `tenant_id`, but most do not enforce a
  foreign key to `tenants`.
- ERP tables often use soft references instead of FK constraints for
  counterparties, employees, and source documents.
- Audit columns are inconsistent: many tables have `created_at`, fewer have
  `updated_at`, `created_by`, `updated_by`, or immutable audit event links.
- Credential tables need explicit review for encryption, rotation, and access
  auditing before pilot use.

## Highest Risk Areas

1. `users` because `scripts/run_users_migration.py` contains destructive table
   recreation.
2. Accounting core: `journal_drafts`, `journal_entries`, `posting_logs`.
3. Runtime-created ERP schemas: inventory, payroll, employees, period locks.
4. Credential tables: Balance, email, tenant secrets.
5. Startup migration chain because it mutates schema during application boot.

## Tables That Should Move To Formal Migrations

All runtime-created or runtime-altered tables should be moved to formal ordered
migrations before pilot use. Highest priority:

1. `journal_drafts`, `journal_entries`, `posting_logs`, `audit_events`.
2. `users`, `tenants`, `tenant_settings`, `tenant_secrets`.
3. Inventory and purchase order tables.
4. Payroll and employee tables.
5. Credential and connector tables.
6. Reporting support tables such as `period_locks`, `exchange_rates`, and bank
   reconciliation tables.
