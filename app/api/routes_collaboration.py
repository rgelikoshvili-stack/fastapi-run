"""
app/api/routes_collaboration.py
Bridge Hub — Collaboration Routes
Comments + Assignment
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.api.tenant_context import resolve_tenant_id
from app.api.services.collaboration_service import (
    add_comment, get_comments,
    assign_draft, get_assigned_drafts, unassign_draft,
)
from app.api.db import get_conn, _q
from app.api.authz import require_permission

router = APIRouter(prefix="/collaboration", tags=["collaboration"])


class CommentRequest(BaseModel):
    comment_text: str
    author: Optional[str] = "accountant"
    author_role: Optional[str] = "accountant"
    comment_type: Optional[str] = "note"


class AssignRequest(BaseModel):
    assigned_to: str
    assigned_by: Optional[str] = "system"
    priority: Optional[str] = "normal"


@router.post("/drafts/{draft_id}/comments")
def create_comment(draft_id: int, req: CommentRequest, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = add_comment(
        draft_id=draft_id,
        comment_text=req.comment_text,
        author=req.author,
        author_role=req.author_role,
        comment_type=req.comment_type,
        tenant_id=tenant_id,
    )
    return result


@router.get("/drafts/{draft_id}/comments")
def list_comments(draft_id: int, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_comments(draft_id=draft_id, tenant_id=tenant_id)


@router.post("/drafts/{draft_id}/assign")
def assign(draft_id: int, req: AssignRequest, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = assign_draft(
        draft_id=draft_id,
        assigned_to=req.assigned_to,
        assigned_by=req.assigned_by,
        priority=req.priority,
        tenant_id=tenant_id,
    )
    return result


@router.delete("/drafts/{draft_id}/assign")
def unassign(draft_id: int, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = request.headers.get("X-Actor", "system")
    return unassign_draft(
        draft_id=draft_id,
        unassigned_by=actor,
        tenant_id=tenant_id,
    )


@router.get("/assigned/{accountant}")
def get_assigned(accountant: str, request: Request, status: str = None):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_assigned_drafts(
        assigned_to=accountant,
        tenant_id=tenant_id,
        status=status,
    )


@router.get("/summary")
async def collaboration_summary(request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        assignments = [dict(r) for r in await conn.fetch(_q("""
            SELECT assigned_to, COUNT(*) as count, priority
            FROM journal_drafts
            WHERE tenant_id = %s
              AND assigned_to IS NOT NULL
              AND status = 'pending_approval'
            GROUP BY assigned_to, priority
            ORDER BY count DESC
        """), tenant_id)]

        total_comments = await conn.fetchval(_q(
            "SELECT COUNT(*) FROM draft_comments WHERE tenant_id = %s"
        ), tenant_id) or 0

        unassigned = await conn.fetchval(_q("""
            SELECT COUNT(*) FROM journal_drafts
            WHERE tenant_id = %s AND assigned_to IS NULL AND status = 'pending_approval'
        """), tenant_id) or 0

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "total_comments": total_comments,
        "unassigned_pending": unassigned,
        "assignments": assignments,
    }
