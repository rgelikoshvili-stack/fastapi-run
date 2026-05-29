"""app/api/routes_company_identity.py — Company Identity Engine routes (Task 12B)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.company_identity_service import (
    get_tenant_inn,
    resolve_journal_type,
    set_tenant_inn,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/company-identity", tags=["company-identity"])


class InnPayload(BaseModel):
    inn: str

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) not in (9, 11):
            raise ValueError("INN must be 9 or 11 digits")
        return v


class ClassifyPayload(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


@router.get("")
async def get_identity(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    inn = await get_tenant_inn(tenant_id)
    return ok_response("Company identity", {"tenant_id": tenant_id, "inn": inn})


@router.put("")
async def set_identity(payload: InnPayload, request: Request):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        ok = await set_tenant_inn(tenant_id, payload.inn)
    except ValueError as exc:
        return error_response(str(exc), "INVALID_INN", payload.inn)
    if not ok:
        return error_response("Failed to save INN", "SAVE_FAILED", tenant_id)
    return ok_response("Company INN saved", {"tenant_id": tenant_id, "inn": payload.inn})


@router.post("/classify")
async def classify_text(payload: ClassifyPayload, request: Request):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await resolve_journal_type(tenant_id, payload.text)
    return ok_response("INN classification result", result)
