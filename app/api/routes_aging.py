"""app/api/routes_aging.py — AR/AP Aging Reports (receivables + payables)."""
import logging
from datetime import date
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, Request, Query

from app.api.authz import require_permission
from app.api.db import get_db
from app.api.response_utils import ok_response
from app.api.tenant_context import resolve_tenant_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/reports/aging", tags=["reports"])

_BUCKETS = [
    ("current",  0,   30,  "მიმდინარე (0–30)"),
    ("31_60",    31,  60,  "31–60 დღე"),
    ("61_90",    61,  90,  "61–90 დღე"),
    ("91_120",   91,  120, "91–120 დღე"),
    ("over_120", 121, None,"120+ დღე"),
]


def _bucket(days_overdue: int) -> str:
    for key, lo, hi, _ in _BUCKETS:
        if days_overdue <= (hi or 999999) and days_overdue >= lo:
            return key
    return "over_120"


def _build_summary(rows: list, as_of: date) -> dict:
    totals = {key: {"label": label, "count": 0, "amount": 0.0}
              for key, _, _, label in _BUCKETS}
    for r in rows:
        due = r.get("due_date")
        if not due:
            k = "current"
        else:
            if isinstance(due, str):
                due = date.fromisoformat(due[:10])
            days = (as_of - due).days
            k = _bucket(max(days, 0))
        totals[k]["count"] += 1
        totals[k]["amount"] = round(totals[k]["amount"] + float(r.get("outstanding", 0) or 0), 2)
    return totals


# ── AR Aging ──────────────────────────────────────────────────────────────────

@router.get("/receivables")
def ar_aging(
    request: Request,
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD, default today"),
    partner: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """
    Accounts Receivable aging — outstanding customer invoices by age bucket.
    Source: invoices table (status = 'sent' | 'overdue').
    """
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = ["tenant_id = %s", "status IN ('sent','overdue','partial')"]
        params: list = [tenant_id]
        if partner:
            conditions.append("partner ILIKE %s")
            params.append(f"%{partner}%")
        where = " AND ".join(conditions)
        cur.execute(f"""
            SELECT
                id, invoice_number, partner, issue_date, due_date,
                total, COALESCE(paid_amount, 0) AS paid_amount,
                total - COALESCE(paid_amount, 0) AS outstanding,
                currency, status, notes
            FROM invoices
            WHERE {where}
              AND total > COALESCE(paid_amount, 0)
            ORDER BY due_date ASC NULLS LAST
            LIMIT %s
        """, params + [limit])
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            for f in ("issue_date", "due_date"):
                if r.get(f):
                    r[f] = str(r[f])[:10]
            if r.get("due_date"):
                due = date.fromisoformat(r["due_date"])
                days = (as_of_date - due).days
                r["days_overdue"] = max(days, 0)
                r["bucket"] = _bucket(max(days, 0))
            else:
                r["days_overdue"] = 0
                r["bucket"] = "current"
    except Exception as e:
        log.warning("ar_aging query failed: %s", e)
        rows = []
    finally:
        cur.close()
        conn.close()

    summary = _build_summary(rows, as_of_date)
    total_outstanding = round(sum(b["amount"] for b in summary.values()), 2)

    return ok_response("AR Aging", {
        "as_of": str(as_of_date),
        "total_outstanding": total_outstanding,
        "buckets": summary,
        "invoices": rows,
    })


# ── AP Aging ──────────────────────────────────────────────────────────────────

@router.get("/payables")
def ap_aging(
    request: Request,
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD, default today"),
    partner: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """
    Accounts Payable aging — outstanding supplier obligations by age bucket.
    Source: journal_drafts with credit_account in payable range (3100–3399).
    """
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = [
            "tenant_id = %s",
            "status IN ('approved','auto_approved','posted')",
            "(credit_account >= '3100' AND credit_account <= '3399')",
            "(reconciled = FALSE OR reconciled IS NULL)",
        ]
        params: list = [tenant_id]
        if partner:
            conditions.append("partner ILIKE %s")
            params.append(f"%{partner}%")
        where = " AND ".join(conditions)
        cur.execute(f"""
            SELECT
                id, date AS issue_date, description, partner,
                ABS(amount) AS outstanding,
                credit_account AS account, status, created_at
            FROM journal_drafts
            WHERE {where}
              AND amount < 0
            ORDER BY date ASC NULLS LAST
            LIMIT %s
        """, params + [limit])
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if r.get("issue_date"):
                r["issue_date"] = str(r["issue_date"])[:10]
            created = r.get("issue_date") or str(r.get("created_at", ""))[:10]
            if created:
                try:
                    created_dt = date.fromisoformat(created[:10])
                    days = (as_of_date - created_dt).days
                    r["days_overdue"] = max(days, 0)
                    r["bucket"] = _bucket(max(days, 0))
                except ValueError:
                    r["days_overdue"] = 0
                    r["bucket"] = "current"
            else:
                r["days_overdue"] = 0
                r["bucket"] = "current"
            r["due_date"] = None  # AP drafts don't have due_date field
    except Exception as e:
        log.warning("ap_aging query failed: %s", e)
        rows = []
    finally:
        cur.close()
        conn.close()

    summary = _build_summary(rows, as_of_date)
    total_outstanding = round(sum(b["amount"] for b in summary.values()), 2)

    return ok_response("AP Aging", {
        "as_of": str(as_of_date),
        "total_outstanding": total_outstanding,
        "buckets": summary,
        "payables": rows,
    })


# ── Combined summary ──────────────────────────────────────────────────────────

@router.get("/summary")
def aging_summary(
    request: Request,
    as_of: Optional[str] = Query(None),
):
    """Quick combined AR + AP snapshot for dashboard widget."""
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE due_date < %s) AS overdue_count,
                COALESCE(SUM(total - COALESCE(paid_amount,0))
                    FILTER (WHERE due_date < %s), 0) AS overdue_amount,
                COALESCE(SUM(total - COALESCE(paid_amount,0)), 0) AS total_ar
            FROM invoices
            WHERE tenant_id = %s AND status IN ('sent','overdue','partial')
              AND total > COALESCE(paid_amount, 0)
        """, (as_of_date, as_of_date, tenant_id))
        ar = cur.fetchone() or (0, 0, 0)

        cur.execute("""
            SELECT
                COUNT(*) AS total_ap_count,
                COALESCE(SUM(ABS(amount)), 0) AS total_ap
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('approved','auto_approved','posted')
              AND (credit_account >= '3100' AND credit_account <= '3399')
              AND amount < 0
              AND (reconciled = FALSE OR reconciled IS NULL)
        """, (tenant_id,))
        ap = cur.fetchone() or (0, 0)
    except Exception:
        ar = (0, 0, 0)
        ap = (0, 0)
    finally:
        cur.close()
        conn.close()

    return ok_response("Aging summary", {
        "as_of": str(as_of_date),
        "ar": {
            "overdue_count": int(ar[0] or 0),
            "overdue_amount": round(float(ar[1] or 0), 2),
            "total_outstanding": round(float(ar[2] or 0), 2),
        },
        "ap": {
            "total_count": int(ap[0] or 0),
            "total_outstanding": round(float(ap[1] or 0), 2),
        },
    })
