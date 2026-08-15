"""app/api/services/cockpit_service.py

Sprint 5 — Chief Accountant Cockpit.
Read-only aggregated dashboard: risks, pending approvals, recent actions,
ledger health, and bank reconciliation gaps.
"""
from __future__ import annotations

import logging
from typing import Any

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)

# Thresholds
HIGH_AMOUNT_GEL = 5_000.0
LOW_CONFIDENCE = 0.6
RECENT_LIMIT = 10
RISK_LIMIT = 20
PENDING_LIMIT = 20


def _safe(row: Any) -> dict:
    if row is None:
        return {}
    import decimal
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, decimal.Decimal):
            d[k] = float(v)
        elif hasattr(v, "isoformat"):
            d[k] = str(v)
    return d


def _safe_list(rows) -> list[dict]:
    return [_safe(r) for r in (rows or [])]


# ─────────────────────────────────────────────────────────────────────────────
# Individual sections
# ─────────────────────────────────────────────────────────────────────────────

async def _get_risks(conn, tenant_id: str) -> dict:
    """High-risk drafts: low confidence, high amount without posting, missing fields."""
    try:
        rows = await conn.fetch(_q("""
            SELECT id, description, amount, partner, account_code,
                   debit_account, credit_account, status, confidence,
                   source_type, date, created_at,
                   CASE
                       WHEN confidence IS NOT NULL AND confidence < %s THEN 'low_confidence'
                       WHEN COALESCE(amount, 0) > %s THEN 'high_amount'
                       WHEN partner IS NULL THEN 'missing_partner'
                       WHEN debit_account IS NULL OR credit_account IS NULL THEN 'missing_accounts'
                       ELSE 'other'
                   END AS risk_reason
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('drafted', 'approved', 'auto_approved')
              AND (
                  (confidence IS NOT NULL AND confidence < %s)
                  OR COALESCE(amount, 0) > %s
                  OR partner IS NULL
                  OR debit_account IS NULL
                  OR credit_account IS NULL
              )
            ORDER BY
                CASE WHEN confidence IS NOT NULL AND confidence < %s THEN 0 ELSE 1 END,
                COALESCE(amount, 0) DESC
            LIMIT %s
        """), LOW_CONFIDENCE, HIGH_AMOUNT_GEL, tenant_id,
             LOW_CONFIDENCE, HIGH_AMOUNT_GEL, LOW_CONFIDENCE, RISK_LIMIT)

        low_conf = sum(1 for r in rows if r.get("risk_reason") == "low_confidence")
        high_amt = sum(1 for r in rows if r.get("risk_reason") == "high_amount")
        missing = sum(1 for r in rows if r.get("risk_reason") in ("missing_partner", "missing_accounts"))

        return {
            "count": len(rows),
            "low_confidence_count": low_conf,
            "high_amount_count": high_amt,
            "missing_fields_count": missing,
            "items": _safe_list(rows),
        }
    except Exception as e:
        log.warning("cockpit _get_risks: %s", e)
        return {"count": 0, "items": [], "error": str(e)}


async def _get_pending(conn, tenant_id: str) -> dict:
    """Pending approval queue: drafted, pending_approval, awaiting_cfo."""
    try:
        rows = await conn.fetch(_q("""
            SELECT id, description, amount, partner, status,
                   confidence, source_type, date, created_at
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('drafted', 'pending_approval', 'awaiting_cfo')
            ORDER BY
                CASE status
                    WHEN 'awaiting_cfo' THEN 0
                    WHEN 'pending_approval' THEN 1
                    ELSE 2
                END,
                COALESCE(amount, 0) DESC
            LIMIT %s
        """), tenant_id, PENDING_LIMIT)

        total = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('drafted', 'pending_approval', 'awaiting_cfo')
        """), tenant_id) or 0

        awaiting_cfo = sum(1 for r in rows if r.get("status") == "awaiting_cfo")
        pending_approval = sum(1 for r in rows if r.get("status") == "pending_approval")
        drafted = sum(1 for r in rows if r.get("status") == "drafted")

        return {
            "total": int(total),
            "awaiting_cfo": awaiting_cfo,
            "pending_approval": pending_approval,
            "drafted": drafted,
            "items": _safe_list(rows),
        }
    except Exception as e:
        log.warning("cockpit _get_pending: %s", e)
        return {"total": 0, "items": [], "error": str(e)}


async def _get_recent_actions(conn, tenant_id: str) -> dict:
    """Last N significant events: postings and approvals."""
    try:
        # Recent postings (success + failed)
        postings = await conn.fetch(_q("""
            SELECT pl.id, pl.draft_id, pl.target_system, pl.status,
                   pl.error_message, pl.mode, pl.actor, pl.created_at,
                   jd.description, jd.amount, jd.partner
            FROM posting_logs pl
            LEFT JOIN journal_drafts jd
                ON jd.id = pl.draft_id AND jd.tenant_id = pl.tenant_id
            WHERE pl.tenant_id = %s
              AND pl.status IN ('success', 'failed')
            ORDER BY pl.created_at DESC
            LIMIT %s
        """), tenant_id, RECENT_LIMIT)

        # Recent approvals / rejections
        approvals = await conn.fetch(_q("""
            SELECT id, description, amount, partner, status, date, created_at
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('approved', 'auto_approved', 'rejected', 'posted')
            ORDER BY created_at DESC
            LIMIT %s
        """), tenant_id, RECENT_LIMIT)

        posting_events = []
        for r in postings:
            d = _safe(r)
            d["event_type"] = "posting_success" if r.get("status") == "success" else "posting_failed"
            posting_events.append(d)

        approval_events = []
        for r in approvals:
            d = _safe(r)
            d["event_type"] = f"draft_{r.get('status', 'unknown')}"
            approval_events.append(d)

        return {
            "postings": posting_events,
            "approvals": approval_events,
        }
    except Exception as e:
        log.warning("cockpit _get_recent_actions: %s", e)
        return {"postings": [], "approvals": [], "error": str(e)}


async def _get_ledger_health(conn, tenant_id: str) -> dict:
    """Quick ledger health counts (reuse logic without importing full service)."""
    try:
        phantom = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM journal_drafts jd
            WHERE jd.tenant_id = %s AND jd.status = 'posted'
              AND NOT EXISTS (
                  SELECT 1 FROM posting_logs pl
                  WHERE pl.tenant_id = jd.tenant_id AND pl.draft_id = jd.id
                    AND pl.status = 'success'
              )
        """), tenant_id) or 0

        failed_unretried = await conn.fetchval(_q("""
            SELECT COUNT(DISTINCT pl.draft_id) FROM posting_logs pl
            WHERE pl.tenant_id = %s AND pl.status = 'failed'
              AND NOT EXISTS (
                  SELECT 1 FROM posting_logs pl2
                  WHERE pl2.tenant_id = pl.tenant_id AND pl2.draft_id = pl.draft_id
                    AND pl2.status = 'success'
              )
        """), tenant_id) or 0

        score = max(0, 100 - int(phantom) * 20 - int(failed_unretried) * 10)
        return {
            "health_score": score,
            "health_label": "HEALTHY" if score >= 90 else ("WARNING" if score >= 60 else "CRITICAL"),
            "phantom_posts": int(phantom),
            "failed_unretried": int(failed_unretried),
        }
    except Exception as e:
        log.warning("cockpit _get_ledger_health: %s", e)
        return {"health_score": None, "error": str(e)}


async def _get_unreconciled_bank(conn, tenant_id: str) -> dict:
    """Count bank transactions not linked to any journal draft (approximate)."""
    try:
        total_txn = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM bank_transactions WHERE tenant_id = %s
        """), tenant_id) or 0

        # transactions whose description or partner appears in NO journal_draft
        # (lightweight proxy — exact reconciliation is a separate sprint)
        unreconciled_est = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM bank_transactions bt
            WHERE bt.tenant_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM journal_drafts jd
                  WHERE jd.tenant_id = bt.tenant_id
                    AND (
                        jd.description ILIKE '%%' || bt.description || '%%'
                        OR (bt.partner IS NOT NULL AND jd.partner ILIKE '%%' || bt.partner || '%%')
                    )
              )
        """), tenant_id) or 0

        return {
            "total_bank_transactions": int(total_txn),
            "unreconciled_estimate": int(unreconciled_est),
            "reconciled_estimate": int(total_txn) - int(unreconciled_est),
        }
    except Exception as e:
        log.warning("cockpit _get_unreconciled_bank: %s", e)
        return {"total_bank_transactions": 0, "unreconciled_estimate": 0, "error": str(e)}


async def _get_period_stats(conn, tenant_id: str) -> dict:
    """Current-month draft and posting counts."""
    try:
        stats = _safe(await conn.fetchrow(_q("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'posted')       AS posted_count,
                COUNT(*) FILTER (WHERE status IN ('approved','auto_approved')) AS approved_count,
                COUNT(*) FILTER (WHERE status IN ('drafted','pending_approval','awaiting_cfo')) AS pending_count,
                COUNT(*) FILTER (WHERE status = 'rejected')     AS rejected_count,
                COALESCE(SUM(amount) FILTER (WHERE status = 'posted'), 0)  AS posted_gel,
                COALESCE(SUM(amount) FILTER (WHERE status IN ('approved','auto_approved')), 0) AS approved_gel
            FROM journal_drafts
            WHERE tenant_id = %s
              AND date >= date_trunc('month', CURRENT_DATE)::TEXT
        """), tenant_id))
        return stats or {}
    except Exception as e:
        log.warning("cockpit _get_period_stats: %s", e)
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Main cockpit entry point
# ─────────────────────────────────────────────────────────────────────────────

async def get_cockpit(tenant_id: str) -> dict:
    """
    Full Chief Accountant Cockpit.
    Single connection, all sections run sequentially (no parallel overhead).
    Read-only.
    """
    async with get_conn() as conn:
        risks          = await _get_risks(conn, tenant_id)
        pending        = await _get_pending(conn, tenant_id)
        recent         = await _get_recent_actions(conn, tenant_id)
        ledger_health  = await _get_ledger_health(conn, tenant_id)
        bank           = await _get_unreconciled_bank(conn, tenant_id)
        period_stats   = await _get_period_stats(conn, tenant_id)

    # Overall alert level
    alerts = []
    if ledger_health.get("phantom_posts", 0) > 0:
        alerts.append(f"{ledger_health['phantom_posts']} phantom post(s) in ledger")
    if ledger_health.get("failed_unretried", 0) > 0:
        alerts.append(f"{ledger_health['failed_unretried']} failed posting(s) need retry")
    if risks.get("count", 0) > 0:
        alerts.append(f"{risks['count']} high-risk draft(s) need attention")
    if pending.get("total", 0) > 0:
        alerts.append(f"{pending['total']} draft(s) awaiting approval")

    alert_level = "OK"
    if ledger_health.get("health_score") is not None:
        if ledger_health["health_score"] < 60:
            alert_level = "CRITICAL"
        elif ledger_health["health_score"] < 90 or risks.get("count", 0) > 5:
            alert_level = "WARNING"

    return {
        "alert_level": alert_level,
        "alerts": alerts,
        "risks": risks,
        "pending": pending,
        "recent_actions": recent,
        "ledger_health": ledger_health,
        "bank_reconciliation": bank,
        "period_stats": period_stats,
        "summary": (
            f"Cockpit: {alert_level} — "
            + (", ".join(alerts) if alerts else "ყველაფერი კარგადაა")
        ),
    }


async def get_cockpit_brief(tenant_id: str) -> dict:
    """Lightweight cockpit for AI tool — counts only, no item lists."""
    async with get_conn() as conn:
        pending_count = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('drafted', 'pending_approval', 'awaiting_cfo')
        """), tenant_id) or 0

        risk_count = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('drafted', 'approved', 'auto_approved')
              AND (
                  (confidence IS NOT NULL AND confidence < %s)
                  OR COALESCE(amount, 0) > %s
                  OR partner IS NULL
              )
        """), tenant_id, LOW_CONFIDENCE, HIGH_AMOUNT_GEL) or 0

        phantom = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM journal_drafts jd
            WHERE jd.tenant_id = %s AND jd.status = 'posted'
              AND NOT EXISTS (
                  SELECT 1 FROM posting_logs pl
                  WHERE pl.tenant_id = jd.tenant_id AND pl.draft_id = jd.id
                    AND pl.status = 'success'
              )
        """), tenant_id) or 0

        failed = await conn.fetchval(_q("""
            SELECT COUNT(DISTINCT draft_id) FROM posting_logs
            WHERE tenant_id = %s AND status = 'failed'
              AND NOT EXISTS (
                  SELECT 1 FROM posting_logs pl2
                  WHERE pl2.tenant_id = posting_logs.tenant_id
                    AND pl2.draft_id = posting_logs.draft_id
                    AND pl2.status = 'success'
              )
        """), tenant_id) or 0

    score = max(0, 100 - int(phantom) * 20 - int(failed) * 10)
    alerts = []
    if phantom > 0:
        alerts.append(f"{phantom} phantom post(s)")
    if failed > 0:
        alerts.append(f"{failed} failed posting(s)")
    if risk_count > 0:
        alerts.append(f"{risk_count} high-risk draft(s)")
    if pending_count > 0:
        alerts.append(f"{pending_count} pending approval")

    return {
        "alert_level": "CRITICAL" if score < 60 else ("WARNING" if score < 90 or risk_count > 0 else "OK"),
        "pending_approvals": int(pending_count),
        "high_risk_drafts": int(risk_count),
        "phantom_posts": int(phantom),
        "failed_postings": int(failed),
        "ledger_health_score": score,
        "alerts": alerts,
        "all_clear": not alerts,
        "summary": "Cockpit: " + (", ".join(alerts) if alerts else "ყველაფერი კარგადაა"),
    }
