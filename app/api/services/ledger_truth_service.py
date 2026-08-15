"""app/api/services/ledger_truth_service.py

Sprint 4 — Posted Ledger Truth.
Read-only verification that the posted ledger is consistent.

Checks:
  1. PHANTOM_POST     — journal_drafts.status='posted' but no posting_log success
  2. SYNC_MISMATCH    — posting_log success exists but draft still shows approved, not posted
  3. FAILED_UNRETRIED — posting_log failed with no later success for same draft
  4. DUPLICATE_POST   — same draft_id posted successfully more than once
  5. HIGH_AMOUNT_UNPOSTED — approved draft over threshold with no posting attempt

Returns a health_score (0–100) and a list of issues sorted by severity.
NEVER mutates posted ledger rows.
"""
from __future__ import annotations

import logging
from datetime import date as _dt_cls

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)

APPROVED_STATUSES = ("approved", "auto_approved")
POSTED_STATUS = "posted"
LARGE_AMOUNT_GEL = 10_000.0   # flag unposted approved drafts above this


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _safe(row) -> dict:
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


def _health_score(issues: list[dict]) -> int:
    """0 = critical problems, 100 = fully healthy."""
    if not issues:
        return 100
    deductions = {
        "PHANTOM_POST": 20,
        "SYNC_MISMATCH": 15,
        "FAILED_UNRETRIED": 10,
        "DUPLICATE_POST": 25,
        "HIGH_AMOUNT_UNPOSTED": 5,
    }
    total = sum(deductions.get(i["type"], 5) * i.get("count", 1) for i in issues)
    return max(0, 100 - total)


# ─────────────────────────────────────────────────────────────────────────────
# Main report
# ─────────────────────────────────────────────────────────────────────────────

async def run_ledger_truth(
    tenant_id: str,
    period_from: str | None = None,
    period_to: str | None = None,
    limit: int = 50,
) -> dict:
    """
    Run all ledger truth checks and return a structured report.
    All queries are read-only.
    """
    issues: list[dict] = []

    async with get_conn() as conn:

        # ── Date range conditions ─────────────────────────────────────────────
        date_cond = ""
        date_args: list = []
        if period_from:
            date_cond += " AND jd.date >= $PF"
            date_args.append(period_from)
        if period_to:
            date_cond += " AND jd.date <= $PT"
            date_args.append(period_to)

        def _build_sql(sql: str) -> str:
            """Replace $PF/$PT placeholders with correct $N indexes."""
            result = sql
            n = 2  # $1 = tenant_id
            if period_from:
                result = result.replace("$PF", f"${n}"); n += 1
            if period_to:
                result = result.replace("$PT", f"${n}"); n += 1
            return result

        # ── 1. PHANTOM_POST ───────────────────────────────────────────────────
        # Drafts marked 'posted' but no success in posting_logs
        try:
            phantom_sql = _build_sql(f"""
                SELECT jd.id, jd.description, jd.amount, jd.partner,
                       jd.date, jd.debit_account, jd.credit_account,
                       jd.status, jd.created_at
                FROM journal_drafts jd
                WHERE jd.tenant_id = $1
                  AND jd.status = 'posted'
                  {date_cond}
                  AND NOT EXISTS (
                      SELECT 1 FROM posting_logs pl
                      WHERE pl.tenant_id = jd.tenant_id
                        AND pl.draft_id = jd.id
                        AND pl.status = 'success'
                  )
                ORDER BY jd.amount DESC NULLS LAST
                LIMIT ${len(date_args)+2}
            """)
            rows = await conn.fetch(phantom_sql, tenant_id, *date_args, limit)
            if rows:
                issues.append({
                    "type": "PHANTOM_POST",
                    "severity": "HIGH",
                    "count": len(rows),
                    "description": f"{len(rows)} draft(s) marked 'posted' but no posting_log success record",
                    "drafts": [_safe(r) for r in rows],
                })
        except Exception as e:
            log.warning("ledger_truth PHANTOM_POST: %s", e)

        # ── 2. SYNC_MISMATCH ──────────────────────────────────────────────────
        # Posting_log has success but draft still shows approved
        try:
            sync_sql = _build_sql(f"""
                SELECT jd.id, jd.description, jd.amount, jd.partner,
                       jd.date, jd.status AS draft_status,
                       pl.target_system, pl.created_at AS posted_at
                FROM journal_drafts jd
                JOIN posting_logs pl
                    ON pl.draft_id = jd.id AND pl.tenant_id = jd.tenant_id
                WHERE jd.tenant_id = $1
                  AND jd.status = ANY(ARRAY['approved','auto_approved'])
                  {date_cond}
                  AND pl.status = 'success'
                ORDER BY pl.created_at DESC
                LIMIT ${len(date_args)+2}
            """)
            rows = await conn.fetch(sync_sql, tenant_id, *date_args, limit)
            if rows:
                issues.append({
                    "type": "SYNC_MISMATCH",
                    "severity": "MEDIUM",
                    "count": len(rows),
                    "description": f"{len(rows)} draft(s) have successful posting but status not updated to 'posted'",
                    "drafts": [_safe(r) for r in rows],
                })
        except Exception as e:
            log.warning("ledger_truth SYNC_MISMATCH: %s", e)

        # ── 3. FAILED_UNRETRIED ───────────────────────────────────────────────
        # posting_log failed and no later success for same draft
        try:
            failed_sql = _build_sql(f"""
                SELECT jd.id, jd.description, jd.amount, jd.partner,
                       jd.date, jd.status AS draft_status,
                       pl.target_system, pl.error_message, pl.created_at AS failed_at
                FROM posting_logs pl
                JOIN journal_drafts jd
                    ON jd.id = pl.draft_id AND jd.tenant_id = pl.tenant_id
                WHERE pl.tenant_id = $1
                  AND pl.status = 'failed'
                  {date_cond.replace('jd.date', 'jd.date')}
                  AND NOT EXISTS (
                      SELECT 1 FROM posting_logs pl2
                      WHERE pl2.tenant_id = pl.tenant_id
                        AND pl2.draft_id = pl.draft_id
                        AND pl2.status = 'success'
                  )
                ORDER BY pl.created_at DESC
                LIMIT ${len(date_args)+2}
            """)
            rows = await conn.fetch(failed_sql, tenant_id, *date_args, limit)
            if rows:
                issues.append({
                    "type": "FAILED_UNRETRIED",
                    "severity": "MEDIUM",
                    "count": len(rows),
                    "description": f"{len(rows)} draft(s) with failed posting never successfully retried",
                    "drafts": [_safe(r) for r in rows],
                })
        except Exception as e:
            log.warning("ledger_truth FAILED_UNRETRIED: %s", e)

        # ── 4. DUPLICATE_POST ─────────────────────────────────────────────────
        # Same draft posted successfully more than once
        try:
            dup_sql = _build_sql(f"""
                SELECT jd.id, jd.description, jd.amount, jd.partner,
                       jd.date, COUNT(pl.id) AS success_count,
                       string_agg(pl.target_system, ', ') AS systems
                FROM journal_drafts jd
                JOIN posting_logs pl
                    ON pl.draft_id = jd.id AND pl.tenant_id = jd.tenant_id
                WHERE jd.tenant_id = $1
                  AND pl.status = 'success'
                  {date_cond}
                GROUP BY jd.id, jd.description, jd.amount, jd.partner, jd.date
                HAVING COUNT(pl.id) > 1
                ORDER BY COUNT(pl.id) DESC
                LIMIT ${len(date_args)+2}
            """)
            rows = await conn.fetch(dup_sql, tenant_id, *date_args, limit)
            if rows:
                issues.append({
                    "type": "DUPLICATE_POST",
                    "severity": "HIGH",
                    "count": len(rows),
                    "description": f"{len(rows)} draft(s) posted to ERP more than once (possible double-entry)",
                    "drafts": [_safe(r) for r in rows],
                })
        except Exception as e:
            log.warning("ledger_truth DUPLICATE_POST: %s", e)

        # ── 5. HIGH_AMOUNT_UNPOSTED ───────────────────────────────────────────
        # Large approved drafts with no posting attempt at all
        try:
            large_sql = _build_sql(f"""
                SELECT jd.id, jd.description, jd.amount, jd.partner,
                       jd.date, jd.status, jd.debit_account, jd.credit_account
                FROM journal_drafts jd
                WHERE jd.tenant_id = $1
                  AND jd.status = ANY(ARRAY['approved','auto_approved'])
                  AND COALESCE(jd.amount, 0) >= ${len(date_args)+2}
                  {date_cond}
                  AND NOT EXISTS (
                      SELECT 1 FROM posting_logs pl
                      WHERE pl.tenant_id = jd.tenant_id AND pl.draft_id = jd.id
                  )
                ORDER BY jd.amount DESC NULLS LAST
                LIMIT ${len(date_args)+3}
            """)
            rows = await conn.fetch(large_sql, tenant_id, LARGE_AMOUNT_GEL, *date_args, limit)
            if rows:
                issues.append({
                    "type": "HIGH_AMOUNT_UNPOSTED",
                    "severity": "LOW",
                    "count": len(rows),
                    "description": f"{len(rows)} large approved draft(s) (>= {LARGE_AMOUNT_GEL:,.0f} GEL) never sent to ERP",
                    "drafts": [_safe(r) for r in rows],
                })
        except Exception as e:
            log.warning("ledger_truth HIGH_AMOUNT_UNPOSTED: %s", e)

        # ── Overview counts ───────────────────────────────────────────────────
        try:
            stats = _safe(await conn.fetchrow(_q("""
                SELECT
                    COUNT(*) FILTER (WHERE jd.status = 'posted')                AS total_posted,
                    COUNT(*) FILTER (WHERE jd.status = ANY(ARRAY['approved','auto_approved'])) AS total_approved_unposted,
                    COUNT(*) FILTER (WHERE jd.status = 'rejected')              AS total_rejected,
                    COALESCE(SUM(jd.amount) FILTER (WHERE jd.status = 'posted'), 0) AS posted_gel,
                    COALESCE(SUM(jd.amount) FILTER (WHERE jd.status = ANY(ARRAY['approved','auto_approved'])), 0) AS approved_unposted_gel
                FROM journal_drafts jd
                WHERE jd.tenant_id = %s
            """), tenant_id))
        except Exception as e:
            log.warning("ledger_truth stats: %s", e)
            stats = {}

    # ── Severity ordering ─────────────────────────────────────────────────────
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    issues.sort(key=lambda x: severity_order.get(x.get("severity", "LOW"), 2))

    score = _health_score(issues)
    high = sum(1 for i in issues if i.get("severity") == "HIGH")
    med = sum(1 for i in issues if i.get("severity") == "MEDIUM")

    return {
        "health_score": score,
        "health_label": "HEALTHY" if score >= 90 else ("WARNING" if score >= 60 else "CRITICAL"),
        "issue_count": len(issues),
        "high_severity": high,
        "medium_severity": med,
        "issues": issues,
        "stats": stats,
        "period_from": period_from,
        "period_to": period_to,
        "summary": (
            f"Posted Ledger: {score}/100 — "
            + (f"{high} HIGH + {med} MEDIUM issues" if issues else "ყველაფერი კარგადაა")
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Quick health check (lightweight, for AI tool)
# ─────────────────────────────────────────────────────────────────────────────

async def quick_ledger_health(tenant_id: str) -> dict:
    """Fast counts only — no full draft lists. For AI tool quick queries."""
    async with get_conn() as conn:
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

            sync_miss = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM journal_drafts jd
                WHERE jd.tenant_id = %s
                  AND jd.status = ANY(ARRAY['approved','auto_approved'])
                  AND EXISTS (
                      SELECT 1 FROM posting_logs pl
                      WHERE pl.tenant_id = jd.tenant_id AND pl.draft_id = jd.id
                        AND pl.status = 'success'
                  )
            """), tenant_id) or 0

            failed = await conn.fetchval(_q("""
                SELECT COUNT(DISTINCT pl.draft_id) FROM posting_logs pl
                WHERE pl.tenant_id = %s AND pl.status = 'failed'
                  AND NOT EXISTS (
                      SELECT 1 FROM posting_logs pl2
                      WHERE pl2.tenant_id = pl.tenant_id AND pl2.draft_id = pl.draft_id
                        AND pl2.status = 'success'
                  )
            """), tenant_id) or 0

            duplicates = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM (
                    SELECT draft_id FROM posting_logs
                    WHERE tenant_id = %s AND status = 'success'
                    GROUP BY draft_id HAVING COUNT(*) > 1
                ) sub
            """), tenant_id) or 0

        except Exception as e:
            log.warning("quick_ledger_health: %s", e)
            return {"error": str(e)}

    issues_summary = []
    if phantom > 0:
        issues_summary.append(f"{phantom} phantom post(s)")
    if sync_miss > 0:
        issues_summary.append(f"{sync_miss} sync mismatch(es)")
    if failed > 0:
        issues_summary.append(f"{failed} failed unretried")
    if duplicates > 0:
        issues_summary.append(f"{duplicates} duplicate post(s)")

    score = max(0, 100 - int(phantom) * 20 - int(sync_miss) * 15
                - int(failed) * 10 - int(duplicates) * 25)

    return {
        "health_score": score,
        "health_label": "HEALTHY" if score >= 90 else ("WARNING" if score >= 60 else "CRITICAL"),
        "phantom_posts": int(phantom),
        "sync_mismatches": int(sync_miss),
        "failed_unretried": int(failed),
        "duplicate_posts": int(duplicates),
        "issues": issues_summary,
        "all_clear": not issues_summary,
        "summary": f"Posted Ledger health: {score}/100" + (
            " — " + ", ".join(issues_summary) if issues_summary else " — ყველაფერი კარგადაა"
        ),
    }
