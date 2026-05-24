import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List, Optional
import httpx, hmac, hashlib, json
from datetime import datetime
from app.api.db import get_conn, _q
from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response
from app.api.authz import require_permission
log = logging.getLogger(__name__)


router = APIRouter(prefix="/webhooks", tags=["webhooks"])

AVAILABLE_EVENTS = [
    "draft.created", "draft.approved", "draft.rejected",
    "reconcile.complete", "invoice.parsed", "pipeline.complete"
]

class WebhookCreate(BaseModel):
    name: str
    url: str
    events: List[str]
    secret: Optional[str] = None

class WebhookTrigger(BaseModel):
    event: str
    payload: Optional[dict] = {}

def sign_payload(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def _ensure_tenant_id_col(conn):
    try:
        await conn.execute("ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'")
    except Exception as e:
        log.warning("unexpected error: %s", e)


async def fire_webhook(webhook: dict, event: str, payload: dict):
    body = json.dumps({"event": event, "timestamp": datetime.now().isoformat(), "data": payload})
    headers = {"Content-Type": "application/json", "X-BridgeHub-Event": event, "X-BridgeHub-Version": "1.0"}
    if webhook.get("secret"):
        headers["X-BridgeHub-Signature"] = sign_payload(webhook["secret"], body)
    success, code = False, 0
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(webhook["url"], content=body, headers=headers)
            code = r.status_code
            success = r.status_code < 400
    except Exception:
        code = 0
    async with get_conn() as conn:
        try:
            await conn.execute(_q("""
                INSERT INTO webhook_logs (webhook_id, event, payload, response_code, success)
                VALUES (%s::uuid,%s,%s,%s,%s)
            """), webhook["id"], event, json.dumps(payload), code, success)
            await conn.execute(_q("UPDATE webhooks SET last_triggered=NOW() WHERE id=%s"), webhook["id"])
        except Exception as e:
            log.warning("unexpected error: %s", e)
    return success, code

@router.get("/events")
def list_events():
    return ok_response("Available events", {"events": AVAILABLE_EVENTS})

@router.post("/create")
async def create_webhook(data: WebhookCreate, request: Request):
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    invalid = [e for e in data.events if e not in AVAILABLE_EVENTS]
    if invalid:
        return error_response("Invalid events", "VALIDATION_ERROR", f"Unknown: {invalid}")
    async with get_conn() as conn:
        await _ensure_tenant_id_col(conn)
        try:
            new_id = await conn.fetchval(_q("""
                INSERT INTO webhooks (tenant_id, name, url, events, secret) VALUES (%s,%s,%s,%s,%s) RETURNING id
            """), tenant_id, data.name, data.url, data.events, data.secret)
        except Exception as e:
            return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Webhook created", {"id": new_id, "name": data.name, "events": data.events, "tenant_id": tenant_id})

@router.get("/list")
async def list_webhooks(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        await _ensure_tenant_id_col(conn)
        hooks = [dict(r) for r in await conn.fetch(_q(
            "SELECT id, name, url, events, active, last_triggered FROM webhooks WHERE tenant_id=%s ORDER BY id"),
            tenant_id)]
    return ok_response("Webhooks", {"count": len(hooks), "webhooks": hooks})

@router.post("/trigger")
async def trigger_webhook(req: WebhookTrigger, request: Request):
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if req.event not in AVAILABLE_EVENTS:
        return error_response("Invalid event", "VALIDATION_ERROR", f"Use: {AVAILABLE_EVENTS}")
    async with get_conn() as conn:
        await _ensure_tenant_id_col(conn)
        hooks = [dict(r) for r in await conn.fetch(_q(
            "SELECT * FROM webhooks WHERE active=TRUE AND %s = ANY(events) AND tenant_id=%s"),
            req.event, tenant_id)]
    results = []
    for hook in hooks:
        success, code = await fire_webhook(hook, req.event, req.payload)
        results.append({"webhook_id": hook["id"], "name": hook["name"], "success": success, "code": code})
    return ok_response("Webhooks triggered", {"event": req.event, "triggered": len(results), "results": results})

@router.get("/logs")
async def webhook_logs(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        await _ensure_tenant_id_col(conn)
        logs = [dict(r) for r in await conn.fetch(_q("""
            SELECT wl.id, w.name, wl.event, wl.response_code, wl.success, wl.created_at
            FROM webhook_logs wl JOIN webhooks w ON w.id=wl.webhook_id
            WHERE w.tenant_id = %s
            ORDER BY wl.created_at DESC LIMIT 50
        """), tenant_id)]
    return ok_response("Webhook logs", {"count": len(logs), "logs": logs})

@router.delete("/delete/{webhook_id}")
async def delete_webhook(webhook_id: int, request: Request):
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        await conn.execute(_q("UPDATE webhooks SET active=FALSE WHERE id=%s AND tenant_id=%s"), webhook_id, tenant_id)
    return ok_response("Webhook deactivated", {"id": webhook_id})
