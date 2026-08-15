"""tests/unit/test_p0_ai_action_confirm.py
P0: /api/ai/action/confirm must require approval:write, not chat:use.
AI supervisor role must NOT be able to approve or reject drafts.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def run_sync(coro):
    return asyncio.run(coro)


def _make_request(role="ai_supervisor", permissions=None):
    """Build a mock request with the given role and permissions."""
    req = MagicMock()
    req.state = MagicMock()
    req.state.tenant_id = "tenant1"
    req.state.user_id = f"user_{role}"
    req.state.role = role
    req.state.permissions = permissions or set()
    return req


# ── Permission gate ───────────────────────────────────────────────────────────

def test_confirm_action_requires_approval_write_not_chat_use():
    """confirm_action must call require_permission with 'approval:write'."""
    import inspect
    from app.api.routes_ai_chat import confirm_action
    src = inspect.getsource(confirm_action)
    assert "approval:write" in src, (
        "confirm_action must require 'approval:write', not 'chat:use'"
    )
    assert "chat:use" not in src.split("require_permission")[1].split(")")[0], (
        "confirm_action must NOT use 'chat:use' permission"
    )


def test_ai_supervisor_cannot_approve_via_confirm():
    """ai_supervisor role (chat:use only) must be blocked from /action/confirm."""
    from fastapi import HTTPException
    from app.api.routes_ai_chat import confirm_action
    from app.api.rbac import require_permission

    req = _make_request(role="ai_supervisor", permissions={"chat:use"})

    def _raise_forbidden(request, permission):
        if permission == "approval:write" and "approval:write" not in (
            getattr(request.state, "permissions", set()) or set()
        ):
            raise HTTPException(status_code=403, detail="Forbidden")

    with patch("app.api.routes_ai_chat.require_permission", side_effect=_raise_forbidden):
        with pytest.raises(HTTPException) as exc_info:
            run_sync(confirm_action(req, {"action": "approve_draft", "params": {"draft_id": 1}}))
        assert exc_info.value.status_code == 403


def test_accountant_with_approval_write_can_approve():
    """User with approval:write permission must be allowed through the gate."""
    from app.api.routes_ai_chat import confirm_action

    req = _make_request(role="accountant", permissions={"approval:write", "chat:use"})
    mock_result = {"ok": True, "message": "approved", "data": {"status": "approved"}, "error": None}

    with patch("app.api.routes_ai_chat.require_permission"), \
         patch("app.api.services.approval_service.approve_draft_service",
               new=AsyncMock(return_value=mock_result)):
        result = run_sync(confirm_action(req, {"action": "approve_draft", "params": {"draft_id": 42}}))
    assert result.get("ok") is True


# ── await correctness ─────────────────────────────────────────────────────────

def test_confirm_action_awaits_approve_draft_service():
    """approve_draft_service is async — confirm_action must await it."""
    import inspect
    from app.api.routes_ai_chat import confirm_action
    src = inspect.getsource(confirm_action)
    # The call must be `await approve_draft_service(...)`
    assert "await approve_draft_service" in src, (
        "confirm_action must await approve_draft_service (it is async)"
    )


def test_confirm_action_awaits_reject_draft_service():
    """reject_draft_service is async — confirm_action must await it."""
    import inspect
    from app.api.routes_ai_chat import confirm_action
    src = inspect.getsource(confirm_action)
    assert "await reject_draft_service" in src, (
        "confirm_action must await reject_draft_service (it is async)"
    )


# ── Unknown action still blocked ──────────────────────────────────────────────

def test_unknown_action_raises_400():
    from fastapi import HTTPException
    from app.api.routes_ai_chat import confirm_action

    req = _make_request(role="accountant", permissions={"approval:write"})

    with patch("app.api.routes_ai_chat.require_permission"):
        with pytest.raises(HTTPException) as exc_info:
            run_sync(confirm_action(req, {"action": "delete_everything", "params": {}}))
        assert exc_info.value.status_code == 400
