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


def test_health_missing_global_balance_key_is_tenant_scoped_not_demo(monkeypatch):
    monkeypatch.delenv("BALANCE_API_KEY", raising=False)
    monkeypatch.delenv("TEST_MODE", raising=False)

    from app.api.routes_health import health_check
    data = asyncio.run(health_check())["data"]

    assert data["connectors"]["balance"] == "tenant_scoped"
    assert "demo" not in data["connectors"]["balance"]
    assert "BALANCE_API_KEY" not in data["env_vars"]
    assert not any("BALANCE_API_KEY" in warning for warning in data["warnings"])


def test_health_global_balance_key_does_not_imply_live_or_configured(monkeypatch):
    monkeypatch.setenv("BALANCE_API_KEY", "synthetic-global-key-must-be-ignored")
    monkeypatch.delenv("TEST_MODE", raising=False)

    from app.api.routes_health import health_check
    data = asyncio.run(health_check())["data"]

    assert data["connectors"]["balance"] == "tenant_scoped"
    assert data["connectors"]["balance"] not in {"live", "configured"}


def test_health_explicit_test_mode_reports_explicit_demo(monkeypatch):
    monkeypatch.delenv("BALANCE_API_KEY", raising=False)
    monkeypatch.setenv("TEST_MODE", "1")

    from app.api.routes_health import health_check
    data = asyncio.run(health_check())["data"]

    assert data["connectors"]["balance"] == "explicit_demo"


def test_missing_legacy_balance_key_does_not_degrade_health(monkeypatch):
    monkeypatch.delenv("BALANCE_API_KEY", raising=False)
    monkeypatch.delenv("TEST_MODE", raising=False)
    for key in ("DATABASE_URL", "JWT_SECRET", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(key, "synthetic-configured-value")

    from app.api.routes_health import health_check
    data = asyncio.run(health_check())["data"]

    assert data["status"] == "ok"
    assert data["connectors"]["balance"] == "tenant_scoped"


def test_health_never_exposes_balance_secret_material(monkeypatch):
    secret = "synthetic-balance-secret-that-must-not-escape"
    monkeypatch.setenv("BALANCE_API_KEY", secret)
    monkeypatch.delenv("TEST_MODE", raising=False)

    from app.api.routes_health import health_check
    result = asyncio.run(health_check())

    assert secret not in str(result)
    assert "BALANCE_API_KEY" not in str(result)


def test_health_balance_status_is_metadata_only():
    src = inspect.getsource(
        __import__("app.api.routes_health", fromlist=["health_check"]).health_check
    )
    for forbidden in ("BalanceConnector", "get_balance_credentials", "requests."):
        assert forbidden not in src


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
