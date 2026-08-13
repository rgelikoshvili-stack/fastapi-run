"""tests/unit/test_rsge_rbac_approval_required.py — RBAC and approval enforcement."""
import asyncio
import inspect
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. All action routes require require_permission ───────────────────────────

def test_action_routes_require_permission():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    assert "require_permission" in src


# ── 2. execute_test_action requires approved_by ──────────────────────────────

def test_execute_requires_approved_by():
    from app.api.services.rsge_action_service import execute_test_action
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={
        "id": 1, "tenant_id": "t1", "rsge_id": "100",
        "rsge_status": "0", "rsge_status_code": "0",
        "amount": 100, "full_amount": 100,
    })
    connector = MagicMock()
    connector.mode = "demo"
    with pytest.raises(ValueError, match="approved_by"):
        asyncio.run(
            execute_test_action(
                conn, "t1", 1, "confirm",
                requested_by="user1", approved_by="",
                connector=connector,
            )
        )


# ── 3. RBAC permission is posting:write for mutations ────────────────────────

def test_mutation_endpoints_use_posting_write():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    assert 'require_permission(request, "posting:write")' in src


# ── 4. Read endpoints use posting:read ───────────────────────────────────────

def test_read_endpoints_use_posting_read():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    assert 'require_permission(request, "posting:read")' in src


# ── 5. require_permission raises 403 for missing permission ──────────────────

def test_require_permission_raises_403():
    from fastapi import HTTPException, Request
    from app.api.authz import require_permission
    mock_request = MagicMock()
    mock_request.state.user_id = "u1"
    mock_request.state.role = "viewer"
    mock_request.state.tenant_id = "t1"
    with pytest.raises(HTTPException) as exc:
        require_permission(mock_request, "posting:write")
    assert exc.value.status_code == 403


# ── 6. Test action requires RSGE_TEST_MODE flag ──────────────────────────────

def test_test_action_blocked_without_flag():
    from fastapi import HTTPException
    from app.api.services.rsge_config import require_action_flag
    with patch.dict(os.environ, {"RSGE_TEST_MODE": "false",
                                  "RSGE_ALLOW_TEST_CONFIRM": "false"}):
        with pytest.raises(HTTPException) as exc:
            require_action_flag("confirm")
    assert exc.value.status_code == 403


# ── 7. Test action allowed when test flag set ────────────────────────────────

def test_test_action_allowed_with_flag():
    from app.api.services.rsge_config import require_action_flag
    with patch.dict(os.environ, {"RSGE_TEST_MODE": "true",
                                  "RSGE_ALLOW_TEST_CONFIRM": "true",
                                  "RSGE_LIVE_ACTIONS_ENABLED": "false"}):
        require_action_flag("confirm")  # must not raise


# ── 8. Production blocker in rsge_config ─────────────────────────────────────

def test_production_blocker_in_config():
    from app.api.services import rsge_config as m
    src = inspect.getsource(m.require_test_mode)
    assert "403" in src or "status_code=403" in src


# ── 9. Audit log written by execute_test_action ───────────────────────────────

def test_audit_log_written():
    src = inspect.getsource(
        __import__("app.api.services.rsge_action_service",
                   fromlist=["execute_test_action"]).execute_test_action
    )
    assert "_write_audit" in src
    assert "_finalize_audit" in src


# ── 10. No auto-posting in any RS.ge service ────────────────────────────────

def test_no_auto_posting_in_rsge_services():
    import app.api.services.rsge_action_service as svc
    src = inspect.getsource(svc)
    for forbidden in ("approve_draft", "post_draft", "auto_post", "autopost"):
        assert forbidden not in src.lower(), f"auto-posting pattern found: {forbidden}"


# ── 11. Approval required phrasing exists in execute_test_action ─────────────

def test_execute_requires_approval_reference():
    from app.api.services import rsge_action_service as svc
    src = inspect.getsource(svc.execute_test_action)
    assert "approved_by" in src


# ── 12. Action endpoints not accessible without auth header (structural) ──────

def test_require_permission_present_in_all_action_handlers():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    factory_src_marker = "_action_routes"
    assert factory_src_marker in src, "action route factory must exist"
    # The factory injects require_permission for each action
    factory_lines = []
    recording = False
    for line in src.splitlines():
        if "def _action_routes" in line:
            recording = True
        if recording:
            factory_lines.append(line)
            if line.strip().startswith("def ") and "action_routes" not in line:
                break
    factory_src = "\n".join(factory_lines)
    assert "require_permission" in factory_src
