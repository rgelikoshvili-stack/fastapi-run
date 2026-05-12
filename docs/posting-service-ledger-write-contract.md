# Bridge Hub — Posting Service Ledger Write Contract

**Task:** 11C-H5
**Type:** Contract document and tests only — no runtime code change, no SQL, no migration execution.
**Date:** 2026-05-12
**Follows:** 11C-H4 `app/storage/migrations/011_posted_journal_entries_schema.sql`

---

## 1. Purpose

This contract defines the **future behavior** for `posting_service` to write immutable posted ledger entries after a **successful real posting only**.

`posting_service.py` is not modified by this task. No runtime behavior changes in H5. This document is the design contract that H6 will implement against, using mocks and contract tests only.

**No SQL is executed in this task. No production DB is touched. No migration is executed. No posting_service.py behavior is changed.**

---

## 2. Background

The H1–H4 foundation that makes this contract necessary:

| Task | Deliverable |
|---|---|
| H1 | Reports ledger integrity audit — CRITICAL: all reports source from `journal_drafts` JSONB; no immutable `journal_entries` table; `/reports/bs/detail` has no status filter; `/reports/pnl/detail` treats `simulated_success` as truth |
| H2 | Posted journal entries schema contract — defined `journal_entry_headers` + `journal_entry_lines` target schema, all required fields, 13 invariants, accounting truth principles |
| H3 | Safe migration plan — defined constraint requirements, index requirements, soft-link strategy, H4–H8 rollout sequence, safe backfill policy |
| H4 | SQL migration file `011_posted_journal_entries_schema.sql` created but **not executed** — additive-only DDL awaiting approved production execution |
| H5 (this task) | Posting service ledger write contract — defines when and how `posting_service` must write immutable ledger entries in future H6 implementation |

Until H6 is implemented and the migration is executed, reports continue to read from `journal_drafts`. H5 prepares the behavioral contract so H6 can be implemented safely and testably.

---

## 3. Accounting Truth Rule

The following principles define what constitutes accounting truth in Bridge Hub. These rules apply to all future posting service ledger write behavior.

| State | Is accounting truth? | Reason |
|---|---|---|
| `draft` | **NO** | Unreviewed working entry — not yet approved |
| `pending approval` | **NO** | Awaiting human review — not confirmed |
| `approved` | **NO** | Approved for execution — not yet ERP-confirmed |
| `auto_approved` | **NO** | Automated approval without human/final policy confirmation |
| `simulated_success` | **NO** | Test/simulation state — no real ERP write occurred |
| `mock_posting` | **NO** | Development connector — no real ERP entry |
| `dry_run` | **NO** | Preview mode — explicitly not a real posting |
| `connector_failed` | **NO** | Connector returned failure — no real ERP entry |
| `demo_mode` | **NO** | Balance.ge or ORIS in demo/stub mode — no live ERP write |
| `posted` (real) | **YES** | ERP connector confirmed — immutable ledger write follows |

**Only a successful real connector posting, followed by an immutable ledger write, becomes accounting truth.**

---

## 4. Future Posting Flow

The complete future flow from draft to accounting truth:

```
Draft created
    │
    ▼
Preview (optional dry_run — NOT accounting truth)
    │
    ▼
Human approval (approved status — NOT accounting truth)
    │
    ▼
Connector Execute (real connector, not mock, not demo_mode, dry_run=false)
    │
    ├── Connector failed → posting_log records failure → NO ledger write
    │
    └── Connector succeeded (real)
            │
            ▼
        posting_log record created (connector execution trail)
            │
            ▼
        Idempotency check (source_hash / source_draft_id + posting_log_id unique)
            │
            ├── Duplicate detected → skip ledger write, return existing entry id
            │
            └── Not duplicate
                    │
                    ▼
                Balance check (total_debit = total_credit)
                    │
                    ├── Unbalanced → fail closed, record inconsistency, alert
                    │
                    └── Balanced
                            │
                            ▼
                        Immutable ledger write (transaction boundary)
                            ├── INSERT journal_entry_headers
                            ├── INSERT journal_entry_lines (all lines, one transaction)
                            └── INSERT journal_entry_sources (optional)
                                    │
                                    ▼
                                Audit/Evidence link
                                    ├── Set evidence_bundle_id if available
                                    └── Audit log records ledger write result
```

**Each step is a separate concern. The ledger write is the last step and only occurs after connector success is confirmed.**

---

## 5. When Ledger Write Is Allowed

An immutable ledger write to `journal_entry_headers` and `journal_entry_lines` is allowed **only when ALL of the following are true:**

1. `draft.tenant_id` matches the authenticated request tenant — tenant isolation enforced
2. Draft status is in an approved or final-approved state before connector execution
3. The accounting period is **not locked** (`is_period_locked` returns false)
4. The connector target is a **real connector** — not mock, not demo_mode, not ORIS stub, not 1C demo
5. `dry_run` is `false` — preview mode must not create ledger entries
6. The connector response indicates **real success** — not simulation, not timeout treated as success
7. A `posting_log` record with successful real posting status exists for this operation
8. The idempotency key / `source_hash` + `source_draft_id` combination is **unique** — no duplicate ledger entry exists for this source
9. Journal lines are **balanced**: `sum(debit) == sum(credit)` at the entry level
10. `tenant_id` is present and non-empty on the header and all lines
11. Evidence/source links are preserved where available (`evidence_bundle_id`, `posting_log_id`, `source_draft_id`)

---

## 6. When Ledger Write Is Forbidden

An immutable ledger write must be **explicitly refused** when any of the following conditions are true:

| Condition | Reason |
|---|---|
| `status = 'draft'` | Not yet reviewed — not accounting truth |
| `status = 'pending_approval'` | Awaiting human confirmation |
| `status = 'rejected'` | Entry was rejected — must not be posted |
| `status = 'auto_approved'` without human/final policy approval | Automated path only — not accounting truth |
| `status = 'simulated_success'` | Test/simulation — not a real ERP write |
| Mock connector target | Development artifact — no real ERP entry |
| `dry_run = true` | Preview mode — explicitly not a real posting |
| Connector config missing | Cannot post without a real target |
| Connector returned failure | No real ERP entry was created |
| `balance.connectors.balance = 'demo_mode'` | Balance.ge is not activated |
| ORIS stub mode | ORIS is not a live connector in this context |
| 1C demo mode | 1C is not a live connector in this context |
| `tenant_id` missing or empty | Tenant isolation violation |
| Period is locked | `is_period_locked` returns true — accounting period is closed |
| Journal lines are unbalanced | `sum(debit) ≠ sum(credit)` — double-entry violated |
| Duplicate idempotency / `source_hash` | Ledger entry for this source already exists |
| Migration / ledger table unavailable | `journal_entry_headers` table does not exist yet — fall back to draft-only model gracefully |
| Production migration not executed | `011_posted_journal_entries_schema.sql` has not been run against production DB |

---

## 7. Future Ledger Write Output

When all conditions in Section 5 are met, the posting service must produce:

### 7.1 `journal_entry_headers` row (exactly one per accounting entry)

| Field | Value source |
|---|---|
| `id` | Generated UUID |
| `tenant_id` | From draft / authenticated tenant |
| `source_draft_id` | `journal_drafts.id` of the approved draft |
| `posting_batch_id` | Generated per batch run (optional) |
| `posting_log_id` | `posting_logs.id` of the successful connector execution |
| `evidence_bundle_id` | `evidence_bundles.id` if available, else NULL |
| `entry_date` | Draft accounting date |
| `posting_date` | Timestamp of connector confirmation |
| `period` | Accounting period (e.g., `2026-01`) |
| `status` | `'posted'` |
| `source_type` | Draft source type (e.g., `bank_transaction`, `manual`) |
| `source_hash` | Hash of source content at time of posting |
| `currency` | From draft |
| `exchange_rate` | Rate at time of posting |
| `total_debit` | Sum of all debit lines |
| `total_credit` | Sum of all credit lines (must equal `total_debit`) |
| `created_by` | Actor who created the draft |
| `approved_by` | Actor who approved the draft |
| `posted_by` | Actor or system that triggered posting |
| `created_at` | NOW() |
| `posted_at` | Connector confirmation timestamp |
| `metadata_json` | Connector response summary — no secrets, no api_key, no password |

### 7.2 `journal_entry_lines` rows (one per debit/credit line)

- One row per line from `journal_drafts.journal_entries` JSONB
- `tenant_id` must match header `tenant_id`
- `journal_entry_id` references the new header `id`
- `line_no` preserves original ordering
- `account_code`, `debit`, `credit`, `amount_gel`, `currency`, `exchange_rate` from draft lines
- `counterparty_id`, `document_id`, `bank_transaction_id` from draft where available
- `tax_code`, `vat_amount` from draft where available
- `line_hash` computed at write time

### 7.3 `journal_entry_sources` rows (optional)

- Links the header to its source objects (draft, document, bank transaction)
- `source_type` and `source_id` for each linked object

---

## 8. Idempotency and Duplicate Protection

The posting service must guarantee that the same successful posting never creates duplicate ledger entries:

1. **Source uniqueness check**: Before inserting, check that no `journal_entry_headers` row exists with the same `source_draft_id` AND `posting_log_id`. If found, return the existing entry id without re-inserting.
2. **Source hash check**: If `source_hash` is set, it must also be unique per tenant. A duplicate `source_hash` indicates the same source content was posted twice.
3. **Retry after connector success**: If the connector succeeded but the ledger write failed (e.g., DB error), the retry path must detect the existing `posting_log_id` and either complete the partial write in a transaction or return the existing entry.
4. **Retry after connector failure**: A failed connector attempt must not create a `journal_entry_headers` row. Only confirmed connector success triggers a ledger write.
5. **No phantom entries**: A `journal_entry_headers` row with `status = 'posted'` must always have at least one corresponding `journal_entry_lines` row. A header with no lines is invalid.

---

## 9. Error Handling / Fail-Closed

The posting service must implement fail-closed error handling for ledger writes:

1. **If ledger write fails after connector success**: Record a recoverable inconsistency state (e.g., a `posting_inconsistency` log entry or a `status = 'posted_no_ledger'` on the draft). Alert/log at ERROR level. Do not silently mark as fully posted without a ledger write.
2. **No partial writes**: The header insert and all line inserts must occur within a single database transaction. If any line insert fails, the transaction rolls back entirely. A header without lines must never be committed.
3. **Balance mismatch**: If `total_debit ≠ total_credit` at write time, fail closed. Log at ERROR level. Do not insert.
4. **Tenant mismatch**: If any line's `tenant_id` does not match the header `tenant_id`, fail closed. Do not insert.
5. **Period lock**: If the period is locked when the write is attempted, fail closed. Return `PERIOD_LOCKED` error.
6. **Duplicate detected**: If a ledger entry already exists for this source, return the existing entry id. Do not insert a duplicate. Log at INFO level.
7. **Missing required fields**: If `tenant_id`, `entry_date`, `posting_date`, `period`, or `status` are missing, fail closed. Do not insert partial data.
8. **Table unavailable**: If `journal_entry_headers` does not exist (migration not yet executed), fail gracefully — continue with `journal_drafts`-only model, log a WARNING, do not crash the posting flow.

---

## 10. Evidence and Audit

1. **Evidence bundle linkage**: Every posted ledger entry should link to `evidence_bundle_id` when an evidence bundle was created during the approval/posting flow. Null is acceptable when no evidence bundle exists.
2. **Audit log**: The audit log (`audit_log` table) must record each ledger write attempt and its result — success, failure, duplicate detected, or skip.
3. **`posting_logs` as connector trail**: `posting_logs` records the connector execution event. The ledger write records the accounting confirmation. These are separate concerns — `posting_logs` must not be modified by the ledger write path.
4. **No raw secrets in ledger metadata**: `metadata_json` on `journal_entry_headers` must never contain `api_key`, `password`, `token`, `secret`, `encrypted_value`, or any credential value. The `_strip_unsafe` function from `evidence_bundle_service.py` must be applied before writing `metadata_json`.
5. **No credentials in `journal_entry_lines`**: Line fields (`description`, `tax_code`, etc.) must not contain credential values. These fields are not sanitized by the DB constraint — application-layer sanitization is required.

---

## 11. Non-Goals for H5

This task explicitly does **not**:

- Change any runtime posting behavior.
- Modify `posting_service.py`.
- Modify `approval_service.py`.
- Modify `routes_posting.py` or any route handler.
- Execute any SQL.
- Create any new SQL migration file.
- Execute any migration.
- Access any database (production or otherwise).
- Touch the production database.
- Change any runtime report behavior.
- Modify `routes_reports.py`, `financial_statements_service.py`, or `ledger_service.py`.
- Change any connector behavior.
- Activate Balance.ge.
- Change any credentials or secrets.
- Change any production infrastructure or deployment configuration.
- Start H6, H7, H8, H9, or H10 work.

This task produces two files only:
- `docs/posting-service-ledger-write-contract.md` (this document)
- `tests/unit/test_posting_service_ledger_write_contract.py`

---

## 12. Future Task Sequence

| Task | Description |
|---|---|
| **H5** (this task) | Posting service ledger write contract / tests only — no runtime change |
| **H6** | Posting service ledger write implementation tests with mocks — test-drive the future `_write_ledger_entry` function using `MagicMock` for DB; still no production DB write |
| **H7** | Reports posted-ledger read contract / tests — define how `financial_statements_service` and `ledger_service` will query `journal_entry_headers` + `journal_entry_lines` instead of `journal_drafts` |
| **H8** | Reversal / correction contract — define append-only reversal and correction flow, including API and UI contract |
| **H9** | Evidence / audit export linkage contract — define how `evidence_bundle_id` links to posted entries and how audit export should work |
| **H10** | Controlled local/test migration execution plan — if explicitly approved, run `011_posted_journal_entries_schema.sql` against a local or test DB only; never production without separate approval |

Each task follows the same protocol: branch → docs/tests → PR → merge → deploy → live verification → confirmed before starting the next task.

---

*Bridge Hub — Task 11C-H5. Contract only. No runtime changes. No SQL. No migration execution. No production DB touch. Balance.ge remains inactive.*
