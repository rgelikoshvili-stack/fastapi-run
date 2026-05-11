"""app/api/services/credential_vault_service.py
Bridge Hub — Credential Vault Service (Task 11C-C3)

Central orchestrator for all credential lifecycle operations.
All services that need credentials must call this service — no direct
DB queries for credential values from outside this module.

Public API:
    CredentialVaultService
        .save_credential(...)
        .get_for_connector(...)
        .get_status(...)
        .rotate_credential(...)
        .disable_credential(...)
        .audit_access(...)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.api.services.credential_vault_repository import CredentialVaultRepository
from app.api.services.secret_crypto_provider import SecretCryptoProvider

log = logging.getLogger(__name__)


class CredentialVaultService:
    """Orchestrates credential save/get/rotate/disable/status/audit.

    Callers must pass an asyncpg connection (`conn`) on every method.
    Tests inject a mock `conn` and mock `repo` to avoid real DB access.

    Safety invariants (enforced by this class):
      - Raw secrets are never returned from get_status().
      - Raw secrets are never logged.
      - Disabled/revoked credentials block connector access.
      - Every access path calls audit_access().
    """

    def __init__(
        self,
        repo: Optional[CredentialVaultRepository] = None,
        crypto: Optional[SecretCryptoProvider] = None,
    ):
        self._repo = repo or CredentialVaultRepository()
        self._crypto = crypto or SecretCryptoProvider()

    # ------------------------------------------------------------------
    # save_credential
    # ------------------------------------------------------------------

    async def save_credential(
        self,
        conn,
        *,
        tenant_id: str,
        provider: str,
        credential_type: str,
        raw_value: str,
        metadata: Optional[dict] = None,
        actor: Optional[str] = None,
    ) -> dict:
        """Encrypt and persist a credential.

        Returns a safe status dict (no raw secret).
        Raises ValueError on empty raw_value.
        """
        if not raw_value:
            raise ValueError("raw_value must not be empty")

        try:
            payload = self._crypto.encrypt_secret(raw_value)
            record = await self._repo.upsert_credential(
                conn,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=credential_type,
                encrypted_value=payload["encrypted_value"],
                key_version=payload["key_version"],
                masked_hint=payload["masked_hint"],
                metadata=metadata or {},
                created_by=actor,
                updated_by=actor,
            )
            await self.audit_access(
                conn,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=credential_type,
                actor=actor,
                purpose="save",
                result="success",
                key_version=payload["key_version"],
            )
            return {
                "configured": True,
                "masked_hint": payload["masked_hint"],
                "key_version": payload["key_version"],
                "status": record.get("status", "active"),
            }
        except ValueError:
            raise
        except Exception as exc:
            log.warning(
                "save_credential failed tenant=%s provider=%s: %s",
                tenant_id, provider, type(exc).__name__,
            )
            await self.audit_access(
                conn,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=credential_type,
                actor=actor,
                purpose="save",
                result="failure",
            )
            raise

    # ------------------------------------------------------------------
    # get_for_connector
    # ------------------------------------------------------------------

    async def get_for_connector(
        self,
        conn,
        *,
        tenant_id: str,
        provider: str,
        credential_type: str,
        actor: Optional[str] = None,
        purpose: str = "connector_execution",
    ) -> str:
        """Return the raw decrypted secret for connector use only.

        This method is the ONLY path that may return a raw secret.
        Caller must never persist, log, or include this value in responses.

        Raises:
          RuntimeError("CREDENTIAL_NOT_FOUND")   — no active record
          RuntimeError("CREDENTIAL_DISABLED")     — record is inactive/revoked
          RuntimeError("CREDENTIAL_DECRYPT_FAILED") — decryption error
        """
        enc_record = await self._repo.get_encrypted_credential(
            conn, tenant_id, provider, credential_type,
        )

        if enc_record is None:
            await self.audit_access(
                conn,
                tenant_id=tenant_id, provider=provider,
                credential_type=credential_type,
                actor=actor, purpose=purpose, result="not_found",
            )
            raise RuntimeError("CREDENTIAL_NOT_FOUND")

        if not enc_record.get("active") or enc_record.get("status") in ("disabled", "revoked"):
            await self.audit_access(
                conn,
                tenant_id=tenant_id, provider=provider,
                credential_type=credential_type,
                actor=actor, purpose=purpose, result="disabled",
                key_version=enc_record.get("key_version"),
            )
            raise RuntimeError("CREDENTIAL_DISABLED")

        try:
            raw_secret = self._crypto.decrypt_secret(
                enc_record["encrypted_value"],
                enc_record["key_version"],
            )
        except Exception as exc:
            log.warning(
                "get_for_connector decrypt failed tenant=%s provider=%s: %s",
                tenant_id, provider, type(exc).__name__,
            )
            await self.audit_access(
                conn,
                tenant_id=tenant_id, provider=provider,
                credential_type=credential_type,
                actor=actor, purpose=purpose, result="failure",
                key_version=enc_record.get("key_version"),
            )
            raise RuntimeError("CREDENTIAL_DECRYPT_FAILED") from exc

        await self._repo.touch_last_accessed(conn, tenant_id, provider, credential_type)
        await self.audit_access(
            conn,
            tenant_id=tenant_id, provider=provider,
            credential_type=credential_type,
            actor=actor, purpose=purpose, result="success",
            key_version=enc_record["key_version"],
        )
        return raw_secret

    # ------------------------------------------------------------------
    # get_status
    # ------------------------------------------------------------------

    async def get_status(
        self,
        conn,
        tenant_id: str,
        provider: str,
        credential_type: str,
    ) -> dict:
        """Return a safe public status dict — never includes raw secrets.

        Returns one of:
          - {"configured": True, "status": "active", "masked_hint": "****xxxx", ...}
          - {"configured": False, "status": "not_configured", ...}
          - {"configured": False, "status": "demo", ...}
        """
        try:
            record = await self._repo.get_active_credential(
                conn, tenant_id, provider, credential_type,
            )
        except Exception as exc:
            log.warning(
                "get_status DB error tenant=%s provider=%s: %s",
                tenant_id, provider, type(exc).__name__,
            )
            return {
                "configured": False,
                "status": "not_configured",
                "provider": provider,
                "credential_type": credential_type,
                "error": "CREDENTIAL_STATUS_UNAVAILABLE",
            }

        if record is None:
            return {
                "configured": False,
                "status": "not_configured",
                "provider": provider,
                "credential_type": credential_type,
                "masked_hint": None,
                "last_test_status": None,
                "last_tested_at": None,
            }

        return {
            "configured": True,
            "status": record.get("status", "active"),
            "provider": provider,
            "credential_type": credential_type,
            "masked_hint": record.get("masked_hint"),
            "last_test_status": record.get("last_test_status"),
            "last_tested_at": record.get("last_tested_at"),
            "company_id": record.get("company_id"),
            "api_base": record.get("api_base"),
        }

    # ------------------------------------------------------------------
    # rotate_credential
    # ------------------------------------------------------------------

    async def rotate_credential(
        self,
        conn,
        *,
        tenant_id: str,
        provider: str,
        credential_type: str,
        new_raw_value: str,
        actor: Optional[str] = None,
    ) -> dict:
        """Re-encrypt credential with new raw value (or re-key existing value).

        Returns safe status dict (no raw secret).
        """
        if not new_raw_value:
            raise ValueError("new_raw_value must not be empty")

        old_record = await self._repo.get_active_credential(
            conn, tenant_id, provider, credential_type,
        )
        if old_record is None:
            raise RuntimeError("CREDENTIAL_NOT_FOUND")

        old_key_version = old_record.get("key_version")

        try:
            payload = self._crypto.encrypt_secret(new_raw_value)
            success = await self._repo.update_rotation(
                conn,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=credential_type,
                encrypted_value=payload["encrypted_value"],
                key_version=payload["key_version"],
                masked_hint=payload["masked_hint"],
                updated_by=actor,
            )
            await self.audit_access(
                conn,
                tenant_id=tenant_id, provider=provider,
                credential_type=credential_type,
                actor=actor, purpose="rotation",
                result="success" if success else "failure",
                key_version=payload["key_version"],
                metadata={"old_key_version": old_key_version},
            )
            return {
                "configured": True,
                "masked_hint": payload["masked_hint"],
                "key_version": payload["key_version"],
                "rotated": success,
            }
        except ValueError:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            log.warning(
                "rotate_credential failed tenant=%s provider=%s: %s",
                tenant_id, provider, type(exc).__name__,
            )
            await self.audit_access(
                conn,
                tenant_id=tenant_id, provider=provider,
                credential_type=credential_type,
                actor=actor, purpose="rotation", result="failure",
            )
            raise RuntimeError("CREDENTIAL_ROTATION_FAILED") from exc

    # ------------------------------------------------------------------
    # disable_credential
    # ------------------------------------------------------------------

    async def disable_credential(
        self,
        conn,
        tenant_id: str,
        provider: str,
        credential_type: str,
        actor: Optional[str] = None,
    ) -> dict:
        """Set active=FALSE and status='disabled'."""
        success = await self._repo.disable_credential(
            conn, tenant_id, provider, credential_type, actor=actor,
        )
        await self.audit_access(
            conn,
            tenant_id=tenant_id, provider=provider,
            credential_type=credential_type,
            actor=actor, purpose="disable",
            result="success" if success else "not_found",
        )
        return {"disabled": success}

    # ------------------------------------------------------------------
    # audit_access
    # ------------------------------------------------------------------

    async def audit_access(
        self,
        conn,
        *,
        tenant_id: str,
        provider: str,
        credential_type: str,
        actor: Optional[str],
        purpose: str,
        result: str,
        key_version: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Write a credential lifecycle audit event. Never includes raw secrets."""
        safe_meta = {k: v for k, v in (metadata or {}).items()}
        try:
            await self._repo.insert_audit_event(
                conn,
                tenant_id=tenant_id,
                provider=provider,
                credential_type=credential_type,
                action=purpose,
                actor=actor,
                purpose=purpose,
                result=result,
                key_version=key_version,
                request_id=request_id,
                metadata=safe_meta,
            )
        except Exception as exc:
            # Audit failures must not block the primary operation
            log.warning("audit_access write failed: %s", type(exc).__name__)
