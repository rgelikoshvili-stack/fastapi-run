import asyncio
import inspect
import os

import pytest


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_health_returns_ok_true_in_test_mode():
    """Liveness probe must return ok=true even when API keys are not configured."""
    from app.api.routes_health import health_check
    result = asyncio.run(health_check())
    assert result["ok"] is True, (
        f"/health returned ok=false — liveness probes must always return ok=true: {result}"
    )


def test_health_returns_ok_true_without_env_vars(monkeypatch):
    """ok=true even when all optional env vars are absent."""
    for key in ("ANTHROPIC_API_KEY", "BALANCE_API_KEY", "OPENROUTER_API_KEY",
                "DATABASE_URL", "JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)

    from app.api.routes_health import health_check
    result = asyncio.run(health_check())
    assert result["ok"] is True


def test_health_data_shape():
    """/health data must include required fields."""
    from app.api.routes_health import health_check
    result = asyncio.run(health_check())
    data = result["data"]
    assert "service" in data
    assert "uptime" in data
    assert "status" in data
    assert "env_vars" in data
    assert "connectors" in data


def test_health_missing_keys_surfaced_as_warnings(monkeypatch):
    """Missing API keys must appear in warnings, not cause ok=false."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from app.api.routes_health import health_check
    result = asyncio.run(health_check())
    assert result["ok"] is True
    data = result["data"]
    assert data["status"] == "degraded"
    assert any("ANTHROPIC_API_KEY" in w for w in data["warnings"])


def test_health_no_db_calls():
    """Fast /health must not call DB — keep it sub-50ms."""
    src = inspect.getsource(__import__("app.api.routes_health", fromlist=["health_check"]).health_check)
    assert "get_conn" not in src
    assert "fetchrow" not in src
    assert "fetchval" not in src


def test_health_deep_endpoint_exists():
    import app.api.routes_health as mod
    assert callable(getattr(mod, "health_check_deep", None))


def test_health_ping_endpoint_exists():
    import app.api.routes_health as mod
    assert callable(getattr(mod, "ping", None))


def test_health_has_uptime():
    src = inspect.getsource(__import__("app.api.routes_health", fromlist=["health_check"]).health_check)
    assert "uptime" in src


def test_deep_health_calls_db():
    import app.api.routes_health as mod
    src = inspect.getsource(mod.health_check_deep)
    assert "get_conn" in src or "_check_db_deep" in src
