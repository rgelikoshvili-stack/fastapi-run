"""app/api/services/saas_service.py — SaaS Layer (Phase 8).

Provides:
  - Plan definitions and quota limits
  - check_quota       — enforce per-plan resource limits
  - get_usage         — count tenant resource usage this month
  - get_onboarding_status — provisioning checklist progress
  - upgrade_plan_request  — record a plan upgrade request
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.api.db import get_conn, _q
from app.api.services.tenant_config_service import get_tenant_setting, set_tenant_setting

# ---------------------------------------------------------------------------
# Plan definitions
# ---------------------------------------------------------------------------

PLANS: dict[str, dict[str, Any]] = {
    "FREE": {
        "display_name": "Free",
        "max_drafts_per_month": 50,
        "max_users": 2,
        "connectors_allowed": [],
        "features": ["reports", "journal", "ask"],
    },
    "STARTER": {
        "display_name": "Starter",
        "max_drafts_per_month": 500,
        "max_users": 5,
        "connectors_allowed": ["balance"],
        "features": ["reports", "journal", "ask", "reconciliation", "inventory"],
    },
    "PROFESSIONAL": {
        "display_name": "Professional",
        "max_drafts_per_month": 5000,
        "max_users": 20,
        "connectors_allowed": ["balance", "1c"],
        "features": ["reports", "journal", "ask", "reconciliation", "inventory",
                     "payroll", "fixed_assets", "budget", "monthly_close"],
    },
    "ENTERPRISE": {
        "display_name": "Enterprise",
        "max_drafts_per_month": -1,     # unlimited
        "max_users": -1,
        "connectors_allowed": ["balance", "1c", "oris"],
        "features": ["*"],              # all features
    },
}

DEFAULT_PLAN = "FREE"

# ---------------------------------------------------------------------------
# Onboarding checklist definition
# ---------------------------------------------------------------------------

ONBOARDING_STEPS = [
    {"id": "company_inn",      "name": "Company INN registered"},
    {"id": "connector_setup",  "name": "At least one ERP connector configured"},
    {"id": "first_draft",      "name": "First journal draft created"},
    {"id": "first_user",       "name": "At least one non-admin user invited"},
    {"id": "trial_balance",    "name": "Trial balance verified (no errors)"},
]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def get_plan_limits(plan: str) -> dict[str, Any]:
    """Return the limits dict for *plan*. Falls back to FREE if unknown."""
    return PLANS.get(plan.upper(), PLANS[DEFAULT_PLAN])


def is_feature_allowed(plan: str, feature: str) -> bool:
    """Return True if *feature* is available on *plan*."""
    limits = get_plan_limits(plan)
    features = limits.get("features", [])
    return "*" in features or feature in features


def is_connector_allowed(plan: str, connector: str) -> bool:
    """Return True if *connector* is available on *plan*."""
    limits = get_plan_limits(plan)
    return connector in limits.get("connectors_allowed", [])


# ---------------------------------------------------------------------------
# Async service functions
# ---------------------------------------------------------------------------

async def get_tenant_plan(tenant_id: str) -> str:
    """Return the tenant's current plan from the tenants table."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("SELECT plan FROM tenants WHERE tenant_id = $1"),
            tenant_id,
        )
    return (row["plan"] if row else DEFAULT_PLAN) or DEFAULT_PLAN


async def get_usage(tenant_id: str, month: str | None = None) -> dict[str, Any]:
    """Return current month's resource usage for a tenant."""
    if not month:
        month = date.today().strftime("%Y-%m")
    month_start = f"{month}-01"
    month_end   = f"{month}-31"

    async with get_conn() as conn:
        draft_count = await conn.fetchval(
            _q("""
                SELECT COUNT(*) FROM journal_drafts
                WHERE tenant_id = $1
                  AND created_at::date BETWEEN $2 AND $3::date
            """),
            tenant_id, month_start, month_end,
        )
        user_count = await conn.fetchval(
            _q("SELECT COUNT(*) FROM users WHERE tenant_id = $1"),
            tenant_id,
        )

    return {
        "month":       month,
        "draft_count": int(draft_count or 0),
        "user_count":  int(user_count or 0),
    }


async def check_quota(tenant_id: str, resource: str) -> dict[str, Any]:
    """Check whether tenant is within quota for *resource*.

    *resource*: "drafts" | "users"

    Returns:
        {"allowed": bool, "current": int, "limit": int, "plan": str}
    """
    plan = await get_tenant_plan(tenant_id)
    limits = get_plan_limits(plan)
    usage = await get_usage(tenant_id)

    if resource == "drafts":
        limit   = limits["max_drafts_per_month"]
        current = usage["draft_count"]
    elif resource == "users":
        limit   = limits["max_users"]
        current = usage["user_count"]
    else:
        return {"allowed": True, "current": 0, "limit": -1, "plan": plan}

    allowed = limit == -1 or current < limit
    return {
        "allowed": allowed,
        "current": current,
        "limit":   limit,
        "plan":    plan,
        "resource": resource,
    }


async def get_onboarding_status(tenant_id: str) -> dict[str, Any]:
    """Return onboarding checklist with completion status per step."""
    async with get_conn() as conn:
        has_inn = await conn.fetchval(
            _q("SELECT value_json FROM tenant_settings WHERE tenant_id=$1 AND key='company.inn'"),
            tenant_id,
        )
        has_connector = await conn.fetchval(
            _q("SELECT COUNT(*) FROM posting_log WHERE tenant_id=$1 AND status='success'"),
            tenant_id,
        )
        has_draft = await conn.fetchval(
            _q("SELECT COUNT(*) FROM journal_drafts WHERE tenant_id=$1"),
            tenant_id,
        )
        has_user = await conn.fetchval(
            _q("SELECT COUNT(*) FROM users WHERE tenant_id=$1"),
            tenant_id,
        )

    checks = {
        "company_inn":     bool(has_inn),
        "connector_setup": int(has_connector or 0) > 0,
        "first_draft":     int(has_draft or 0) > 0,
        "first_user":      int(has_user or 0) > 0,
        "trial_balance":   False,  # requires manual sign-off
    }

    steps = []
    completed = 0
    for step in ONBOARDING_STEPS:
        done = checks.get(step["id"], False)
        if done:
            completed += 1
        steps.append({**step, "completed": done})

    pct = round(completed / len(ONBOARDING_STEPS) * 100)
    return {
        "tenant_id":  tenant_id,
        "steps":      steps,
        "completed":  completed,
        "total":      len(ONBOARDING_STEPS),
        "pct":        pct,
        "onboarded":  pct == 100,
    }


async def upgrade_plan_request(
    tenant_id: str,
    requested_plan: str,
    requested_by: str,
) -> dict[str, Any]:
    """Record a plan upgrade request in tenant_settings."""
    if requested_plan.upper() not in PLANS:
        raise ValueError(f"INVALID_PLAN: {requested_plan}")
    request_data = {
        "requested_plan": requested_plan.upper(),
        "requested_by":   requested_by,
        "requested_at":   date.today().isoformat(),
        "status":         "pending",
    }
    await set_tenant_setting(tenant_id, "plan_upgrade_request", request_data)
    return request_data
