"""app/api/routes_closing.py — Period closing entries (6xxx/7xxx → 3600)."""
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
router = APIRouter(prefix="/accounting", tags=["accounting"])

RETAINED_EARNINGS = "3600"   # განუაწილებელი მოგება
CLOSING_PREFIX    = "CLOSING"


def _account_range(code: str) -> str:
    """Return 'revenue' | 'expense' | 'other'."""
    if code and code[:1] == "6":
        return "revenue"
    if code and code[:1] == "7":
        return "expense"
    return "other"


@router.get("/close-period/preview")
def preview_close(
    request: Request,
    year: int = Query(...),
    month: Optional[int] = Query(None, description="1-12; omit for full-year close"),
):
    """Preview what closing entries would be created."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    date_filter, params = _build_date_filter(tenant_id, year, month)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Revenue accounts (6xxx) — net credit balances
        cur.execute(f"""
            SELECT account_code,
                   COALESCE(SUM(CASE WHEN credit_account = account_code THEN amount ELSE 0 END), 0)
                   - COALESCE(SUM(CASE WHEN debit_account = account_code THEN amount ELSE 0 END), 0) AS net
            FROM (
                SELECT credit_account AS account_code, amount, debit_account FROM journal_drafts
                WHERE {date_filter} AND status IN ('approved','auto_approved','posted')
                  AND credit_account LIKE '6%'
                UNION ALL
                SELECT debit_account AS account_code, amount, credit_account FROM journal_drafts
                WHERE {date_filter} AND status IN ('approved','auto_approved','posted')
                  AND debit_account LIKE '6%'
            ) t
            GROUP BY account_code
            HAVING ABS(COALESCE(SUM(CASE WHEN credit_account = account_code THEN amount ELSE 0 END), 0)
                   - COALESCE(SUM(CASE WHEN debit_account = account_code THEN amount ELSE 0 END), 0)) > 0.001
        """, params + params)
        revenue_rows = [dict(r) for r in cur.fetchall()]

        # Expense accounts (7xxx) — net debit balances
        cur.execute(f"""
            SELECT account_code,
                   COALESCE(SUM(CASE WHEN debit_account = account_code THEN amount ELSE 0 END), 0)
                   - COALESCE(SUM(CASE WHEN credit_account = account_code THEN amount ELSE 0 END), 0) AS net
            FROM (
                SELECT debit_account AS account_code, amount, credit_account FROM journal_drafts
                WHERE {date_filter} AND status IN ('approved','auto_approved','posted')
                  AND debit_account LIKE '7%'
                UNION ALL
                SELECT credit_account AS account_code, amount, debit_account FROM journal_drafts
                WHERE {date_filter} AND status IN ('approved','auto_approved','posted')
                  AND credit_account LIKE '7%'
            ) t
            GROUP BY account_code
            HAVING ABS(COALESCE(SUM(CASE WHEN debit_account = account_code THEN amount ELSE 0 END), 0)
                   - COALESCE(SUM(CASE WHEN credit_account = account_code THEN amount ELSE 0 END), 0)) > 0.001
        """, params + params)
        expense_rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

    total_revenue = round(sum(float(r["net"]) for r in revenue_rows), 2)
    total_expenses = round(sum(float(r["net"]) for r in expense_rows), 2)
    net_income = round(total_revenue - total_expenses, 2)

    label = _period_label(year, month)
    return ok_response("Closing preview", {
        "period": label,
        "year": year,
        "month": month,
        "revenue_accounts": [{"code": r["account_code"], "amount": float(r["net"])} for r in revenue_rows],
        "expense_accounts": [{"code": r["account_code"], "amount": float(r["net"])} for r in expense_rows],
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_income": net_income,
        "entries_count": len(revenue_rows) + len(expense_rows) + (1 if net_income != 0 else 0),
    })


@router.post("/close-period")
def close_period(request: Request, payload: dict):
    """
    Execute period closing:
    1. Dr each 6xxx account (zero out revenue)
    2. Cr each 7xxx account (zero out expenses)
    3. Net difference → 3600 (retained earnings)
    All entries get status='posted', source_type='closing'.
    """
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    year  = int(payload.get("year", date.today().year))
    month = payload.get("month")
    month = int(month) if month is not None else None
    user  = getattr(request.state, "user_email", "system")

    # Check period not already closed
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT 1 FROM journal_drafts
            WHERE tenant_id = %s AND source_type = 'closing'
              AND EXTRACT(YEAR FROM date) = %s
              AND (%s IS NULL OR EXTRACT(MONTH FROM date) = %s)
            LIMIT 1
        """, (tenant_id, year, month, month))
        if cur.fetchone():
            cur.close()
            conn.close()
            return http_error(409, f"Period {_period_label(year, month)} already closed", "ALREADY_CLOSED")
    except Exception:
        pass

    date_filter, params = _build_date_filter(tenant_id, year, month)
    close_date = date(year, month or 12, 28 if (month or 12) != 2 else 28)

    try:
        # Revenue balances
        cur.execute(f"""
            SELECT
                CASE WHEN credit_account LIKE '6%' THEN credit_account ELSE debit_account END AS account_code,
                COALESCE(SUM(CASE WHEN credit_account LIKE '6%' THEN amount ELSE -amount END), 0) AS net
            FROM journal_drafts
            WHERE {date_filter}
              AND status IN ('approved','auto_approved','posted')
              AND (credit_account LIKE '6%' OR debit_account LIKE '6%')
            GROUP BY 1
            HAVING ABS(SUM(CASE WHEN credit_account LIKE '6%' THEN amount ELSE -amount END)) > 0.001
        """, params)
        revenue_rows = [dict(r) for r in cur.fetchall()]

        # Expense balances
        cur.execute(f"""
            SELECT
                CASE WHEN debit_account LIKE '7%' THEN debit_account ELSE credit_account END AS account_code,
                COALESCE(SUM(CASE WHEN debit_account LIKE '7%' THEN amount ELSE -amount END), 0) AS net
            FROM journal_drafts
            WHERE {date_filter}
              AND status IN ('approved','auto_approved','posted')
              AND (debit_account LIKE '7%' OR credit_account LIKE '7%')
            GROUP BY 1
            HAVING ABS(SUM(CASE WHEN debit_account LIKE '7%' THEN amount ELSE -amount END)) > 0.001
        """, params)
        expense_rows = [dict(r) for r in cur.fetchall()]

        label = _period_label(year, month)
        entries_created = 0

        # Close revenue accounts → Dr 6xxx / Cr 3600
        for r in revenue_rows:
            amt = round(float(r["net"]), 2)
            if abs(amt) < 0.01:
                continue
            cur.execute("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, amount,
                     debit_account, credit_account, account_code,
                     reason, confidence, status, source_type, approved_by_mode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1.0, 'posted', 'closing', 'system')
            """, (
                tenant_id, close_date,
                f"{CLOSING_PREFIX} {label} — Close {r['account_code']}",
                abs(amt),
                r["account_code"] if amt > 0 else RETAINED_EARNINGS,
                RETAINED_EARNINGS if amt > 0 else r["account_code"],
                r["account_code"],
                f"period_close_revenue_{year}_{month or 'annual'}",
            ))
            entries_created += 1

        # Close expense accounts → Dr 3600 / Cr 7xxx
        for r in expense_rows:
            amt = round(float(r["net"]), 2)
            if abs(amt) < 0.01:
                continue
            cur.execute("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, amount,
                     debit_account, credit_account, account_code,
                     reason, confidence, status, source_type, approved_by_mode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1.0, 'posted', 'closing', 'system')
            """, (
                tenant_id, close_date,
                f"{CLOSING_PREFIX} {label} — Close {r['account_code']}",
                abs(amt),
                RETAINED_EARNINGS if amt > 0 else r["account_code"],
                r["account_code"] if amt > 0 else RETAINED_EARNINGS,
                r["account_code"],
                f"period_close_expense_{year}_{month or 'annual'}",
            ))
            entries_created += 1

        conn.commit()
        log.info("action=period_close tenant=%s period=%s entries=%d by=%s",
                 tenant_id, label, entries_created, user)

        total_rev  = round(sum(float(r["net"]) for r in revenue_rows), 2)
        total_exp  = round(sum(float(r["net"]) for r in expense_rows), 2)
        net_income = round(total_rev - total_exp, 2)

        return ok_response(f"Period closed: {label}", {
            "period": label,
            "entries_created": entries_created,
            "total_revenue_closed": total_rev,
            "total_expenses_closed": total_exp,
            "net_income_to_retained": net_income,
        })
    except Exception as e:
        conn.rollback()
        log.error("close_period error: %s", e)
        return http_error(500, str(e), "CLOSE_ERROR")
    finally:
        cur.close()
        conn.close()


def _build_date_filter(tenant_id: str, year: int, month: Optional[int]):
    if month:
        return (
            "tenant_id = %s AND EXTRACT(YEAR FROM date) = %s AND EXTRACT(MONTH FROM date) = %s",
            [tenant_id, year, month],
        )
    return (
        "tenant_id = %s AND EXTRACT(YEAR FROM date) = %s",
        [tenant_id, year],
    )


def _period_label(year: int, month: Optional[int]) -> str:
    if not month:
        return f"FY {year}"
    return date(year, month, 1).strftime("%B %Y")
