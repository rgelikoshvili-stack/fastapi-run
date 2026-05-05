"""tests/unit/test_llm_ping.py — unit tests for GET /debug/llm-ping."""
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _request(role="admin"):
    return SimpleNamespace(
        state=SimpleNamespace(authenticated=True, role=role, tenant_id="tenant-a")
    )


def _ok_ant():
    return {"ok": True,  "model": "claude-sonnet-4-6", "error": None}

def _ok_or():
    return {"ok": True,  "model": "openai/gpt-4o-mini", "error": None}

def _fail_ant(code="PROVIDER_ERROR"):
    return {"ok": False, "model": "claude-sonnet-4-6", "error": code}

def _fail_or(code="PROVIDER_ERROR"):
    return {"ok": False, "model": "openai/gpt-4o-mini", "error": code}


# ── Permission guard ──────────────────────────────────────────────────────────

def test_llm_ping_requires_tenants_manage():
    """Non-admin roles must get 403."""
    from app.api.routes_debug import debug_llm_ping

    for role in ("viewer", "reviewer", "accountant"):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(debug_llm_ping(_request(role)))
        assert exc.value.status_code == 403, f"Expected 403 for role={role}"


def test_llm_ping_unauthenticated_gets_401():
    from app.api.routes_debug import debug_llm_ping

    req = SimpleNamespace(
        state=SimpleNamespace(authenticated=False, role=None, tenant_id="tenant-a")
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(debug_llm_ping(req))
    assert exc.value.status_code == 401


# ── Response shape — both providers succeed ───────────────────────────────────

def test_llm_ping_both_ok_on_mocked_success():
    """Both providers return ok=true when helpers are mocked to succeed."""
    from app.api.routes_debug import debug_llm_ping

    with patch("app.api.routes_debug._ping_anthropic", AsyncMock(return_value=_ok_ant())), \
         patch("app.api.routes_debug._ping_openrouter", AsyncMock(return_value=_ok_or())):
        result = asyncio.run(debug_llm_ping(_request("admin")))

    assert result["anthropic"]["ok"] is True
    assert result["openrouter"]["ok"] is True
    assert result["anthropic"]["error"] is None
    assert result["openrouter"]["error"] is None
    assert "model" in result["anthropic"]
    assert "model" in result["openrouter"]


def test_llm_ping_both_fail_returns_ok_false():
    """A provider exception must return ok=false without crashing."""
    from app.api.routes_debug import debug_llm_ping

    with patch("app.api.routes_debug._ping_anthropic", AsyncMock(return_value=_fail_ant())), \
         patch("app.api.routes_debug._ping_openrouter", AsyncMock(return_value=_fail_or())):
        result = asyncio.run(debug_llm_ping(_request("admin")))

    assert result["anthropic"]["ok"] is False
    assert result["openrouter"]["ok"] is False
    assert result["anthropic"]["error"] is not None
    assert result["openrouter"]["error"] is not None


def test_llm_ping_partial_failure_reported_independently():
    """One provider success + one failure are both reported correctly."""
    from app.api.routes_debug import debug_llm_ping

    with patch("app.api.routes_debug._ping_anthropic", AsyncMock(return_value=_ok_ant())), \
         patch("app.api.routes_debug._ping_openrouter", AsyncMock(return_value=_fail_or("TIMEOUT"))):
        result = asyncio.run(debug_llm_ping(_request("admin")))

    assert result["anthropic"]["ok"] is True
    assert result["openrouter"]["ok"] is False
    assert result["openrouter"]["error"] == "TIMEOUT"


# ── NOT_CONFIGURED when keys absent ──────────────────────────────────────────

def test_llm_ping_not_configured_when_keys_absent(monkeypatch):
    """Missing env vars must return NOT_CONFIGURED without importing provider SDKs."""
    from app.api.routes_debug import debug_llm_ping

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # No SDK mock needed — early return before import
    result = asyncio.run(debug_llm_ping(_request("admin")))

    assert result["anthropic"]["ok"] is False
    assert result["anthropic"]["error"] == "NOT_CONFIGURED"
    assert result["openrouter"]["ok"] is False
    assert result["openrouter"]["error"] == "NOT_CONFIGURED"


# ── No secrets leak ───────────────────────────────────────────────────────────

def test_llm_ping_response_never_contains_api_key(monkeypatch):
    """Response must not contain any fragment of the API keys."""
    from app.api.routes_debug import debug_llm_ping

    fake_ant = "sk-ant-realkey123456"
    fake_or  = "sk-or-realkey654321"

    with patch("app.api.routes_debug._ping_anthropic",
               AsyncMock(return_value=_fail_ant("AUTH_ERROR"))), \
         patch("app.api.routes_debug._ping_openrouter",
               AsyncMock(return_value=_fail_or("AUTH_ERROR"))):
        # Even if the keys were somehow in scope, the response must not expose them
        monkeypatch.setenv("ANTHROPIC_API_KEY", fake_ant)
        monkeypatch.setenv("OPENROUTER_API_KEY", fake_or)
        result = asyncio.run(debug_llm_ping(_request("admin")))

    result_str = str(result)
    assert fake_ant   not in result_str, "Anthropic key leaked into response"
    assert fake_or    not in result_str, "OpenRouter key leaked into response"
    assert "sk-ant"   not in result_str
    assert "sk-or"    not in result_str


def test_llm_ping_response_never_contains_base_url():
    """Response must not expose provider base URLs."""
    from app.api.routes_debug import debug_llm_ping

    with patch("app.api.routes_debug._ping_anthropic", AsyncMock(return_value=_fail_ant())), \
         patch("app.api.routes_debug._ping_openrouter", AsyncMock(return_value=_fail_or())):
        result = asyncio.run(debug_llm_ping(_request("admin")))

    result_str = str(result)
    assert "openrouter.ai"  not in result_str
    assert "api.anthropic"  not in result_str
    assert "api/v1"         not in result_str


# ── _ping helpers with injected SDK mocks ────────────────────────────────────

def _make_ant_module(response_text: str):
    """Build a fake `anthropic` module with AsyncAnthropic that returns response_text."""
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]

    client_inst = MagicMock()
    client_inst.messages.create = AsyncMock(return_value=msg)

    mod = MagicMock()
    mod.AsyncAnthropic.return_value = client_inst
    return mod


def _make_or_module(response_text: str):
    """Build a fake `openai` module with AsyncOpenAI that returns response_text."""
    choice = MagicMock()
    choice.message.content = response_text
    resp = MagicMock()
    resp.choices = [choice]

    client_inst = MagicMock()
    client_inst.chat.completions.create = AsyncMock(return_value=resp)

    mod = MagicMock()
    mod.AsyncOpenAI.return_value = client_inst
    return mod


def test_ping_anthropic_ok_on_expected_response(monkeypatch):
    """_ping_anthropic returns ok=true when model echoes ANTHROPIC_OK."""
    from app.api.routes_debug import _ping_anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    with patch.dict(sys.modules, {"anthropic": _make_ant_module("ANTHROPIC_OK")}):
        result = asyncio.run(_ping_anthropic())

    assert result["ok"] is True
    assert result["error"] is None


def test_ping_anthropic_fails_on_wrong_response(monkeypatch):
    """_ping_anthropic returns ok=false when model returns unexpected text."""
    from app.api.routes_debug import _ping_anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    with patch.dict(sys.modules, {"anthropic": _make_ant_module("I don't know")}):
        result = asyncio.run(_ping_anthropic())

    assert result["ok"] is False


def test_ping_openrouter_ok_on_expected_response(monkeypatch):
    """_ping_openrouter returns ok=true when model echoes OPENROUTER_OK."""
    from app.api.routes_debug import _ping_openrouter

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fake")
    with patch.dict(sys.modules, {"openai": _make_or_module("OPENROUTER_OK")}):
        result = asyncio.run(_ping_openrouter())

    assert result["ok"] is True
    assert result["error"] is None


def test_ping_openrouter_fails_on_sdk_exception(monkeypatch):
    """_ping_openrouter returns ok=false when SDK raises."""
    from app.api.routes_debug import _ping_openrouter

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fake")

    client_inst = MagicMock()
    client_inst.chat.completions.create = AsyncMock(side_effect=RuntimeError("network down"))
    or_mod = MagicMock()
    or_mod.AsyncOpenAI.return_value = client_inst

    with patch.dict(sys.modules, {"openai": or_mod}):
        result = asyncio.run(_ping_openrouter())

    assert result["ok"] is False
    assert result["error"] is not None


# ── Error classification ──────────────────────────────────────────────────────

def test_safe_error_maps_known_exceptions():
    from app.api.routes_debug import _safe_error

    class AuthenticationError(Exception): pass
    class RateLimitError(Exception): pass
    class APITimeoutError(Exception): pass
    class APIConnectionError(Exception): pass
    class NotFoundError(Exception): pass

    assert _safe_error(AuthenticationError("bad key")) == "AUTH_ERROR"
    assert _safe_error(RateLimitError("too many"))     == "RATE_LIMIT"
    assert _safe_error(APITimeoutError("timed out"))   == "TIMEOUT"
    assert _safe_error(APIConnectionError("no conn"))  == "CONNECTION_ERROR"
    assert _safe_error(NotFoundError("model"))         == "MODEL_NOT_FOUND"


def test_safe_error_unknown_exception_returns_generic():
    from app.api.routes_debug import _safe_error

    assert _safe_error(ValueError("some weird error")) == "PROVIDER_ERROR"


def test_safe_error_never_leaks_key_text():
    """_safe_error must not include the original exception message in its output."""
    from app.api.routes_debug import _safe_error

    code = _safe_error(RuntimeError("sk-ant-supersecretkey1234"))
    assert "sk-ant" not in code
    assert "supersecretkey" not in code
