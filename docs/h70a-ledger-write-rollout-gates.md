# Bridge Hub — H70A Ledger Write Rollout Gates

**Task:** 11C-H70A-PRE
**Type:** Docs/tests only. No runtime code changed. No SQL executed. No production DB touched.
**Date:** 2026-05-24
**Depends on:** h70a-ledger-write-atomicity-plan.md, h70a-split-brain-recovery-plan.md
**Follows:** H70A_PRE_SPLIT_BRAIN_PLAN_READY_WAITING_FOR_H69

---

## 1. Purpose

This document defines the 10 rollout gates that MUST all pass before
`POSTED_LEDGER_WRITES_ENABLED` may be set to `true`.

No SQL is executed by this task. No production DB connection is made.

---

## 2. Gate Evaluation

| Gate | Requirement | Status | Notes |
|---|---|---|---|
| H70A-G1 | Migration 011 executed and verified in production | BLOCKED | Waiting for H69 window (2026-05-24 23:00 UTC) |
| H70A-G2 | `journal_entry_headers` table exists in production | BLOCKED | Depends on H70A-G1 |
| H70A-G3 | `ledger_write_failed` emits structured `log_event()` audit record | OPEN | REQ-1 — implementation required |
| H70A-G4 | Recovery query (SB detection) implemented and tested | OPEN | REQ-2 — implementation required |
| H70A-G5 | Idempotent retry of `_write_ledger_entries()` implemented | OPEN | REQ-3 — implementation required |
| H70A-G6 | `ledger_write_recovered` audit event on successful recovery | OPEN | REQ-4 — implementation required |
| H70A-G7 | `journal_entry_sources` pre-check in `_write_ledger_entries()` | OPEN | REQ-5 — implementation required |
| H70A-G8 | Integration test: ledger write with real Postgres (migration 011 schema) | BLOCKED | Depends on H70A-G1 |
| H70A-G9 | Load test: 100 concurrent postings, zero split-brain in ledger | BLOCKED | Depends on H70A-G8 |
| H70A-G10 | Go/No-Go sign-off from Rolandi Gelikoshvili | OPEN | Final gate — human approval required |

**Gate Summary:** 0 PASS | 5 BLOCKED | 5 OPEN | 0 FAIL

---

## 3. Gate Details

### H70A-G1: Migration 011 Executed

**Requirement:** `011_posted_journal_entries_schema.sql` must be applied to production.
**Verification:** `SELECT to_regclass('public.journal_entry_headers') IS NOT NULL;` returns `t`.
**Migration SHA-256:** `3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0`
**Window:** Tonight 2026-05-24 23:00–00:00 UTC (second renewal H69-WINDOW-REAPPROVAL-2).
**Blocker:** Cannot proceed until this gate passes.

### H70A-G2: Table Existence Confirmed

**Requirement:** All three ledger tables must exist:
- `journal_entry_headers`
- `journal_entry_lines`
- `journal_entry_sources`

**Verification:** Post-execution checklist in migration-011-production-execution-plan-h68.md Section 7.
**Depends on:** H70A-G1 PASS.

### H70A-G3: Structured Audit Event on Failure (REQ-1)

**Requirement:** The current `log.error(...)` in the ledger write catch block MUST be
replaced with or supplemented by a structured `log_event("ledger_write_failed", ...)` call.

**Current state (deployed):**
```python
except Exception as _ledger_exc:
    log.error("ledger_write_failed draft_id=%s tenant=%s target=%s: %s",
              draft_id, tenant_id, target_normalized, _ledger_exc)
```

**Required state:**
```python
except Exception as _ledger_exc:
    log.error("ledger_write_failed draft_id=%s tenant=%s target=%s: %s",
              draft_id, tenant_id, target_normalized, _ledger_exc)
    log_event("ledger_write_failed",
              draft_id=draft_id, tenant_id=tenant_id,
              target=target_normalized, error=str(_ledger_exc))
```

**Gate passes when:** Unit test confirms `log_event` is called with correct fields on exception.

### H70A-G4: Recovery Query Implemented (REQ-2)

**Requirement:** A recovery endpoint or management command must execute the split-brain
detection query (defined in h70a-split-brain-recovery-plan.md Section 2.2) and return
the list of draft IDs requiring recovery.

**Gate passes when:** Integration test (post-H70A-G1) confirms recovery query returns
correct rows against a real schema.

### H70A-G5: Idempotent Retry (REQ-3)

**Requirement:** `_write_ledger_entries()` must be safe to call multiple times for the
same draft without creating duplicate rows.

**Required mechanism:**
1. Check `journal_entry_sources` for existing `source_type='journal_draft', source_id=str(draft_id)`.
2. If found → skip (emit `ledger_write_skipped`).
3. If not found → proceed with full insert.

**Gate passes when:** Unit test confirms calling `_write_ledger_entries()` twice for the
same draft produces exactly one header, one-or-more lines, and exactly one source row.

### H70A-G6: Recovery Audit Event (REQ-4)

**Requirement:** Successful recovery re-run MUST emit `log_event("ledger_write_recovered", ...)`.

**Fields required:** `draft_id`, `tenant_id`, `header_id`, `case` (SB-1 through SB-5).

**Gate passes when:** Unit test confirms `log_event` is called with all required fields
after successful recovery.

### H70A-G7: Sources Pre-Check in Write (REQ-5)

**Requirement:** `_write_ledger_entries()` itself MUST begin with the idempotency pre-check
(not only the recovery path). This ensures the main posting flow is safe to retry
without a separate recovery pass.

**Gate passes when:** Unit test confirms that `_write_ledger_entries()` exits early
(emitting `ledger_write_skipped`) when `journal_entry_sources` already contains the
source record for the given `draft_id`.

### H70A-G8: Integration Test (Real Schema)

**Requirement:** A full end-to-end test must post a journal draft through the real
posting service against a database with migration 011 schema applied, and verify that:

1. `journal_entry_headers` row inserted with `total_debit = total_credit`.
2. At least one `journal_entry_lines` row inserted.
3. `journal_entry_sources` row inserted with correct `source_type` and `source_id`.
4. Re-running produces identical state (idempotency).

**Depends on:** H70A-G1, H70A-G2, H70A-G3, H70A-G5, H70A-G7.

### H70A-G9: Load Test

**Requirement:** 100 concurrent posting requests against a test environment with
migration 011 schema. Zero split-brain rows after all requests complete (confirmed
by running the split-brain detection query).

**Pass criteria:**
- All 100 drafts have matching `journal_entry_sources` rows.
- `total_debit = total_credit` on all inserted headers.
- No duplicate `source_hash` violations.

**Depends on:** H70A-G8.

### H70A-G10: Go/No-Go Sign-Off

**Requirement:** Human approval from Rolandi Gelikoshvili after H70A-G1 through H70A-G9 all pass.

**Activation command (template):**
```bash
# Template only — do NOT run until H70A-G1..G9 PASS and H70A-G10 signed off
# gcloud run services update fastapi-run \
#   --update-env-vars="POSTED_LEDGER_WRITES_ENABLED=true" \
#   --region europe-west1
```

**Gate passes when:** Explicit approval recorded in a follow-up gate doc (H70B or later).

---

## 4. Blocking Dependencies

```
H70A-G1 (H69 execution) ─┬─► H70A-G2 (table exists)
                          └─► H70A-G8 (integration test) ─► H70A-G9 (load test) ─► H70A-G10

H70A-G3 (audit event)  ─┐
H70A-G4 (recovery qry) ─┤
H70A-G5 (idempotent)   ─┼─► H70A-G8
H70A-G6 (recovery evt) ─┤
H70A-G7 (pre-check)    ─┘
```

H70A-G3 through H70A-G7 can be implemented independently of H70A-G1.
H70A-G8 and H70A-G9 are blocked until H70A-G1 passes.
H70A-G10 is blocked until all other gates pass.

---

## 5. Current Gate State Summary

**Date evaluated:** 2026-05-24

| Category | Count |
|---|---|
| PASS | 0 |
| BLOCKED (waiting for H69) | 3 |
| OPEN (implementation required) | 6 |
| FAIL | 0 |
| **Total gates** | **10** |

`POSTED_LEDGER_WRITES_ENABLED` MUST remain `false` until all 10 gates pass.

---

## 6. Decision

**Decision: `H70A_PRE_ROLLOUT_GATES_DOCUMENTED_WAITING_FOR_H69`**

All 10 gates are documented. Zero gates currently pass (H69 not yet executed).
This document is docs/tests only. No runtime code was changed.
`POSTED_LEDGER_WRITES_ENABLED` remains false.
Migration 011 has not been executed.
Production DB was not touched.
No SQL was executed.

---

*Bridge Hub — Task 11C-H70A-PRE. Rollout gates. No SQL executed. No production DB connection.*
