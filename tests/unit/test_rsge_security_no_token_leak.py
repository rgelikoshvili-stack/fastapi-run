"""tests/unit/test_rsge_security_no_token_leak.py — Security: no token/credential leaks."""
import inspect
import logging
import re

import pytest


# ── 1. Auth service never returns raw su/sp/token in any public function ──────

def test_auth_service_public_functions_never_return_raw_token():
    from app.api.services import rsge_auth_service as m
    for fn_name in ("start_soap_auth", "get_connection_status", "signout"):
        fn = getattr(m, fn_name)
        src = inspect.getsource(fn)
        # Must not return raw_value or token variable directly
        assert "return raw_value" not in src, f"{fn_name} must not return raw_value"
        assert "return token" not in src, f"{fn_name} must not return token"
        assert "return sp" not in src, f"{fn_name} must not return sp"
        assert "return su" not in src, f"{fn_name} must not return su"


# ── 2. Token never appears in route responses ─────────────────────────────────

def test_routes_do_not_return_tokens():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    # Raw secret accessors must not be called from route handlers
    assert "raw_token" not in src
    assert "get_decrypted_soap_creds" not in src  # raw credential accessor not in routes
    # Routes do respond (sanity check)
    assert "ok_response" in src
    # No line that returns ACCESS_TOKEN as a value in a response dict
    for line in src.splitlines():
        stripped = line.strip()
        if "ACCESS_TOKEN" in stripped and not stripped.startswith(("#", '"""', "'''", '"', "'")):
            assert False, f"ACCESS_TOKEN appears in non-comment route line: {line}"


# ── 3. No Authorization header in logs ───────────────────────────────────────

def test_no_authorization_header_in_log_calls():
    from app.api.services import rsge_auth_service as m
    src = inspect.getsource(m)
    # Log statements must not include Authorization header
    log_lines = [l for l in src.splitlines() if "log." in l]
    for line in log_lines:
        line_lower = line.lower()
        assert "authorization" not in line_lower, f"Authorization found in log: {line}"
        assert "bearer" not in line_lower, f"Bearer found in log: {line}"


# ── 4. Connector does not log credentials ────────────────────────────────────

def test_connector_does_not_log_credentials():
    from app.api.connectors import rs_ge_connector as m
    src = inspect.getsource(m)
    log_lines = [l for l in src.splitlines() if "log." in l]
    for line in log_lines:
        assert ".sp" not in line or "._sp" not in line or "log.info" not in line, \
            f"Service password may be in log: {line}"
        assert "password" not in line.lower(), f"Password found in log: {line}"


# ── 5. Action service redacts credentials in audit log ───────────────────────

def test_action_service_redacts_in_audit():
    from app.api.services.rsge_action_service import _redacted_payload
    import json
    doc = {"id": 1, "rsge_id": "X", "amount": 100, "reg_no": "N1",
           "full_amount": 100, "direction": "incoming", "waybill_number": ""}
    payload = _redacted_payload("confirm", doc)
    assert payload["su"] == "****"
    assert payload["sp"] == "****"
    # Raw credentials must not be in JSON serialization
    serialized = json.dumps(payload)
    assert "tbilisi" not in serialized
    assert "123456" not in serialized


# ── 6. get_decrypted_soap_creds is internal-only ─────────────────────────────

def test_decrypted_creds_not_in_routes():
    import app.api.routes_rs_ge as routes
    src = inspect.getsource(routes)
    assert "get_decrypted_soap_creds" not in src, \
        "Raw credential accessor must not be called from routes"


# ── 7. rsge_config has production blocker ────────────────────────────────────

def test_production_blocker_exists():
    from app.api.services import rsge_config as m
    src = inspect.getsource(m.require_test_mode)
    assert "LIVE_ACTIONS_BLOCKED" in src or "TEST_MODE_REQUIRED" in src
    assert "403" in src or "status_code=403" in src


# ── 8. Credential vault is used for storage ──────────────────────────────────

def test_auth_uses_credential_vault():
    from app.api.services import rsge_auth_service as m
    src = inspect.getsource(m)
    assert "CredentialVaultService" in src or "credential_vault_service" in src
    assert "save_credential" in src
    assert "get_for_connector" in src
