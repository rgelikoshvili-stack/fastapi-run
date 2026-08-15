"""app/api/routes_ledger_truth.py

Sprint 4 — Posted Ledger Truth.
Read-only health checks on the posted ledger.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Query

from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response
from app.api.security import limiter
from app.api.services.ledger_truth_service import run_ledger_truth, quick_ledger_health

router = APIRouter(prefix="/ledger-truth", tags=["Ledger Truth"])


@router.get("/report")
@limiter.limit("10/minute")
async def ledger_truth_report(
    request: Request,
    period_from: str | None = Query(None, description="YYYY-MM-DD"),
    period_to: str | None = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=200),
):
    """Full posted ledger health report (read-only)."""
    await require_permission(request, "journal:read")
    tenant_id = await resolve_tenant_id(request)

    result = await run_ledger_truth(
        tenant_id,
        period_from=period_from,
        period_to=period_to,
        limit=limit,
    )
    return ok_response("Posted ledger truth report", result)


@router.get("/health")
@limiter.limit("30/minute")
async def ledger_quick_health(request: Request):
    """Lightweight health score — counts only, no draft details."""
    await require_permission(request, "journal:read")
    tenant_id = await resolve_tenant_id(request)

    result = await quick_ledger_health(tenant_id)
    return ok_response("Posted ledger health", result)


@router.get("/unverified")
@limiter.limit("10/minute")
async def ledger_unverified(
    request: Request,
    period_from: str | None = Query(None),
    period_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Drafts marked 'posted' with no corresponding posting_log success."""
    await require_permission(request, "journal:read")
    tenant_id = await resolve_tenant_id(request)

    result = await run_ledger_truth(
        tenant_id, period_from=period_from, period_to=period_to, limit=limit
    )
    phantom = next(
        (i for i in result.get("issues", []) if i["type"] == "PHANTOM_POST"), None
    )
    return ok_response("Unverified posted drafts", {
        "count": phantom["count"] if phantom else 0,
        "drafts": phantom["drafts"] if phantom else [],
        "period_from": period_from,
        "period_to": period_to,
    })


@router.get("/failed-postings")
@limiter.limit("10/minute")
async def ledger_failed_postings(
    request: Request,
    period_from: str | None = Query(None),
    period_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Postings that failed and were never successfully retried."""
    await require_permission(request, "journal:read")
    tenant_id = await resolve_tenant_id(request)

    result = await run_ledger_truth(
        tenant_id, period_from=period_from, period_to=period_to, limit=limit
    )
    failed = next(
        (i for i in result.get("issues", []) if i["type"] == "FAILED_UNRETRIED"), None
    )
    return ok_response("Failed postings never retried", {
        "count": failed["count"] if failed else 0,
        "drafts": failed["drafts"] if failed else [],
        "period_from": period_from,
        "period_to": period_to,
    })
