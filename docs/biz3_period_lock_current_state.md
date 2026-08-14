# BIZ-3 Audit: Period Lock Current State (Pre-BIZ-3 Baseline)

**Date:** 2026-08-14  
**Branch:** `codex/biz3-period-lock-reversal-controls`  
**Author:** Automated (BIZ-3 Phase 1 audit)

---

## 1. What Existed Before BIZ-3

### 1.1 `period_locks` Table

The table was already defined in `routes_period_lock.py` as an inline `CREATE TABLE IF NOT EXISTS`:

```sql
CREATE TABLE IF NOT EXISTS period_locks (
    id           SERIAL PRIMARY KEY,
    tenant_id    TEXT NOT NULL DEFAULT 'default',
    period_year  INTEGER NOT NULL,
    period_month INTEGER NOT NULL,   -- 0 = full-year lock
    locked_by    TEXT,
    locked_at    TIMESTAMP DEFAULT NOW(),
    unlocked_at  TIMESTAMP,          -- NULL = locked
    notes        TEXT,
    UNIQUE(tenant_id, period_year, period_month)
)
```

A period is **locked** when `unlocked_at IS NULL`. Unlocking sets `unlocked_at = NOW()`.

### 1.2 Existing Routes (`/accounting/periods`)

| Method | Path | Permission | Notes |
|--------|------|-----------|-------|
| `GET`  | `/accounting/periods` | `reports:read` | Lists 13 periods (0=full year, 1–12=months) |
| `POST` | `/accounting/periods/lock` | `settings:write` | Upsert lock row |
| `POST` | `/accounting/periods/unlock` | `settings:write` | Sets `unlocked_at=NOW()` |

**Gaps before BIZ-3:**
- Unlock required **no reason** — any authorized user could silently unlock.
- Lock and unlock emitted **no audit events** to the audit log.
- No enforcement at mutation boundaries — posting service had a local `_is_period_locked_sync()` helper but it was inconsistently applied.

### 1.3 Existing Check in Posting Service

`app/api/services/posting_service.py` contained a local psycopg2-based helper:

```python
def _is_period_locked_sync(cur, tenant_id, entry_date) -> bool:
    # Queried period_locks directly, psycopg2 cursor
```

This was only invoked during the ERP dispatch path. It was **not reusable** by other services.

### 1.4 GeoTrade Integration Test Gap

`tests/integration/test_business_scenario_geotrade_full_coverage.py` contained:

```python
@pytest.mark.xfail(reason="EXPECTED_GAP_PERIOD_LOCK: ...")
def test_locked_period_blocks_new_posting(self):
    raise NotImplementedError("Period lock requires DB")
```

This xfail marked the gap explicitly. BIZ-3 closes it.

---

## 2. What BIZ-3 Adds

| Component | File | Purpose |
|-----------|------|---------|
| `PeriodLockedError` | `app/api/services/period_lock_service.py` | Typed exception at every blocked boundary |
| `is_period_closed()` | same | Async asyncpg check |
| `assert_period_open()` | same | Raises `PeriodLockedError` + emits audit event |
| `is_period_closed_sync()` | same | Sync psycopg2 mirror |
| Unlock reason enforcement | `routes_period_lock.py` | `UNLOCK_REASON_REQUIRED` error if blank |
| Audit events | `routes_period_lock.py` | `period_locked`, `period_unlocked` events |
| `flip_lines()` | `app/api/services/reversal_service.py` | Swap DR↔CR on every line |
| `create_reversal_draft()` | same | Full reversal workflow |
| `create_adjustment_draft()` | same | Correcting entry workflow |
| Reversal/adjustment routes | `app/api/routes_journal_entries.py` | `/api/journal-entries/{id}/reverse` + `/adjust` |
| DB columns | `app/startup/migrations.py` | `reversal_of_draft_id`, `reversal_reason`, `entry_type` |
| 83 unit tests | `tests/unit/test_period_lock_*_biz3.py` | Coverage of all new paths |

---

## 3. Gap Closure Confirmation

| Gap | Status after BIZ-3 |
|-----|-------------------|
| `EXPECTED_GAP_PERIOD_LOCK` xfail | Closed — 7 passing mock-based period lock tests replace it |
| No central enforcement service | Closed — `period_lock_service.py` is the single source of truth |
| Unlock without reason | Closed — `UNLOCK_REASON_REQUIRED` HTTP 400 if reason blank |
| No audit trail for lock/unlock | Closed — `period_locked` / `period_unlocked` events emitted |
| No reversal/adjustment workflow | Closed — `reversal_service.py` + 2 new API endpoints |
| No duplicate reversal protection | Closed — `_reversal_already_exists()` check before insert |
