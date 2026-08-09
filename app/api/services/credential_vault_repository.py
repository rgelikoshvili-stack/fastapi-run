"""app/api/services/credential_vault_repository.py
Bridge Hub — Credential Vault Repository (Task 11C-C3)

Handles DB reads/writes for the credential vault. All methods receive an
asyncpg connection from the caller (CredentialVaultService); the repository
never opens its own connections.

Never returns encrypted_value to callers outside the vault service boundary.
Never performs encryption or decryption.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


class CredentialVaultRepository:
    """DB access layer for credential_vault_credentials and _audit_events.

    All methods accept an asyncpg connection `conn`.
    Tests mock this class to avoid real DB connections.
    """

    # ------------------------------------------------------------------
    # Credential records
    # ------------------------------------------------------------------

    async def upsert_credential(
        self,
        conn,
        *,
        tenant_id: str,
        provider: str,
        credential_type: str,
        encrypted_value: str,
        key_version: str,
        masked_hint: str,
        status: str = "active",
        active: bool = True,
        company_id: Optional[str] = None,
        api_base: Optional[str] = None,
        metadata: Optional[dict] = None,
        created_by: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        meta_json = json.dumps(metadata or {})
        row = await conn.fetchrow(
            """
            INSERT INTO credential_vault_credentials (
                tenant_id, provider, credential_type,
                encrypted_value, key_version, masked_hint,
                status, active, company_id, api_base, metadata,
                created_at, updated_at, created_by, updated_by
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$12,$13,$14)
            ON CONFLICT (tenant_id, provider, credential_type)
            DO UPDATE SET
                encrypted_value = EXCLUDED.encrypted_value,
                key_version     = EXCLUDED.key_version,
                masked_hint     = EXCLUDED.masked_hint,
                status          = EXCLUDED.status,
                active          = EXCLUDED.active,
                company_id      = COALESCE(EXCLUDED.company_id, credential_vault_credentials.company_id),
                api_base        = COALESCE(EXCLUDED.api_base,   credential_vault_credentials.api_base),
                metadata        = EXCLUDED.metadata,
                updated_at      = EXCLUDED.updated_at,
                updated_by      = EXCLUDED.updated_by
            RETURNING id, tenant_id, provider, credential_type,
                      masked_hint, key_version, status, active,
                      created_at, updated_at
            """,
            tenant_id, provider, credential_type,
            encrypted_value, key_version, masked_hint,
            status, active, company_id, api_base, meta_json,
            now, created_by, updated_by,
        )
        return dict(row) if row else {}

    async def get_active_credential(
        self,
        conn,
        tenant_id: str,
        provider: str,
        credential_type: str,
    ) -> Optional[dict]:
        """Return the active credential record metadata (no encrypted_value)."""
        row = await conn.fetchrow(
            """
            SELECT id, tenant_id, provider, credential_type,
                   masked_hint, key_version, status, active,
                   company_id, api_base,
                   last_test_status, last_tested_at, last_accessed_at,
                   rotated_at, created_at, updated_at
            FROM credential_vault_credentials
            WHERE tenant_id = $1 AND provider = $2 AND credential_type = $3
              AND active = TRUE
            """,
            tenant_id, provider, credential_type,
        )
        return dict(row) if row else None

    async def get_encrypted_credential(
        self,
        conn,
        tenant_id: str,
        provider: str,
        credential_type: str,
    ) -> Optional[dict]:
        """Return the encrypted value + key_version for internal decryption.

        This method must only be called from CredentialVaultService
        on the connector path. Never return this to API callers.
        """
        row = await conn.fetchrow(
            """
            SELECT encrypted_value, key_version, status, active
            FROM credential_vault_credentials
            WHERE tenant_id = $1 AND provider = $2 AND credential_type = $3
              AND active = TRUE
            """,
            tenant_id, provider, credential_type,
        )
        return dict(row) if row else None

    async def update_rotation(
        self,
        conn,
        *,
        tenant_id: str,
        provider: str,
        credential_type: str,
        encrypted_value: str,
        key_version: str,
        masked_hint: str,
        updated_by: Optional[str] = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        result = await conn.execute(
            """
            UPDATE credential_vault_credentials
            SET encrypted_value = $4, key_version = $5, masked_hint = $6,
                rotated_at = $7, updated_at = $7, updated_by = $8
            WHERE tenant_id = $1 AND provider = $2 AND credential_type = $3
              AND active = TRUE
            """,
            tenant_id, provider, credential_type,
            encrypted_value, key_version, masked_hint,
            now, updated_by,
        )
        return result != "UPDATE 0"

    async def disable_credential(
        self,
        conn,
        tenant_id: str,
        provider: str,
        credential_type: str,
        actor: Optional[str] = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        result = await conn.execute(
            """
            UPDATE credential_vault_credentials
            SET active = FALSE, status = 'disabled', updated_at = $4, updated_by = $5
            WHERE tenant_id = $1 AND provider = $2 AND credential_type = $3
            """,
            tenant_id, provider, credential_type, now, actor,
        )
        return result != "UPDATE 0"

    async def touch_last_accessed(
        self,
        conn,
        tenant_id: str,
        provider: str,
        credential_type: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        await conn.execute(
            """
            UPDATE credential_vault_credentials
            SET last_accessed_at = $4
            WHERE tenant_id = $1 AND provider = $2 AND credential_type = $3
            """,
            tenant_id, provider, credential_type, now,
        )

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------

    async def insert_audit_event(
        self,
        conn,
        *,
        tenant_id: str,
        provider: str,
        credential_type: str,
        action: str,
        result: str,
        actor: Optional[str] = None,
        purpose: Optional[str] = None,
        key_version: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        meta_json = json.dumps(metadata or {})
        try:
            await conn.execute(
                """
                INSERT INTO credential_vault_audit_events (
                    tenant_id, provider, credential_type, action,
                    actor, purpose, result, key_version, request_id, metadata
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
                """,
                tenant_id, provider, credential_type, action,
                actor, purpose, result, key_version, request_id, meta_json,
            )
        except Exception as exc:
            # Audit failures must not block the primary operation
            log.warning("insert_audit_event failed: %s", type(exc).__name__)
