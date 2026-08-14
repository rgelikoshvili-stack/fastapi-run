"""tests/unit/test_p0_ai_approve_bypass.py
P0-1: AI approve_draft must NOT perform direct DB updates.

All tests are pure Python — no DB required.
"""
import asyncio
import pytest


def run_sync(coro):
    return asyncio.run(coro)


def _get_tool():
    from app.api.routes_claude_chat import _tool_approve_draft
    return _tool_approve_draft


# ── Core contract ─────────────────────────────────────────────────────────────

def test_approve_draft_returns_approval_required_true():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 42}, "tenant1"))
    assert result["approval_required"] is True


def test_approve_draft_returns_correct_draft_id():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 99}, "tenant1"))
    assert result["draft_id"] == 99


def test_approve_draft_returns_action_field():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 1}, "tenant1"))
    assert result["action"] == "approve_draft"


def test_approve_draft_returns_next_endpoint():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 7}, "tenant1"))
    assert "next_endpoint" in result
    assert "7" in result["next_endpoint"]


def test_approve_draft_does_not_contain_status_approved():
    """Result must never contain status=approved — that is set only by approval_service."""
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 1}, "tenant1"))
    assert result.get("status") != "approved"
    assert result.get("ok") is not True or result.get("approval_required") is True


def test_approve_draft_no_db_access():
    """Tool must not import or call get_conn — verified by not having DB in env."""
    import os
    # Unset DATABASE_URL — if tool tried to connect it would fail
    old = os.environ.pop("DATABASE_URL", None)
    try:
        tool = _get_tool()
        result = run_sync(tool({"draft_id": 1}, "tenant1"))
        assert result["approval_required"] is True
    finally:
        if old is not None:
            os.environ["DATABASE_URL"] = old


def test_approve_draft_carries_comment():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 5, "comment": "LGTM"}, "tenant1"))
    assert result["comment"] == "LGTM"


def test_approve_draft_empty_comment_becomes_none():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 5, "comment": ""}, "tenant1"))
    assert result["comment"] is None


def test_approve_draft_invalid_id_returns_error():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": "abc"}, "tenant1"))
    assert result.get("success") is False or "error" in result


def test_approve_draft_missing_id_returns_error():
    tool = _get_tool()
    result = run_sync(tool({}, "tenant1"))
    assert result.get("success") is False or "error" in result


# ── Warning message content ───────────────────────────────────────────────────

def test_approve_draft_warning_mentions_period_lock():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 1}, "tenant1"))
    warning = (result.get("warning") or "") + (result.get("message") or "")
    assert "period" in warning.lower() or "lock" in warning.lower()


def test_approve_draft_warning_mentions_cfo():
    tool = _get_tool()
    result = run_sync(tool({"draft_id": 1}, "tenant1"))
    warning = (result.get("warning") or "") + (result.get("message") or "")
    assert "cfo" in warning.lower() or "10" in warning


# ── Tool definition sanity ────────────────────────────────────────────────────

def test_approve_draft_tool_description_mentions_human():
    from app.api.routes_claude_chat import TOOLS
    tool_def = next((t for t in TOOLS if t["name"] == "approve_draft"), None)
    assert tool_def is not None
    desc = tool_def["description"].lower()
    assert "ai" in desc or "human" in desc or "ადამიანი" in desc


def test_system_prompt_does_not_claim_direct_approval():
    from app.api.routes_claude_chat import SYSTEM_PROMPT
    # Old prompt said "approve_draft"-ს გამოიყენე (use approve_draft to approve)
    # New prompt must clarify human approval is required
    assert "ადამიანი" in SYSTEM_PROMPT or "human" in SYSTEM_PROMPT.lower()
