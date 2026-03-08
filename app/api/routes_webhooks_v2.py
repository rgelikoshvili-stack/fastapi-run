from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import httpx, hmac, hashlib, json
from datetime import datetime
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

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

async def fire_webhook(webhook: dict, event: str, payload: dict):
    body = json.dumps({"event": event, "timestamp": datetime.now().isoformat(), "data": payload})
    headers = {
        "Content-Type": "application/json",
        "X-BridgeHub-Event": event,
        "X-BridgeHub-Version": "1.0",
    }
    if webhook.get("secret"):
        headers["X-BridgeHub-Signature"] = sign_payload(webhook["secret"], body)

    success, code = False, 0
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(webhook["url"], content=body, headers=headers)
            code = r.status_code
            success = r.status_code < 400
    except Exception as e:
        code = 0

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO webhook_logs (webhook_id, event, payload, response_code, success) VALUES (%s::uuid,%s,%s,%s,%s)",
            (webhook["id"], event, json.dumps(payload), code, success)
        )
        cur.execute("UPDATE webhooks SET last_triggered=NOW() WHERE id=%s", (webhook["id"],))
        conn.commit()
    finally:
        cur.close(); conn.close()
    return success, code

@router.get("/events")
def list_events():
    return ok_response("Available events", {"events": AVAILABLE_EVENTS})

@router.post("/create")
def create_webhook(data: WebhookCreate):
    invalid = [e for e in data.events if e not in AVAILABLE_EVENTS]
    if invalid:
        return error_response("Invalid events", "VALIDATION_ERROR", f"Unknown: {invalid}")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO webhooks (name, url, events, secret) VALUES (%s,%s,%s,%s) RETURNING id",
            (data.name, data.url, data.events, data.secret)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Webhook created", {"id": new_id, "name": data.name, "events": data.events})

@router.get("/list")
def list_webhooks():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT id, name, url, events, active, last_triggered FROM webhooks ORDER BY id")
        hooks = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Webhooks", {"count": len(hooks), "webhooks": hooks})

@router.post("/trigger")
async def trigger_webhook(req: WebhookTrigger):
    if req.event not in AVAILABLE_EVENTS:
        return error_response("Invalid event", "VALIDATION_ERROR", f"Use: {AVAILABLE_EVENTS}")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM webhooks WHERE active=TRUE AND %s = ANY(events)", (req.event,))
        hooks = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    results = []
    for hook in hooks:
        success, code = await fire_webhook(hook, req.event, req.payload)
        results.append({"webhook_id": hook["id"], "name": hook["name"], "success": success, "code": code})

    return ok_response("Webhooks triggered", {"event": req.event, "triggered": len(results), "results": results})

@router.get("/logs")
def webhook_logs():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT wl.id, w.name, wl.event, wl.response_code, wl.success, wl.created_at
            FROM webhook_logs wl JOIN webhooks w ON w.id=wl.webhook_id
            ORDER BY wl.created_at DESC LIMIT 50
        """)
        logs = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Webhook logs", {"count": len(logs), "logs": logs})

@router.delete("/delete/{webhook_id}")
def delete_webhook(webhook_id: int):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE webhooks SET active=FALSE WHERE id=%s", (webhook_id,))
        conn.commit()
    finally:
        cur.close(); conn.close()
    return ok_response("Webhook deactivated", {"id": webhook_id})
