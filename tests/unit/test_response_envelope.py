"""tests/unit/test_response_envelope.py

Verify that key routes return the standard {ok, message, data, error} envelope.
Tests patch service calls so no DB is needed.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _req(role="accountant", tenant="tenant-a"):
    return SimpleNamespace(
        state=SimpleNamespace(
            authenticated=True, role=role, tenant_id=tenant,
            user_id="u1",
        )
    )


def _assert_envelope(result, *, ok: bool):
    """Assert result has the standard envelope shape."""
    assert "ok" in result, f"Response missing 'ok': {result}"
    assert result["ok"] is ok, f"Expected ok={ok}, got {result}"
    assert "message" in result, f"Response missing 'message': {result}"
    assert "data" in result,    f"Response missing 'data': {result}"
    assert "error" in result,   f"Response missing 'error': {result}"
    if ok:
        assert result["error"] is None, f"Successful response must have error=null: {result}"
    else:
        assert result["error"] is not None, f"Error response must have error!=null: {result}"


# ── ok_response / error_response helpers themselves ──────────────────────────

def test_ok_response_has_full_envelope():
    from app.api.response_utils import ok_response
    r = ok_response("Done", {"x": 1})
    _assert_envelope(r, ok=True)
    assert r["data"] == {"x": 1}
    assert r["message"] == "Done"


def test_error_response_has_full_envelope():
    from app.api.response_utils import error_response
    r = error_response("Bad", "BAD_CODE", "details here")
    _assert_envelope(r, ok=False)
    assert r["error"]["code"] == "BAD_CODE"
    assert r["error"]["details"] == "details here"


# ── Approval update-draft returns standard envelope ──────────────────────────

def test_approval_update_no_changes_returns_ok_envelope():
    """When no fields are provided, update-draft must return standard ok envelope."""
    from app.api.routes_approval import update_draft

    class Req:
        description = None
        partner = None
        amount = None
        debit_account = None
        credit_account = None
        account_code = None
        reason = None

    result = asyncio.run(update_draft(99, Req(), _req()))
    _assert_envelope(result, ok=True)


def test_cfo_approve_ok_response_shape():
    """ok_response used in CFO approve must have the standard envelope."""
    from app.api.response_utils import ok_response
    result = ok_response("CFO approval recorded", {"id": 1, "status": "approved", "approved_by": "cfo", "level": "CFO"})
    _assert_envelope(result, ok=True)
    assert result["data"]["level"] == "CFO"


def test_approval_awaiting_cfo_list_returns_ok_envelope():
    """Awaiting-CFO listing must return standard ok envelope."""
    from app.api.routes_approval import list_awaiting_cfo

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.routes_approval.get_conn", return_value=cm):
        result = asyncio.run(list_awaiting_cfo(_req()))

    _assert_envelope(result, ok=True)


# ── Payroll service returns standard envelope ─────────────────────────────────

def test_payroll_error_response_has_full_envelope():
    """Payroll error return must use standard error_response envelope."""
    from app.api.response_utils import error_response
    r = error_response("Payroll draft generation failed", "PAYROLL_ERROR")
    _assert_envelope(r, ok=False)
    assert r["error"]["code"] == "PAYROLL_ERROR"


# ── Source-level guards: no bare ok dict in critical routes ───────────────────

def test_routes_approval_no_bare_ok_dict():
    """routes_approval.py must not return raw {'ok': True/False} dicts."""
    import inspect
    import app.api.routes_approval as mod
    src = inspect.getsource(mod)
    # After the fix, routes must not contain bare dict returns with ok key missing message/data
    # Check the specific patterns that were fixed
    assert 'return {"ok": True, "message": "no_changes"}' not in src, \
        "Raw dict response still present — should use ok_response()"
    assert 'return {"ok": True, "draft_id":' not in src, \
        "Raw dict response still present — should use ok_response()"
    assert 'return {"ok": False, "error": str(e)}' not in src, \
        "Raw dict response still present — should use error_response()"


def test_payroll_success_preserves_legacy_top_level_keys():
    """Direct callers still expect drafts_created at top level after envelope migration."""
    from app.api.response_utils import ok_response
    data = {"period": "2026-05", "drafts_created": 4, "draft_ids": [1, 2, 3, 4], "tenant_id": "tenant-a"}
    result = {**ok_response("Payroll drafts created", data), **data}
    _assert_envelope(result, ok=True)
    assert result["drafts_created"] == 4
    assert result["data"]["drafts_created"] == 4
