from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from app.api.response_utils import error_response
from app.api.tenant_context import resolve_tenant_id
from app.api.services.approval_service import (
    get_queue_service,
    approve_draft_service,
    reject_draft_service,
    get_audit_service,
    autopilot_approve_service,
)
from app.api.services.correct_draft_service import correct_draft
from app.services.route_bridge_service import build_preview_response

router = APIRouter(prefix="/approval", tags=["approval"])


def _validate_pagination(limit: int, offset: int):
    if limit < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "limit უნდა იყოს 0 ან მეტი"},
        )
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "offset უნდა იყოს 0 ან მეტი"},
        )


class RejectRequest(BaseModel):
    reason: Optional[str] = ""


class CorrectRequest(BaseModel):
    account_code: Optional[str] = None
    reason: Optional[str] = None
    debit_account: Optional[str] = None
    credit_account: Optional[str] = None
    user: Optional[str] = "human"


@router.get("/queue")
def get_queue(request: Request, status: str = "", limit: int = 100, offset: int = 0):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_queue_service(status, limit, offset, tenant_id=tenant_id)


@router.post("/approve/{draft_id}")
def approve_draft(draft_id: int, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return approve_draft_service(draft_id, tenant_id=tenant_id)


@router.post("/reject/{draft_id}")
def reject_draft(draft_id: int, req: RejectRequest, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return reject_draft_service(draft_id, req.reason, tenant_id=tenant_id)


@router.post("/correct/{draft_id}")
def correct_draft_route(draft_id: int, req: CorrectRequest, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    payload = {
        "account_code": req.account_code,
        "reason": req.reason,
        "debit_account": req.debit_account,
        "credit_account": req.credit_account,
    }
    return correct_draft(draft_id, payload, req.user or "human", tenant_id=tenant_id)


@router.get("/audit")
def get_audit_log(request: Request, limit: int = 50, offset: int = 0):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_audit_service(limit, offset, tenant_id=tenant_id)


@router.post("/autopilot")
def run_autopilot(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return autopilot_approve_service(tenant_id=tenant_id)


@router.post("/preview")
def preview_draft(payload: dict):
    try:
        return build_preview_response(payload)
    except Exception as e:
        return error_response("Preview failed", "PREVIEW_ERROR", str(e))