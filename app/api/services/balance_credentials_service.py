"""Tenant-scoped Balance.ge credential persistence and retrieval."""
import logging
from datetime import datetime, timezone
from typing import Optional

from psycopg2.extras import RealDictCursor

from app.api.db import get_conn, get_db, _q
from app.api.services.credential_response_sanitizer import sanitize_credential_response

log = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://api.balance.ge"


async def ensure_table():
    """Create the connector metadata table if it does not exist."""
    async with get_conn() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tenant_balance_credentials (
                id          SERIAL PRIMARY KEY,
                tenant_id   TEXT NOT NULL UNIQUE,
                api_key     TEXT,
                company_id  TEXT,
                api_base    TEXT DEFAULT 'https://api.balance.ge',
                active      BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)


async def _legacy_status(conn, tenant_id: str) -> dict:
    """Return safe metadata only; the legacy key itself is never selected."""
    row = await conn.fetchrow(_q(
        "SELECT company_id, api_base, credential_status, "
        "(api_key IS NOT NULL AND api_key <> '') AS legacy_present "
        "FROM tenant_balance_credentials WHERE tenant_id = %s AND active = TRUE"
    ), tenant_id)
    legacy_present = bool(row and (
        row.get("legacy_present")
        or row.get("credential_status") in {"legacy_plaintext", "rotation_required"}
    ))
    metadata_status = row.get("credential_status") if row else None
    return {
        "api_key": "",
        "company_id": (row.get("company_id") if row else "") or "",
        "api_base": (row.get("api_base") if row else _DEFAULT_API_BASE) or _DEFAULT_API_BASE,
        "source": "none",
        "credential_status": (
            "rotation_required" if legacy_present else
            "invalid_reference" if metadata_status in {"vault", "active"} else
            "not_configured"
        ),
    }


async def get_balance_credentials(tenant_id: str) -> dict:
    """Return a tenant's credential from the vault, never from plaintext/env.

    The raw key is for connector use in memory only. A missing/disabled vault
    item yields no credential and safe metadata; any other vault failure raises
    a generic error so callers cannot downgrade to legacy/shared credentials.
    """
    from app.api.services.credential_vault_service import CredentialVaultService

    async with get_conn() as conn:
        svc = CredentialVaultService()
        try:
            raw_key = await svc.get_for_connector(
                conn,
                tenant_id=tenant_id,
                provider="balance",
                credential_type="api_key",
                purpose="connector_read",
            )
        except RuntimeError as exc:
            if str(exc) not in {"CREDENTIAL_NOT_FOUND", "CREDENTIAL_DISABLED"}:
                log.warning("Balance.ge vault read failed tenant=%s type=%s", tenant_id, type(exc).__name__)
                raise RuntimeError("BALANCE_CREDENTIAL_UNAVAILABLE") from None
            return await _legacy_status(conn, tenant_id)
        except Exception as exc:
            log.warning("Balance.ge vault read failed tenant=%s type=%s", tenant_id, type(exc).__name__)
            raise RuntimeError("BALANCE_CREDENTIAL_UNAVAILABLE") from None

        row = await conn.fetchrow(_q(
            "SELECT company_id, api_base FROM tenant_balance_credentials "
            "WHERE tenant_id = %s AND active = TRUE"
        ), tenant_id)
        return {
            "api_key": raw_key,
            "company_id": (row["company_id"] if row else "") or "",
            "api_base": (row["api_base"] if row else _DEFAULT_API_BASE) or _DEFAULT_API_BASE,
            "source": "vault",
            "credential_status": "active",
        }


def get_balance_credentials_sync(tenant_id: str) -> dict:
    """Synchronous connector lookup using only the tenant-scoped vault row.

    BalanceConnector retains a synchronous interface. The DB predicate is
    tenant/provider/type scoped; the legacy key is represented only as a
    boolean for rotation reporting, and shared environment keys are ignored.
    """
    conn = None
    try:
        conn = get_db(tenant_id)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT encrypted_value, key_version, status, active
                   FROM credential_vault_credentials
                   WHERE tenant_id = %s AND provider = %s AND credential_type = %s""",
                (tenant_id, "balance", "api_key"),
            )
            vault_row = cur.fetchone()
            cur.execute(
                """SELECT company_id, api_base, credential_status,
                          (api_key IS NOT NULL AND api_key <> '') AS legacy_present
                   FROM tenant_balance_credentials
                   WHERE tenant_id = %s AND active = TRUE""",
                (tenant_id,),
            )
            metadata = cur.fetchone()

            if vault_row and vault_row.get("active") and vault_row.get("status") == "active":
                from app.api.services.secret_crypto_provider import SecretCryptoProvider
                raw_key = SecretCryptoProvider().decrypt_secret(
                    vault_row["encrypted_value"], vault_row["key_version"]
                )
                try:
                    cur.execute(
                        """INSERT INTO credential_vault_audit_events
                           (tenant_id, provider, credential_type, action, purpose, result)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (tenant_id, "balance", "api_key", "connector_read", "connector_read", "success"),
                    )
                    conn.commit()
                except Exception as audit_exc:
                    conn.rollback()
                    log.warning("Balance.ge credential audit failed type=%s", type(audit_exc).__name__)
                return {
                    "api_key": raw_key,
                    "company_id": (metadata.get("company_id") if metadata else "") or "",
                    "api_base": (metadata.get("api_base") if metadata else _DEFAULT_API_BASE) or _DEFAULT_API_BASE,
                    "source": "vault",
                    "credential_status": "active",
                }

            status = (vault_row or {}).get("status")
            legacy_present = bool(metadata and (
                metadata.get("legacy_present")
                or metadata.get("credential_status") in {"legacy_plaintext", "rotation_required"}
            ))
            metadata_status = metadata.get("credential_status") if metadata else None
            return {
                "api_key": "",
                "company_id": (metadata.get("company_id") if metadata else "") or "",
                "api_base": (metadata.get("api_base") if metadata else _DEFAULT_API_BASE) or _DEFAULT_API_BASE,
                "source": "none",
                "credential_status": (
                    "rotation_required" if legacy_present else
                    "invalid_reference" if not vault_row and metadata_status in {"vault", "active"} else
                    (status or "not_configured")
                ),
            }
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        log.warning("Balance.ge credential lookup failed tenant=%s type=%s", tenant_id, type(exc).__name__)
        raise RuntimeError("BALANCE_CREDENTIAL_UNAVAILABLE") from None
    finally:
        if conn is not None:
            conn.close()


async def save_balance_credentials(
    tenant_id: str,
    api_key: str,
    company_id: str = "",
    api_base: str = _DEFAULT_API_BASE,
    actor: Optional[str] = None,
) -> bool:
    """Store the key through the vault and update safe metadata atomically."""
    if not api_key:
        return False

    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
            async with conn.transaction():
                svc = CredentialVaultService()
                result = await svc.save_credential(
                    conn,
                    tenant_id=tenant_id,
                    provider="balance",
                    credential_type="api_key",
                    raw_value=api_key,
                    metadata={"company_id": company_id, "api_base": api_base},
                    actor=actor,
                )
                now = datetime.now(timezone.utc)
                await conn.execute(_q("""
                    INSERT INTO tenant_balance_credentials
                        (tenant_id, api_key, company_id, api_base, masked_hint,
                         credential_status, active, updated_at)
                    VALUES (%s, NULL, %s, %s, %s, 'vault', TRUE, %s)
                    ON CONFLICT (tenant_id) DO UPDATE
                        SET api_key = NULL,
                            company_id = EXCLUDED.company_id,
                            api_base = EXCLUDED.api_base,
                            masked_hint = EXCLUDED.masked_hint,
                            credential_status = 'vault',
                            active = TRUE,
                            updated_at = EXCLUDED.updated_at
                """), tenant_id, company_id, api_base, result.get("masked_hint"), now)
        return True
    except Exception as exc:
        log.warning("Balance.ge credential save failed tenant=%s type=%s", tenant_id, type(exc).__name__)
        raise RuntimeError("BALANCE_CREDENTIAL_SAVE_FAILED") from None


async def get_credentials_status(tenant_id: str) -> dict:
    """Return masked status; this function never includes a raw credential."""
    try:
        creds = await get_balance_credentials(tenant_id)
        raw = {
            "configured": bool(creds.get("api_key")),
            "source": creds.get("source", "none"),
            "company_id": creds.get("company_id", ""),
            "api_base": creds.get("api_base", ""),
            "mode": "live" if creds.get("api_key") else "demo",
            "credential_status": creds.get("credential_status", "not_configured"),
        }
    except Exception as exc:
        # A status read must not turn infrastructure failures into a credential
        # fallback or expose provider/exception details to the caller.
        log.warning("Balance.ge credential status unavailable tenant=%s type=%s", tenant_id, type(exc).__name__)
        raw = {
            "configured": False,
            "source": "none",
            "company_id": "",
            "api_base": _DEFAULT_API_BASE,
            "mode": "unavailable",
            "credential_status": "unavailable",
        }
    return sanitize_credential_response(raw)


async def get_vault_status(tenant_id: str) -> dict:
    """Return masked vault status and flag legacy plaintext for controlled rotation."""
    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
            svc = CredentialVaultService()
            status = await svc.get_status(conn, tenant_id, "balance", "api_key")
            if not status.get("configured"):
                legacy = await conn.fetchrow(_q(
                    "SELECT credential_status, "
                    "(api_key IS NOT NULL AND api_key <> '') AS legacy_present "
                    "FROM tenant_balance_credentials WHERE tenant_id = %s AND active = TRUE"
                ), tenant_id)
                if legacy and (
                    legacy.get("legacy_present")
                    or legacy.get("credential_status") in {"legacy_plaintext", "rotation_required"}
                ):
                    status.update({
                        "configured": False,
                        "status": "rotation_required",
                        "legacy_credential_present": True,
                    })
    except Exception as exc:
        log.warning("Balance.ge vault status unavailable tenant=%s type=%s", tenant_id, type(exc).__name__)
        status = {"configured": False, "status": "not_configured"}

    safe = sanitize_credential_response(status)
    safe.setdefault("provider", "balance")
    safe.setdefault("mode", "live" if safe.get("configured") else "demo")
    return safe
