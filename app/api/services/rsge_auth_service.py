"""app/api/services/rsge_auth_service.py — RS.ge credential management.

Supports:
  SOAP auth (su/sp) — for WayBill + Invoice SOAP services
  RSoAuth eAPI      — for eapi.rs.ge Bearer token (1-step or 2-step with SMS)

Security invariants:
  - Raw su/sp/token is NEVER returned from any public function.
  - NEVER logged.
  - Stored ONLY via CredentialVaultService.
  - Masked hint only is shown in status responses.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

_PROVIDER = "rs_ge"
_SOAP_TYPE = "soap_credentials"   # stores JSON {"su": "...", "sp": "..."}
_TOKEN_TYPE = "eapi_token"        # RSoAuth ACCESS_TOKEN


# ── Internal helpers ─────────────────────────────────────────────────────────

def _vault():
    from app.api.services.credential_vault_service import CredentialVaultService
    return CredentialVaultService()


def _mask(value: str) -> str:
    if not value:
        return "****"
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


# ── SOAP auth (su / sp) ──────────────────────────────────────────────────────

async def start_soap_auth(
    conn,
    tenant_id: str,
    su: str,
    sp: str,
    actor: Optional[str] = None,
    skip_verify: bool = False,
) -> dict:
    """Verify RS.ge SOAP credentials and store them in Credential Vault.

    Args:
        skip_verify: If True, skip live chek_service_user call (test/unit mode).

    Returns a safe status dict — never contains raw su/sp.
    """
    if not su or not sp:
        return {"connected": False, "error": "su and sp are required"}

    un_id = None
    if not skip_verify:
        try:
            from app.api.connectors.rs_ge_connector import RsGeConnector
            import os
            _orig_su = os.environ.get("RS_GE_SU", "")
            _orig_sp = os.environ.get("RS_GE_SP", "")
            os.environ["RS_GE_SU"] = su
            os.environ["RS_GE_SP"] = sp
            try:
                check = RsGeConnector().check_service_user()
                if not check.get("valid"):
                    return {"connected": False, "error": "RS.ge rejected credentials"}
                un_id = check.get("un_id")
            finally:
                if _orig_su:
                    os.environ["RS_GE_SU"] = _orig_su
                else:
                    os.environ.pop("RS_GE_SU", None)
                if _orig_sp:
                    os.environ["RS_GE_SP"] = _orig_sp
                else:
                    os.environ.pop("RS_GE_SP", None)
        except Exception as exc:
            log.warning("[RS.GE] auth verify failed: %s", exc)
            return {"connected": False, "error": f"verification failed: {type(exc).__name__}"}

    raw_blob = json.dumps({"su": su, "sp": sp, "un_id": un_id or ""})
    vault = _vault()
    result = await vault.save_credential(
        conn,
        tenant_id=tenant_id,
        provider=_PROVIDER,
        credential_type=_SOAP_TYPE,
        raw_value=raw_blob,
        metadata={"un_id": un_id or "", "masked_su": _mask(su)},
        actor=actor,
    )

    await _upsert_rsge_credentials_row(conn, tenant_id, _mask(su), "configured")
    log.info("[RS.GE] SOAP credentials saved tenant=%s su=%s", tenant_id, _mask(su))

    return {
        "connected": True,
        "mode": "soap",
        "masked_su": _mask(su),
        "un_id": un_id,
        "vault_status": result.get("status"),
    }


async def signout(conn, tenant_id: str, actor: Optional[str] = None) -> dict:
    """Revoke RS.ge credentials for tenant."""
    vault = _vault()
    r1 = await vault.disable_credential(conn, tenant_id, _PROVIDER, _SOAP_TYPE, actor=actor)
    r2 = await vault.disable_credential(conn, tenant_id, _PROVIDER, _TOKEN_TYPE, actor=actor)
    await _upsert_rsge_credentials_row(conn, tenant_id, None, "disconnected")
    return {"disconnected": True, "soap": r1.get("disabled"), "token": r2.get("disabled")}


async def get_connection_status(conn, tenant_id: str) -> dict:
    """Return safe status — no raw secrets."""
    vault = _vault()
    soap_status = await vault.get_status(conn, tenant_id, _PROVIDER, _SOAP_TYPE)
    token_status = await vault.get_status(conn, tenant_id, _PROVIDER, _TOKEN_TYPE)

    connected = soap_status.get("configured") or token_status.get("configured")
    return {
        "connected": connected,
        "soap_configured": soap_status.get("configured", False),
        "soap_status": soap_status.get("status"),
        "soap_masked_hint": soap_status.get("masked_hint"),
        "token_configured": token_status.get("configured", False),
        "token_status": token_status.get("status"),
    }


async def get_decrypted_soap_creds(conn, tenant_id: str) -> dict:
    """INTERNAL USE ONLY — returns raw su/sp for connector calls.

    Must NEVER be returned in API responses or logged.
    """
    vault = _vault()
    raw = await vault.get_for_connector(
        conn, tenant_id=tenant_id, provider=_PROVIDER,
        credential_type=_SOAP_TYPE, purpose="rs_ge_soap_call",
    )
    try:
        return json.loads(raw)
    except Exception:
        return {"su": raw, "sp": ""}


async def load_connector_creds(conn, tenant_id: str) -> dict:
    """Public alias for loading connector credentials from vault.

    Routes should call this instead of get_decrypted_soap_creds directly.
    Returns {"su": ..., "sp": ..., "un_id": ...} — never log or return these values.
    """
    return await get_decrypted_soap_creds(conn, tenant_id)


# ── RSoAuth eAPI — two-step auth ─────────────────────────────────────────────

async def start_eapi_auth(
    conn,
    tenant_id: str,
    public_key: str,
    secret_key: str,
    actor: Optional[str] = None,
) -> dict:
    """Initiate RS.ge RSoAuth v3 flow.

    Returns:
      - one-step: {"connected": True, "steps": 1}
      - two-step: {"connected": False, "steps": 2, "pin_token": "...", "masked_mobile": "..."}

    Pin token is stored in vault, NOT returned directly. Frontend receives
    only the masked_mobile and a session reference.
    """
    try:
        import hashlib, hmac, time, random, string
        import requests

        ts = str(int(time.time()))
        rand_str = "".join(random.choices(string.ascii_letters + string.digits, k=16))
        msg = (public_key + ts + rand_str).encode("utf-8")
        auth_key = public_key + ":" + hmac.new(
            secret_key.encode("utf-8"), msg, hashlib.sha256
        ).hexdigest()

        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><AuthorizationRequest xmlns="http://eservices.rs.ge/">'
            f'<AuthKey>{auth_key}</AuthKey>'
            f'<Timestamp>{ts}</Timestamp>'
            f'<RandomString>{rand_str}</RandomString>'
            '</AuthorizationRequest></soap:Body></soap:Envelope>'
        )
        r = requests.post(
            "https://eservices.rs.ge/WebServices/oAuth.ashx",
            data=body.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=15, verify=True,
        )
        r.raise_for_status()
        # Parse response — check if PIN_TOKEN (two-step) or ACCESS_TOKEN (one-step)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.content)
        ns = "{http://eservices.rs.ge/}"
        access_token = root.findtext(f".//{ns}AccessToken") or root.findtext(".//AccessToken")
        pin_token = root.findtext(f".//{ns}PINToken") or root.findtext(".//PINToken")
        masked_mobile = root.findtext(f".//{ns}MaskedMobile") or root.findtext(".//MaskedMobile")

        if access_token:
            await vault_store_token(conn, tenant_id, access_token, actor)
            return {"connected": True, "steps": 1}
        if pin_token:
            # Store pin_token temporarily — frontend only gets masked_mobile
            await vault_store_token(conn, tenant_id, pin_token, actor,
                                    meta={"phase": "pin_pending",
                                          "masked_mobile": masked_mobile or ""})
            return {
                "connected": False,
                "steps": 2,
                "masked_mobile": masked_mobile or "***",
                "message": "SMS code required",
            }
        return {"connected": False, "error": "No token in RS.ge response"}
    except Exception as exc:
        log.warning("[RS.GE] RSoAuth failed: %s", exc)
        return {"connected": False, "error": str(exc)[:120]}


async def verify_pin(
    conn,
    tenant_id: str,
    pin_code: str,
    actor: Optional[str] = None,
) -> dict:
    """Complete two-step auth: exchange PIN_TOKEN + SMS code for ACCESS_TOKEN."""
    try:
        import requests
        import xml.etree.ElementTree as ET

        vault = _vault()
        raw_pin_token = await vault.get_for_connector(
            conn, tenant_id=tenant_id, provider=_PROVIDER,
            credential_type=_TOKEN_TYPE, purpose="pin_exchange",
        )

        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soap:Body><PinAuthorizationRequest xmlns="http://eservices.rs.ge/">'
            f'<PINToken>{raw_pin_token}</PINToken>'
            f'<PINCode>{pin_code}</PINCode>'
            '</PinAuthorizationRequest></soap:Body></soap:Envelope>'
        )
        r = requests.post(
            "https://eservices.rs.ge/WebServices/oAuth.ashx",
            data=body.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=15, verify=True,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = "{http://eservices.rs.ge/}"
        access_token = root.findtext(f".//{ns}AccessToken") or root.findtext(".//AccessToken")
        if not access_token:
            return {"connected": False, "error": "PIN verification failed"}

        await vault_store_token(conn, tenant_id, access_token, actor,
                                meta={"phase": "active"})
        return {"connected": True, "steps": 2}
    except RuntimeError as exc:
        return {"connected": False, "error": str(exc)}
    except Exception as exc:
        log.warning("[RS.GE] verify_pin failed: %s", exc)
        return {"connected": False, "error": str(exc)[:120]}


async def vault_store_token(
    conn, tenant_id: str, token: str, actor: Optional[str],
    meta: Optional[dict] = None,
) -> None:
    vault = _vault()
    await vault.save_credential(
        conn,
        tenant_id=tenant_id,
        provider=_PROVIDER,
        credential_type=_TOKEN_TYPE,
        raw_value=token,
        metadata=meta or {},
        actor=actor,
    )


# ── DB helpers ───────────────────────────────────────────────────────────────

async def _upsert_rsge_credentials_row(
    conn, tenant_id: str, masked_su: Optional[str], status: str,
) -> None:
    """Keep rsge_credentials pointer table in sync."""
    try:
        from app.api.db import _q
        sql = _q("""
            INSERT INTO rsge_credentials (tenant_id, masked_su, status, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (tenant_id, credential_type) DO UPDATE
              SET masked_su = EXCLUDED.masked_su,
                  status = EXCLUDED.status,
                  updated_at = NOW()
        """)
        await conn.execute(sql, tenant_id, masked_su, status)
    except Exception as exc:
        log.debug("rsge_credentials upsert skipped: %s", exc)
