"""
app/api/routes_notifications_ws.py
Bridge Hub — Real-time WebSocket Notifications
"""
import json
import asyncio
from datetime import datetime
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from app.api.db import get_conn, _q
from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission

router = APIRouter(prefix="/notifications/ws", tags=["notifications-ws"])


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


@router.websocket("/live")
async def websocket_notifications(websocket: WebSocket, tenant_id: str = "default", token: str = ""):
    """Read-only live notifications, bound to an authenticated tenant.

    WebSocket connections do not traverse HTTP auth middleware. Refuse missing,
    invalid, refresh-only, default-tenant or cross-tenant access tokens even
    when the optional live-membership release flag is not enabled.
    """
    from app.api.db import tenant_db_context
    from app.api.services.auth_service import (
        access_membership_check_enabled,
        verify_live_access_membership,
        verify_token,
    )

    if not token:
        await websocket.close(code=4001)
        return
    payload = verify_token(token, expected_type="access")
    if not payload:
        await websocket.close(code=4001)
        return
    signed_tenant = payload.get("tenant_id")
    if (
        not isinstance(signed_tenant, str)
        or not signed_tenant
        or signed_tenant != signed_tenant.strip()
        or signed_tenant.casefold() == "default"
        or signed_tenant != tenant_id
        or not payload.get("sub")
    ):
        await websocket.close(code=4003)
        return

    live_enabled = access_membership_check_enabled()

    async def member_still_active() -> bool:
        if not live_enabled:
            return True
        try:
            return await verify_live_access_membership(payload)
        except Exception:
            # Do not send notifications when membership status is unknown.
            return False

    if not await member_still_active():
        await websocket.close(code=4003)
        return

    await manager.connect(websocket, signed_tenant)
    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "tenant_id": signed_tenant,
            "message": "Bridge Hub live notifications connected",
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False))

        while True:
            # Existing sockets revalidate before each poll (maximum 30 seconds
            # between checks). This is not instantaneous revocation of a
            # broadcast already in flight; release still requires that gate.
            if not await member_still_active():
                await websocket.close(code=4003)
                break
            async with tenant_db_context(signed_tenant):
                stats = await _get_tenant_stats(signed_tenant)
            await websocket.send_text(json.dumps({
                "type": "stats_update",
                "tenant_id": signed_tenant,
                "data": stats,
                "timestamp": datetime.now().isoformat(),
            }, ensure_ascii=False))
            await asyncio.sleep(30)

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, signed_tenant)


@router.get("/stats")
async def get_notification_stats(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    stats = await _get_tenant_stats(tenant_id)
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "stats": stats,
        "active_connections": len(manager.connections.get(tenant_id, set())),
    }


@router.get("/pending")
async def get_pending_notifications(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        pending = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id = %s AND status = 'pending_approval'
            ORDER BY created_at DESC
            LIMIT 20
        """), tenant_id)]
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "count": len(pending),
        "items": pending,
    }


@router.post("/push")
async def push_notification(request: Request):
    """ხელით notification-ის გაგზავნა ყველა connected client-ზე."""
    require_permission(request, "notifications:write")
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


async def _get_tenant_stats(tenant_id: str) -> dict:
    try:
        async with get_conn() as conn:
            status_rows = await conn.fetch(_q("""
                SELECT status, COUNT(*) as count
                FROM journal_drafts WHERE tenant_id = %s GROUP BY status
            """), tenant_id)
            status_counts = {r["status"]: r["count"] for r in status_rows}

            new_today = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM journal_drafts
                WHERE tenant_id = %s AND status = 'pending_approval'
                  AND created_at > NOW() - INTERVAL '24 hours'
            """), tenant_id) or 0

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


def _build_message(status_counts: dict) -> str:
    pending = status_counts.get("pending_approval", 0)
    if pending == 0:
        return "ყველა draft დამუშავებულია"
    if pending == 1:
        return "1 draft გელოდება დამტკიცებას"
    return f"{pending} draft გელოდება დამტკიცებას"
