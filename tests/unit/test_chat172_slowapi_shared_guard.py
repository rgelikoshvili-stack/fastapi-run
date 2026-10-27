"""Chat172: SlowAPI v0.1.9 strict-Redis and decorated-route contracts.

Synthetic TestClient only; no external Redis, Cloud Run, SQL or SMTP.
"""
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.security import _make_limiter, rate_limit_exceeded_handler
from app.api.slowapi_shared_guard import (
    GuardedSlowAPILimiter,
    SharedRateLimitStoreUnavailable,
    shared_rate_limit_unavailable_handler,
)


@pytest.fixture(autouse=True)
def isolated_rate_limit_env(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("RATE_LIMIT_REQUIRE_SHARED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TEST_MODE", "1")


def _app(limiter, limit="2/minute", middleware_limits=False):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(
        SharedRateLimitStoreUnavailable, shared_rate_limit_unavailable_handler
    )
    app.add_middleware(SlowAPIMiddleware)

    if middleware_limits:
        @app.get("/chat172-global-check")
        async def global_route(request: Request):
            return {"ok": True}
    else:
        @app.get("/chat172-limited")
        @limiter.limit(limit)
        async def decorated_route(request: Request):
            return {"ok": True}
    return app


@pytest.mark.parametrize("bad_url", ["", "not-redis://example.invalid", "memory://"])
def test_prod_missing_or_invalid_redis_returns_503_for_decorated_route(monkeypatch, bad_url):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", bad_url)
    limiter = _make_limiter()
    assert isinstance(limiter, GuardedSlowAPILimiter)
    assert limiter._shared_unavailable_on_startup is True
    assert limiter._in_memory_fallback_enabled is False
    assert limiter._swallow_errors is False
    with TestClient(_app(limiter)) as client:
        response = client.get("/chat172-limited")
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "RATE_LIMIT_BACKEND_UNAVAILABLE", "details": None
    }
    assert response.headers["Retry-After"] == "5"
    assert response.headers["Cache-Control"] == "no-store"


def test_shared_required_staging_is_also_strict(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUIRE_SHARED", "1")
    limiter = _make_limiter()
    assert limiter._shared_unavailable_on_startup is True
    with TestClient(_app(limiter)) as client:
        assert client.get("/chat172-limited").status_code == 503


def test_development_preserves_strict_per_route_2_per_minute(monkeypatch):
    limiter = _make_limiter()
    assert limiter._shared_unavailable_on_startup is False
    with TestClient(_app(limiter)) as client:
        codes = [client.get("/chat172-limited").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


@pytest.mark.parametrize("limit", ["3/minute", "5/minute"])
def test_actual_slowapi_decorator_quota_preserved(monkeypatch, limit):
    limiter = _make_limiter()
    with TestClient(_app(limiter, limit=limit)) as client:
        count = int(limit.split("/")[0])
        codes = [client.get("/chat172-limited").status_code for _ in range(count + 1)]
    assert codes == [200] * count + [429]


def test_runtime_storage_failure_in_decorated_route_returns_safe_503(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/14")
    limiter = _make_limiter()
    assert not limiter._shared_unavailable_on_startup
    assert limiter._in_memory_fallback_enabled is False
    # Simulate untrusted service outage with an error message containing a
    # synthetic secret; it must never appear in the response body or log.
    monkeypatch.setattr(
        limiter._limiter, "hit",
        Mock(side_effect=ConnectionError("SYNTHETIC_REDIS_SECRET_DO_NOT_EXPOSE")),
    )
    with TestClient(_app(limiter)) as client:
        result = client.get("/chat172-limited")
    assert result.status_code == 503
    assert "SYNTHETIC_REDIS_SECRET" not in result.text
    assert "Redis" not in result.text


def test_runtime_storage_failure_in_slowapi_middleware_returns_503(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    limiter = GuardedSlowAPILimiter(
        key_func=lambda request: request.client.host,
        storage_uri="memory://",
        application_limits=["2/minute"],
    )
    monkeypatch.setattr(
        limiter._limiter, "hit", Mock(side_effect=ConnectionError("SYNTHETIC")),
    )
    with TestClient(_app(limiter, middleware_limits=True)) as client:
        result = client.get("/chat172-global-check")
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "RATE_LIMIT_BACKEND_UNAVAILABLE"


def test_strict_failure_does_not_turn_429_into_503(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    limiter = GuardedSlowAPILimiter(
        key_func=lambda request: request.client.host,
        storage_uri="memory://",
    )
    with TestClient(_app(limiter, limit="1/minute")) as client:
        assert client.get("/chat172-limited").status_code == 200
        blocked = client.get("/chat172-limited")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMIT"


def test_real_main_app_registers_503_handler_without_disabling_slowapi():
    from pathlib import Path

    src = Path("main.py").read_text(encoding="utf-8")
    assert "app.add_middleware(SlowAPIMiddleware)" in src
    assert "SharedRateLimitStoreUnavailable, shared_rate_limit_unavailable_handler" in src
    assert "app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)" in src
