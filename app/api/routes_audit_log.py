from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit import log_event

router = APIRouter(prefix="/audit", tags=["audit"])

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
    ip = request.client.host if request.client else None
    log_event(
        action=data.action,
        resource=data.resource,
        resource_id=data.resource_id,
        actor=data.actor,
        role=data.role,
        details=data.details,
        status=data.status,
        ip_address=ip
    )
    return ok_response("Event logged", {
        "action": data.action,
        "resource": data.resource,
        "actor": data.actor
    })

@router.get("/list")
def list_audit_log(
    action: Optional[str] = None,
    resource: Optional[str] = None,
    actor: Optional[str] = None,
    limit: int = 50
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if action:
            query += " AND action=%s"; params.append(action)
        if resource:
            query += " AND resource=%s"; params.append(resource)
        if actor:
            query += " AND actor=%s"; params.append(actor)
        query += " ORDER BY COALESCE(event_time, created_at) DESC LIMIT %s"
        params.append(limit)
        cur.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Audit log", {"count": len(rows), "events": rows})

@router.get("/stats")
def audit_stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT action, COUNT(*) as cnt
            FROM audit_log GROUP BY action ORDER BY cnt DESC
        """)
        by_action = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT resource, COUNT(*) as cnt
            FROM audit_log GROUP BY resource ORDER BY cnt DESC
        """)
        by_resource = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT actor, role, COUNT(*) as cnt
            FROM audit_log GROUP BY actor, role ORDER BY cnt DESC LIMIT 10
        """)
        by_actor = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT COUNT(*) as total FROM audit_log")
        total = cur.fetchone()["total"]

        cur.execute("""
            SELECT COUNT(*) as cnt FROM audit_log
            WHERE status='error'
        """)
        errors = cur.fetchone()["cnt"]
    finally:
        cur.close(); conn.close()

    return ok_response("Audit stats", {
        "total_events": total,
        "error_events": errors,
        "by_action": by_action,
        "by_resource": by_resource,
        "by_actor": by_actor
    })

@router.get("/timeline")
def audit_timeline():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT DATE_TRUNC('hour', COALESCE(event_time, created_at)) as hour,
                   COUNT(*) as cnt
            FROM audit_log
            WHERE COALESCE(event_time, created_at) >= NOW() - INTERVAL '24 hours'
            GROUP BY hour ORDER BY hour
        """)
        timeline = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Audit timeline (24h)", {"timeline": timeline})

@router.delete("/clear")
def clear_old_events(days: int = 90):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM audit_log
            WHERE event_time < NOW() - INTERVAL '%s days'
        """, (days,))
        deleted = cur.rowcount
        conn.commit()
    finally:
        cur.close(); conn.close()
    return ok_response("Old events cleared", {"deleted": deleted, "older_than_days": days})
