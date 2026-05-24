"""app/api/routes_rsge_credentials.py
Bridge Hub — Per-tenant RS.ge (Revenue Service) credentials.
Stores RS.ge portal username/password for future direct API posting.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_conn, _q
from app.api.authz import require_permission

router = APIRouter(prefix="/rsge-credentials", tags=["rsge-credentials"])

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS tenant_rsge_credentials (
        id           SERIAL PRIMARY KEY,
        tenant_id    TEXT NOT NULL UNIQUE,
        username     TEXT NOT NULL,
        password     TEXT NOT NULL,
        taxpayer_inn TEXT DEFAULT '',
        updated_at   TIMESTAMPTZ DEFAULT NOW()
    )
"""


class RsgeCredsPayload(BaseModel):
    username: str
    password: str
    taxpayer_inn: Optional[str] = ""


@router.get("/status")
async def get_status(request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await conn.execute(_CREATE_TABLE)
            row = await conn.fetchrow(_q(
                "SELECT username, taxpayer_inn FROM tenant_rsge_credentials WHERE tenant_id = %s"
            ), tenant_id)
        if row:
            return ok_response("ok", {"configured": True, "username": row["username"], "taxpayer_inn": row["taxpayer_inn"]})
        return ok_response("ok", {"configured": False})
    except Exception as e:
        return ok_response("ok", {"configured": False, "error": str(e)})


@router.post("/save")
async def save_creds(body: RsgeCredsPayload, request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.username:
        return error_response("username is required", "ERROR", "")
    if not body.password:
        return error_response("password is required", "ERROR", "")
    try:
        async with get_conn() as conn:
            await conn.execute(_CREATE_TABLE)
            await conn.execute(_q("""
                INSERT INTO tenant_rsge_credentials (tenant_id, username, password, taxpayer_inn)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE
                SET username = EXCLUDED.username,
                    password = EXCLUDED.password,
                    taxpayer_inn = EXCLUDED.taxpayer_inn,
                    updated_at = NOW()
            """), tenant_id, body.username, body.password, body.taxpayer_inn or "")
        return ok_response("ok", {"message": "RS.ge credentials saved"})
    except Exception as e:
        return error_response(str(e), "ERROR", "")


@router.post("/test")
async def test_connection(request: Request):
    """Verify credentials are saved. Live portal validation coming soon."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT username, taxpayer_inn FROM tenant_rsge_credentials WHERE tenant_id = %s"
            ), tenant_id)
        if row:
            return {
                "ok": True,
                "message": f"Credentials saved for {row['username']}. Live RS.ge portal sync: coming soon.",
            }
        return error_response("No credentials saved — please save first", "ERROR", "")
    except Exception:
        return error_response("Credentials not found", "ERROR", "")
