# Bridge Hub — Posting Ledger Rollout Gates

**Task:** 11C-H70-PRE
**Type:** Design document — rollout gates and feature flag plan for H70.
**Date:** 2026-05-21
**Depends on:** 11C-H69 (Migration 011 production execution success)

---

## 1. Purpose

This document defines the rollout gates, feature flag, and rollback strategy for
deploying H70 (posting to immutable ledger). It ensures H70 writes can be enabled
and disabled safely without modifying code, and that H70 cannot activate before
H69 tables exist.

**Decision: `H70_PRE_DESIGN_READY_WAITING_FOR_H69`**

H70 implementation is blocked until H69 migration success is confirmed.
If H69 has not run: `BLOCKED_H69_MIGRATION_NOT_EXECUTED`
If schema is unavailable: `BLOCKED_LEDGER_SCHEMA_UNAVAILABLE`

---

## 2. Gate Hierarchy

```
GATE-1  H69_PRODUCTION_MIGRATION_SUCCESS_CONFIRMED
         ↓
GATE-2  POSTED_LEDGER_WRITES_ENABLED=true (env var / tenant setting)
         ↓
GATE-3  H70 implementation deployed and verified in staging
         ↓
GATE-4  H70 enabled in production (POSTED_LEDGER_WRITES_ENABLED=true on Cloud Run)
         ↓
GATE-5  Post-enable monitoring (30 min, zero 5xx, no auth bypass, no ledger leak)
         ↓
        H70_PRODUCTION_WRITES_CONFIRMED
```

---

## 3. Gate 1 — H69 Schema Confirmed

**Required before any H70 code is merged to main.**

Check:
```sql
SELECT to_regclass('public.journal_entry_headers') IS NOT NULL
   AND to_regclass('public.journal_entry_lines') IS NOT NULL
   AND to_regclass('public.journal_entry_sources') IS NOT NULL;
```

If any table is missing: `BLOCKED_LEDGER_SCHEMA_UNAVAILABLE`. Do not merge H70.

Gate closure: H69 execution report confirms `MIGRATION_011_PRODUCTION_EXECUTION_SUCCESS`.

---

## 4. Gate 2 — POSTED_LEDGER_WRITES_ENABLED Feature Flag

The H70 implementation must be gated behind:

```python
import os
POSTED_LEDGER_WRITES_ENABLED = os.getenv("POSTED_LEDGER_WRITES_ENABLED", "false").lower() == "true"
```

Behaviour:
- `false` (default): `apply_posting_service` runs exactly as today. No ledger writes.
  H70 code is deployed but dormant. Posting_logs and journal_drafts behave identically
  to pre-H70.
- `true`: ledger writes are active. The additional INSERT statements execute inside
  the same transaction as `posting_logs`.

This flag allows:
- H70 code to be deployed and validated in production with writes off
- Writes to be enabled without a code deploy (Cloud Run env var update only)
- Immediate rollback by setting flag back to `false` without a code change

---

## 5. Gate 3 — Staging Verification

Before enabling in production, verify in a staging environment:

| Check | Expected |
|---|---|
| Mock posting creates header+lines+sources | ✓ one row each |
| Second mock posting same draft | ✓ `POSTING_DUPLICATE_BLOCKED` |
| Connector failure rolls back all rows | ✓ no partial state |
| `ck_jeh_balanced` fires on unbalanced draft | ✓ transaction rolls back |
| `POSTING_DUPLICATE_BLOCKED` still fires | ✓ no duplicate ledger entry |
| Period lock blocks ledger write | ✓ no header row when period is locked |
| Report endpoints still return 401 without auth | ✓ no auth bypass |
| Reports still read `journal_drafts` (H70 does not change report layer) | ✓ |

---

## 6. Gate 4 — Production Enable

To enable H70 writes in production:

```bash
# Cloud Run env var update — requires Cloud Run mutation approval
# gcloud run services update fastapi-run \
#   --region europe-west1 \
#   --update-env-vars POSTED_LEDGER_WRITES_ENABLED=true
```

This command is redacted and not executed in H70-PRE. It requires a separate Cloud Run
mutation approval analogous to the existing deployment gate. No concurrent deploys
or schema changes should be in flight during enable.

---

## 7. Gate 5 — Post-Enable Monitoring

After enabling, the monitoring owner must observe for 30 minutes:

| Check | Method | Expected |
|---|---|---|
| `/health` | HTTP GET | 200, no crash |
| Report endpoints without auth | HTTP GET | 401 — no bypass |
| `journal_entry_headers` row count after test mock posting | DB query | Increments by 1 |
| `journal_entry_lines` count for the test posting | DB query | Equals number of draft lines |
| `journal_entry_sources` count | DB query | 2+ rows per posting |
| No 5xx spike | Monitoring | Zero |
| `journal_drafts.status = 'posted'` still set | DB query | Unchanged behaviour |
| Balance.ge | `/health` | Still `demo_mode` |

If any check fails: set `POSTED_LEDGER_WRITES_ENABLED=false` immediately.

---

## 8. Fallback and Rollback

### 8.1 Flag rollback (preferred)

If H70 ledger writes cause issues after enablement:

1. Set `POSTED_LEDGER_WRITES_ENABLED=false` via Cloud Run env var update.
2. All new postings revert to pre-H70 behaviour immediately.
3. Existing ledger rows remain — do NOT delete them.
4. Investigate ledger rows for consistency; correct via the append-only correction
   pattern if needed.

### 8.2 Correction pattern (not destructive)

Posted ledger rows are immutable — they must never be deleted or updated.
If a write contained incorrect data, use the correction workflow:

1. Insert a new `journal_entry_headers` row with `status = 'correction'`,
   `correction_of_entry_id = original_header_id`.
2. Insert corrected `journal_entry_lines` under the new header.
3. The original rows remain visible in audit queries.
4. Reports can filter `WHERE status = 'posted'` to exclude corrections (or include both).

### 8.3 No DROP TABLE

`DROP TABLE journal_entry_headers` or related tables is a last resort only.
It requires a separate emergency approval that is not part of APPROVAL-2026-H68-001
and must not be executed without explicit written authorisation from the engineering
and accounting owners.

---

## 9. Report Layer Independence

H70 does NOT change the report layer. After H70:

- `/reports/trial-balance` still reads `journal_drafts`
- `/reports/balance-sheet` still reads `journal_drafts`
- `/reports/profit-loss` still reads `journal_drafts`
- `/reports/vat` still reads `journal_drafts`

The `journal_entry_headers` / `journal_entry_lines` tables are written to but not yet
read by reports. Report migration is a separate task (H6 / H71). No report behavior
changes in H70.

---

## 10. Summary of Gates

| Gate | Condition | Status |
|---|---|---|
| GATE-1 | H69 migration success + tables confirmed | BLOCKED — waiting for H69 execution |
| GATE-2 | `POSTED_LEDGER_WRITES_ENABLED=true` | Not set (default false) |
| GATE-3 | Staging verification | Not started |
| GATE-4 | Production enable | Not started |
| GATE-5 | Post-enable monitoring | Not started |

Current overall gate status: `H70_PRE_DESIGN_READY_WAITING_FOR_H69`

---

*Bridge Hub — Task 11C-H70-PRE. Rollout gates plan only.
No runtime code changed. No SQL executed. No production DB connection.
No Cloud Run mutated. No Balance.ge activated.
Decision: H70_PRE_DESIGN_READY_WAITING_FOR_H69.*
