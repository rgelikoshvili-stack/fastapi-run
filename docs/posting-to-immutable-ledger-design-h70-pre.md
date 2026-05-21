# Bridge Hub — Posting to Immutable Ledger Design

**Task:** 11C-H70-PRE
**Type:** Design document — no runtime code changes, no SQL execution.
**Date:** 2026-05-21
**Depends on:** 11C-H69 (Migration 011 production execution success)
**Follows:** H69-GATES (H69_READY_FOR_PRODUCTION_MIGRATION_EXECUTION)

---

## 1. Purpose

This document specifies the design for H70: extending `posting_service.apply_posting_service`
so that every successful ERP connector posting also writes an immutable row to
`journal_entry_headers` + `journal_entry_lines` + `journal_entry_sources`.

No runtime code is changed in this task. No SQL is executed. This is a design and
planning document only.

**Decision: `H70_PRE_DESIGN_READY_WAITING_FOR_H69`**

H70 implementation is BLOCKED until H69 migration 011 is executed successfully and
tables `journal_entry_headers`, `journal_entry_lines`, `journal_entry_sources` are
confirmed present in production.

If H69 has not run: `BLOCKED_H69_MIGRATION_NOT_EXECUTED`
If schema is unavailable: `BLOCKED_LEDGER_SCHEMA_UNAVAILABLE`

---

## 2. Current Posting Behavior (pre-H70)

`app/api/services/posting_service.py` — `apply_posting_service(draft_id, target, tenant_id)`:

### 2.1 Guards (preserved in H70 — no changes)

| Guard | Location | Behavior |
|---|---|---|
| Approved-only | `_validate_approved_draft` | Returns `DRAFT_NOT_APPROVED` if `journal_drafts.status != 'approved'` |
| Period lock | asyncpg `period_locks` query | Returns `PERIOD_LOCKED` if entry_date falls in a locked period |
| Duplicate invoice | `partner + amount + date ±3d` check | Returns `DUPLICATE_INVOICE_WARNING` (overrideable with `force=True`) |
| Re-post block | `posting_logs` query for `posted`/`simulated_success` | Returns `POSTING_DUPLICATE_BLOCKED` |
| Row lock | `FOR UPDATE NOWAIT` on `journal_drafts` | Returns `DRAFT_LOCKED` on `LockNotAvailableError` |
| Connector readiness | `_get_connector_readiness` | Returns `CONNECTOR_NOT_READY` if connector not available |
| Line validation | `_validate_lines` | Returns `INVALID_JOURNAL_LINES` |

### 2.2 Success Path (current)

```
apply_posting_service(draft_id, target, tenant_id)
  → SELECT journal_drafts FOR UPDATE NOWAIT
  → validate approved + period + duplicate + re-post guards
  → _draft_to_posting_payload(draft)
  → _post_via_connector(target, payload, tenant_id)
  → INSERT posting_logs (entry_hash ON CONFLICT DO NOTHING)
  → UPDATE journal_drafts SET status = 'posted'
  → COMMIT
```

### 2.3 What is NOT written (pre-H70)

- `journal_entry_headers` — not written
- `journal_entry_lines` — not written
- `journal_entry_sources` — not written

The posted ledger tables are present in the schema after H69 but contain zero rows
until H70 writes begin.

---

## 3. Target Behavior — H70 Immutable Ledger Write

After H70 is implemented and `POSTED_LEDGER_WRITES_ENABLED=true`, the success path
extends atomically:

```
apply_posting_service(draft_id, target, tenant_id)
  → [all existing guards — unchanged]
  → _post_via_connector(target, payload, tenant_id)
  → INSERT posting_logs ... RETURNING id  → log_id
  → [NEW] INSERT journal_entry_headers ... RETURNING id  → header_id
  → [NEW] INSERT journal_entry_lines (one row per line in draft.lines)
  → [NEW] INSERT journal_entry_sources (source_draft_id, posting_log_id)
  → UPDATE journal_drafts SET status = 'posted'
  → COMMIT
```

All writes are inside the **same transaction** as `posting_logs`. If any ledger
write fails, the entire transaction rolls back — no partial state is left.

### 3.1 journal_entry_headers row

| Column | Source |
|---|---|
| `tenant_id` | `draft["tenant_id"]` |
| `source_draft_id` | NULL (draft.id is INTEGER; UUID field reserved for future migration) |
| `posting_log_id` | NULL (posting_logs.id is INTEGER; UUID field reserved for future migration) |
| `entry_date` | `draft["date"]` |
| `posting_date` | `NOW()` (set by DB default) |
| `period` | `YYYY-MM` derived from `entry_date` |
| `status` | `'posted'` |
| `source_type` | `'journal_draft'` |
| `source_hash` | SHA-256 of `draft_id + tenant_id + amount + date + target` (same inputs as `entry_hash`) |
| `currency` | `draft["currency"]` |
| `exchange_rate` | `payload["exchange_rate"]` |
| `total_debit` | sum of all `line["debit"]` values from normalized lines |
| `total_credit` | sum of all `line["credit"]` values from normalized lines |
| `created_by` | `tenant_id` (user identity not yet threaded to service layer) |
| `approved_by` | NULL (approval actor not yet stored on draft) |
| `posted_by` | `target` (connector identity) |
| `metadata_json` | `{"erp_id": response["erp_id"], "target": target}` |

`total_debit = total_credit` is enforced by `ck_jeh_balanced` at the DB layer.
The service must pre-validate this before attempting the insert to return a clean
error instead of a DB constraint violation.

### 3.2 journal_entry_lines rows

One row per entry in `draft["lines"]` (normalized by `_normalize_lines`):

| Column | Source |
|---|---|
| `tenant_id` | `draft["tenant_id"]` |
| `journal_entry_id` | `header_id` from the headers insert |
| `line_no` | 1-indexed position in lines array |
| `account_code` | `line["account_code"]` |
| `account_name` | NULL (not stored on draft lines currently) |
| `debit` | `line["debit"]` or 0 |
| `credit` | `line["credit"]` or 0 |
| `currency` | `draft["currency"]` |
| `exchange_rate` | `payload["exchange_rate"]` |
| `amount_gel` | `debit_or_credit * exchange_rate` |
| `account_type` | NULL (not currently carried on draft lines — H71 may populate) |
| `cashflow_category` | NULL (not currently carried on draft lines — H71 may populate) |
| `description` | `line.get("label", "")` |
| `line_hash` | SHA-256 of `(header_id, line_no, account_code, debit, credit, amount_gel)` |

### 3.3 journal_entry_sources rows

Two rows per successful posting (minimum):

| Row | `source_type` | `source_id` |
|---|---|---|
| Draft link | `'journal_draft'` | `str(draft_id)` |
| Log link | `'posting_log'` | `str(log_id)` from `posting_logs` insert |

If `draft["source_document_id"]` is set, a third row:
`source_type='document', source_id=str(source_document_id)`

---

## 4. Integer/UUID Impedance Mismatch

`journal_drafts.id` is `SERIAL` (INTEGER). `journal_entry_sources.source_id` is `TEXT`.
`journal_entry_headers.source_draft_id` is `UUID`.

Resolution:
- Do NOT populate `source_draft_id` or `posting_log_id` UUID columns in H70.
- Use `journal_entry_sources` (TEXT source_id) for all soft links.
- When journal_drafts and posting_logs are migrated to UUID PKs in a future task,
  backfill `source_draft_id` and `posting_log_id` at that time.

---

## 5. Balanced Entry Validation

Before inserting `journal_entry_headers`, the service must verify:

```python
total_debit  = sum(Decimal(str(l.get("debit",  0) or 0)) for l in lines)
total_credit = sum(Decimal(str(l.get("credit", 0) or 0)) for l in lines)
assert total_debit == total_credit  # else return LEDGER_ENTRY_NOT_BALANCED
```

The existing `_validate_lines` helper checks that each line has at least one non-zero
side, but does NOT assert the cross-line balance. H70 must add that check explicitly
before attempting the `journal_entry_headers` insert so the DB constraint `ck_jeh_balanced`
is never the first line of defence.

---

## 6. Preserved Invariants

| Invariant | How preserved |
|---|---|
| approved-only | `_validate_approved_draft` runs before any ledger write |
| period lock | period_locks check runs before any ledger write |
| balanced entry | explicit pre-validation + `ck_jeh_balanced` DB constraint |
| duplicate post block | `POSTING_DUPLICATE_BLOCKED` check runs before any ledger write |
| tenant isolation | `tenant_id` on every row; queries always filter by `tenant_id` |
| immutability | no UPDATE/DELETE on `journal_entry_headers` or `journal_entry_lines` |
| rollback/correction | use append-only reversal pattern; no destructive edits to posted rows |
| posting_logs preserved | existing log insert unchanged; ledger writes are additive |

---

## 7. Rollback / Correction Pattern

Posted ledger rows are immutable. If a posted entry must be corrected:

1. Insert a new `journal_entry_headers` row with `status = 'correction'` or `'reversed'`.
2. Set `correction_of_entry_id` or `reversed_by_entry_id` to point to the original.
3. Never DELETE or UPDATE existing `journal_entry_headers` or `journal_entry_lines` rows.
4. The original `journal_drafts` row remains with `status = 'posted'`.

This pattern is designed in H70 but implemented in a later task (H7 / correction workflow).

---

## 8. What H70 Does NOT Change

- `posting_service.apply_posting_service` routing logic
- ERP connector dispatch (balance, onec, oris, mock)
- `journal_drafts.status = 'posted'` update
- `posting_logs` insert and `entry_hash` idempotency
- All HTTP route handlers
- Report endpoints (still read from `journal_drafts` until H6/H71)
- Balance.ge activation state (remains `demo_mode`)
- RBAC / permission map

---

## 9. H70 Dependency on H69

H70 implementation requires:
- `journal_entry_headers` table exists in production
- `journal_entry_lines` table exists in production
- `journal_entry_sources` table exists in production

These tables are created by migration 011 in task 11C-H69.

**H70 implementation is blocked until H69 migration success is confirmed.**

Gate: `H69_PRODUCTION_MIGRATION_SUCCESS_CONFIRMED`

Until that gate is met, any H70 implementation attempt will fail at the DB layer
because the target tables do not exist.

---

*Bridge Hub — Task 11C-H70-PRE. Design document only.
No runtime code changed. No SQL executed. No production DB connection.
Decision: H70_PRE_DESIGN_READY_WAITING_FOR_H69.*
