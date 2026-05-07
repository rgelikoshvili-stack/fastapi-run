import json
import logging
from app.api.db import get_db

log = logging.getLogger(__name__)

def log_event(event_type: str, details: dict | None = None, actor: str = "system", tenant_id: str = "default"):
    if details is None:
        details = {}
    details["_tenant_id"] = tenant_id
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_events (event_type, actor, details, tenant_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                event_type,
                actor,
                json.dumps(details, ensure_ascii=False),
                tenant_id,
            ),
        )
        conn.commit()
    except Exception:
        try:
            cur.execute(
                """
                INSERT INTO audit_events (event_type, actor, details, tenant_id)
                VALUES (%s, %s, %s, %s)
                """,
                (event_type, actor, json.dumps(details, ensure_ascii=False), tenant_id),
            )
            conn.commit()
        except Exception as e2:
            log.exception(
                "audit_log_write_failed event_type=%s actor=%s tenant_id=%s error=%s",
                event_type,
                actor,
                tenant_id,
                e2,
            )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
