import psycopg2.extras
from app.api.db import get_db
from fastapi import Header, HTTPException
from typing import Optional

ROLE_PERMISSIONS = {
    "admin": ["read", "write", "approve", "reject", "export", "manage_users"],
    "accountant": ["read", "write", "approve", "reject", "export"],
    "viewer": ["read", "export"],
}

def get_user_by_key(api_key: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM users WHERE api_key=%s AND active=TRUE", (api_key,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close(); conn.close()

def can(user: dict, permission: str) -> bool:
    role = user.get("role", "viewer")
    return permission in ROLE_PERMISSIONS.get(role, [])

def require_permission(permission: str):
    def dependency(x_api_key: Optional[str] = Header(None)):
        if not x_api_key:
            raise HTTPException(status_code=401, detail="X-Api-Key header required")
        user = get_user_by_key(x_api_key)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if not can(user, permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return user
    return dependency
