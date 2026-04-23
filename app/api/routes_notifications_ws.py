"""
app/api/routes_notifications_ws.py
Bridge Hub — Real-time WebSocket Notifications
არსებული routes_notifications.py-ს არ ეხება.
"""
import json
import asyncio
from datetime import datetime
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from app.api.db import get_db
from app.api.tenant_context import resolve_tenant_id
import psycopg2.extras

router = APIRouter(prefix="/notifications/ws", tags=["notifications-ws"])


# ========== Connection Manager ==========

class NotificationManager:
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.connections:
            self.connections[tenant_id] = set()
        self.connections[tenant_id].add(websocket)

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.connections:
            self.connections[tenant_id].discard(websocket)

    async def send_to_tenant(self, tenant_id: str, message: dict):
        if tenant_id not in self.connections:
            return
        dead = set()
        for ws in self.connections[tenant_id]:
            try:
                await ws.send_text(json.dumps(message, ensure_ascii=False))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.connections[tenant_id].discard(ws)

    async def broadcast(self, message: dict):
        for tenant_id in self.connections:
            await self.send_to_tenant(tenant_id, message)


manager = NotificationManager()


# ========== WebSocket Endpoint ==========

@router.websocket("/live")
async def websocket_notifications(websocket: WebSocket, tenant_id: str = "default", token: str = ""):
    """
    WebSocket endpoint with JWT token verification.
    Query params: ?tenant_id=xxx&token=<jwt>
    """
    # Verify JWT token
    if token:
        try:
            from app.api.services.auth_service import verify_token
            payload = verify_token(token, expected_type="access")
            token_tenant = payload.get("tenant_id", "default")
            # Enforce tenant isolation: token's tenant_id must match requested tenant_id
            if token_tenant != tenant_id:
                await websocket.close(code=4003)
                return
        except Exception:
            await websocket.close(code=4001)
            return

    await manager.connect(websocket, tenant_id)
    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "tenant_id": tenant_id,
            "message": "Bridge Hub live notifications connected",
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False))

        while True:
            stats = _get_tenant_stats(tenant_id)
            await websocket.send_text(json.dumps({
                "type": "stats_update",
                "tenant_id": tenant_id,
                "data": stats,
                "timestamp": datetime.now().isoformat(),
            }, ensure_ascii=False))
            await asyncio.sleep(30)

    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)


# ========== REST Endpoints ==========

@router.get("/stats")
def get_notification_stats(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    stats = _get_tenant_stats(tenant_id)
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "stats": stats,
        "active_connections": len(manager.connections.get(tenant_id, set())),
    }


@router.get("/pending")
def get_pending_notifications(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id = %s AND status = 'pending_approval'
            ORDER BY created_at DESC
            LIMIT 20
        """, (tenant_id,))
        pending = [dict(r) for r in cur.fetchall()]
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "count": len(pending),
            "items": pending,
        }
    finally:
        cur.close()
        conn.close()


@router.post("/push")
async def push_notification(request: Request):
    """
    ხელით notification-ის გაგზავნა ყველა connected client-ზე.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    message = {
        "type": "manual_push",
        "tenant_id": tenant_id,
        "message": body.get("message", ""),
        "level": body.get("level", "info"),
        "timestamp": datetime.now().isoformat(),
    }
    await manager.send_to_tenant(tenant_id, message)
    return {
        "ok": True,
        "sent_to": len(manager.connections.get(tenant_id, set())),
        "message": message,
    }


# ========== Helper ==========

def _get_tenant_stats(tenant_id: str) -> dict:
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT status, COUNT(*) as count
            FROM journal_drafts
            WHERE tenant_id = %s
            GROUP BY status
        """, (tenant_id,))
        status_counts = {r["status"]: r["count"] for r in cur.fetchall()}

        cur.execute("""
            SELECT COUNT(*) as count
            FROM journal_drafts
            WHERE tenant_id = %s
            AND status = 'pending_approval'
            AND created_at > NOW() - INTERVAL '24 hours'
        """, (tenant_id,))
        new_today = cur.fetchone()["count"]

        return {
            "pending_approval": status_counts.get("pending_approval", 0),
            "approved_today": status_counts.get("approved", 0),
            "auto_approved": status_counts.get("auto_approved", 0),
            "rejected": status_counts.get("rejected", 0),
            "new_last_24h": new_today,
            "message": _build_message(status_counts),
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()


def _build_message(status_counts: dict) -> str:
    pending = status_counts.get("pending_approval", 0)
    if pending == 0:
        return "ყველა draft დამუშავებულია"
    if pending == 1:
        return "1 draft გელოდება დამტკიცებას"
    return f"{pending} draft გელოდება დამტკიცებას"