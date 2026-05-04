"""app/api/routes_audit_trail.py — Immutable entity audit trail endpoints."""
from fastapi import APIRouter, Request, Query
from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, http_error
from app.api.services.entity_audit_service import get_entity_history_async
import logging

router = APIRouter(prefix="/audit-trail", tags=["audit-trail"])
log = logging.getLogger(__name__)

_VALID_ENTITIES = {
    "journal_drafts", "journal_entries", "expenses", "invoices",
    "contracts", "customers", "bank_transactions", "fixed_assets",
    "inventory_items", "purchase_orders", "budgets",
}


@router.get("/{entity_type}/{entity_id}")
async def get_history(entity_type: str, entity_id: int, request: Request,
                      limit: int = Query(50, ge=1, le=200)):
    """Full immutable change history for any entity — who changed what, when."""
    require_permission(request, "audit:read")
    if entity_type not in _VALID_ENTITIES:
        return http_error(400, f"Unknown entity type: {entity_type}", "VALIDATION_ERROR")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        history = await get_entity_history_async(conn, entity_type, entity_id, tenant_id, limit)

    return ok_response(f"History for {entity_type}/{entity_id}", {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "count": len(history),
        "history": history,
    })


@router.get("/recent")
async def recent_changes(request: Request,
                         entity_type: str = Query(None),
                         actor: str = Query(None),
                         limit: int = Query(100, ge=1, le=500)):
    """Recent audit events across all entities for this tenant."""
    require_permission(request, "audit:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conditions = ["tenant_id::text = %s"]
    params: list = [tenant_id]
    if entity_type:
        conditions.append("resource = %s"); params.append(entity_type)
    if actor:
        conditions.append("actor = %s"); params.append(actor)
    params.append(limit)

    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, actor, action, resource, resource_id,
                   old_value, new_value, details, created_at
            FROM audit_log
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT %s
        """), *params)]
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()

    return ok_response("Recent audit events", {"count": len(rows), "events": rows})
