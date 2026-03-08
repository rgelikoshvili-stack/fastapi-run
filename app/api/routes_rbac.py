from fastapi import APIRouter, Header, Depends
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.rbac import get_user_by_key, can, ROLE_PERMISSIONS, require_permission
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/auth", tags=["auth"])

class UserCreate(BaseModel):
    name: str
    email: str
    role: str = "accountant"
    tenant_id: Optional[int] = None

@router.get("/me")
def get_me(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        return error_response("API key required", "AUTH_ERROR", "Pass X-Api-Key header")
    user = get_user_by_key(x_api_key)
    if not user:
        return error_response("Invalid API key", "AUTH_ERROR", "")
    perms = ROLE_PERMISSIONS.get(user.get("role","viewer"), [])
    return ok_response("User info", {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "permissions": perms
    })

@router.get("/users")
def list_users(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        return error_response("Auth required", "AUTH_ERROR", "")
    caller = get_user_by_key(x_api_key)
    if not caller or not can(caller, "manage_users"):
        return error_response("Admin only", "FORBIDDEN", "")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT id, name, email, role, active, created_at FROM users ORDER BY id")
        users = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Users", {"count": len(users), "users": users})

@router.post("/users/create")
def create_user(data: UserCreate, x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        return error_response("Auth required", "AUTH_ERROR", "")
    caller = get_user_by_key(x_api_key)
    if not caller or not can(caller, "manage_users"):
        return error_response("Admin only", "FORBIDDEN", "")
    if data.role not in ROLE_PERMISSIONS:
        return error_response("Invalid role", "VALIDATION_ERROR", f"Use: {list(ROLE_PERMISSIONS.keys())}")
    conn = get_db()
    cur = conn.cursor()
    try:
        import secrets
        api_key = secrets.token_hex(16)
        cur.execute(
            "INSERT INTO users (name, email, role, tenant_id, api_key) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (data.name, data.email, data.role, data.tenant_id, api_key)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("User created", {"id": new_id, "email": data.email, "role": data.role, "api_key": api_key})

@router.get("/roles")
def list_roles():
    return ok_response("Roles & permissions", ROLE_PERMISSIONS)
