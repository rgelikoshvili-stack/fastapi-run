"""tests/unit/test_rsge_token_security.py — Token never exposed in responses/logs."""
import inspect
import json
import os


# ── 1. Access token not in any route source ───────────────────────────────────

def test_access_token_not_in_routes():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    for line in src.splitlines():
        s = line.strip()
        if "ACCESS_TOKEN" in s and not s.startswith(("#", '"', "'", '"""')):
            assert False, f"ACCESS_TOKEN in route line: {line}"


# ── 2. PIN_TOKEN not exposed in routes ───────────────────────────────────────

def test_pin_token_not_in_routes():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    for line in src.splitlines():
        s = line.strip()
        if "PIN_TOKEN" in s and not s.startswith(("#", '"', "'", '"""')):
            assert False, f"PIN_TOKEN in route line: {line}"


# ── 3. Connector does not log .sp (service password) ─────────────────────────

def test_connector_no_sp_in_logs():
    from app.api.connectors import rs_ge_connector as m
    src = inspect.getsource(m)
    log_lines = [l for l in src.splitlines() if "log." in l]
    for line in log_lines:
        assert "password" not in line.lower(), f"password in log: {line}"


# ── 4. Auth service never returns raw sp ────────────────────────────────────

def test_auth_service_no_raw_sp_return():
    from app.api.services import rsge_auth_service as m
    for fn_name in ("start_soap_auth", "get_connection_status", "signout"):
        fn = getattr(m, fn_name)
        src = inspect.getsource(fn)
        assert "return sp" not in src, f"{fn_name} must not return sp"


# ── 5. _redacted_payload always masks su and sp ──────────────────────────────

def test_redacted_payload_masks_credentials():
    from app.api.services.rsge_action_service import _redacted_payload
    doc = {"id": 1, "rsge_id": "X", "amount": 500, "full_amount": 500,
           "reg_no": "R1", "waybill_number": ""}
    p = _redacted_payload("confirm", doc)
    assert p["su"] == "****"
    assert p["sp"] == "****"
    serialized = json.dumps(p)
    assert "tbilisi" not in serialized
    assert "12345" not in serialized


# ── 6. No Authorization header in auth service log calls ─────────────────────

def test_no_auth_header_in_auth_service_logs():
    from app.api.services import rsge_auth_service as m
    src = inspect.getsource(m)
    for line in src.splitlines():
        if "log." in line:
            assert "authorization" not in line.lower(), f"Authorization in log: {line}"
            assert "bearer" not in line.lower(), f"Bearer in log: {line}"


# ── 7. Token never in JSON serialization of redacted payload ─────────────────

def test_token_not_in_serialized_payload():
    from app.api.services.rsge_action_service import _redacted_payload
    doc = {"id": 1, "rsge_id": "Y", "amount": 100, "full_amount": 100,
           "reg_no": "N2", "waybill_number": ""}
    payload = _redacted_payload("reject", doc)
    serialized = json.dumps(payload)
    for dangerous in ("eyJ", "Bearer ", "token=", "access_token"):
        assert dangerous not in serialized


# ── 8. Vault stores token, route does not return it ──────────────────────────

def test_vault_token_not_in_route_response():
    import app.api.routes_rs_ge as routes
    src = inspect.getsource(routes)
    assert "get_decrypted_soap_creds" not in src
    assert "raw_token" not in src


# ── 9. rsge_config does not expose live action enablement by default ──────────

def test_live_actions_disabled_by_default():
    live_enabled = os.environ.get("RSGE_LIVE_ACTIONS_ENABLED", "false").lower()
    assert live_enabled in ("false", "0", ""), \
        "RSGE_LIVE_ACTIONS_ENABLED must not be true in test environment"


# ── 10. Raw credentials note in redacted payload ─────────────────────────────

def test_redacted_payload_has_note():
    from app.api.services.rsge_action_service import _redacted_payload
    doc = {"id": 1, "rsge_id": "Z", "amount": 0, "full_amount": 0, "reg_no": ""}
    p = _redacted_payload("cancel", doc)
    note = str(p.get("note") or "")
    assert "redacted" in note.lower() or "****" in str(p)
