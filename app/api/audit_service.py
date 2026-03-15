import json
from app.api.db import get_db


def log_event(event_type: str, details: dict | None = None, actor: str = "system"):
    if details is None:
        details = {}

    conn = None
    cur = None

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_events (event_type, actor, details)
            VALUES (%s, %s, %s)
            """,
            (
                event_type,
                actor,
                json.dumps(details, ensure_ascii=False),
            ),
        )
        conn.commit()

    except Exception as e:
        print(f"Audit log error: {e}")

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()