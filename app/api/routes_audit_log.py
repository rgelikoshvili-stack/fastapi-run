from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.audit import log_event

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


class AuditEventCreate(BaseModel):
    action: str
    resource: str
    resource_id: Optional[str] = None
    actor: Optional[str] = "system"
    role: Optional[str] = "system"
    details: Optional[str] = None
    status: Optional[str] = "success"


@router.post("/log")
def create_audit_event(data: AuditEventCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    ip = request.client.host if request.client else None
    log_event(action=data.action, resource=data.resource, resource_id=data.resource_id,
              actor=data.actor, role=data.role, details=data.details, status=data.status,
              ip_address=ip, tenant_id=tenant_id)
    return ok_response("Event logged", {"action": data.action, "resource": data.resource, "actor": data.actor})


@router.get("/list")
async def list_audit_log(request: Request, action: Optional[str] = None,
                          resource: Optional[str] = None, actor: Optional[str] = None, limit: int = 50):
    tenant_id = getattr(request.state, "tenant_id", "default")
    sql = "SELECT * FROM audit_log WHERE (tenant_id IS NULL OR tenant_id::text = $1)"
    params: list = [tenant_id]
    if action:
        params.append(action); sql += f" AND action = ${len(params)}"
    if resource:
        params.append(resource); sql += f" AND resource = ${len(params)}"
    if actor:
        params.append(actor); sql += f" AND actor = ${len(params)}"
    params.append(limit); sql += f" ORDER BY COALESCE(event_time, created_at) DESC LIMIT ${len(params)}"
    async with get_conn() as conn:
        try:
            rows = [dict(r) for r in await conn.fetch(sql, *params)]
        except Exception as e:
            return error_response("Failed to fetch audit log", "AUDIT_LIST_ERROR", str(e))
    return ok_response("Audit log", {"count": len(rows), "events": rows})


@router.get("/stats")
async def audit_stats(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        try:
            by_action = [dict(r) for r in await conn.fetch(_q("""
                SELECT action, COUNT(*) as cnt FROM audit_log
                WHERE (tenant_id IS NULL OR tenant_id::text = %s)
                GROUP BY action ORDER BY cnt DESC
            """), tenant_id)]
            by_resource = [dict(r) for r in await conn.fetch(_q("""
                SELECT resource, COUNT(*) as cnt FROM audit_log
                WHERE (tenant_id IS NULL OR tenant_id::text = %s)
                GROUP BY resource ORDER BY cnt DESC
            """), tenant_id)]
            by_actor = [dict(r) for r in await conn.fetch(_q("""
                SELECT actor, role, COUNT(*) as cnt FROM audit_log
                WHERE (tenant_id IS NULL OR tenant_id::text = %s)
                GROUP BY actor, role ORDER BY cnt DESC LIMIT 10
            """), tenant_id)]
            total = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM audit_log WHERE (tenant_id IS NULL OR tenant_id::text = %s)"), tenant_id) or 0
            errors = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM audit_log
                WHERE status = 'error' AND (tenant_id IS NULL OR tenant_id::text = %s)
            """), tenant_id) or 0
        except Exception as e:
            return error_response("Failed to fetch audit stats", "AUDIT_STATS_ERROR", str(e))
    return ok_response("Audit stats", {"total_events": total, "error_events": errors,
                                        "by_action": by_action, "by_resource": by_resource, "by_actor": by_actor})


@router.get("/timeline")
async def audit_timeline(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        try:
            timeline = [dict(r) for r in await conn.fetch(_q("""
                SELECT DATE_TRUNC('hour', COALESCE(event_time, created_at)) as hour, COUNT(*) as cnt
                FROM audit_log
                WHERE COALESCE(event_time, created_at) >= NOW() - INTERVAL '24 hours'
                  AND (tenant_id IS NULL OR tenant_id::text = %s)
                GROUP BY hour ORDER BY hour
            """), tenant_id)]
        except Exception as e:
            return error_response("Failed to fetch audit timeline", "AUDIT_TIMELINE_ERROR", str(e))
    return ok_response("Audit timeline (24h)", {"timeline": timeline})


@router.delete("/clear")
async def clear_old_events(request: Request, days: int = 90):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        try:
            st = await conn.execute(_q("""
                DELETE FROM audit_log
                WHERE tenant_id = %s
                  AND COALESCE(event_time, created_at) < NOW() - (%s || ' days')::interval
            """), tenant_id, str(days))
            deleted = int(st.split()[-1])
        except Exception as e:
            return error_response("Failed to clear old events", "AUDIT_CLEAR_ERROR", str(e))
    return ok_response("Old events cleared", {"deleted": deleted, "older_than_days": days})
