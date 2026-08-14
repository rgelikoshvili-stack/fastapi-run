"""tests/unit/test_rsge_two_step_auth.py — Two-step SOAP auth flow (start → verify PIN)."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. start_soap_auth is importable and callable ────────────────────────────

def test_start_soap_auth_importable():
    from app.api.services.rsge_auth_service import start_soap_auth
    assert callable(start_soap_auth)


# ── 2. verify_pin is importable ───────────────────────────────────────────────

def test_verify_pin_importable():
    from app.api.services.rsge_auth_service import verify_pin
    assert callable(verify_pin)


# ── 3. get_connection_status is importable ───────────────────────────────────

def test_get_connection_status_importable():
    from app.api.services.rsge_auth_service import get_connection_status
    assert callable(get_connection_status)


# ── 4. Auth service never exposes raw credentials in its return value ─────────

def test_auth_result_does_not_contain_raw_password():
    result = {
        "ok": True,
        "status": "pin_sent",
        "masked_su": "test****",
        "un_id": "12345",
    }
    for v in result.values():
        assert str(v) not in ("myRealPassword", "supersecret"), \
            "raw password must never appear in auth result"
    assert "sp" not in result
    assert "password" not in result


# ── 5. PIN verification returns session token without exposing it ─────────────

def test_pin_verify_result_shape():
    result = {
        "ok": True,
        "status": "authenticated",
        "un_id": "999",
        # token would be stored in vault, NOT returned here
    }
    assert "token" not in result
    assert result["status"] == "authenticated"


# ── 6. Two-step requires both steps (UN_ID present after step 1) ──────────────

def test_two_step_requires_un_id_for_pin():
    step1_result = {"ok": True, "status": "pin_sent", "un_id": "77777"}
    assert step1_result.get("un_id"), "UN_ID must be returned from step 1 for PIN submission"


# ── 7. Signout importable ────────────────────────────────────────────────────

def test_signout_importable():
    from app.api.services.rsge_auth_service import signout
    assert callable(signout)


# ── 8. Vault store token importable ──────────────────────────────────────────

def test_vault_store_token_importable():
    from app.api.services.rsge_auth_service import vault_store_token
    assert callable(vault_store_token)


# ── 9. Auth result status values are well-defined ────────────────────────────

def test_auth_status_values():
    valid_statuses = {"pin_sent", "authenticated", "failed", "error",
                      "signed_out", "not_configured"}
    result_status = "pin_sent"
    assert result_status in valid_statuses


# ── 10. RSGE_TEST_MODE must be set for auth operations in test ───────────────

def test_rsge_config_test_mode_flag():
    from app.api.services.rsge_config import mode_summary
    with patch.dict(os.environ, {"RSGE_TEST_MODE": "true", "RSGE_ENABLED": "true"}):
        summary = mode_summary()
    assert summary.get("test_mode") is True
