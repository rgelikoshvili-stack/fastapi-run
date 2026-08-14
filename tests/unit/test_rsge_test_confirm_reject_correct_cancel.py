"""tests/unit/test_rsge_test_confirm_reject_correct_cancel.py — Test mode actions."""
import asyncio
import inspect
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _doc(status="0", amount=1000.0):
    return {
        "id": 1, "tenant_id": "t1", "rsge_id": "100",
        "reg_no": "INV-001", "rsge_status": status,
        "rsge_status_code": status, "amount": amount,
        "full_amount": amount, "direction": "incoming",
    }


# ── 1. preview_action returns valid preview ───────────────────────────────────

def test_preview_confirm_returns_valid():
    from app.api.services.rsge_action_service import preview_action
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=_doc())

    result = asyncio.run(
        preview_action(mock_conn, "t1", 1, "confirm")
    )
    assert result["valid"] is True
    assert result["action"] == "confirm"
    assert result["test_mode"] is True
    assert result["requires_approval"] is True
    assert "****" in str(result["payload_preview"])  # credentials redacted


def test_preview_reject_returns_valid():
    from app.api.services.rsge_action_service import preview_action
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=_doc())

    result = asyncio.run(
        preview_action(mock_conn, "t1", 1, "reject")
    )
    assert result["valid"] is True
    assert result["action"] == "reject"


def test_preview_unknown_action_is_invalid():
    from app.api.services.rsge_action_service import preview_action
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=_doc())

    result = asyncio.run(
        preview_action(mock_conn, "t1", 1, "UNKNOWN_ACTION")
    )
    assert result["valid"] is False


# ── 2. Preview never contains raw credentials ─────────────────────────────────

def test_redacted_payload_hides_credentials():
    from app.api.services.rsge_action_service import _redacted_payload
    doc = _doc()
    payload = _redacted_payload("confirm", doc)
    assert payload["su"] == "****"
    assert payload["sp"] == "****"
    assert "confirm" == payload["action"]


# ── 3. execute_test_action requires approved_by ──────────────────────────────

def test_execute_requires_approved_by():
    from app.api.services.rsge_action_service import execute_test_action

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=_doc())
    mock_connector = MagicMock()

    with pytest.raises(ValueError, match="approved_by"):
        asyncio.run(
            execute_test_action(
                mock_conn, "t1", 1, "confirm",
                requested_by="user1", approved_by="",  # empty!
                connector=mock_connector,
            )
        )


# ── 4. test-confirm blocked without RSGE_TEST_MODE ───────────────────────────

def test_confirm_blocked_without_test_mode():
    from fastapi import HTTPException
    from app.api.services.rsge_config import require_action_flag

    with patch.dict(os.environ, {"RSGE_TEST_MODE": "false",
                                  "RSGE_ALLOW_TEST_CONFIRM": "false"}):
        with pytest.raises(HTTPException) as exc_info:
            require_action_flag("confirm")
    assert exc_info.value.status_code == 403


def test_reject_blocked_without_test_mode():
    from fastapi import HTTPException
    from app.api.services.rsge_config import require_action_flag

    with patch.dict(os.environ, {"RSGE_TEST_MODE": "false",
                                  "RSGE_ALLOW_TEST_REJECT": "false"}):
        with pytest.raises(HTTPException) as exc_info:
            require_action_flag("reject")
    assert exc_info.value.status_code == 403


def test_correct_blocked_without_test_mode():
    from fastapi import HTTPException
    from app.api.services.rsge_config import require_action_flag

    with patch.dict(os.environ, {"RSGE_TEST_MODE": "false",
                                  "RSGE_ALLOW_TEST_CORRECT": "false"}):
        with pytest.raises(HTTPException) as exc_info:
            require_action_flag("correct")
    assert exc_info.value.status_code == 403


def test_cancel_blocked_without_test_mode():
    from fastapi import HTTPException
    from app.api.services.rsge_config import require_action_flag

    with patch.dict(os.environ, {"RSGE_TEST_MODE": "false",
                                  "RSGE_ALLOW_TEST_CANCEL": "false"}):
        with pytest.raises(HTTPException) as exc_info:
            require_action_flag("cancel")
    assert exc_info.value.status_code == 403


# ── 5. execute_test_action in demo mode succeeds ─────────────────────────────

def test_execute_confirm_in_demo_mode():
    from app.api.services.rsge_action_service import execute_test_action

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=_doc())
    mock_conn.execute = AsyncMock()

    mock_connector = MagicMock()
    # Demo connector
    mock_connector.mode = "demo"
    mock_connector.su = ""
    mock_connector.sp = ""

    with patch.dict(os.environ, {"RSGE_TEST_MODE": "true",
                                  "RSGE_ALLOW_TEST_CONFIRM": "true",
                                  "RSGE_LIVE_ACTIONS_ENABLED": "false"}):
        result = asyncio.run(
            execute_test_action(
                mock_conn, "t1", 1, "confirm",
                requested_by="user1", approved_by="approver1",
                connector=mock_connector,
            )
        )
    assert result["success"] is True
    assert result["test_mode"] is True


# ── 6. Audit log written before AND after ────────────────────────────────────

def test_audit_log_written_before_and_after():
    from app.api.services import rsge_action_service as svc
    src = inspect.getsource(svc.execute_test_action)
    # Both _write_audit (before) and _finalize_audit (after) must be present
    assert "_write_audit" in src
    assert "_finalize_audit" in src
    # Audit must be called in order: write first, finalize after dispatch
    write_idx = src.index("_write_audit")
    dispatch_idx = src.index("_dispatch_action")
    finalize_idx = src.index("_finalize_audit")
    assert write_idx < dispatch_idx < finalize_idx


# ── 7. Accounting impact is returned ─────────────────────────────────────────

def test_preview_includes_accounting_impact():
    from app.api.services.rsge_action_service import preview_action
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=_doc())

    result = asyncio.run(
        preview_action(mock_conn, "t1", 1, "confirm")
    )
    assert "accounting_impact" in result
    assert isinstance(result["accounting_impact"], dict)
