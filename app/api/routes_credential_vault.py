"""app/api/routes_credential_vault.py — Credential Vault API (Task 11C).

Endpoints:
  GET  /vault/credentials/{provider}/{credential_type}/status  — masked hint only
  POST /vault/credentials/{provider}/{credential_type}         — save/encrypt
  POST /vault/credentials/{provider}/{credential_type}/rotate  — rotate key
  DELETE /vault/credentials/{provider}/{credential_type}       — disable

All endpoints require tenants:manage (admin only).
Raw secrets are never returned. Responses contain only masked_hint.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from app.api.authz import require_permission
from app.api.db import get_conn
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/vault/credentials", tags=["credential-vault"])


class SaveCredentialPayload(BaseModel):
    raw_value: str
    company_id: Optional[str] = None
    api_base: Optional[str] = None
    metadata: Optional[dict] = None


class RotateCredentialPayload(BaseModel):
    new_raw_value: str


# ---------------------------------------------------------------------------
# GET /vault/credentials/{provider}/{credential_type}/status
# ---------------------------------------------------------------------------

@router.get("/{provider}/{credential_type}/status")
async def get_credential_status(provider: str, credential_type: str, request: Request):
    """Return masked credential status — never includes raw secret."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
            svc = CredentialVaultService()
            status = await svc.get_status(conn, tenant_id, provider, credential_type)
        return ok_response("ok", status)
    except Exception as exc:
        return error_response("Status unavailable", "VAULT_ERROR", str(type(exc).__name__))


# ---------------------------------------------------------------------------
# POST /vault/credentials/{provider}/{credential_type}
# ---------------------------------------------------------------------------

@router.post("/{provider}/{credential_type}")
async def save_credential(
    provider: str,
    credential_type: str,
    body: SaveCredentialPayload,
    request: Request,
):
    """Encrypt and save a credential. Returns masked_hint only."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.raw_value:
        return error_response("raw_value required", "INVALID_INPUT", "")
    actor = getattr(request.state, "user_id", None)
    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
            svc = CredentialVaultService()
            result = await svc.save_credential(
                conn,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=credential_type,
                raw_value=body.raw_value,
                metadata=body.metadata,
                actor=str(actor) if actor else None,
            )
        return ok_response("Credential saved", result)
    except ValueError as exc:
        return error_response(str(exc), "INVALID_INPUT", "")
    except Exception as exc:
        return error_response("Save failed", "VAULT_ERROR", str(type(exc).__name__))


# ---------------------------------------------------------------------------
# POST /vault/credentials/{provider}/{credential_type}/rotate
# ---------------------------------------------------------------------------

@router.post("/{provider}/{credential_type}/rotate")
async def rotate_credential(
    provider: str,
    credential_type: str,
    body: RotateCredentialPayload,
    request: Request,
):
    """Re-encrypt credential with new value. Returns new masked_hint."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.new_raw_value:
        return error_response("new_raw_value required", "INVALID_INPUT", "")
    actor = getattr(request.state, "user_id", None)
    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
            svc = CredentialVaultService()
            result = await svc.rotate_credential(
                conn,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=credential_type,
                new_raw_value=body.new_raw_value,
                actor=str(actor) if actor else None,
            )
        return ok_response("Credential rotated", result)
    except ValueError as exc:
        return error_response(str(exc), "INVALID_INPUT", "")
    except RuntimeError as exc:
        code = str(exc)
        if "NOT_FOUND" in code:
            return error_response("Credential not found", "NOT_FOUND", "")
        return error_response("Rotation failed", "VAULT_ERROR", code)
    except Exception as exc:
        return error_response("Rotation failed", "VAULT_ERROR", str(type(exc).__name__))


# ---------------------------------------------------------------------------
# DELETE /vault/credentials/{provider}/{credential_type}
# ---------------------------------------------------------------------------

@router.delete("/{provider}/{credential_type}")
async def disable_credential(
    provider: str,
    credential_type: str,
    request: Request,
):
    """Disable (deactivate) a credential. Does not delete it."""
    require_permission(request, "tenants:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", None)
    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
            svc = CredentialVaultService()
            result = await svc.disable_credential(
                conn,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=credential_type,
                actor=str(actor) if actor else None,
            )
        return ok_response("Credential disabled", result)
    except Exception as exc:
        return error_response("Disable failed", "VAULT_ERROR", str(type(exc).__name__))
