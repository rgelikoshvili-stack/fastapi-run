"""app/api/routes_saas.py — SaaS self-service (Phase 8)."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.saas_service import (
    PLANS,
    check_quota,
    get_onboarding_status,
    get_tenant_plan,
    get_usage,
    upgrade_plan_request,
    get_plan_limits,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/saas", tags=["saas"])


class UpgradePayload(BaseModel):
    requested_plan: str

    @field_validator("requested_plan")
    @classmethod
    def valid_plan(cls, v: str) -> str:
        if v.upper() not in PLANS:
            raise ValueError(f"Plan must be one of {list(PLANS.keys())}")
        return v.upper()


@router.get("/plans")
async def list_plans(request: Request):
    """List all available plans and their limits (public endpoint)."""
    return ok_response("Available plans", {
        "plans": [{"name": k, **v} for k, v in PLANS.items()]
    })


@router.get("/my-plan")
async def my_plan(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    plan = await get_tenant_plan(tenant_id)
    limits = get_plan_limits(plan)
    return ok_response("Current plan", {"plan": plan, "limits": limits})


@router.get("/usage")
async def usage(request: Request, month: str = Query(None, description="YYYY-MM")):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_usage(tenant_id, month)
    plan = await get_tenant_plan(tenant_id)
    limits = get_plan_limits(plan)
    result["plan"] = plan
    result["max_drafts_per_month"] = limits["max_drafts_per_month"]
    result["max_users"] = limits["max_users"]
    return ok_response("Usage statistics", result)


@router.get("/quota/{resource}")
async def quota_check(resource: str, request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if resource not in ("drafts", "users"):
        return error_response("Invalid resource", "INVALID_RESOURCE", resource)
    result = await check_quota(tenant_id, resource)
    return ok_response(f"Quota check: {resource}", result)


@router.get("/onboarding")
async def onboarding(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_onboarding_status(tenant_id)
    return ok_response("Onboarding status", result)


@router.post("/upgrade")
async def upgrade(payload: UpgradePayload, request: Request):
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")
    try:
        result = await upgrade_plan_request(tenant_id, payload.requested_plan, actor)
    except ValueError as exc:
        return error_response(str(exc), str(exc).split(":")[0], payload.requested_plan)
    return ok_response("Upgrade request submitted", result)
