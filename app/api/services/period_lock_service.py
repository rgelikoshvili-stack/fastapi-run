"""app/api/services/period_lock_service.py — Central period-lock enforcement helpers (BIZ-3).

Provides:
  PeriodLockedError          — raised at every blocked mutation boundary
  is_period_closed()         — async predicate (DB-backed via period_locks table)
  assert_period_open()       — raises PeriodLockedError if period is closed
  is_period_closed_sync()    — sync predicate for psycopg2 callers

All DB queries use the same period_locks table populated by routes_period_lock.py.
A period is locked when period_locks.unlocked_at IS NULL for the matching row.

Usage:
    from app.api.services.period_lock_service import assert_period_open, PeriodLockedError

    async def my_posting_function(conn, tenant_id, posting_date, ...):
        await assert_period_open(conn, tenant_id, posting_date, "posting")
        # ... safe to write now
"""
from __future__ import annotations

import logging
from datetime import date as _date
from typing import Union

from app.api.db import _q

log = logging.getLogger(__name__)

try:
    from app.api.audit_service import log_event as _log_event_impl
except Exception:
    _log_event_impl = None  # type: ignore


def log_event(event_type: str, details: dict | None = None, **kwargs) -> None:
    """Module-level shim so tests can patch app.api.services.period_lock_service.log_event."""
    if _log_event_impl is not None:
        try:
            _log_event_impl(event_type, details, **kwargs)
        except Exception as _e:
            log.warning("audit log_event failed: %s", _e)

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class PeriodLockedError(Exception):
    """Raised when a mutation targets a locked/closed accounting period.

    Callers should catch this and return error_response(..., code="PERIOD_LOCKED").
    """

    def __init__(
        self,
        tenant_id: str,
        period_year: int,
        period_month: int,
        action_type: str = "posting",
    ) -> None:
        self.tenant_id   = tenant_id
        self.period_year  = period_year
        self.period_month = period_month
        self.action_type  = action_type
        if period_month:
            month_label = _date(period_year, period_month, 1).strftime("%B %Y")
        else:
            month_label = f"year {period_year}"
        super().__init__(
            f"Accounting period is locked/closed ({month_label}). "
            "Create an adjustment in an open period or unlock with admin approval."
        )


# ---------------------------------------------------------------------------
# Async helpers (asyncpg conn)
# ---------------------------------------------------------------------------

async def is_period_closed(
    conn,
    tenant_id: str,
    posting_date: Union[_date, str],
) -> bool:
    """Return True if the period containing posting_date is locked.

    A period is locked when period_locks has a row with unlocked_at IS NULL
    for the matching (tenant_id, period_year, period_month) or full-year lock
    (period_month = 0).
    """
    if not posting_date:
        return False
    if isinstance(posting_date, str):
        posting_date = _date.fromisoformat(str(posting_date)[:10])
    row = await conn.fetchrow(
        _q("""
            SELECT 1 FROM period_locks
            WHERE tenant_id = %s
              AND unlocked_at IS NULL
              AND period_year = %s
              AND (period_month = 0 OR period_month = %s)
            LIMIT 1
        """),
        tenant_id,
        posting_date.year,
        posting_date.month,
    )
    return row is not None


async def assert_period_open(
    conn,
    tenant_id: str,
    posting_date: Union[_date, str],
    action_type: str = "posting",
) -> None:
    """Raise PeriodLockedError if posting_date falls in a locked period.

    Call this at EVERY accounting mutation boundary before any DB write.
    Lock check occurs before any DB write — no partial write on period failure.
    Also emits a posting_blocked_period_locked audit event (best-effort).
    """
    if not posting_date:
        return
    if isinstance(posting_date, str):
        posting_date = _date.fromisoformat(str(posting_date)[:10])

    closed = await is_period_closed(conn, tenant_id, posting_date)
    if closed:
        log_event(
            "posting_blocked_period_locked",
            {
                "entity_type":  "period_lock",
                "period_year":  posting_date.year,
                "period_month": posting_date.month,
                "action_type":  action_type,
            },
            tenant_id=tenant_id,
        )

        raise PeriodLockedError(
            tenant_id, posting_date.year, posting_date.month, action_type
        )


# ---------------------------------------------------------------------------
# Sync helper (psycopg2 cursor) — mirrors _is_period_locked_sync in posting_service
# ---------------------------------------------------------------------------

def is_period_closed_sync(cur, tenant_id: str, entry_date: Union[_date, str]) -> bool:
    """Sync variant for psycopg2 callers (migrations, legacy services).

    cur must be a psycopg2 cursor (not asyncpg).
    """
    if not entry_date:
        return False
    if not isinstance(entry_date, _date):
        entry_date = _date.fromisoformat(str(entry_date)[:10])
    cur.execute(
        """
        SELECT 1 FROM period_locks
        WHERE tenant_id = %s
          AND unlocked_at IS NULL
          AND period_year = %s
          AND (period_month = 0 OR period_month = %s)
        LIMIT 1
        """,
        (tenant_id, entry_date.year, entry_date.month),
    )
    return cur.fetchone() is not None
