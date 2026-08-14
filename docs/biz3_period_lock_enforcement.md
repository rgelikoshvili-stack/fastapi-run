# BIZ-3: Period Lock Enforcement

**Branch:** `codex/biz3-period-lock-reversal-controls`  
**Service:** `app/api/services/period_lock_service.py`

---

## Overview

BIZ-3 introduces a **central period lock enforcement service** that provides a single,
consistent API for checking and enforcing accounting period locks across all mutation
boundaries. Before BIZ-3, each service had its own local period-check helper with
inconsistent naming and coverage.

---

## Database Model

Period locks are stored in the `period_locks` table (created by `routes_period_lock.py`):

```sql
SELECT 1 FROM period_locks
WHERE tenant_id = $1
  AND unlocked_at IS NULL
  AND period_year = $2
  AND (period_month = 0 OR period_month = $3)
LIMIT 1
```

- `period_month = 0` is a full-year lock — blocks all months in that year.
- `unlocked_at IS NULL` = locked. Setting `unlocked_at = NOW()` unlocks.
- `UNIQUE(tenant_id, period_year, period_month)` prevents duplicate rows.

---

## Public API

### `PeriodLockedError`

```python
from app.api.services.period_lock_service import PeriodLockedError

raise PeriodLockedError(
    tenant_id="acme",
    period_year=2025,
    period_month=12,
    action_type="posting",   # or "reversal", "adjustment", etc.
)
```

Attributes: `tenant_id`, `period_year`, `period_month`, `action_type`.  
Message: `"Accounting period is locked/closed (December 2025). Create an adjustment in an open period or unlock with admin approval."`

### `is_period_closed(conn, tenant_id, posting_date) → bool`

Async asyncpg predicate. Returns `True` if the period is locked.

```python
closed = await is_period_closed(conn, "acme", date(2025, 12, 31))
```

- `posting_date` can be a `date` object or ISO string (`"2025-12-31"`).
- Returns `False` if `posting_date` is falsy (no date = no block).

### `assert_period_open(conn, tenant_id, posting_date, action_type="posting")`

Async. Raises `PeriodLockedError` if the period is locked. Call this at **every**
accounting mutation boundary before any DB write.

```python
await assert_period_open(conn, tenant_id, entry_date, "posting")
# safe to INSERT / UPDATE now
```

Also emits a `posting_blocked_period_locked` audit event (best-effort, never raises).

### `is_period_closed_sync(cur, tenant_id, entry_date) → bool`

Sync variant for psycopg2 callers (migrations, legacy services). Uses `%s` placeholders.

---

## Audit Events

| Event | When emitted | Source |
|-------|-------------|--------|
| `period_locked` | After successful lock | `routes_period_lock.py::lock_period` |
| `period_unlocked` | After successful unlock | `routes_period_lock.py::unlock_period` |
| `posting_blocked_period_locked` | When `assert_period_open` blocks | `period_lock_service.py::assert_period_open` |

All events include `actor`, `tenant_id`, `period_year`, `period_month`.

---

## Unlock Requires Reason

The `/accounting/periods/unlock` endpoint (BIZ-3 change) requires a non-blank `reason`:

```json
POST /accounting/periods/unlock
{ "year": 2025, "month": 12, "reason": "Audit adjustment approved by CFO" }
```

If `reason` is blank → HTTP 400 `UNLOCK_REASON_REQUIRED`.

The reason is appended to the `period_locks.notes` column:
```
COALESCE(notes, '') || ' | UNLOCK: ' || $reason
```

---

## RBAC

| Operation | Required Permission | Role (minimum) |
|-----------|-------------------|----------------|
| List periods | `reports:read` | Viewer |
| Lock period | `settings:write` | Accountant |
| Unlock period | `settings:write` | Accountant |
| Reversal / Adjustment | `approval:write` | Accountant |

---

## Usage Pattern for New Services

```python
from app.api.services.period_lock_service import assert_period_open, PeriodLockedError

async def my_posting_function(conn, tenant_id, posting_date, ...):
    # Always first — raises before any DB write
    await assert_period_open(conn, tenant_id, posting_date, "posting")

    # ... safe to write now
    await conn.execute(...)
```

Route handlers catch `PeriodLockedError` and return `error_response(..., "PERIOD_LOCKED")`.

---

## Testing

Unit tests: `tests/unit/test_period_lock_enforcement_biz3.py`

- `TestIsPeriodClosed` — 6 tests (open, locked, None date, string date, date object)
- `TestAssertPeriodOpen` — 10 tests (no raise when open, raises with correct fields, all action_types)
- `TestIsPeriodClosedSync` — 5 tests
- `TestPeriodLockedError` — 7 tests (fields, message, month vs year label)
- `TestRoutesJournalEntriesImport` — 3 import smoke tests
