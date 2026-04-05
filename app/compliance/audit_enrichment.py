"""
app/compliance/audit_enrichment.py
Bridge Hub — Audit Log Enrichment
audit_events-ს ამატებს დამატებით მეტადატას.
append-only პრინციპი რჩება — მხოლოდ enrichment, არა overwrite.
"""
from datetime import datetime, timezone
from typing import Optional
import psycopg2.extras
from app.api.db import get_db


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
    """
    Audit event-ს ამდიდრებს სტანდარტული მეტადატით.
    """
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


def log_enriched_event(
    event_type: str,
    actor: str = "system",
    actor_role: str = "system",
    tenant_id: str = "default",
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    action_source: str = "api",
    details: dict = None,
) -> bool:
    """
    Enriched audit event-ს DB-ში წერს.
    append-only — არასდროს არ განახლდება.
    """
    import json
    enriched = enrich_audit_event(
        event_type=event_type,
        actor=actor,
        actor_role=actor_role,
        tenant_id=tenant_id,
        object_type=object_type,
        object_id=object_id,
        action_source=action_source,
        details=details,
    )

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO audit_events (
                event_type, actor, tenant_id, details, created_at
            ) VALUES (%s, %s, %s, %s, NOW())
        """, (
            enriched["event_type"],
            f"{enriched['actor']}:{enriched['actor_role']}",
            enriched["tenant_id"],
            json.dumps({
                **enriched["details"],
                "object_type": enriched["object_type"],
                "object_id": enriched["object_id"],
                "action_source": enriched["action_source"],
                "actor_role": enriched["actor_role"],
            }, ensure_ascii=False),
        ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def get_audit_summary(tenant_id: str = "default", limit: int = 100) -> dict:
    """
    Audit log-ის შეჯამება tenant-ისთვის.
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
                event_type,
                COUNT(*) as count,
                MAX(created_at) as last_at
            FROM audit_events
            WHERE tenant_id = %s
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT %s
        """, (tenant_id, limit))
        by_type = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(*) as total
            FROM audit_events
            WHERE tenant_id = %s
        """, (tenant_id,))
        total = cur.fetchone()["total"]

        cur.execute("""
            SELECT event_type, actor, details, created_at
            FROM audit_events
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT 5
        """, (tenant_id,))
        recent = [dict(r) for r in cur.fetchall()]

        return {
            "tenant_id": tenant_id,
            "total_events": total,
            "by_type": by_type,
            "recent": recent,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()