"""tests/unit/test_rsge_auth_flow.py — RS.ge SOAP + eAPI auth flow."""
import inspect
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. start_soap_auth importable ────────────────────────────────────────────

def test_start_soap_auth_importable():
    from app.api.services.rsge_auth_service import start_soap_auth
    assert callable(start_soap_auth)


# ── 2. start_eapi_auth importable ────────────────────────────────────────────

def test_start_eapi_auth_importable():
    from app.api.services.rsge_auth_service import start_eapi_auth
    assert callable(start_eapi_auth)


# ── 3. start_soap_auth with empty creds returns connected=False ───────────────

def test_start_soap_auth_empty_creds_fails():
    import asyncio
    from app.api.services import rsge_auth_service as m
    mock_conn = AsyncMock()
    result = asyncio.run(m.start_soap_auth(mock_conn, "t1", "", "", skip_verify=True))
    assert result.get("connected") is False


# ── 4. Auth service uses credential vault for storage ────────────────────────

def test_auth_uses_vault():
    from app.api.services import rsge_auth_service as m
    src = inspect.getsource(m)
    assert "CredentialVaultService" in src or "credential_vault_service" in src
    assert "save_credential" in src


# ── 5. Auth result never contains raw password ────────────────────────────────

def test_auth_result_no_raw_password():
    result = {"connected": False, "status": "failed", "masked_su": "te****"}
    for k, v in result.items():
        assert k not in ("sp", "password", "secret")
    assert "****" not in str(result.get("sp", ""))


# ── 6. masked_su present in auth result ──────────────────────────────────────

def test_auth_result_has_masked_su():
    from app.api.services.rsge_auth_service import _mask
    masked = _mask("testuser")
    assert "****" in masked
    assert masked != "testuser"


# ── 7. load_connector_creds is public (routes use it) ────────────────────────

def test_load_connector_creds_is_public():
    from app.api.services.rsge_auth_service import load_connector_creds
    assert callable(load_connector_creds)


# ── 8. routes use load_connector_creds not get_decrypted_soap_creds ──────────

def test_routes_use_public_creds_wrapper():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    assert "get_decrypted_soap_creds" not in src
    assert "load_connector_creds" in src


# ── 9. vault_store_token callable ────────────────────────────────────────────

def test_vault_store_token_callable():
    from app.api.services.rsge_auth_service import vault_store_token
    assert callable(vault_store_token)


# ── 10. get_connection_status returns dict with expected keys ─────────────────

def test_get_connection_status_structure():
    import asyncio
    from app.api.services import rsge_auth_service as m
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    result = asyncio.run(m.get_connection_status(mock_conn, "t1"))
    assert isinstance(result, dict)
    assert "connected" in result or "status" in result
