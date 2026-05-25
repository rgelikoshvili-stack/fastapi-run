"""tests/unit/test_debug_metrics_no_secrets.py

Secret-safety tests for /debug/* and /metrics responses.
Verifies that no raw credential values are ever returned by debug endpoints.
No DB, no network.
"""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _req(role="admin"):
    return SimpleNamespace(
        state=SimpleNamespace(authenticated=True, role=role, tenant_id="t1")
    )


_SECRET_PATTERNS = [
    "postgresql://",
    "DATABASE_URL",
    "JWT_SECRET",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "BALANCE_API_KEY",
]


def _assert_no_secret_values(result_str: str, monkeypatch):
    """Assert that the result string doesn't contain injected fake secret values."""
    fake_secrets = [
        "fake-db-password-xyz",
        "fake-jwt-secret-xyz",
        "sk-ant-fakeanthropic",
        "sk-openai-fakekey",
        "sk-or-fakeopenrouter",
        "fake-balance-key-xyz",
    ]
    for secret in fake_secrets:
        assert secret not in result_str, f"Secret value leaked into response: {secret!r}"


class TestDebugOpenaiNoSecrets:
    def test_openai_key_not_in_response(self, monkeypatch):
        from app.api.routes_debug import debug_openai
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fakekey")
        result = debug_openai(_req())
        result_str = str(result)
        assert "sk-openai-fakekey" not in result_str
        assert "sk-" not in result_str or "configured" in result_str

    def test_openai_response_shape_safe(self, monkeypatch):
        from app.api.routes_debug import debug_openai
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fakekey")
        result = debug_openai(_req())
        data = result["data"]
        assert set(data.keys()) == {"configured"}
        assert data["configured"] is True

    def test_openai_key_absent_shows_false(self, monkeypatch):
        from app.api.routes_debug import debug_openai
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = debug_openai(_req())
        assert result["data"]["configured"] is False


class TestDebugBalancePingNoSecrets:
    def test_balance_key_not_in_response(self, monkeypatch):
        from app.api.routes_debug import debug_balance_ping
        monkeypatch.setenv("BALANCE_API_URL", "https://balance.internal/api")
        monkeypatch.setenv("BALANCE_API_KEY", "fake-balance-key-xyz")
        monkeypatch.setenv("BALANCE_COMPANY_ID", "fake-company-id")
        result = debug_balance_ping(_req())
        result_str = str(result)
        assert "fake-balance-key-xyz" not in result_str
        assert "https://balance.internal/api" not in result_str
        assert "fake-company-id" not in result_str

    def test_balance_response_only_boolean_flags(self, monkeypatch):
        from app.api.routes_debug import debug_balance_ping
        monkeypatch.setenv("BALANCE_API_URL", "https://balance.internal/api")
        monkeypatch.setenv("BALANCE_API_KEY", "fake-balance-key-xyz")
        monkeypatch.setenv("BALANCE_COMPANY_ID", "c123")
        data = debug_balance_ping(_req())["data"]
        assert data == {
            "base_url_configured": True,
            "api_key_configured": True,
            "company_id_configured": True,
        }


class TestDebugAiRoutingNoSecrets:
    def test_ai_routing_no_api_keys(self):
        from app.api.routes_debug import debug_ai_routing
        result = debug_ai_routing(_req())
        result_str = str(result)
        for pat in ("sk-ant", "sk-openai", "postgresql://", "JWT_SECRET"):
            assert pat not in result_str, f"Secret pattern {pat!r} found in ai-routing response"

    def test_ai_routing_claude_available_boolean_only(self, monkeypatch):
        from app.api.routes_debug import debug_ai_routing
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fakeanthropic")
        result = debug_ai_routing(_req())
        data = result["data"]
        assert isinstance(data.get("claude_available"), bool)
        assert "sk-ant-fakeanthropic" not in str(data)


class TestDebugLlmPingNoSecrets:
    def test_llm_ping_no_api_keys_in_response(self, monkeypatch):
        from app.api.routes_debug import debug_llm_ping
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fakeanthropic")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fakeopenrouter")

        with patch("app.api.routes_debug._ping_anthropic",
                   AsyncMock(return_value={"ok": False, "model": "m", "error": "AUTH_ERROR"})), \
             patch("app.api.routes_debug._ping_openrouter",
                   AsyncMock(return_value={"ok": False, "model": "m", "error": "AUTH_ERROR"})):
            result = asyncio.run(debug_llm_ping(_req()))

        result_str = str(result)
        assert "sk-ant-fakeanthropic" not in result_str
        assert "sk-or-fakeopenrouter" not in result_str

    def test_llm_ping_error_codes_are_generic(self, monkeypatch):
        from app.api.routes_debug import debug_llm_ping
        with patch("app.api.routes_debug._ping_anthropic",
                   AsyncMock(return_value={"ok": False, "model": "m", "error": "AUTH_ERROR"})), \
             patch("app.api.routes_debug._ping_openrouter",
                   AsyncMock(return_value={"ok": False, "model": "m", "error": "TIMEOUT"})):
            result = asyncio.run(debug_llm_ping(_req()))
        assert result["anthropic"]["error"] in (
            "AUTH_ERROR", "RATE_LIMIT", "CONNECTION_ERROR", "TIMEOUT",
            "MODEL_NOT_FOUND", "BAD_REQUEST", "PROVIDER_ERROR", "NOT_CONFIGURED",
        )

    def test_llm_ping_no_base_urls(self, monkeypatch):
        from app.api.routes_debug import debug_llm_ping
        with patch("app.api.routes_debug._ping_anthropic",
                   AsyncMock(return_value={"ok": False, "model": "m", "error": "NOT_CONFIGURED"})), \
             patch("app.api.routes_debug._ping_openrouter",
                   AsyncMock(return_value={"ok": False, "model": "m", "error": "NOT_CONFIGURED"})):
            result = asyncio.run(debug_llm_ping(_req()))
        result_str = str(result)
        assert "openrouter.ai" not in result_str
        assert "api.anthropic" not in result_str


class TestHealthNoSecrets:
    def test_health_env_vars_only_set_or_missing(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/health")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        env_vars = data.get("env_vars", {})
        for key, value in env_vars.items():
            assert value in ("set", "missing"), (
                f"Health endpoint exposed raw env var value for {key!r}: {value!r}"
            )

    def test_health_no_database_url_value(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/health")
        body = resp.text
        assert "postgresql://" not in body
        assert "DATABASE_URL=" not in body

    def test_health_no_jwt_secret_value(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/health")
        body = resp.text
        assert "test-secret" not in body
        assert "JWT_SECRET=" not in body


class TestMetricsNoSecrets:
    def test_metrics_no_secret_keys_in_schema(self):
        from fastapi.testclient import TestClient
        from main import app
        resp = TestClient(app).get("/metrics")
        assert resp.status_code in (401, 403)
        body = resp.text
        for pattern in ("postgresql://", "sk-ant", "sk-or", "JWT_SECRET="):
            assert pattern not in body, f"Secret pattern {pattern!r} leaked in 401/403 response"


class TestSourceCodeNoHardcodedSecrets:
    def test_routes_debug_no_hardcoded_credentials(self):
        import pathlib
        src = pathlib.Path("app/api/routes_debug.py").read_text(encoding="utf-8")
        assert "postgresql://" not in src
        assert 'api_key="sk-' not in src
        assert "api_key='sk-" not in src
        assert 'password="' not in src
        assert "password='" not in src

    def test_main_metrics_handler_no_hardcoded_secrets(self):
        import pathlib
        import inspect
        import main as _main
        src = inspect.getsource(_main.metrics)
        assert "postgresql://" not in src
        assert "sk-ant" not in src
        assert "password" not in src.lower()
