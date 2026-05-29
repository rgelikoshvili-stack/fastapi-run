"""app/api/routes_approval_cockpit.py — Approval Cockpit 2.0 (Phase 5)."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.approval_cockpit_service import (
    add_comment,
    delegate_draft,
    get_cockpit_queue,
    get_overdue_summary,
    list_comments,
    set_priority,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/approval-cockpit", tags=["approval-cockpit"])


class PriorityPayload(BaseModel):
    priority: str

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, v: str) -> str:
        if v not in ("high", "normal", "low"):
            raise ValueError("priority must be high, normal, or low")
        return v


class DelegatePayload(BaseModel):
    assigned_to: str

    @field_validator("assigned_to")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("assigned_to must not be blank")
        return v.strip()


class CommentPayload(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("body must not be blank")
        return v.strip()


@router.get("/queue")
async def cockpit_queue(
    request: Request,
    status: str = Query("drafted"),
    sla_hours: int = Query(48, ge=1, le=720),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "approval:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_cockpit_queue(tenant_id, status=status, sla_hours=sla_hours,
                                     limit=limit, offset=offset)
    return ok_response("Cockpit queue", result)


@router.get("/overdue")
async def overdue_summary(
    request: Request,
    sla_hours: int = Query(48, ge=1, le=720),
):
    require_permission(request, "approval:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_overdue_summary(tenant_id, sla_hours=sla_hours)
    return ok_response("Overdue summary", result)


@router.patch("/{draft_id}/priority")
async def update_priority(draft_id: int, payload: PriorityPayload, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        result = await set_priority(tenant_id, draft_id, payload.priority)
    except ValueError as exc:
        return error_response(str(exc), str(exc).split(":")[0], f"draft_id={draft_id}")
    return ok_response("Priority updated", result)


@router.patch("/{draft_id}/delegate")
async def delegate(draft_id: int, payload: DelegatePayload, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")
    try:
        result = await delegate_draft(tenant_id, draft_id, payload.assigned_to, actor)
    except ValueError as exc:
        return error_response(str(exc), str(exc), f"draft_id={draft_id}")
    return ok_response("Draft delegated", result)


@router.get("/{draft_id}/comments")
async def get_comments(draft_id: int, request: Request):
    require_permission(request, "approval:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    comments = await list_comments(tenant_id, draft_id)
    return ok_response("Comments", {"draft_id": draft_id, "comments": comments})


@router.post("/{draft_id}/comments")
async def post_comment(draft_id: int, payload: CommentPayload, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")
    try:
        comment = await add_comment(tenant_id, draft_id, actor, payload.body)
    except ValueError as exc:
        return error_response(str(exc), str(exc), f"draft_id={draft_id}")
    return ok_response("Comment added", comment)
