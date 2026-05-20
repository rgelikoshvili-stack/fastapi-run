# Bridge Hub — Migration 011 Production Rollback Plan

**Task:** 11C-H68
**Type:** Production migration rollback plan — docs only.
**Date:** 2026-05-20
**Branch:** codex/h68-migration-011-production-execution-plan

---

## 1. Purpose

This document defines the rollback strategy for migration 011 in case execution
in production triggers unexpected failures. It is a companion to the execution
plan and approval packet.

---

## 2. Rollback Principle: Restore-Based, Not DROP-Based

Migration 011 is purely additive. The correct rollback for an additive migration is:

1. **Stop execution** if mid-flight failure occurs.
2. **Use backup/PITR restore** if the DB is in an inconsistent state.
3. **Optionally disable the feature flag** (`POSTED_LEDGER_REPORTS_ENABLED`) if
   report behavior changes unexpectedly.

**Default rollback does NOT include:**
- `DROP TABLE journal_entry_headers`
- `DROP TABLE journal_entry_lines`
- `DROP TABLE journal_entry_sources`

These would be destructive and are only used as a last resort if an empty new table
causes unforeseen constraint interference (which is not expected given IF NOT EXISTS
idempotency and no FK links FROM existing tables).

---

## 3. Rollback Decision Tree

```
Migration 011 execution started
│
├── Migration completes successfully
│   └── Proceed to H69 post-execution verification
│       ├── Verification PASS → H69 complete
│       └── Verification FAIL (5xx / auth bypass / secret exposure)
│           └── → ROLLBACK LEVEL 2 (feature-flag disable + investigation)
│
├── Migration fails mid-execution (psql exits non-zero)
│   ├── Tables partially created?
│   │   ├── No → idempotent — re-run migration (IF NOT EXISTS guards)
│   │   └── Yes, inconsistent state
│   │       └── → ROLLBACK LEVEL 1 (restore from PITR)
│   └── Error is non-fatal (e.g. index already exists)
│       └── Re-run migration — IF NOT EXISTS guards protect idempotency
│
└── App fails to start after migration
    └── → ROLLBACK LEVEL 1 (restore from PITR)
```

---

## 4. Rollback Levels

### Level 0 — Re-run (idempotent)

When: Non-fatal error during index creation (index already exists, etc.)
Action: Re-run `011_posted_journal_entries_schema.sql` — all statements use IF NOT EXISTS.
Risk: None — idempotent.

### Level 1 — PITR Restore

When: DB in inconsistent state after partial execution, OR app fails to start.
Action:
1. Stop any ongoing migration execution immediately.
2. Note exact timestamp of failure (UTC).
3. Initiate Cloud SQL PITR restore to the restore point captured before migration.
4. Verify DB is back to pre-migration state.
5. Confirm app starts cleanly (`/health` 200).
6. Document incident.

Rollback owner executes.
Estimated restore time: per Cloud SQL PITR SLA (typically < 15 minutes for small DB).

### Level 2 — Feature-Flag Disable

When: Migration completed but report endpoints return unexpected errors.
Action:
1. Disable `POSTED_LEDGER_REPORTS_ENABLED` flag in Cloud Run env vars
   (requires Cloud Run env update — needs authorized operator).
2. Redeploy or trigger a new revision.
3. Verify `/reports/trial-balance` returns controlled graceful response (not 5xx).
4. Investigation proceeds offline.
5. Re-enable flag once root cause is identified and fixed.

This level does NOT involve DB mutation.

### Level 3 — Emergency DROP (last resort only)

**This level must ONLY be used if authorized by the rollback owner AND an accounting
owner, and ONLY if the new tables cause constraint violations with existing data.**

This scenario is extremely unlikely because:
- The new tables have no FK relationships FROM existing tables
- No existing row references the new tables
- IF NOT EXISTS prevents re-creation conflicts

If authorized:
```sql
-- LAST RESORT ONLY — requires explicit human authorization
-- DO NOT run in H68, H69, or any automated step
DROP TABLE IF EXISTS journal_entry_sources;
DROP TABLE IF EXISTS journal_entry_lines;
DROP TABLE IF EXISTS journal_entry_headers;
```

**This SQL is documented for reference only. It is forbidden to run
without explicit rollback owner + accounting owner authorization.**

---

## 5. Rollback Triggers

| Trigger | Rollback Level |
|---|---|
| `psql` exits non-zero, DB inconsistent | Level 1 — PITR |
| App fails to start after migration | Level 1 — PITR |
| 5xx on any report endpoint after migration | Level 2 — flag disable |
| Auth bypass detected after migration | Level 2 — flag disable + Level 1 if persistent |
| Secret exposure in response | Level 2 — immediate investigation |
| Accounting invariant violated (debit ≠ credit in existing data) | Level 1 — PITR |
| New table causes unexpected FK cascade on existing table | Level 3 — last resort |

---

## 6. Rollback Owner Responsibilities

- Has access to Cloud SQL Console or `gcloud sql` to initiate PITR
- Has access to Cloud Run Console to update env vars (Level 2)
- Is on-call during the H69 maintenance window
- Has confirmed PITR restore point before execution starts
- Documents all actions taken during rollback

---

## 7. Post-Rollback Verification

After any rollback:

| Check | Expected |
|---|---|
| `/health` | HTTP 200 |
| `/reports/trial-balance` without auth | 401 |
| `/reports/trial-balance` authenticated | `POSTED_LEDGER_UNAVAILABLE` (graceful) |
| No 5xx | Zero |
| Balance.ge | `demo_mode` |
| Existing bank_transactions data intact | Confirmed via `/reports/cashflow` |
| No secrets in any response | Confirmed |

---

## 8. Rollback Decision

**Decision: `ROLLBACK_PLAN_READY_RESTORE_BASED`**

Rollback plan documented. Default strategy is PITR restore or feature-flag disable.
Destructive DROP is last resort only and requires explicit human authorization.

---

*Bridge Hub — Task 11C-H68. Rollback plan prepared.
ROLLBACK_PLAN_READY_RESTORE_BASED. No SQL executed in H68.*
