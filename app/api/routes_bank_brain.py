"""app/api/routes_bank_brain.py — Bank Brain (Task 14)."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.api.authz import require_permission
from app.api.response_utils import ok_response
from app.api.services.bank_brain_service import (
    get_aged_unreconciled,
    get_bank_brain_summary,
    compute_reconciliation_health,
    extract_match_patterns,
    suggest_categories_for_unmatched,
)
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/bank-brain", tags=["bank-brain"])


class SuggestPayload(BaseModel):
    unmatched_bank: list[dict]
    auto_matched: list[dict] = []


@router.get("/health")
async def reconciliation_health(
    request: Request,
    month: str = Query(None, description="YYYY-MM, defaults to current month"),
):
    require_permission(request, "bank:process")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await compute_reconciliation_health(tenant_id, month)
    return ok_response("Reconciliation health", result)


@router.get("/aged")
async def aged_unreconciled(request: Request, limit: int = Query(200, ge=1, le=500)):
    require_permission(request, "bank:process")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_aged_unreconciled(tenant_id, limit=limit)
    return ok_response("Aged unreconciled items", result)


@router.get("/summary")
async def brain_summary(
    request: Request,
    month: str = Query(None, description="YYYY-MM, defaults to current month"),
):
    require_permission(request, "bank:process")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await get_bank_brain_summary(tenant_id, month)
    return ok_response("Bank Brain summary", result)


@router.post("/suggest")
async def suggest_categories(payload: SuggestPayload, request: Request):
    require_permission(request, "bank:process")
    patterns   = extract_match_patterns(payload.auto_matched)
    suggestions = suggest_categories_for_unmatched(payload.unmatched_bank, patterns)
    return ok_response("Category suggestions", {
        "suggestions": suggestions,
        "patterns_learned": len(patterns),
    })
