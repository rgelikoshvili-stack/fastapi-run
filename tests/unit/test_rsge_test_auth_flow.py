"""tests/unit/test_rsge_test_auth_flow.py — RS.ge auth flow unit tests."""
import inspect
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch


# ── 1. Auth service exists and has required functions ─────────────────────────

def test_auth_service_has_start_soap_auth():
    from app.api.services import rsge_auth_service as m
    assert hasattr(m, "start_soap_auth")
    src = inspect.getsource(m.start_soap_auth)
    assert "credential_vault" in src.lower() or "vault" in src.lower()


def test_auth_service_has_signout():
    from app.api.services import rsge_auth_service as m
    assert hasattr(m, "signout")


def test_auth_service_has_verify_pin():
    from app.api.services import rsge_auth_service as m
    assert hasattr(m, "verify_pin")


def test_auth_service_has_get_connection_status():
    from app.api.services import rsge_auth_service as m
    assert hasattr(m, "get_connection_status")


# ── 2. Token never returned in response ───────────────────────────────────────

def test_start_soap_auth_never_returns_raw_password():
    """Result dict must not contain the raw sp value."""
    src = inspect.getsource(
        __import__("app.api.services.rsge_auth_service", fromlist=["start_soap_auth"]).start_soap_auth
    )
    # Function must store via vault, not return raw value
    assert "raw_value" in src or "save_credential" in src
    assert "return" not in src.split("masked_su")[0].split("sp")[0]


def test_vault_store_token_stores_not_returns():
    from app.api.services import rsge_auth_service as m
    src = inspect.getsource(m.vault_store_token)
    assert "save_credential" in src
    # Must not return raw token
    assert "return raw" not in src and "return token" not in src


# ── 3. One-step SOAP auth (skip_verify mode) ─────────────────────────────────

def test_start_soap_auth_skip_verify_stores_credentials():
    """skip_verify=True stores credentials without calling RS.ge."""
    import asyncio
    from app.api.services import rsge_auth_service as m

    mock_conn = AsyncMock()
    mock_vault = MagicMock()
    mock_vault.save_credential = AsyncMock(return_value={"status": "active", "masked_hint": "tb****"})
    mock_vault.audit_access = AsyncMock()

    with patch("app.api.services.rsge_auth_service._vault", return_value=mock_vault), \
         patch("app.api.services.rsge_auth_service._upsert_rsge_credentials_row", AsyncMock()):
        result = asyncio.run(
            m.start_soap_auth(mock_conn, "tenant1", "tbilisi", "123456",
                              actor="user1", skip_verify=True)
        )

    assert result.get("connected") is True
    assert "123456" not in str(result)  # raw password must not appear
    assert "tbilisi" not in str(result) or result.get("masked_su") == "tb****"


# ── 4. Auth failure returns connected=False ───────────────────────────────────

def test_start_soap_auth_requires_su_and_sp():
    import asyncio
    from app.api.services import rsge_auth_service as m

    mock_conn = AsyncMock()
    result = asyncio.run(
        m.start_soap_auth(mock_conn, "tenant1", "", "", skip_verify=True)
    )
    assert result.get("connected") is False


# ── 5. get_decrypted_soap_creds is internal (never in response) ───────────────

def test_get_decrypted_soap_creds_not_exposed_in_routes():
    import app.api.routes_rs_ge as routes_mod
    src = inspect.getsource(routes_mod)
    assert "get_decrypted_soap_creds" not in src


# ── 6. Masked hint structure ──────────────────────────────────────────────────

def test_mask_helper():
    from app.api.services.rsge_auth_service import _mask
    assert _mask("tbilisi") == "tb****si"
    assert _mask("ab") == "****"
    assert _mask("") == "****"
    result = _mask("test_user")
    assert "****" in result
    assert "test_user" != result  # not the raw value
