"""app/api/routes_cross_reference.py

Sprint 3C — Cross-reference view.
Ties all document types (ზედნადები, ფაქტურა, bank, journal) for a party or document.

Endpoints:
  GET /cross-reference/party?q=    — all docs for a supplier/buyer (INN or name)
  GET /cross-reference/document?number=  — full chain for one document number
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
from app.api.services.cross_reference_service import (
    get_cross_ref_by_party,
    get_cross_ref_by_document,
)

router = APIRouter(prefix="/cross-reference", tags=["cross-reference"])


@router.get("/party")
async def cross_reference_by_party(
    request: Request,
    q: str = Query(..., min_length=2, description="Supplier/buyer INN or name"),
    limit: int = Query(20, ge=1, le=100),
):
    """All documents linked to a supplier or buyer (waybills + tax invoices + bank + drafts)."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    result = await get_cross_ref_by_party(tenant_id, q, limit=limit)
    if "error" in result:
        return error_response(result["error"], "INVALID_INPUT", f"q={q}")

    return ok_response(
        f"Cross-reference for '{q}'",
        result,
    )


@router.get("/document")
async def cross_reference_by_document(
    request: Request,
    number: str = Query(..., min_length=1, description="Waybill number or tax invoice number"),
):
    """Full document chain for a specific waybill or tax invoice number."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    result = await get_cross_ref_by_document(tenant_id, number)
    if "error" in result:
        return error_response(result["error"], "INVALID_INPUT", f"number={number}")

    if not result.get("found"):
        return error_response(
            f"Document '{number}' not found",
            "NOT_FOUND",
            f"number={number}",
        )

    return ok_response(f"Document chain for '{number}'", result)
