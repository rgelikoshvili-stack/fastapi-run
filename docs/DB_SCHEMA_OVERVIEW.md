# Bridge Hub - DB Schema Overview

This document is a compact orientation map, not a full DDL dump. The runtime source of truth is the startup migration code in `app/startup/migrations.py`, route-local `CREATE TABLE IF NOT EXISTS` statements, and SQL migrations under `migrations/` when present.

## Core Principles

- Every tenant-owned table must carry `tenant_id` and every route/service query must scope by `tenant_id`.
- Financial reports should use posted ledger state unless the endpoint is explicitly labelled as draft or pending.
- Posting attempts are append-only in `posting_logs`; do not infer ERP success from `journal_drafts.status` alone.
- Period locks are enforced before approval/posting paths that affect financial state.
- Configurable tenant business rules live in `tenant_settings`; defaults stay in code as safe fallbacks.

## High-Value Tables

| Table | Purpose | Important columns / notes |
|---|---|---|
| `pipeline_runs` | Document ingestion and OCR/AI processing history. | `tenant_id`, `created_at`, state/status fields, document metadata. Report queries must filter by `tenant_id`. |
| `journal_drafts` | Main accounting draft table. Holds AI/human-classified transactions before and after approval/posting. | `tenant_id`, `status`, `amount`, `date`, `description`, `partner`, `currency`, `account_code`, `debit_account`, `credit_account`, `lines_json`, `confidence`, `classification_source`, `pattern_matched_on`. |
| `posting_logs` | Immutable-ish audit trail of ERP connector attempts. | `tenant_id`, `draft_id`, `target_system`, `status`, `response_json`, `error_message`, `entry_hash`, `source_draft_id`. `entry_hash` is used for idempotency. |
| `period_locks` | Accounting period close/lock guard. | `tenant_id`, `period_year`, `period_month`, `locked_by`, `locked_at`, `unlocked_at`. Month `0` means whole year. |
| `tenant_settings` | Per-tenant JSON config key-value store. | `tenant_id`, `key`, `value_json`, `created_at`, `updated_at`. Example key: `approval.cfo_threshold_gel`. |
| `bank_transactions` | Bank feed/imported transaction rows. | `tenant_id`, transaction date/amount/description/account metadata. Hot paths need tenant/date indexes. |
| `bank_accounts` | Tenant bank account records. | `tenant_id`, account identifiers, balances/status. Avoid `tenant_id::text` casts so indexes work. |
| `budgets` | Budget planning/actual comparison. | `tenant_id`, period/account/category amounts. Avoid `tenant_id::text` casts. |
| `audit_log` / entity audit tables | Operational and entity change history. | Include actor/user/tenant context where available. Never log secrets or bearer tokens. |
| `password_reset_tokens` | Password reset flow state. | Token storage must be scoped, expiring, and never logged. |

## Status Meanings

### `journal_drafts.status`

| Status | Meaning |
|---|---|
| `drafted`, `pending_approval`, `pending_human_review` | Draft state; not ledger truth. |
| `auto_approved` | AI confidence passed threshold but not posted; do not include in P&L ledger reports. |
| `approved` | Human-approved draft, eligible for posting. |
| `awaiting_cfo` | First approval complete; amount exceeds tenant CFO threshold. |
| `posted` | Posted to external or internal ledger state; use for financial statements. |
| `simulated_success` | Mock/simulated posting success used by tests/dev paths; allowed in some drill-down endpoints where explicitly intended. |
| `rejected` | Human/system rejected. |

### `posting_logs.status`

| Status | Meaning |
|---|---|
| `posted` | Connector reported success. |
| `simulated_success` | Mock connector success. |
| `failed` | Connector attempted and failed. |
| `config_missing` | Connector was not ready/configured; draft must not be marked posted. |

## Tenant Settings

`tenant_settings` stores JSON values by key.

Current keys:

| Key | Default | Used by |
|---|---:|---|
| `approval.cfo_threshold_gel` | `10000.0` | `approval_service.approve_draft_service` dual-approval gate. |

Read settings via `app/api/services/tenant_config_service.py`:

- `get_tenant_setting(tenant_id, key, default)` returns the stored JSON value or `default` on missing/invalid/DB error.
- `set_tenant_setting(tenant_id, key, value)` performs an upsert.
- `ensure_tenant_settings_table(conn)` is called from startup migrations.

## Required Index Patterns

These are the patterns that matter most for current hot paths:

- `pipeline_runs(tenant_id, created_at)` for reports/audit summaries.
- `bank_transactions(tenant_id, created_at)` for dashboard/report windows.
- `journal_drafts(tenant_id, status, created_at)` for approval queue and posting eligibility.
- `posting_logs(tenant_id, draft_id, target_system, status)` for idempotency and posting history.
- Partial unique/idempotency support on `posting_logs(entry_hash)` where `entry_hash IS NOT NULL`.

## Query Safety Checklist

Before adding/changing SQL:

- Include `tenant_id = ...` for tenant-owned tables.
- Do not use `tenant_id::text = ...` on hot paths; it can prevent index use.
- Use `FOR UPDATE NOWAIT` around approval/posting state transitions to avoid races.
- Keep period-lock checks before state changes that approve/post financial records.
- Use `status = 'posted'` for ledger truth unless the endpoint intentionally includes simulated/draft data.
- Never return `SELECT *` from public APIs when only a few fields are needed.

## Where DDL Lives

- Startup migration orchestration: `app/startup/migrations.py`
- Tenant settings helper/table creation: `app/api/services/tenant_config_service.py`
- Period-lock table setup: `app/api/routes_period_lock.py`
- Route-local legacy table setup still exists in a few routes and should be moved into centralized migrations over time.
