"""app/api/routes_monthly_close.py — Monthly Close Cockpit (Phase 6)."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.monthly_close_service import (
    get_close_status,
    get_trial_balance_snapshot,
    run_checklist,
    save_close_signoff,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/monthly-close", tags=["monthly-close"])

_MONTH_RE = __import__("re").compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class SignoffPayload(BaseModel):
    month: str
    role: str

    @field_validator("month")
    @classmethod
    def valid_month(cls, v: str) -> str:
        import re
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", v):
            raise ValueError("month must be YYYY-MM format")
        return v

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("accountant", "cfo"):
            raise ValueError("role must be accountant or cfo")
        return v


@router.get("/status")
async def close_status(
    request: Request,
    month: str = Query(..., description="YYYY-MM"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_close_status(tenant_id, month)
    return ok_response(f"Monthly close status for {month}", result)


@router.get("/checklist")
async def checklist(
    request: Request,
    month: str = Query(..., description="YYYY-MM"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    items = await run_checklist(tenant_id, month)
    all_ok = all(i["status"] == "ok" for i in items)
    return ok_response(f"Checklist for {month}", {"month": month, "items": items, "all_ok": all_ok})


@router.get("/trial-balance")
async def trial_balance(
    request: Request,
    month: str = Query(..., description="YYYY-MM"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_trial_balance_snapshot(tenant_id, month)
    return ok_response(f"Trial balance for {month}", result)


@router.post("/signoff")
async def signoff(payload: SignoffPayload, request: Request):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")
    try:
        result = await save_close_signoff(tenant_id, payload.month, actor, payload.role)
    except ValueError as exc:
        return error_response(str(exc), str(exc).split(":")[0], payload.month)
    return ok_response("Sign-off recorded", result)
