from fastapi import APIRouter, Header
from pydantic import BaseModel
from typing import Optional
from app.api.db import get_conn, _q
from app.api.authz import ROLE_PERMISSIONS, has_role_permission
from app.api.response_utils import ok_response, error_response


async def get_user_by_key(api_key: str):
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT * FROM users WHERE api_key=%s AND active=TRUE"), api_key)
    return dict(row) if row else None

router = APIRouter(prefix="/auth", tags=["auth"])

class UserCreate(BaseModel):
    name: str
    email: str
    role: str = "accountant"
    tenant_id: Optional[int] = None

@router.get("/me-apikey")
async def get_me(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        return error_response("API key required", "AUTH_ERROR", "Pass X-Api-Key header")
    user = await get_user_by_key(x_api_key)
    if not user:
        return error_response("Invalid API key", "AUTH_ERROR", "")
    perms = sorted(ROLE_PERMISSIONS.get(user.get("role", "viewer"), set()))
    return ok_response("User info", {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "permissions": perms
    })

@router.get("/users")
async def list_users(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        return error_response("Auth required", "AUTH_ERROR", "")
    caller = await get_user_by_key(x_api_key)
    if not caller or not has_role_permission(caller.get("role", "viewer"), "tenants:manage"):
        return error_response("Admin only", "FORBIDDEN", "")
    async with get_conn() as conn:
        users = [dict(r) for r in await conn.fetch(
            "SELECT id, name, email, role, active, created_at FROM users ORDER BY id")]
    return ok_response("Users", {"count": len(users), "users": users})

@router.post("/users/create")
async def create_user(data: UserCreate, x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        return error_response("Auth required", "AUTH_ERROR", "")
    caller = await get_user_by_key(x_api_key)
    if not caller or not has_role_permission(caller.get("role", "viewer"), "tenants:manage"):
        return error_response("Admin only", "FORBIDDEN", "")
    if data.role not in ROLE_PERMISSIONS:
        return error_response("Invalid role", "VALIDATION_ERROR", f"Use: {list(ROLE_PERMISSIONS.keys())}")
    try:
        import secrets
        api_key = secrets.token_hex(16)
        async with get_conn() as conn:
            new_id = await conn.fetchval(_q(
                "INSERT INTO users (name, email, role, tenant_id, api_key) VALUES (%s,%s,%s,%s,%s) RETURNING id"),
                data.name, data.email, data.role, data.tenant_id, api_key)
    except Exception as e:
        return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("User created", {"id": new_id, "email": data.email, "role": data.role, "api_key": api_key})

@router.get("/roles")
def list_roles():
    return ok_response("Roles & permissions", {r: sorted(p) for r, p in ROLE_PERMISSIONS.items()})
