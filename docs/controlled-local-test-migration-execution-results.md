# Bridge Hub — Controlled Local/Test Migration Execution Results

**Task:** 11C-H12
**Type:** Controlled local/test migration execution — results and verification record.
**Date:** 2026-05-14
**Follows:** 11C-H11 `docs/controlled-local-test-migration-execution-plan.md`

---

## 1. Purpose

This document records the H12 execution attempt of
`app/storage/migrations/011_posted_journal_entries_schema.sql` against a disposable
local/test database, as specified in the H11 execution plan.

H12 confirms:
- All preflight checks passed.
- Migration SQL was statically verified as additive-only.
- Production DB was not touched.
- Execution was attempted only against a disposable local/test database.
- H12 verdict: **BLOCKED** — no disposable local/test PostgreSQL instance was
  available in the execution environment. Production was never used as a substitute.

---

## 2. Safety Scope

This task explicitly confirms:

- **Production DB was not touched.** No connection to production was made.
- **Cloud Run DB was not touched.** No Cloud Run production database was accessed.
- **No production DATABASE_URL used.** DATABASE_URL was empty during execution.
- **No credentials changed.** No API keys, passwords, or secrets were modified.
- **Balance.ge not activated.** BALANCE_API_KEY remains missing. Connector remains demo_mode.
- **No runtime report behavior changed.** financial_statements_service, ledger_service,
  and routes_reports are unchanged.
- **No posting behavior changed.** posting_service.py is unchanged.
- **No approval logic changed.** approval_service.py is unchanged.
- **No connector behavior changed.**
- **No infrastructure changed.**
- **H13 not started.**

---

## 3. Preflight Results

### 3.1 Git state

| Field | Value |
|---|---|
| Branch | `codex/controlled-local-test-migration-execution` |
| Starting main HEAD | `c06c529c6077255581928233099f9a97e15b7f1f` |
| Previous live verified SHA (H11) | `c06c529c6077255581928233099f9a97e15b7f1f` |
| Branch base confirmed | Yes — branched from latest verified main |

### 3.2 Migration file

| Field | Value |
|---|---|
| Migration path | `app/storage/migrations/011_posted_journal_entries_schema.sql` |
| File exists | Yes |
| SHA-256 checksum | `f552e49703b164ff03656ef09f223f4a3292636423c529890849b06c648af9ba` |
| Matches H4-committed file | Yes — file content unchanged since H4 |

### 3.3 DATABASE_URL classification

| Field | Value |
|---|---|
| DATABASE_URL present | No — empty string |
| DATABASE_URL danger check | No production identifiers found |
| Production guard result | **PASSED** — DATABASE_URL is empty/absent |
| Connection attempted | No |
| Classification | Absent (safe — execution correctly blocked by missing PostgreSQL) |

Danger keywords checked: `production`, `prod`, `cloudsql`, `google`, `run.app` — none matched.

### 3.4 Additive-only validation

Static analysis of migration SQL text:

| Check | Result |
|---|---|
| `DROP` statement | Not found |
| `DELETE` DML statement | Not found — `delete` appears only as `ON DELETE CASCADE` (FK constraint) and in a COMMENT string — not a DML statement |
| `UPDATE` statement | Not found |
| `TRUNCATE` statement | Not found |
| `INSERT INTO journal_drafts` | Not found |
| `ALTER TABLE journal_drafts` | Not found |
| `CREATE TABLE IF NOT EXISTS journal_entry_headers` | Found (1) |
| `CREATE TABLE IF NOT EXISTS journal_entry_lines` | Found (1) |
| `CREATE TABLE IF NOT EXISTS journal_entry_sources` | Found (1) |
| `CREATE INDEX IF NOT EXISTS` | Found (14) |
| Additive-only validation | **PASSED** |

### 3.5 Balance.ge and credentials

| Check | Result |
|---|---|
| Balance.ge activation in migration | Not found |
| Credentials or secrets in migration | Not found |
| Migration touches journal_drafts | Not found |

---

## 4. Execution Results

### 4.1 PostgreSQL availability

| Field | Value |
|---|---|
| PostgreSQL available locally | **No** |
| `psql` command found | Not found — not installed in environment |
| `pg_isready` command found | Not found — not installed in environment |
| `createdb` command found | Not found — not installed in environment |

### 4.2 Disposition

Per the H11 execution plan (section 4 rule: "Local/test DB only") and the H12 task
specification:

> If PostgreSQL is unavailable, mark H12 as BLOCKED by missing disposable
> local/test PostgreSQL and do not substitute production.

This environment does not have a local PostgreSQL installation. **Production was not
used as a substitute.** No connection to any database was attempted.

### 4.3 Execution results

| Step | Result |
|---|---|
| Create disposable DB (`bridge_hub_h12_test`) | Not executed — PostgreSQL unavailable |
| First migration run | Not executed — PostgreSQL unavailable |
| Second migration run (idempotency) | Not executed — PostgreSQL unavailable |
| Table inspection | Not executed — PostgreSQL unavailable |
| Constraint inspection | Not executed — PostgreSQL unavailable |
| Index inspection | Not executed — PostgreSQL unavailable |
| Synthetic rows inserted | No |
| Disposable DB dropped | N/A — never created |

### 4.4 H12 verdict

**BLOCKED** — no disposable local/test PostgreSQL available in execution environment.
Production was not used. Safety was maintained.

---

## 5. Schema Objects Verified (Static Analysis)

Although live execution was blocked, the migration SQL was fully inspected statically.
The following objects are defined in `011_posted_journal_entries_schema.sql`:

### 5.1 Tables

| Table | Status |
|---|---|
| `journal_entry_headers` | Defined — `CREATE TABLE IF NOT EXISTS` |
| `journal_entry_lines` | Defined — `CREATE TABLE IF NOT EXISTS` |
| `journal_entry_sources` | Defined — `CREATE TABLE IF NOT EXISTS` |

### 5.2 Comments

| Object | Comment present |
|---|---|
| `COMMENT ON TABLE journal_entry_headers` | Yes |
| `COMMENT ON TABLE journal_entry_lines` | Yes |
| `COMMENT ON TABLE journal_entry_sources` | Yes |
| Column comments on `journal_entry_headers` | Yes (status, total_debit, total_credit, source_draft_id, posting_log_id, evidence_bundle_id, reversed_by_entry_id, correction_of_entry_id, metadata_json) |
| Column comments on `journal_entry_lines` | Yes (journal_entry_id, line_hash, debit, credit) |

---

## 6. Constraints Verified (Static Analysis)

| Constraint | Table | Rule |
|---|---|---|
| `ck_jeh_tenant_nonempty` | `journal_entry_headers` | `tenant_id <> ''` |
| `ck_jeh_status` | `journal_entry_headers` | `status IN ('posted','reversed','correction','voided')` |
| `ck_jeh_source_type_nonempty` | `journal_entry_headers` | `source_type <> ''` |
| `ck_jeh_period_nonempty` | `journal_entry_headers` | `period <> ''` |
| `ck_jeh_currency_nonempty` | `journal_entry_headers` | `currency <> ''` |
| `ck_jeh_total_debit_nonneg` | `journal_entry_headers` | `total_debit >= 0` |
| `ck_jeh_total_credit_nonneg` | `journal_entry_headers` | `total_credit >= 0` |
| `ck_jeh_balanced` | `journal_entry_headers` | `total_debit = total_credit` |
| `ck_jel_tenant_nonempty` | `journal_entry_lines` | `tenant_id <> ''` |
| `ck_jel_account_nonempty` | `journal_entry_lines` | `account_code <> ''` |
| `ck_jel_debit_nonneg` | `journal_entry_lines` | `debit >= 0` |
| `ck_jel_credit_nonneg` | `journal_entry_lines` | `credit >= 0` |
| `ck_jel_nonzero` | `journal_entry_lines` | `debit > 0 OR credit > 0` |
| `ck_jel_not_both_positive` | `journal_entry_lines` | `NOT (debit > 0 AND credit > 0)` |
| `uq_jel_line_no` | `journal_entry_lines` | `UNIQUE (journal_entry_id, line_no)` |
| FK `journal_entry_lines.journal_entry_id` | `journal_entry_lines` | `REFERENCES journal_entry_headers(id) ON DELETE CASCADE` |
| `ck_jes_tenant_nonempty` | `journal_entry_sources` | `tenant_id <> ''` |
| `ck_jes_source_type_nonempty` | `journal_entry_sources` | `source_type <> ''` |
| `ck_jes_source_id_nonempty` | `journal_entry_sources` | `source_id <> ''` |
| FK `journal_entry_sources.journal_entry_id` | `journal_entry_sources` | `REFERENCES journal_entry_headers(id) ON DELETE CASCADE` |

**Confirmed**: `draft`, `approved`, `auto_approved`, `simulated_success`, `mock_posting`,
`dry_run` are all absent from the `status` CHECK constraint — only final confirmed states
`posted`, `reversed`, `correction`, `voided` are allowed.

---

## 7. Indexes Verified (Static Analysis)

All 14 indexes defined with `CREATE INDEX IF NOT EXISTS` (idempotent):

### journal_entry_headers (7 indexes)

| Index | Columns / Condition |
|---|---|
| `idx_jeh_tenant` | `(tenant_id)` |
| `idx_jeh_tenant_period` | `(tenant_id, period)` |
| `idx_jeh_tenant_entry_date` | `(tenant_id, entry_date)` |
| `idx_jeh_tenant_status` | `(tenant_id, status) WHERE status = 'posted'` |
| `idx_jeh_tenant_source_draft` | `(tenant_id, source_draft_id) WHERE source_draft_id IS NOT NULL` |
| `idx_jeh_tenant_posting_log` | `(tenant_id, posting_log_id) WHERE posting_log_id IS NOT NULL` |
| `idx_jeh_tenant_evidence_bundle` | `(tenant_id, evidence_bundle_id) WHERE evidence_bundle_id IS NOT NULL` |

### journal_entry_lines (6 indexes)

| Index | Columns / Condition |
|---|---|
| `idx_jel_tenant` | `(tenant_id)` |
| `idx_jel_tenant_journal_entry` | `(tenant_id, journal_entry_id)` |
| `idx_jel_tenant_account_code` | `(tenant_id, account_code)` |
| `idx_jel_tenant_counterparty` | `(tenant_id, counterparty_id) WHERE counterparty_id IS NOT NULL` |
| `idx_jel_tenant_document` | `(tenant_id, document_id) WHERE document_id IS NOT NULL` |
| `idx_jel_tenant_bank_transaction` | `(tenant_id, bank_transaction_id) WHERE bank_transaction_id IS NOT NULL` |

### journal_entry_sources (1 index)

| Index | Columns / Condition |
|---|---|
| `idx_jes_tenant_journal_entry` | `(tenant_id, journal_entry_id)` |

---

## 8. Journal Drafts / Backfill Safety

| Check | Result |
|---|---|
| `journal_drafts` referenced in migration DDL | No |
| `INSERT INTO journal_drafts` | Not found |
| `ALTER TABLE journal_drafts` | Not found |
| Any existing table mutated | No — migration creates only new tables |
| Data backfill executed | No — no `INSERT` or `UPDATE` statements in migration |
| `journal_drafts` JSONB untouched | Confirmed |

---

## 9. Result

**H12 Verdict: BLOCKED**

Reason: No disposable local/test PostgreSQL instance was available in the execution
environment (`psql`, `pg_isready`, and `createdb` commands not found). Production
was not used as a substitute, as required by the H11 execution plan safety rules.

All preflight checks passed. Static analysis of the migration file confirms it is
fully additive-only and structurally sound. When a local/test PostgreSQL instance
becomes available, H12 execution can proceed against a disposable DB following the
H11 plan exactly.

**No production DB was touched. No connection to any database was made. Safety maintained.**

---

## 10. Non-Goals Confirmed

This task explicitly did **not**:

- Connect to the production database.
- Connect to the Cloud Run production database.
- Use a production DATABASE_URL.
- Execute SQL against any production instance.
- Execute `011_posted_journal_entries_schema.sql` against production.
- Change runtime report behavior (`financial_statements_service`, `ledger_service`).
- Change posting behavior (`posting_service.py`).
- Change approval logic (`approval_service.py`).
- Activate Balance.ge or change `BALANCE_API_KEY`.
- Change any credentials or secrets.
- Change any connector behavior.
- Change any production infrastructure or deployment configuration.
- Add `011_posted_journal_entries_schema.sql` to the automatic startup migration list.
- Start H13 work.

This task produces two files only:
- `docs/controlled-local-test-migration-execution-results.md` (this document)
- `tests/unit/test_controlled_local_test_migration_execution_results_contract.py`

---

## 11. Next Task

After this PR is merged, deployed, and live-verified:

**11C-H13 — Runtime Report Migration Plan / Tests**

Define how `financial_statements_service` and `ledger_service` must be migrated to read
from `journal_entry_headers` + `journal_entry_lines` after a successful H12 execution is
confirmed (whether in this environment or a future one with local/test PostgreSQL available).

H13 is a plan and contract document — no runtime code change until explicitly approved.

---

*Bridge Hub — Task 11C-H12. Execution BLOCKED — no local/test PostgreSQL available.
Production DB not touched. No SQL executed against any production instance.
Balance.ge remains inactive. No runtime behavior changed.*
