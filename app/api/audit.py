import psycopg2
from app.api.db import get_db
from datetime import datetime
import json

def log_event(
    action: str,
    resource: str,
    resource_id: str = None,
    actor: str = "system",
    role: str = "system",
    old_value: dict = None,
    new_value: dict = None,
    status: str = "success",
    details: str = None,
    tenant_id: str = None,
    ip_address: str = None
):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log 
            (actor, role, action, resource, resource_id, old_value, new_value,
             ip_address, status, details, tenant_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            actor, role, action, resource,
            str(resource_id) if resource_id else None,
            json.dumps(old_value) if old_value else None,
            json.dumps(new_value) if new_value else None,
            ip_address, status, details,
            str(tenant_id) if tenant_id else None
        ))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Audit log error: {e}")
