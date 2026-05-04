"""
app/api/services/insights_service.py
Bridge Hub — Dashboard Insights (read-only aggregates)
"""
import logging
from decimal import Decimal

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)

_EXPENSE_PREFIX = "7"
_INCOME_PREFIX = "6"


async def _detect_duplicates(conn, tenant_id: str) -> list:
    """Find possible duplicate transactions within last 24 hours."""
    try:
        from rapidfuzz import fuzz as _rff
    except ImportError:
        return []

    rows = [dict(r) for r in await conn.fetch(_q("""
        SELECT id, description, amount, created_at
        FROM journal_drafts
        WHERE tenant_id = %s
          AND created_at >= NOW() - INTERVAL '24 hours'
        ORDER BY created_at DESC
        LIMIT 200
    """), tenant_id)]

    seen = set()
    duplicates = []
    for i, a in enumerate(rows):
        for j, b in enumerate(rows):
            if i >= j:
                continue
            pair_key = (min(a["id"], b["id"]), max(a["id"], b["id"]))
            if pair_key in seen:
                continue
            amt_a = float(a["amount"] or 0)
            amt_b = float(b["amount"] or 0)
            if abs(amt_a - amt_b) < 0.01:
                score = _rff.WRatio(str(a["description"] or ""), str(b["description"] or ""))
                if score >= 80:
                    seen.add(pair_key)
                    duplicates.append({
                        "id_a": a["id"],
                        "id_b": b["id"],
                        "description": a["description"],
                        "amount": amt_a,
                        "similarity_pct": score,
                        "possible_duplicate": True,
                    })
                    if len(duplicates) >= 10:
                        return duplicates
    return duplicates


async def _calculate_runway(conn, tenant_id: str) -> dict:
    """Estimate cash runway based on last 30 days expense burn rate."""
    try:
        row = await conn.fetchrow(_q("""
            SELECT COALESCE(SUM(amount), 0) / 30.0 AS daily_burn
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status = 'approved'
              AND account_code LIKE '7%%'
              AND date >= CURRENT_DATE - INTERVAL '30 days'
        """), tenant_id)
        daily_burn = float(row["daily_burn"] or 0) if row else 0

        row2 = await conn.fetchrow(_q("""
            SELECT COALESCE(SUM(
                CASE WHEN account_code IN ('1110','1120') THEN amount ELSE 0 END
            ), 0) AS cash_balance
            FROM journal_drafts
            WHERE tenant_id = %s AND status = 'approved'
        """), tenant_id)
        cash_balance = float(row2["cash_balance"] or 0) if row2 else 0

        runway_days = int(cash_balance / daily_burn) if daily_burn > 0 else None
        return {
            "daily_burn_gel": round(daily_burn, 2),
            "estimated_cash_balance": round(cash_balance, 2),
            "runway_days": runway_days,
            "warning": runway_days is not None and runway_days < 30,
        }
    except Exception as e:
        log.warning("runway calc failed: %s", e)
        return {"daily_burn_gel": None, "estimated_cash_balance": None, "runway_days": None, "warning": False}


async def _add_anomaly_flags(anomalies: list, conn, tenant_id: str) -> list:
    """Flag anomalies where amount > 1.5× historical average for that account_code."""
    if not anomalies:
        return anomalies

    account_codes = list({a["account_code"] for a in anomalies if a.get("account_code")})
    if not account_codes:
        return anomalies

    avgs = {}
    try:
        rows = await conn.fetch(_q("""
            SELECT account_code, AVG(amount) AS avg_amount
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status = 'approved'
              AND account_code = ANY(%s)
            GROUP BY account_code
        """), tenant_id, account_codes)
        avgs = {r["account_code"]: float(r["avg_amount"] or 0) for r in rows}
    except Exception:
        pass

    result = []
    for a in anomalies:
        entry = dict(a)
        avg = avgs.get(a.get("account_code"))
        if avg and avg > 0:
            entry["historical_avg"] = round(avg, 2)
            entry["is_anomaly"] = float(a.get("amount") or 0) > 1.5 * avg
        else:
            entry["historical_avg"] = None
            entry["is_anomaly"] = None
        result.append(entry)
    return result


async def get_dashboard_insights(tenant_id: str) -> dict:
    try:
        async with get_conn() as conn:
            top_expenses = [dict(r) for r in await conn.fetch(_q("""
                SELECT account_code,
                       COUNT(*) AS count,
                       COALESCE(SUM(amount), 0) AS total
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND status = 'approved'
                  AND account_code LIKE '7%%'
                GROUP BY account_code
                ORDER BY total DESC
                LIMIT 10
            """), tenant_id)]

            rev_exp = dict(await conn.fetchrow(_q("""
                SELECT
                    COALESCE(SUM(amount) FILTER (WHERE account_code LIKE '6%%'), 0) AS total_revenue,
                    COALESCE(SUM(amount) FILTER (WHERE account_code LIKE '7%%'), 0) AS total_expenses
                FROM journal_drafts
                WHERE tenant_id = %s AND status = 'approved'
            """), tenant_id) or {})
            total_revenue = float(rev_exp.get("total_revenue") or 0)
            total_expenses = float(rev_exp.get("total_expenses") or 0)
            net = round(total_revenue - total_expenses, 2)

            queue = dict(await conn.fetchrow(_q("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending_approval') AS pending_approval,
                    COUNT(*) FILTER (WHERE status = 'drafted') AS drafted,
                    COUNT(*) FILTER (WHERE review_required = TRUE AND status = 'drafted') AS needs_review
                FROM journal_drafts WHERE tenant_id = %s
            """), tenant_id) or {})

            anomalies = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, description, amount, date, account_code, status
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND amount >= 5000
                  AND status IN ('drafted', 'pending_approval')
                ORDER BY amount DESC
                LIMIT 10
            """), tenant_id)]

            trends = [dict(r) for r in await conn.fetch(_q("""
                SELECT
                    TO_CHAR(DATE_TRUNC('month', date::date), 'YYYY-MM') AS month,
                    COALESCE(SUM(amount) FILTER (WHERE account_code LIKE '6%%'), 0) AS revenue,
                    COALESCE(SUM(amount) FILTER (WHERE account_code LIKE '7%%'), 0) AS expenses
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND status = 'approved'
                  AND date::date >= CURRENT_DATE - INTERVAL '6 months'
                GROUP BY DATE_TRUNC('month', date::date)
                ORDER BY DATE_TRUNC('month', date::date)
            """), tenant_id)]

            possible_duplicates = await _detect_duplicates(conn, tenant_id)
            runway = await _calculate_runway(conn, tenant_id)

            raw_anomalies = [
                {
                    "id": r["id"],
                    "description": r["description"],
                    "amount": float(r["amount"] or 0),
                    "date": str(r["date"]) if r["date"] else None,
                    "account_code": r["account_code"],
                    "status": r["status"],
                    "alert": "high_value",
                }
                for r in anomalies
            ]
            flagged_anomalies = await _add_anomaly_flags(raw_anomalies, conn, tenant_id)

    except Exception as e:
        log.error("insights_service tenant=%s: %s", tenant_id, e)
        return {"ok": False, "error": {"code": "INSIGHTS_ERROR", "details": str(e)}}

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "top_expenses": [
            {"account_code": r["account_code"], "count": r["count"], "total": float(r["total"])}
            for r in top_expenses
        ],
        "revenue_vs_expenses": {
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net": net,
            "profitable": net >= 0,
        },
        "approval_queue": {
            "pending_approval": queue.get("pending_approval", 0),
            "drafted": queue.get("drafted", 0),
            "needs_review": queue.get("needs_review", 0),
        },
        "anomalies": flagged_anomalies,
        "trends": [
            {
                "month": r["month"],
                "revenue": float(r["revenue"]),
                "expenses": float(r["expenses"]),
                "net": round(float(r["revenue"]) - float(r["expenses"]), 2),
            }
            for r in trends
        ],
        "possible_duplicates": possible_duplicates,
        "runway": runway,
    }
