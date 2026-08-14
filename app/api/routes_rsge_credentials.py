"""app/api/routes_rsge_credentials.py
Bridge Hub — Per-tenant RS.ge (Revenue Service) credentials.

P0-2 FIX: Passwords are encrypted via CredentialVaultService.
Plain-text password is never stored or returned. Existing rows
with plaintext passwords are flagged as 'legacy_plaintext' / 'rotation_required'.
"""
import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_conn, _q
from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response
from app.api.services.credential_vault_service import CredentialVaultService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/rsge-credentials", tags=["rsge-credentials"])

# Self-migrating schema: idempotent DDL executed on first route use.
# password is nullable — new rows NEVER write password (stored in vault).
# credential_vault_ref points to credential_vault_credentials(id).
_ENSURE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS tenant_rsge_credentials (
        id                   SERIAL PRIMARY KEY,
        tenant_id            TEXT NOT NULL UNIQUE,
        username             TEXT NOT NULL,
        password             TEXT,
        taxpayer_inn         TEXT DEFAULT '',
        credential_vault_ref TEXT,
        credential_status    TEXT NOT NULL DEFAULT 'legacy_plaintext',
        updated_at           TIMESTAMPTZ DEFAULT NOW()
    );
    ALTER TABLE tenant_rsge_credentials ALTER COLUMN password DROP NOT NULL;
    ALTER TABLE tenant_rsge_credentials
        ADD COLUMN IF NOT EXISTS credential_vault_ref TEXT;
    ALTER TABLE tenant_rsge_credentials
        ADD COLUMN IF NOT EXISTS credential_status TEXT NOT NULL DEFAULT 'legacy_plaintext';
    UPDATE tenant_rsge_credentials
        SET credential_status = 'rotation_required'
        WHERE password IS NOT NULL AND password NOT IN ('', '[stored-in-vault]')
          AND credential_status = 'legacy_plaintext';
"""


class RsgeCredsPayload(BaseModel):
    username: str
    password: str
    taxpayer_inn: Optional[str] = ""


async def _ensure_schema(conn) -> None:
    for stmt in _ENSURE_SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                await conn.execute(stmt)
            except Exception as _ddl_err:
                log.debug("rsge_creds schema stmt skipped (%s): %s", stmt[:60], _ddl_err)


@router.get("/status")
async def get_status(request: Request):
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            await _ensure_schema(conn)
            row = await conn.fetchrow(_q(
                "SELECT username, taxpayer_inn, credential_status FROM tenant_rsge_credentials "
                "WHERE tenant_id = %s"
            ), tenant_id)
        if row:
            return ok_response("ok", {
                "configured": True,
                "username": row["username"],
                "taxpayer_inn": row["taxpayer_inn"],
                "credential_status": row["credential_status"],
            })
        return ok_response("ok", {"configured": False})
    except Exception as e:
        log.error("rsge get_status error: %s", e)
        return ok_response("ok", {"configured": False, "error": str(e)})


@router.post("/save")
async def save_creds(body: RsgeCredsPayload, request: Request):
    """Save RS.ge credentials. Password is encrypted in the credential vault.
    Plain-text password is never written to tenant_rsge_credentials.
    """
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.username:
        return error_response("username is required", "VALIDATION_ERROR", "")
    if not body.password:
        return error_response("password is required", "VALIDATION_ERROR", "")

    try:
        vault = CredentialVaultService()

        async with get_conn() as conn:
            await _ensure_schema(conn)

            # Encrypt and store in credential_vault_credentials
            vault_record = await vault.save_credential(
                conn,
                tenant_id=tenant_id,
                provider="rsge",
                credential_type="portal_password",
                raw_value=body.password,
                metadata={"username": body.username},
                actor=getattr(request.state, "user_id", "api"),
            )
            vault_ref = str(vault_record.get("id", ""))

            # Update metadata row — no plaintext password
            await conn.execute(_q("""
                INSERT INTO tenant_rsge_credentials
                    (tenant_id, username, password, taxpayer_inn, credential_vault_ref, credential_status)
                VALUES (%s, %s, '[stored-in-vault]', %s, %s, 'active')
                ON CONFLICT (tenant_id) DO UPDATE
                SET username             = EXCLUDED.username,
                    password             = '[stored-in-vault]',
                    taxpayer_inn         = EXCLUDED.taxpayer_inn,
                    credential_vault_ref = EXCLUDED.credential_vault_ref,
                    credential_status    = 'active',
                    updated_at           = NOW()
            """), tenant_id, body.username, body.taxpayer_inn or "", vault_ref)

        log.info("rsge_creds saved to vault for tenant=%s username=%s", tenant_id, body.username)
        return ok_response("ok", {
            "message": "RS.ge credentials saved (encrypted in vault)",
            "username": body.username,
            "credential_status": "active",
        })

    except Exception as e:
        log.error("rsge save_creds error (vault write): %s", e)
        return error_response(
            "Failed to save RS.ge credentials. Vault may not be configured.",
            "CREDENTIAL_VAULT_ERROR",
            str(e),
        )


@router.post("/test")
async def test_connection(request: Request):
    """Verify credentials are saved. Live portal validation: coming soon."""
    require_permission(request, "settings:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT username, taxpayer_inn, credential_status FROM tenant_rsge_credentials "
                "WHERE tenant_id = %s"
            ), tenant_id)
        if row and row["credential_status"] == "active":
            return ok_response("ok", {
                "message": f"Credentials saved for {row['username']}. Live RS.ge portal sync: coming soon.",
                "credential_status": row["credential_status"],
            })
        if row and row["credential_status"] == "rotation_required":
            return ok_response("ok", {
                "message": "Credentials found but require re-save (legacy plaintext detected — P0-2 migration).",
                "credential_status": "rotation_required",
                "action_required": "Re-save credentials via POST /rsge-credentials/save",
            })
        return error_response("No credentials saved — please save first", "NOT_CONFIGURED", "")
    except Exception:
        return error_response("Credentials not found", "NOT_CONFIGURED", "")
