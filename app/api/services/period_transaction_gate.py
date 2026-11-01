"""FIN-11: serialize posting vs month/year close/reopen in one transaction.

Postings acquire shared year + shared month locks; month close obtains shared
year + exclusive month, year close obtains exclusive year. All locks use
pg_advisory_xact_lock and MUST be held through commit/rollback. Missing storage
or transaction means BLOCK, not an open period. Draft only; no production DDL.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from app.api.db import _validate_tenant_id, _q


class PeriodGateUnavailable(ValueError):
    """Fail closed when the trusted period or locking operation is unavailable."""


def _deny() -> None:
    raise PeriodGateUnavailable("PERIOD_LOCK_UNAVAILABLE")


def _tenant(value: str) -> str:
    try:
        return _validate_tenant_id(value)
    except ValueError:
        _deny()


def _date(value) -> date:
    if isinstance(value, datetime):
        _deny()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) != 10:
        _deny()
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        _deny()


def _period(year: int, month: int) -> tuple[int, int]:
    if (type(year) is not int or type(month) is not int
            or not 1 <= year <= 9999 or not 0 <= month <= 12):
        _deny()
    return year, month


def _key(tenant: str, year: int, month: int) -> str:
    return json.dumps(["bridge-period-v1", tenant, year, month],
                      separators=(",", ":"), ensure_ascii=True)


async def _lock(conn, key: str, *, shared: bool) -> None:
    if conn.is_in_transaction() is not True:
        raise PeriodGateUnavailable("PERIOD_LOCK_TRANSACTION_REQUIRED")
    sql = ("SELECT pg_advisory_xact_lock_shared(hashtextextended(%s,0))"
           if shared else "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))")
    try:
        await conn.execute(_q(sql), key)
    except Exception:
        _deny()


async def acquire_posting_gate(conn, tenant_id: str, posting_date) -> None:
    """Caller checks period_locks and writes within this SAME transaction."""
    tenant = _tenant(tenant_id)
    day = _date(posting_date)
    await _lock(conn, _key(tenant, day.year, 0), shared=True)
    await _lock(conn, _key(tenant, day.year, day.month), shared=True)


async def acquire_close_gate(conn, tenant_id: str, year: int, month: int) -> None:
    """Caller updates period_locks within this SAME transaction."""
    tenant = _tenant(tenant_id)
    y, m = _period(year, month)
    await _lock(conn, _key(tenant, y, 0), shared=m != 0)
    if m != 0:
        await _lock(conn, _key(tenant, y, m), shared=False)
