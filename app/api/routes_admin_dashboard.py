"""app/api/routes_admin_dashboard.py — Admin/Support Tools Dashboard (Phase 8)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.admin_dashboard_service import (
    adjust_tenant_plan,
    get_system_health,
    get_tenant_detail,
    get_tenant_summary,
)
from app.api.services.saas_service import PLANS

router = APIRouter(prefix="/admin", tags=["admin"])


class AdjustPlanPayload(BaseModel):
    new_plan: str

    @field_validator("new_plan")
    @classmethod
    def valid_plan(cls, v: str) -> str:
        if v.upper() not in PLANS:
            raise ValueError(f"plan must be one of {list(PLANS.keys())}")
        return v.upper()


@router.get("/health")
async def system_health(request: Request):
    require_permission(request, "tenants:manage")
    result = await get_system_health()
    return ok_response("System health", result)


@router.get("/tenants")
async def tenant_summary(request: Request):
    require_permission(request, "tenants:manage")
    result = await get_tenant_summary()
    return ok_response("Tenant summary", result)


@router.get("/tenants/{tenant_id}")
async def tenant_detail(tenant_id: str, request: Request):
    require_permission(request, "tenants:manage")
    try:
        result = await get_tenant_detail(tenant_id)
    except ValueError as exc:
        return error_response(str(exc), str(exc).split(":")[0], tenant_id)
    return ok_response(f"Tenant detail: {tenant_id}", result)


@router.patch("/tenants/{tenant_id}/plan")
async def set_plan(tenant_id: str, payload: AdjustPlanPayload, request: Request):
    require_permission(request, "tenants:manage")
    actor = getattr(request.state, "user_id", "unknown")
    try:
        result = await adjust_tenant_plan(tenant_id, payload.new_plan, actor)
    except ValueError as exc:
        return error_response(str(exc), str(exc).split(":")[0], tenant_id)
    return ok_response("Plan updated", result)
