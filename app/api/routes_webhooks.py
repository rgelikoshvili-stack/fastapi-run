"""app/api/routes_webhooks.py — Webhook registration and management."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, HttpUrl
from typing import List, Optional

from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_db
from app.api.response_utils import ok_response, http_error
from app.api.services.webhook_service import _ensure_table, _SUPPORTED_EVENTS
import secrets
import logging

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)


class WebhookCreate(BaseModel):
    url: str
    events: List[str] = []   # empty = all events
    description: Optional[str] = None
    generate_secret: bool = True


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/events")
def list_supported_events(request: Request):
    """List all supported webhook event types."""
    require_permission(request, "tenants:manage")
    return ok_response("Supported events", sorted(_SUPPORTED_EVENTS))


@router.post("/")
def create_webhook(body: WebhookCreate, request: Request):
    """Register a new webhook endpoint."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    # Validate events
    invalid = [e for e in body.events if e not in _SUPPORTED_EVENTS]
    if invalid:
        return http_error(400, f"Unknown events: {invalid}", "VALIDATION_ERROR")

    secret = secrets.token_hex(32) if body.generate_secret else None
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_table(conn)
        cur.execute("""
            INSERT INTO webhooks (tenant_id, url, events, secret, description)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (tenant_id, body.url, body.events or [], secret, body.description))
        hook_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return http_error(500, "Failed to create webhook", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    return ok_response("Webhook registered", {
        "id": hook_id,
        "url": body.url,
        "events": body.events or ["all"],
        "secret": secret,
        "note": "Store the secret — it won't be shown again. Use it to verify X-BridgeHub-Signature.",
    })


@router.get("/")
def list_webhooks(request: Request):
    """List all webhooks for this tenant."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_table(conn)
        cur.execute("""
            SELECT id, url, events, is_active, description,
                   last_fired, failure_count, created_at
            FROM webhooks WHERE tenant_id = %s ORDER BY created_at DESC
        """, (tenant_id,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            for f in ("last_fired", "created_at"):
                if r.get(f):
                    r[f] = r[f].isoformat()
    finally:
        cur.close(); conn.close()

    return ok_response("Webhooks", rows)


@router.get("/{hook_id}/deliveries")
def get_deliveries(hook_id: int, request: Request):
    """Recent delivery history for a webhook."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, event, status_code, success, response, delivered_at
            FROM webhook_deliveries
            WHERE webhook_id = %s AND tenant_id = %s
            ORDER BY delivered_at DESC LIMIT 50
        """, (hook_id, tenant_id))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            if r.get("delivered_at"):
                r["delivered_at"] = r["delivered_at"].isoformat()
    except Exception:
        rows = []
    finally:
        cur.close(); conn.close()

    return ok_response("Deliveries", rows)


@router.put("/{hook_id}")
def update_webhook(hook_id: int, body: WebhookUpdate, request: Request):
    """Update webhook URL, events, or active state."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor()
    try:
        sets, params = [], []
        if body.url is not None:
            sets.append("url = %s"); params.append(body.url)
        if body.events is not None:
            sets.append("events = %s"); params.append(body.events)
        if body.description is not None:
            sets.append("description = %s"); params.append(body.description)
        if body.is_active is not None:
            sets.append("is_active = %s"); params.append(body.is_active)

        if not sets:
            return http_error(400, "No fields to update", "VALIDATION_ERROR")

        params += [hook_id, tenant_id]
        cur.execute(f"""
            UPDATE webhooks SET {', '.join(sets)}
            WHERE id = %s AND tenant_id = %s RETURNING id
        """, params)
        row = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        return http_error(500, "Update failed", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    if not row:
        return http_error(404, "Webhook not found", "NOT_FOUND")
    return ok_response("Webhook updated", {"id": hook_id})


@router.delete("/{hook_id}")
def delete_webhook(hook_id: int, request: Request):
    """Delete a webhook registration."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM webhooks WHERE id = %s AND tenant_id = %s RETURNING id",
            (hook_id, tenant_id),
        )
        row = cur.fetchone()
        conn.commit()
    finally:
        cur.close(); conn.close()

    if not row:
        return http_error(404, "Webhook not found", "NOT_FOUND")
    return ok_response("Webhook deleted", {"id": hook_id})
