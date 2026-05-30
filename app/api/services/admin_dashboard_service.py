"""app/api/services/admin_dashboard_service.py — Admin/Support Tools (Phase 8).

System-wide admin dashboard for support engineers:
  - get_system_health    — connector + DB + background task status
  - get_tenant_summary   — all tenants with plan, usage, onboarding status
  - get_tenant_detail    — deep dive into one tenant
  - adjust_tenant_plan   — manually upgrade/downgrade a tenant's plan
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.api.db import get_conn, _q
from app.api.services.saas_service import PLANS, get_tenant_plan, get_usage


# ---------------------------------------------------------------------------
# System health
# ---------------------------------------------------------------------------

async def get_system_health() -> dict[str, Any]:
    """Return overall system health: DB ping, background tasks status, connector modes."""
    db_ok = False
    db_message = ""
    try:
        async with get_conn() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
        db_message = "OK"
    except Exception as exc:
        db_message = str(exc)[:80]

    # Connector demo/live status (no network calls — just check env vars)
    import os
    connectors = {
        "balance": "live" if os.environ.get("BALANCE_API_KEY") else "demo",
        "1c":      "live" if os.environ.get("ONEC_ENDPOINT")   else "demo",
        "oris":    "live" if os.environ.get("ORIS_ENDPOINT")   else "demo",
        "fina":    "live" if os.environ.get("FINA_ENDPOINT")   else "demo",
        "apex":    "live" if os.environ.get("APEX_ENDPOINT")   else "demo",
    }

    redis_configured = bool(os.environ.get("REDIS_URL"))
    gcs_configured   = bool(os.environ.get("GCS_BUCKET_NAME"))

    return {
        "database":          {"ok": db_ok, "message": db_message},
        "connectors":        connectors,
        "redis_configured":  redis_configured,
        "gcs_configured":    gcs_configured,
        "all_ok":            db_ok,
    }


# ---------------------------------------------------------------------------
# Tenant overview
# ---------------------------------------------------------------------------

async def get_tenant_summary() -> dict[str, Any]:
    """Return all tenants with plan, draft count, and onboarding status."""
    async with get_conn() as conn:
        tenants = await conn.fetch("""
            SELECT tenant_id, name, plan, is_active, status, created_at
            FROM tenants
            ORDER BY created_at DESC
        """)
        total_drafts = await conn.fetchval(
            "SELECT COUNT(*) FROM journal_drafts"
        )
        plan_counts_rows = await conn.fetch("""
            SELECT plan, COUNT(*) AS cnt
            FROM tenants
            GROUP BY plan
        """)

    plan_counts = {r["plan"]: int(r["cnt"]) for r in plan_counts_rows}
    today_month = date.today().strftime("%Y-%m")

    tenant_list = []
    for t in tenants:
        usage = await get_usage(t["tenant_id"], today_month)
        tenant_list.append({
            "tenant_id":    t["tenant_id"],
            "name":         t["name"],
            "plan":         t["plan"],
            "is_active":    t["is_active"],
            "status":       t["status"],
            "created_at":   str(t["created_at"]),
            "draft_count_month": usage["draft_count"],
            "user_count":   usage["user_count"],
        })

    return {
        "total_tenants": len(tenant_list),
        "total_drafts":  int(total_drafts or 0),
        "plan_counts":   plan_counts,
        "tenants":       tenant_list,
    }


async def get_tenant_detail(tenant_id: str) -> dict[str, Any]:
    """Return a detailed view of one tenant for support purposes."""
    async with get_conn() as conn:
        tenant = await conn.fetchrow(
            _q("SELECT * FROM tenants WHERE tenant_id = $1"),
            tenant_id,
        )
        if not tenant:
            raise ValueError("TENANT_NOT_FOUND")

        draft_stats = await conn.fetchrow(
            _q("""
                SELECT
                    COUNT(*)                                        AS total,
                    COUNT(*) FILTER (WHERE status = 'posted')      AS posted,
                    COUNT(*) FILTER (WHERE status = 'drafted')     AS drafted,
                    COUNT(*) FILTER (WHERE status = 'rejected')    AS rejected,
                    COALESCE(SUM(amount) FILTER (WHERE status='posted'), 0) AS posted_amount
                FROM journal_drafts WHERE tenant_id = $1
            """),
            tenant_id,
        )
        posting_log_count = await conn.fetchval(
            _q("SELECT COUNT(*) FROM posting_log WHERE tenant_id = $1"),
            tenant_id,
        )

    plan  = (tenant["plan"] or "FREE").upper()
    today = date.today().strftime("%Y-%m")
    usage = await get_usage(tenant_id, today)

    return {
        "tenant":       dict(tenant),
        "plan":         plan,
        "plan_limits":  PLANS.get(plan, PLANS["FREE"]),
        "usage_month":  usage,
        "drafts": {
            "total":          int(draft_stats["total"] or 0),
            "posted":         int(draft_stats["posted"] or 0),
            "drafted":        int(draft_stats["drafted"] or 0),
            "rejected":       int(draft_stats["rejected"] or 0),
            "posted_amount":  round(float(draft_stats["posted_amount"] or 0), 2),
        },
        "posting_log_count": int(posting_log_count or 0),
    }


async def adjust_tenant_plan(
    tenant_id: str,
    new_plan: str,
    adjusted_by: str,
) -> dict[str, Any]:
    """Manually set a tenant's plan. Admin-only."""
    new_plan = new_plan.upper()
    if new_plan not in PLANS:
        raise ValueError(f"INVALID_PLAN: {new_plan}")

    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                UPDATE tenants
                SET plan = $2, updated_at = NOW()
                WHERE tenant_id = $1
                RETURNING tenant_id, name, plan, updated_at
            """),
            tenant_id, new_plan,
        )
    if not row:
        raise ValueError("TENANT_NOT_FOUND")
    return {**dict(row), "adjusted_by": adjusted_by}
