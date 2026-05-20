# Bridge Hub — Migration 011 Production Execution Plan

**Task:** 11C-H68
**Type:** Production migration execution plan — docs only. No SQL executed in this task.
**Date:** 2026-05-20
**Branch:** codex/h68-migration-011-production-execution-plan
**Follows:** 11C-H67 `docs/report-mismatch-recheck-after-schema-fix-h67.md`

---

## 1. Purpose

H67 confirmed that `journal_entry_lines`, `journal_entry_headers`, and
`journal_entry_sources` are absent from the production database because
migration 011 has never been executed against production.

This document defines the controlled plan for executing migration 011 in production
once all prerequisites are satisfied. **No SQL is executed in this task (H68).**

---

## 2. H67 Root Cause

| Field | Value |
|---|---|
| H67 decision | `H67_BLOCKED_POSTED_LEDGER_SCHEMA_MISSING` |
| Missing tables | `journal_entry_headers`, `journal_entry_lines`, `journal_entry_sources` |
| Root cause | Migration 011 created in H4 but never run against production DB |
| Current behavior | `/reports/trial-balance` and `/reports/balance-sheet` return `POSTED_LEDGER_UNAVAILABLE` |
| No 5xx | Confirmed — app handles missing schema gracefully |
| Rollback triggered in H67 | No |

---

## 3. Migration 011 Identity

| Field | Value |
|---|---|
| File path | `app/storage/migrations/011_posted_journal_entries_schema.sql` |
| SHA-256 | `3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0` |
| File size | 15,999 bytes |
| Last modified by | Task 11C-H66 (added account_type/cashflow_category columns) |
| Original created by | Task 11C-H4 |

---

## 4. Migration 011 Review: MIGRATION_011_REVIEW_PASS_ADDITIVE

### 4.1 Tables Created

| Table | Statement |
|---|---|
| `journal_entry_headers` | `CREATE TABLE IF NOT EXISTS` |
| `journal_entry_lines` | `CREATE TABLE IF NOT EXISTS` |
| `journal_entry_sources` | `CREATE TABLE IF NOT EXISTS` |

### 4.2 Indexes Created (all idempotent)

**journal_entry_headers (7):**
`idx_jeh_tenant`, `idx_jeh_tenant_period`, `idx_jeh_tenant_entry_date`,
`idx_jeh_tenant_status`, `idx_jeh_tenant_source_draft`, `idx_jeh_tenant_posting_log`,
`idx_jeh_tenant_evidence_bundle`

**journal_entry_lines (8, including H66 additions):**
`idx_jel_tenant`, `idx_jel_tenant_journal_entry`, `idx_jel_tenant_account_code`,
`idx_jel_tenant_counterparty`, `idx_jel_tenant_document`, `idx_jel_tenant_bank_transaction`,
`idx_jel_tenant_account_type`, `idx_jel_tenant_cashflow_category`

**journal_entry_sources (1):**
`idx_jes_tenant_journal_entry`

### 4.3 Tenant Isolation

All three tables have `tenant_id TEXT NOT NULL` and `CHECK (tenant_id <> '')`.
All indexes include `tenant_id` as the leading column.

### 4.4 Accounting Invariants

`journal_entry_headers` enforces:
- `CHECK (status IN ('posted','reversed','correction','voided'))` — no draft/simulated states
- `CHECK (total_debit = total_credit)` — double-entry balance invariant
- `CHECK (total_debit >= 0)` and `CHECK (total_credit >= 0)`

`journal_entry_lines` enforces:
- `CHECK (debit > 0 OR credit > 0)` — no zero lines
- `CHECK (NOT (debit > 0 AND credit > 0))` — single-side per line
- `UNIQUE (journal_entry_id, line_no)` — no duplicate line numbers

### 4.5 Foreign Keys

- `journal_entry_lines.journal_entry_id` → `journal_entry_headers(id) ON DELETE CASCADE`
- `journal_entry_sources.journal_entry_id` → `journal_entry_headers(id) ON DELETE CASCADE`

### 4.6 Destructive SQL Scan

| Pattern | Found |
|---|---|
| `DROP TABLE` | Not found |
| `TRUNCATE` | Not found |
| `DELETE FROM` | Not found (ON DELETE CASCADE is a FK constraint, not a DML statement) |
| `UPDATE … SET` | Not found |
| `INSERT INTO` | Not found |
| `ALTER TABLE … DROP COLUMN` | Not found |
| `ALTER TABLE … DROP CONSTRAINT` | Not found |

**Decision: MIGRATION_011_REVIEW_PASS_ADDITIVE**

---

## 5. Pre-execution Checklist

All items must be confirmed BEFORE H69 production execution begins.

### 5.1 Backup and PITR

| Item | Required | Status |
|---|---|---|
| Automated backup confirmed available | Yes | PENDING |
| PITR restore point before execution identified | Yes | PENDING |
| Restore point timestamp documented | Yes | PENDING |
| Restore test on staging completed | Recommended | PENDING |
| Backup owner identified | Yes | PENDING |

### 5.2 Staging / Disposable Dry-Run

| Item | Required | Status |
|---|---|---|
| Disposable DB or staging clone created | Yes | PENDING |
| Migration 011 applied on staging | Yes | PENDING |
| Tables verified on staging | Yes | PENDING |
| Indexes verified on staging | Yes | PENDING |
| App startup verified on staging | Yes | PENDING |
| Report endpoints verified on staging | Yes | PENDING |
| Staging DB cleaned up | Yes | PENDING |

### 5.3 Personnel

| Role | Required | Identified |
|---|---|---|
| Engineering owner | Yes | PENDING |
| Accounting owner | Yes | PENDING |
| Rollback owner | Yes | PENDING |
| Monitoring owner | Yes | PENDING |

### 5.4 Window

| Item | Required | Status |
|---|---|---|
| Maintenance window confirmed | Yes | PENDING |
| Traffic is low during window | Recommended | PENDING |
| No concurrent deployments during window | Yes | PENDING |

---

## 6. Execution Command Template

The execution command template is defined below. **Credentials must never be
committed or logged.** The exact `DATABASE_URL` value must be sourced from the
secure vault or Cloud Run secret at execution time only, not stored in any file.

```
# Template only — DO NOT run in H68
# Replace [REDACTED_DATABASE_URL] with the actual value from the secure vault
# at execution time only
psql "[REDACTED_DATABASE_URL]" \
  -f app/storage/migrations/011_posted_journal_entries_schema.sql \
  -v ON_ERROR_STOP=1

# Verify execution:
psql "[REDACTED_DATABASE_URL]" -c \
  "SELECT table_name FROM information_schema.tables WHERE table_name IN
   ('journal_entry_headers','journal_entry_lines','journal_entry_sources')
   ORDER BY table_name;"
```

**This template must be executed by H69 after all prerequisites are met.**
**Do NOT execute this command in H68.**

---

## 7. Post-Execution Verification Plan (for H69)

After production execution, H69 must verify:

| Check | Method | Expected |
|---|---|---|
| `/version` | HTTP GET | 200, H68+ SHA |
| `/health` | HTTP GET | 200, no crash |
| Unauthenticated report endpoints | HTTP GET | 401 — no auth bypass |
| `/reports/trial-balance` (authenticated) | HTTP GET | No `journal_entry_lines` error |
| `/reports/balance-sheet` (authenticated) | HTTP GET | No missing-table error |
| Tables exist | Safe read-only DB query or `/health` inference | confirmed |
| No 5xx | All endpoints | Zero |
| Balance.ge | `/health` | `demo_mode` |
| No write/apply endpoints | Confirmed | No write calls |
| H67 recheck | Re-run report mismatch check | Upgraded classification |

---

## 8. Execution Decision Gate

Migration 011 production execution (H69) is BLOCKED until:

1. `BACKUP_PREREQUISITES_READY` — confirmed
2. `DRY_RUN_ALREADY_PASSED_WITH_EVIDENCE` — staging dry-run complete
3. `APPROVAL_PACKET_SIGNED` — all approvers confirmed
4. Maintenance window confirmed
5. No concurrent deployments during window

**H68 decision: APPROVAL_READY_FOR_SIGNATURE_AFTER_BACKUP_AND_DRY_RUN**

---

## 9. Safety

| Safety Item | Status |
|---|---|
| No production SQL executed in H68 | Confirmed |
| No direct DB connection in H68 | Confirmed |
| No migration run in H68 | Confirmed |
| No Cloud Run mutation in H68 | Confirmed |
| No Balance.ge activation | Confirmed |
| No write or apply endpoints called | Confirmed |
| No credentials in this doc | Confirmed |
| H69 not started | Confirmed |

---

*Bridge Hub — Task 11C-H68. Migration 011 production execution plan prepared.
No SQL executed. Docs only. All prerequisites PENDING human confirmation.*
