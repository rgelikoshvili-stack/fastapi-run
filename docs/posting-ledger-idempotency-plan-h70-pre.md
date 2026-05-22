# Bridge Hub — Posting Ledger Idempotency Plan

**Task:** 11C-H70-PRE
**Type:** Design document — idempotency plan for immutable ledger writes.
**Date:** 2026-05-21
**Depends on:** 11C-H69 (Migration 011 production execution success)

---

## 1. Purpose

This document defines the idempotency strategy for writing to `journal_entry_headers`,
`journal_entry_lines`, and `journal_entry_sources` in H70. The goal is that calling
`apply_posting_service` twice for the same draft produces exactly one posted ledger
entry, never two.

**Decision: `H70_PRE_DESIGN_READY_WAITING_FOR_H69`**

H70 implementation is blocked until H69 produces tables in production.
If H69 has not run: `BLOCKED_H69_MIGRATION_NOT_EXECUTED`
If schema is unavailable: `BLOCKED_LEDGER_SCHEMA_UNAVAILABLE`

---

## 2. Existing Idempotency Layers (unchanged in H70)

### 2.1 posting_logs.entry_hash

`apply_posting_service` computes:

```python
entry_hash = SHA-256(f"{draft_id}:{tenant_id}:{amount}:{date}:{target}")[:16]
```

The `posting_logs` insert uses:
```sql
INSERT INTO posting_logs (..., entry_hash, ...)
ON CONFLICT (entry_hash) WHERE entry_hash IS NOT NULL DO NOTHING
RETURNING id
```

If the `entry_hash` already exists, the insert returns no row (`log_id = None`).
The service then proceeds to update `journal_drafts.status = 'posted'` regardless
of whether the log insert was new or a no-op. This is the current behaviour.

### 2.2 POSTING_DUPLICATE_BLOCKED guard

Before the connector call, `apply_posting_service` queries:

```sql
SELECT id FROM posting_logs
WHERE tenant_id = %s AND draft_id = %s AND target_system = %s
  AND status IN ('posted', 'simulated_success')
ORDER BY id DESC LIMIT 1
```

If a row exists: returns `POSTING_DUPLICATE_BLOCKED` immediately without calling
the connector or writing anything.

This is the primary re-post guard. It fires before any ledger write in H70.

---

## 3. Ledger Idempotency Strategy

### 3.1 Transaction-level idempotency (primary)

The H70 ledger writes (`journal_entry_headers`, `journal_entry_lines`,
`journal_entry_sources`) happen inside the **same DB transaction** as the
`posting_logs` insert. Transaction behaviour:

| Scenario | Outcome |
|---|---|
| Normal first posting | `posting_logs` inserted, header+lines+sources inserted, `journal_drafts` updated, COMMIT |
| Connector fails | Transaction rolls back. No ledger row written. No partial state. Same draft can be retried. |
| Ledger insert fails (DB constraint) | Transaction rolls back. `posting_logs` row also rolled back. No partial state. Retry is safe. |
| Transaction committed then second attempt | `POSTING_DUPLICATE_BLOCKED` fires — exits before reaching connector or ledger write |
| entry_hash conflict (concurrent duplicate) | `posting_logs` DO NOTHING → `log_id = None` → H70 must check for None and skip ledger write |

### 3.2 entry_hash conflict handling in H70

Current code proceeds with the status update even when `log_id` is None (DO NOTHING case).
H70 must extend this:

```python
if log_id is None:
    # entry_hash conflict: posting_logs row already existed.
    # Check whether a header already exists for this draft to decide if we need to write.
    existing_header = SELECT id FROM journal_entry_headers
        WHERE tenant_id = $tenant_id
          AND source_type = 'journal_draft'
          AND id IN (
              SELECT journal_entry_id FROM journal_entry_sources
              WHERE tenant_id = $tenant_id
                AND source_type = 'journal_draft'
                AND source_id = str(draft_id)
          )
        LIMIT 1
    if existing_header:
        # Ledger row already exists — idempotent, skip.
        pass
    else:
        # Log row existed (hash conflict) but no ledger row yet — write header now.
        # This can occur if a previous attempt crashed after posting_logs commit
        # but before the ledger writes (split-brain window).
        _write_ledger_rows(conn, draft, payload, log_id=None, ...)
```

This handles the split-brain case: `posting_logs` committed but the ledger write
crashed before completing.

### 3.3 Source-based existence check

The idempotency existence check uses `journal_entry_sources` rather than
`journal_entry_headers` directly, because the `source_draft_id` UUID column on
headers is NULL (integer/UUID mismatch — see design doc). The canonical lookup is:

```sql
SELECT jes.journal_entry_id
FROM journal_entry_sources jes
WHERE jes.tenant_id = $tenant_id
  AND jes.source_type = 'journal_draft'
  AND jes.source_id = $str_draft_id
LIMIT 1
```

If this returns a row, the ledger entry for this draft already exists.

### 3.4 Future: unique constraint on sources

In a later task, add:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_jes_draft_per_tenant
    ON journal_entry_sources (tenant_id, source_type, source_id)
    WHERE source_type = 'journal_draft';
```

This makes the DB enforce the single-ledger-entry-per-draft rule, eliminating the
need for the application-layer existence check entirely. Not added in H70 (separate
migration approval required).

---

## 4. Concurrent Write Safety

`apply_posting_service` holds a `FOR UPDATE NOWAIT` row lock on `journal_drafts`
for the duration of the transaction. Only one concurrent caller can hold this lock;
all others get `DRAFT_LOCKED`. This serialises the entire posting path per draft,
including the ledger writes.

No additional lock is needed for the ledger tables.

---

## 5. Mock Target Idempotency

When `target = 'mock'`, `post_status = 'simulated_success'`. The ledger write
behaviour in H70:

- If `POSTED_LEDGER_WRITES_ENABLED=true`: write header with `status = 'posted'`
  (mock postings are treated as real for ledger purposes — consistent with the
  existing `journal_drafts.status = 'posted'` update).
- Idempotency applies identically — `POSTING_DUPLICATE_BLOCKED` fires on retry.

---

## 6. Summary of Idempotency Guarantees

| Scenario | Guaranteed outcome |
|---|---|
| First call, connector success | One `posting_logs` row, one `journal_entry_headers` row, N `journal_entry_lines` rows, 2+ `journal_entry_sources` rows |
| Second call, same draft/target | `POSTING_DUPLICATE_BLOCKED` before any write |
| Crash after `posting_logs` commit, before ledger write | Split-brain: resolved by entry_hash + sources existence check on next call |
| Concurrent duplicate calls | `DRAFT_LOCKED` on second caller; first caller writes once |
| Connector failure | Transaction rolled back; no ledger row; safe to retry |
| DB constraint violation on ledger insert | Transaction rolled back; `posting_logs` also rolled back; safe to retry |

All scenarios preserve the invariant: **one draft → at most one posted ledger entry per target**.

---

*Bridge Hub — Task 11C-H70-PRE. Idempotency plan only.
No runtime code changed. No SQL executed. No production DB connection.
Decision: H70_PRE_DESIGN_READY_WAITING_FOR_H69.*
