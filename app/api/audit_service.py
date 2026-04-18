import json
from app.api.db import get_db

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
            print(f"Audit log error: {e2}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
