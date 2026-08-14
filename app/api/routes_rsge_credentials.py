"""app/api/routes_rsge_credentials.py
Bridge Hub - per-tenant RS.ge credential metadata.

RS.ge secrets are stored only in Credential Vault. This route keeps safe
metadata for status/testing and never returns or logs raw credentials.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_conn, _q
from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response
from app.api.services.credential_vault_service import CredentialVaultService

router = APIRouter(prefix="/rsge-credentials", tags=["rsge-credentials"])

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS tenant_rsge_credentials (
        id                   SERIAL PRIMARY KEY,
        tenant_id            TEXT NOT NULL UNIQUE,
        username             TEXT NOT NULL,
        taxpayer_inn         TEXT DEFAULT '',
        credential_vault_ref TEXT DEFAULT 'rsge:portal_password',
        credential_status    TEXT DEFAULT 'vault',
        updated_at           TIMESTAMPTZ DEFAULT NOW()
    )
"""

_LEGACY_COLUMNS = """
    ALTER TABLE tenant_rsge_credentials
        ADD COLUMN IF NOT EXISTS credential_vault_ref TEXT DEFAULT 'rsge:portal_password',
        ADD COLUMN IF NOT EXISTS credential_status TEXT DEFAULT 'legacy_plaintext'
"""


class RsgeCredsPayload(BaseModel):
    username: str
    password: str
    taxpayer_inn: Optional[str] = ""


def _actor(request: Request) -> Optional[str]:
    actor = getattr(request.state, "user_id", None) or getattr(request.state, "user", None)
    return str(actor) if actor else None


@router.get("/status")
async def get_status(request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await conn.execute(_CREATE_TABLE)
            await conn.execute(_LEGACY_COLUMNS)
            row = await conn.fetchrow(_q(
                """
                SELECT username, taxpayer_inn, credential_vault_ref, credential_status
                FROM tenant_rsge_credentials
                WHERE tenant_id = %s
                """
            ), tenant_id)
            vault_status = await CredentialVaultService().get_status(
                conn, tenant_id, "rsge", "portal_password"
            )
        if row:
            return ok_response("ok", {
                "configured": bool(vault_status.get("configured")),
                "username": row["username"],
                "taxpayer_inn": row["taxpayer_inn"],
                "credential_vault_ref": row["credential_vault_ref"],
                "credential_status": (
                    "vault" if vault_status.get("configured") else row["credential_status"]
                ),
                "masked_hint": vault_status.get("masked_hint"),
            })
        return ok_response("ok", {"configured": False, "credential_status": "not_configured"})
    except Exception as e:
        return ok_response("ok", {"configured": False, "error": type(e).__name__})


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
            await conn.execute(_LEGACY_COLUMNS)
            vault_result = await CredentialVaultService().save_credential(
                conn,
                tenant_id=tenant_id,
                provider="rsge",
                credential_type="portal_password",
                raw_value=body.password,
                metadata={"username": body.username, "taxpayer_inn": body.taxpayer_inn or ""},
                actor=_actor(request),
            )
            await conn.execute(_q("""
                INSERT INTO tenant_rsge_credentials (
                    tenant_id, username, taxpayer_inn, credential_vault_ref,
                    credential_status, updated_at
                ) VALUES (%s, %s, %s, %s, 'vault', NOW())
                ON CONFLICT (tenant_id) DO UPDATE
                SET username = EXCLUDED.username,
                    taxpayer_inn = EXCLUDED.taxpayer_inn,
                    credential_vault_ref = EXCLUDED.credential_vault_ref,
                    credential_status = 'vault',
                    updated_at = NOW()
            """), tenant_id, body.username, body.taxpayer_inn or "", "rsge:portal_password")
        return ok_response("ok", {
            "message": "RS.ge credentials saved in Credential Vault",
            "credential_status": "vault",
            "masked_hint": vault_result.get("masked_hint"),
        })
    except Exception as e:
        return error_response("RS.ge credentials save failed", "ERROR", type(e).__name__)


@router.post("/test")
async def test_connection(request: Request):
    """Verify credentials are configured. Live portal validation is intentionally not called."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await conn.execute(_CREATE_TABLE)
            await conn.execute(_LEGACY_COLUMNS)
            row = await conn.fetchrow(_q(
                "SELECT username, taxpayer_inn FROM tenant_rsge_credentials WHERE tenant_id = %s"
            ), tenant_id)
            vault_status = await CredentialVaultService().get_status(
                conn, tenant_id, "rsge", "portal_password"
            )
        if row and vault_status.get("configured"):
            return {
                "ok": True,
                "message": "RS.ge credentials are configured in Credential Vault. Live RS.ge portal sync: coming soon.",
                "username": row["username"],
                "taxpayer_inn": row["taxpayer_inn"],
                "credential_status": "vault",
                "masked_hint": vault_status.get("masked_hint"),
            }
        return error_response("No vaulted RS.ge credentials found", "ERROR", "")
    except Exception:
        return error_response("Credentials not found", "ERROR", "")
