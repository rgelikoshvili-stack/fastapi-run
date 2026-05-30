"""app/api/services/balance_credentials_service.py
Bridge Hub — Per-tenant Balance.ge credentials (Task 11G vault wiring).

Read priority:
  1. CredentialVaultService.get_for_connector() — encrypted record in vault
  2. Plaintext api_key in tenant_balance_credentials (legacy / migration window)
  3. BALANCE_API_KEY env var (global fallback)

Write path:
  - save_balance_credentials() encrypts via vault; sets api_key=NULL and
    credential_status='vault' on the legacy row.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from app.api.db import get_conn, _q
from app.api.services.credential_response_sanitizer import sanitize_credential_response

log = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://api.balance.ge"


async def ensure_table():
    """Create table if not exists — called at startup."""
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


async def get_balance_credentials(tenant_id: str) -> dict:
    """Return Balance.ge credentials for a tenant.

    Tries the credential vault first (encrypted), falls back to the
    legacy plaintext column, then to the BALANCE_API_KEY env var.
    This is the ONLY function that may return the raw api_key value;
    callers must never expose it in API responses.
    """
    # ── 1. Vault (encrypted) ─────────────────────────────────────────────────
    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
            svc = CredentialVaultService()
            raw_key = await svc.get_for_connector(
                conn,
                tenant_id=tenant_id,
                provider="balance",
                credential_type="api_key",
                purpose="connector_read",
            )
            row = await conn.fetchrow(_q(
                "SELECT company_id, api_base FROM tenant_balance_credentials "
                "WHERE tenant_id = %s AND active = TRUE"
            ), tenant_id)
        return {
            "api_key": raw_key,
            "company_id": (row["company_id"] if row else "") or "",
            "api_base": (row["api_base"] if row else _DEFAULT_API_BASE) or _DEFAULT_API_BASE,
            "source": "vault",
        }
    except RuntimeError as exc:
        err = str(exc)
        if "CREDENTIAL_NOT_FOUND" not in err and "CREDENTIAL_DISABLED" not in err:
            log.warning("vault read error tenant=%s: %s", tenant_id, exc)
    except Exception as exc:
        log.warning("vault read exception tenant=%s: %s", tenant_id, type(exc).__name__)

    # ── 2. Legacy plaintext fallback ─────────────────────────────────────────
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT api_key, company_id, api_base FROM tenant_balance_credentials "
                "WHERE tenant_id = %s AND active = TRUE"
            ), tenant_id)
        if row and row["api_key"]:
            return {
                "api_key": row["api_key"],
                "company_id": row["company_id"] or "",
                "api_base": row["api_base"] or _DEFAULT_API_BASE,
                "source": "db_legacy",
            }
    except Exception as exc:
        log.warning("get_balance_credentials DB: %s", exc)

    # ── 3. Env var global fallback ────────────────────────────────────────────
    api_key = os.environ.get("BALANCE_API_KEY", "")
    if api_key:
        return {
            "api_key": api_key,
            "company_id": os.environ.get("BALANCE_COMPANY_ID", ""),
            "api_base": os.environ.get("BALANCE_API_BASE", _DEFAULT_API_BASE),
            "source": "env",
        }
    return {"api_key": "", "company_id": "", "api_base": _DEFAULT_API_BASE, "source": "none"}


async def save_balance_credentials(
    tenant_id: str,
    api_key: str,
    company_id: str = "",
    api_base: str = _DEFAULT_API_BASE,
    actor: Optional[str] = None,
) -> bool:
    """Encrypt api_key into vault; update legacy row with masked hint and status."""
    if not api_key:
        return False

    vault_ok = False
    masked_hint: Optional[str] = None

    # ── Save to vault ─────────────────────────────────────────────────────────
    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
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
        vault_ok = True
        masked_hint = result.get("masked_hint")
    except Exception as exc:
        log.warning("vault save failed tenant=%s: %s", tenant_id, type(exc).__name__)

    # ── Update legacy row (api_key=NULL when vault saved; metadata always updated) ─
    try:
        now = datetime.now(timezone.utc)
        async with get_conn() as conn:
            await conn.execute(_q("""
                INSERT INTO tenant_balance_credentials
                    (tenant_id, api_key, company_id, api_base, masked_hint,
                     credential_status, active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
                ON CONFLICT (tenant_id) DO UPDATE
                    SET api_key           = EXCLUDED.api_key,
                        company_id        = EXCLUDED.company_id,
                        api_base          = EXCLUDED.api_base,
                        masked_hint       = EXCLUDED.masked_hint,
                        credential_status = EXCLUDED.credential_status,
                        active            = TRUE,
                        updated_at        = EXCLUDED.updated_at
            """),
                tenant_id,
                None if vault_ok else api_key,    # NULL when vault holds the real key
                company_id,
                api_base,
                masked_hint,
                "vault" if vault_ok else "legacy_plaintext",
                now,
            )
        return True
    except Exception as exc:
        log.error("save_balance_credentials DB update: %s", exc)
        return vault_ok  # vault saved — partial success


async def get_credentials_status(tenant_id: str) -> dict:
    """Return status summary for the settings UI — never includes raw api_key."""
    creds = await get_balance_credentials(tenant_id)
    configured = bool(creds.get("api_key"))
    raw = {
        "configured": configured,
        "source": creds.get("source", "none"),
        "company_id": creds.get("company_id", ""),
        "api_base": creds.get("api_base", ""),
        "mode": "live" if configured else "demo",
    }
    return sanitize_credential_response(raw)


async def get_vault_status(tenant_id: str) -> dict:
    """Return safe masked credential status using the vault service directly."""
    try:
        from app.api.services.credential_vault_service import CredentialVaultService
        async with get_conn() as conn:
            svc = CredentialVaultService()
            status = await svc.get_status(conn, tenant_id, "balance", "api_key")
    except Exception as exc:
        log.warning("get_vault_status failed tenant=%s: %s", tenant_id, type(exc).__name__)
        status = {"configured": False, "status": "not_configured"}

    safe = sanitize_credential_response(status)
    safe.setdefault("provider", "balance")
    safe.setdefault("mode", "live" if safe.get("configured") else "demo")
    return safe
