"""app/api/routes_cockpit.py

Sprint 5 — Chief Accountant Cockpit.
Aggregated read-only dashboard.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response
from app.api.security import limiter
from app.api.services.cockpit_service import get_cockpit, get_cockpit_brief

router = APIRouter(prefix="/cockpit", tags=["Cockpit"])


@router.get("")
@limiter.limit("20/minute")
async def cockpit_full(request: Request):
    """Full Chief Accountant Cockpit: risks, pending, recent actions, ledger health."""
    await require_permission(request, "journal:read")
    tenant_id = await resolve_tenant_id(request)

    result = await get_cockpit(tenant_id)
    return ok_response("Chief Accountant Cockpit", result)


@router.get("/brief")
@limiter.limit("60/minute")
async def cockpit_brief(request: Request):
    """Lightweight cockpit summary — counts only. Fast."""
    await require_permission(request, "journal:read")
    tenant_id = await resolve_tenant_id(request)

    result = await get_cockpit_brief(tenant_id)
    return ok_response("Cockpit brief", result)


@router.get("/risks")
@limiter.limit("20/minute")
async def cockpit_risks(request: Request):
    """High-risk drafts: low confidence, high amount, missing fields."""
    await require_permission(request, "journal:read")
    tenant_id = await resolve_tenant_id(request)

    result = await get_cockpit(tenant_id)
    return ok_response("Cockpit risks", result.get("risks", {}))


@router.get("/pending")
@limiter.limit("20/minute")
async def cockpit_pending(request: Request):
    """Pending approval queue: drafted, pending_approval, awaiting_cfo."""
    await require_permission(request, "journal:read")
    tenant_id = await resolve_tenant_id(request)

    result = await get_cockpit(tenant_id)
    return ok_response("Pending approvals", result.get("pending", {}))
