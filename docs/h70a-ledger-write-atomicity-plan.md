# Bridge Hub — H70A Ledger Write Atomicity Plan

**Task:** 11C-H70A-PRE
**Type:** Docs/tests only. No runtime code changed. No SQL executed. No production DB touched.
**Date:** 2026-05-24
**Depends on:** H69 migration execution (migration 011 tables must exist before flag enable)
**Follows:** POST_DEPLOY_SAFETY_PASS_H70_DORMANT_WAITING_FOR_H69

---

## 1. Purpose

This document defines the required atomicity contract for H70 posted ledger writes before
`POSTED_LEDGER_WRITES_ENABLED` can ever be set to `true`.

H70 code is deployed and dormant. `POSTED_LEDGER_WRITES_ENABLED=false`.
Migration 011 has not been executed. This plan governs behaviour once the flag is enabled.

No SQL is executed by this task. No production DB connection is made.

---

## 2. Current H70 Behaviour (Dormant)

| Field | Value |
|---|---|
| H70 code deployed | YES — `_write_ledger_entries()` in `app/api/services/posting_service.py` |
| Flag state | `POSTED_LEDGER_WRITES_ENABLED` absent from env → defaults to `false` |
| Ledger writes active | NO — `_ledger_writes_enabled()` returns false |
| Migration 011 tables | DO NOT EXIST in production |
| Runtime behaviour change | NONE — posting flow identical to pre-H70 |

---

## 3. Required Consistency Model

### 3.1 Source of Truth Hierarchy

```
Tier 1 (ERP truth):    ERP connector acknowledgement (Balance.ge / 1C / Oris response)
Tier 2 (DB truth):     journal_drafts.status = 'posted' + posting_logs.status = 'posted'
Tier 3 (Ledger truth): journal_entry_headers + journal_entry_lines + journal_entry_sources
```

Tier 1 and 2 are committed in the main posting transaction.
Tier 3 is written in a separate transaction after Tier 2 commits.

### 3.2 Atomicity Contract

The main posting transaction (Tier 2) MUST commit before any ledger write (Tier 3) begins.
If the main transaction fails, no ledger write is attempted.

The ledger write transaction (Tier 3) MUST be:
- Idempotent: re-running produces identical state, not duplicate rows.
- Non-blocking: ledger write failure MUST NOT roll back the already-committed Tier 2 state.
- Auditable: every ledger write failure MUST produce a `ledger_write_failed` log event.
- Recoverable: a subsequent recovery pass MUST be able to reconstruct the ledger row from Tier 2 data.

### 3.3 Idempotency Anchors

| Table | Idempotency Key |
|---|---|
| `journal_entry_headers` | `source_hash` (unique per draft+tenant+amount+date+target) |
| `journal_entry_lines` | `(journal_entry_id, line_no)` — unique constraint `uq_jel_line_no` |
| `journal_entry_sources` | `(journal_entry_id, source_type, source_id)` — checked before insert |

A recovery pass MUST check `journal_entry_sources` for `source_type='journal_draft'`
and `source_id=str(draft_id)` before attempting any insert. If a source record exists,
the ledger write for that draft is considered complete and MUST be skipped.

### 3.4 Consistency Invariants

| Invariant | Rule |
|---|---|
| INV-1: Balanced totals | `total_debit = total_credit` on every `journal_entry_headers` row |
| INV-2: Source exists | Every `journal_entry_headers` row has at least one `journal_entry_sources` row |
| INV-3: Lines exist | Every `journal_entry_headers` row has at least one `journal_entry_lines` row |
| INV-4: No draft without lines | No `journal_entry_sources` row without a corresponding header |
| INV-5: Immutability | Posted ledger rows MUST NOT be updated or deleted — reversal/correction appends new rows |

---

## 4. Ledger Write Transaction Boundaries

### 4.1 Current Implementation (as deployed)

```
async with get_conn() as conn:
    tr = conn.transaction()
    await tr.start()
    # --- MAIN TRANSACTION (Tier 2) ---
    # 1. Lock draft (FOR UPDATE NOWAIT)
    # 2. Validate approved status
    # 3. Check period lock
    # 4. Check duplicate
    # 5. Call ERP connector (outside DB, may succeed even if DB fails)
    # 6. INSERT posting_logs
    # 7. UPDATE journal_drafts SET status='posted'
    await tr.commit()   # <-- Tier 2 committed HERE

    # --- LEDGER WRITE (Tier 3, separate transaction) ---
    if _ledger_writes_enabled():
        try:
            async with conn.transaction():          # new tx on same conn
                await _write_ledger_entries(...)    # INV-1..5 enforced here
        except Exception as _ledger_exc:
            log.error("ledger_write_failed ...")    # MUST emit audit event
```

### 4.2 Required Enhancement Before Flag Enable

The current `log.error(...)` on ledger write failure is necessary but not sufficient.
Before `POSTED_LEDGER_WRITES_ENABLED=true`, the following MUST be implemented:

| Requirement | Description | Gate |
|---|---|---|
| REQ-1 | `ledger_write_failed` structured audit event via `log_event()` | H70A-G3 |
| REQ-2 | Recovery query: detect posted drafts with missing ledger source | H70A-G4 |
| REQ-3 | Idempotent retry: re-run `_write_ledger_entries()` safely | H70A-G5 |
| REQ-4 | `ledger_write_recovered` audit event on successful recovery | H70A-G6 |
| REQ-5 | `journal_entry_sources` existence pre-check in `_write_ledger_entries()` | H70A-G7 |

---

## 5. Audit Events Required

| Event | When emitted | Fields |
|---|---|---|
| `ledger_write_failed` | Any exception in `_write_ledger_entries()` | draft_id, tenant_id, target, error |
| `ledger_write_recovered` | Successful idempotent retry of a failed write | draft_id, tenant_id, header_id |
| `ledger_write_skipped` | Source row already exists — idempotent skip | draft_id, tenant_id, source_id |

---

## 6. Immutability Contract

Posted ledger rows in `journal_entry_headers` and `journal_entry_lines` MUST be immutable once inserted.

- No UPDATE on posted rows (status constraint enforces `posted`, `reversed`, `correction`, `voided` only).
- No DELETE on posted rows (reversals append new rows with `reversed_by_entry_id` set).
- Corrections append new rows with `correction_of_entry_id` set.
- The `journal_entry_sources` table records the lineage — also immutable per header.

---

## 7. Decision

**Decision: `H70A_PRE_ATOMICITY_PLAN_READY_WAITING_FOR_H69`**

This plan is docs/tests only. No runtime code was changed.
`POSTED_LEDGER_WRITES_ENABLED` remains false.
Migration 011 has not been executed.
Production DB was not touched.
No SQL was executed.

Implementation of REQ-1 through REQ-5 (Section 4.2) is required before
`POSTED_LEDGER_WRITES_ENABLED` may be set to `true`.

---

*Bridge Hub — Task 11C-H70A-PRE. Atomicity plan. No SQL executed. No production DB connection.*
