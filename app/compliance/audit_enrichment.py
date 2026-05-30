"""
app/compliance/audit_enrichment.py
Bridge Hub — Audit Log Enrichment
audit_events-ს ამატებს დამატებით მეტადატას.
append-only პრინციპი რჩება — მხოლოდ enrichment, არა overwrite.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from app.api.db import get_conn, _q


def enrich_audit_event(
    event_type: str,
    actor: str = "system",
    actor_role: str = "system",
    tenant_id: str = "default",
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    action_source: str = "api",
    details: dict = None,
) -> dict:
    return {
        "event_type": event_type,
        "actor": actor,
        "actor_role": actor_role,
        "tenant_id": tenant_id,
        "object_type": object_type,
        "object_id": str(object_id) if object_id else None,
        "action_source": action_source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    }


async def log_enriched_event(
    event_type: str,
    actor: str = "system",
    actor_role: str = "system",
    tenant_id: str = "default",
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    action_source: str = "api",
    details: dict = None,
) -> bool:
    enriched = enrich_audit_event(
        event_type=event_type, actor=actor, actor_role=actor_role,
        tenant_id=tenant_id, object_type=object_type, object_id=object_id,
        action_source=action_source, details=details,
    )
    try:
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO audit_events (event_type, actor, tenant_id, details, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """),
            enriched["event_type"],
            f"{enriched['actor']}:{enriched['actor_role']}",
            enriched["tenant_id"],
            json.dumps({
                **enriched["details"],
                "object_type": enriched["object_type"],
                "object_id": enriched["object_id"],
                "action_source": enriched["action_source"],
                "actor_role": enriched["actor_role"],
            }, ensure_ascii=False))
        return True
    except Exception:
        return False


async def get_audit_summary(tenant_id: str = "default", limit: int = 100) -> dict:
    try:
        async with get_conn() as conn:
            by_type_rows = await conn.fetch(_q("""
                SELECT event_type, COUNT(*) as count, MAX(created_at) as last_at
                FROM audit_events WHERE tenant_id = %s
                GROUP BY event_type ORDER BY count DESC LIMIT %s
            """), tenant_id, limit)

            total = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM audit_events WHERE tenant_id = %s"
            ), tenant_id)

            recent_rows = await conn.fetch(_q("""
                SELECT event_type, actor, details, created_at
                FROM audit_events WHERE tenant_id = %s
                ORDER BY created_at DESC LIMIT 5
            """), tenant_id)

        return {
            "tenant_id": tenant_id,
            "total_events": total,
            "by_type": [dict(r) for r in by_type_rows],
            "recent": [dict(r) for r in recent_rows],
        }
    except Exception as e:
        return {"error": str(e)}
