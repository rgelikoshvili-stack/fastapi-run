"""app/api/routes_period_lock.py — Accounting period lock/unlock."""
import logging
from datetime import date
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, Request, Query

from app.api.authz import require_permission
from app.api.db import get_db
from app.api.response_utils import ok_response, http_error
from app.api.tenant_context import resolve_tenant_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/accounting/periods", tags=["accounting"])


def _ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS period_locks (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,  -- 0 = full year lock
            locked_by   TEXT,
            locked_at   TIMESTAMP DEFAULT NOW(),
            unlocked_at TIMESTAMP,
            notes       TEXT,
            UNIQUE(tenant_id, period_year, period_month)
        )
    """)
    conn.commit()
    cur.close()


def is_period_locked(conn, tenant_id: str, entry_date: date) -> bool:
    """Check if a given date falls in a locked period."""
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 1 FROM period_locks
            WHERE tenant_id = %s
              AND unlocked_at IS NULL
              AND period_year = %s
              AND (period_month = 0 OR period_month = %s)
            LIMIT 1
        """, (tenant_id, entry_date.year, entry_date.month))
        return cur.fetchone() is not None
    finally:
        cur.close()


@router.get("")
def list_periods(
    request: Request,
    year: Optional[int] = Query(None),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    target_year = year or date.today().year

    conn = get_db()
    try:
        _ensure_table(conn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT period_year, period_month, locked_by, locked_at, unlocked_at, notes
            FROM period_locks
            WHERE tenant_id = %s AND period_year = %s
            ORDER BY period_month
        """, (tenant_id, target_year))
        locked = {r["period_month"]: dict(r) for r in cur.fetchall()}
        cur.close()
    finally:
        conn.close()

    periods = []
    for m in range(0, 13):  # 0 = full year, 1-12 = months
        lock = locked.get(m)
        periods.append({
            "year": target_year,
            "month": m,
            "label": "Full Year" if m == 0 else date(target_year, m, 1).strftime("%B %Y"),
            "locked": lock is not None and lock.get("unlocked_at") is None,
            "locked_by": lock.get("locked_by") if lock else None,
            "locked_at": str(lock["locked_at"])[:19] if lock and lock.get("locked_at") else None,
            "notes": lock.get("notes") if lock else None,
        })

    return ok_response("Periods", {"year": target_year, "periods": periods})


@router.post("/lock")
def lock_period(request: Request, payload: dict):
    """Lock a period. payload: {year, month, notes}"""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    year  = int(payload.get("year", date.today().year))
    month = int(payload.get("month", 0))
    notes = str(payload.get("notes", ""))
    user  = getattr(request.state, "user_email", "system")

    if month not in range(0, 13):
        return http_error(400, "month must be 0–12 (0 = full year)", "INVALID_MONTH")

    conn = get_db()
    try:
        _ensure_table(conn)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO period_locks (tenant_id, period_year, period_month, locked_by, notes)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, period_year, period_month)
            DO UPDATE SET locked_by=%s, locked_at=NOW(), unlocked_at=NULL, notes=%s
        """, (tenant_id, year, month, user, notes, user, notes))
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        conn.close()
        return http_error(500, str(e), "DB_ERROR")
    finally:
        conn.close()

    label = "Full Year" if month == 0 else date(year, month, 1).strftime("%B %Y")
    log.info("action=period_lock tenant=%s year=%d month=%d by=%s", tenant_id, year, month, user)
    return ok_response(f"Period locked: {label} {year}", {"year": year, "month": month, "locked": True})


@router.post("/unlock")
def unlock_period(request: Request, payload: dict):
    """Unlock a period. payload: {year, month}"""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    year  = int(payload.get("year", date.today().year))
    month = int(payload.get("month", 0))
    user  = getattr(request.state, "user_email", "system")

    conn = get_db()
    try:
        _ensure_table(conn)
        cur = conn.cursor()
        cur.execute("""
            UPDATE period_locks
            SET unlocked_at = NOW(), locked_by = %s
            WHERE tenant_id = %s AND period_year = %s AND period_month = %s
        """, (user, tenant_id, year, month))
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        conn.close()
        return http_error(500, str(e), "DB_ERROR")
    finally:
        conn.close()

    log.info("action=period_unlock tenant=%s year=%d month=%d by=%s", tenant_id, year, month, user)
    return ok_response("Period unlocked", {"year": year, "month": month, "locked": False})
