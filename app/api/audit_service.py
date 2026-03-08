import psycopg2, json
from app.api.db import get_db

def log_event(event_type: str, details: dict = {}, actor: str = "system"):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_events (event_type, actor, details) VALUES (%s, %s, %s)",
            (event_type, actor, json.dumps(details))
        )
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Audit log error: {e}")
