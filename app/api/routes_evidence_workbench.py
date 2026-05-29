"""app/api/routes_evidence_workbench.py — Document Evidence Workbench (Task 13)."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.evidence_workbench_service import (
    get_evidence_summary,
    link_document_to_draft,
    list_bundles_for_draft,
    list_drafts_without_evidence,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/evidence-workbench", tags=["evidence-workbench"])


class LinkPayload(BaseModel):
    draft_id: int
    document_id: int


@router.get("/draft/{draft_id}")
async def get_draft_evidence(draft_id: int, request: Request):
    require_permission(request, "audit:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    bundles = await list_bundles_for_draft(tenant_id, draft_id)
    return ok_response("Evidence bundles", {"draft_id": draft_id, "bundles": bundles, "count": len(bundles)})


@router.get("/summary/{draft_id}")
async def get_draft_summary(draft_id: int, request: Request):
    require_permission(request, "audit:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    summary = await get_evidence_summary(tenant_id, draft_id)
    return ok_response("Evidence summary", summary)


@router.get("/gaps")
async def get_evidence_gaps(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "audit:view")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await list_drafts_without_evidence(tenant_id, limit=limit, offset=offset)
    return ok_response("Drafts without evidence", result)


@router.post("/link")
async def link_evidence(payload: LinkPayload, request: Request):
    require_permission(request, "audit:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", "unknown")
    try:
        bundle = await link_document_to_draft(tenant_id, payload.draft_id, payload.document_id, actor)
    except ValueError as exc:
        code = str(exc)
        return error_response(code.replace("_", " ").title(), code, f"draft={payload.draft_id} doc={payload.document_id}")
    return ok_response("Document linked to draft", bundle)
