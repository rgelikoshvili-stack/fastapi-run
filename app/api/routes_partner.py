"""app/api/routes_partner.py — Partner API/SDK + White-label (Phase 7)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.partner_service import (
    DEFAULT_BRANDING,
    deactivate_partner,
    get_branding,
    get_partner_profile,
    register_partner,
    set_branding,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/partner", tags=["partner"])


class RegisterPayload(BaseModel):
    partner_name:  str
    contact_email: str

    @field_validator("partner_name", "contact_email")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be blank")
        return v.strip()


class BrandingPayload(BaseModel):
    product_name:    str | None = None
    logo_url:        str | None = None
    primary_color:   str | None = None
    accent_color:    str | None = None
    support_email:   str | None = None
    custom_domain:   str | None = None
    hide_powered_by: bool | None = None


@router.post("/register")
async def register(payload: RegisterPayload, request: Request):
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")
    result = await register_partner(tenant_id, payload.partner_name, payload.contact_email, actor)
    return ok_response("Partner registered", result)


@router.get("/profile")
async def profile(request: Request):
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    p = await get_partner_profile(tenant_id)
    if not p:
        return error_response("No partner profile found", "NOT_FOUND", tenant_id)
    return ok_response("Partner profile", p)


@router.delete("/deactivate")
async def deactivate(request: Request):
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    ok = await deactivate_partner(tenant_id)
    if not ok:
        return error_response("No partner profile to deactivate", "NOT_FOUND", tenant_id)
    return ok_response("Partner deactivated", {"tenant_id": tenant_id})


@router.get("/branding")
async def get_brand(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    branding = await get_branding(tenant_id)
    return ok_response("Branding config", branding)


@router.put("/branding")
async def update_branding(payload: BrandingPayload, request: Request):
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        result = await set_branding(tenant_id, updates)
    except ValueError as exc:
        return error_response(str(exc), str(exc).split(":")[0], "")
    return ok_response("Branding updated", result)
