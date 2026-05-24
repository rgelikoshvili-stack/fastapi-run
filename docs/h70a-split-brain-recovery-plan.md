# Bridge Hub — H70A Split-Brain Recovery Plan

**Task:** 11C-H70A-PRE
**Type:** Docs/tests only. No runtime code changed. No SQL executed. No production DB touched.
**Date:** 2026-05-24
**Depends on:** H70A atomicity plan (h70a-ledger-write-atomicity-plan.md)
**Follows:** H70A_PRE_ATOMICITY_PLAN_READY_WAITING_FOR_H69

---

## 1. Purpose

This document defines the split-brain detection and recovery procedures for H70 posted
ledger writes. A split-brain occurs when Tier 2 (journal_drafts/posting_logs) is committed
but Tier 3 (journal_entry_*) is missing or incomplete.

No SQL is executed by this task. No production DB connection is made.

---

## 2. Split-Brain Taxonomy

### 2.1 Case Definitions

| Case | Trigger | Tier 2 State | Tier 3 State | Severity |
|---|---|---|---|---|
| SB-1 | ERP connector success + ledger tx exception | posted | MISSING | HIGH |
| SB-2 | ledger tx partial — header inserted, lines lost | posted | PARTIAL | HIGH |
| SB-3 | ledger tx partial — header+lines inserted, sources lost | posted | PARTIAL | MEDIUM |
| SB-4 | Process restart mid-ledger-write | posted | PARTIAL or MISSING | HIGH |
| SB-5 | Idempotent retry duplicate attempt (false split-brain) | posted | COMPLETE | LOW |

### 2.2 Detection Query Pattern (template — not executed)

The recovery pass MUST identify split-brain rows using the following logic:

```sql
-- Template only — never executed in this task
-- Find posted drafts with no corresponding ledger source
SELECT jd.id       AS draft_id,
       jd.tenant_id,
       jd.target
FROM   journal_drafts jd
JOIN   posting_logs   pl ON pl.draft_id  = jd.id
                         AND pl.tenant_id = jd.tenant_id
                         AND pl.status    = 'posted'
WHERE  jd.status = 'posted'
  AND  NOT EXISTS (
           SELECT 1
           FROM   journal_entry_sources jes
           WHERE  jes.source_type = 'journal_draft'
             AND  jes.source_id   = jd.id::text
       );
```

This query is the canonical split-brain detection query. It is recorded here for
documentation purposes. Execution requires migration 011 tables to exist (post-H69).

---

## 3. Recovery Rules

### 3.1 Recovery Entry Point

The recovery pass is invoked only when:

1. Migration 011 tables exist (post-H69).
2. `POSTED_LEDGER_WRITES_ENABLED=true`.
3. A `ledger_write_failed` audit event was previously emitted for the draft.

The recovery pass MUST NOT be invoked in the main posting flow. It is a separate
maintenance operation executed after the fact.

### 3.2 Idempotency Pre-Check (REQ-5)

Before any recovery insert, the recovery pass MUST check:

```python
# Idempotency pre-check (implementation template — not yet active)
existing = await conn.fetchrow(
    """
    SELECT id FROM journal_entry_sources
    WHERE source_type = 'journal_draft'
      AND source_id   = $1
    """,
    str(draft_id),
)
if existing:
    log_event("ledger_write_skipped", draft_id=draft_id, source_id=existing["id"])
    return  # Ledger write already complete — skip
```

If the source record exists, the ledger write for that draft is COMPLETE. No insert.

### 3.3 Case-by-Case Recovery Rules

#### SB-1: Missing ledger entry (most common)

Recovery: Re-run `_write_ledger_entries()` in a new transaction.
Pre-check: verify `journal_entry_sources` absence (step 3.2).
Outcome: Full header + lines + sources inserted. Emit `ledger_write_recovered`.

#### SB-2: Partial — header exists, lines missing

Detection: `journal_entry_headers` row exists with `source_hash` matching the draft,
but `COUNT(journal_entry_lines)` = 0.

Recovery:
1. DELETE the orphaned header row (it has no lines — invariant INV-3 violated).
2. Re-run `_write_ledger_entries()` fresh.
3. Emit `ledger_write_recovered`.

Note: The header DELETE is safe pre-`_write_ledger_entries()` because no source
record exists yet (idempotency pre-check confirmed this).

#### SB-3: Partial — header+lines exist, sources missing

Detection: `journal_entry_headers` row and `journal_entry_lines` rows exist, but
`journal_entry_sources` row for `source_type='journal_draft', source_id=str(draft_id)` absent.

Recovery:
1. Locate the orphaned header via `source_hash`.
2. INSERT only the missing `journal_entry_sources` row, referencing the existing header.
3. Emit `ledger_write_recovered`.

This case requires targeted partial re-insert rather than full re-run.

#### SB-4: Partial from process restart

Same detection logic as SB-2 or SB-3 depending on how far the ledger write progressed.
Recovery path is identical to SB-2 or SB-3 respectively.

#### SB-5: False split-brain (idempotent skip)

Detection: `journal_entry_sources` row exists — ledger write already complete.
Recovery: NO ACTION required.
Emit: `ledger_write_skipped` audit event to confirm idempotency pass.

---

## 4. Recovery Audit Events

| Event | When emitted | Required Fields |
|---|---|---|
| `ledger_write_failed` | Any exception in `_write_ledger_entries()` | draft_id, tenant_id, target, error |
| `ledger_write_recovered` | Successful recovery re-run | draft_id, tenant_id, header_id, case |
| `ledger_write_skipped` | Source row already exists — skip | draft_id, tenant_id, source_id |
| `ledger_recovery_partial_delete` | Orphaned header deleted before re-run | draft_id, tenant_id, header_id |

The `ledger_write_failed` event MUST be emitted in the main posting flow catch block
before recovery is possible. Without it, the recovery pass has no audit trail to
reconstruct which drafts need recovery.

---

## 5. Recovery Invariants

These invariants MUST hold after every recovery pass:

| Invariant | Rule |
|---|---|
| RINV-1 | Every recovered draft has exactly one `journal_entry_sources` row |
| RINV-2 | Recovery pass emits exactly one audit event per draft |
| RINV-3 | Recovery pass never creates duplicate `journal_entry_headers` rows for the same `source_hash` |
| RINV-4 | Recovery pass never modifies `journal_drafts` or `posting_logs` — Tier 2 is immutable post-commit |
| RINV-5 | Recovery pass is idempotent — running it twice produces identical state |

---

## 6. Non-Recovery Cases (Out of Scope)

The following are NOT handled by the H70 ledger write recovery mechanism:

| Case | Reason Out of Scope |
|---|---|
| ERP connector failure (Tier 1) | Main tx never commits — no Tier 2 state, no Tier 3 needed |
| journal_drafts.status ≠ 'posted' | Never reached ledger write stage — not a split-brain |
| Double-posting prevention | Handled by duplicate-detection in main posting flow |
| Period lock conflicts | Checked in main posting flow before Tier 2 commit |

---

## 7. Activation Sequence

The split-brain recovery mechanism becomes active only after:

1. Migration 011 executed successfully (H69 window, tonight 2026-05-24 23:00 UTC).
2. Post-migration verification passed (Section 7 of migration-011-production-execution-plan-h68.md).
3. REQ-1 through REQ-5 implemented (see h70a-ledger-write-atomicity-plan.md Section 4.2).
4. `POSTED_LEDGER_WRITES_ENABLED=true` set via env var update.

Until all 4 conditions are met, no recovery is needed (ledger writes are dormant).

---

## 8. Decision

**Decision: `H70A_PRE_SPLIT_BRAIN_PLAN_READY_WAITING_FOR_H69`**

This plan is docs/tests only. No runtime code was changed.
`POSTED_LEDGER_WRITES_ENABLED` remains false.
Migration 011 has not been executed.
Production DB was not touched.
No SQL was executed.

---

*Bridge Hub — Task 11C-H70A-PRE. Split-brain recovery plan. No SQL executed. No production DB connection.*
