"""Chat171: strict multi-replica quota dependency, safe outage and recovery.

All tests use synthetic mocks or local memory. No Redis/network/Cloud SQL.
Actual independent Redis connections are tested by the disposable integration CI.
"""
import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api.middleware import rate_limit_middleware as rate_mw
from app.api.services import rate_limiter_service as rls
from app.api.services.rate_limit_policy_service import (
    RateLimitCategory, classify_rate_limit_category, get_rate_limit_rule,
)


def _rule():
    return get_rate_limit_rule(RateLimitCategory.AUTH)


@pytest.fixture(autouse=True)
def reset_singleton():
    rls._reset_service_singleton()
    yield
    rls._reset_service_singleton()


def test_production_missing_redis_denies_even_when_test_mode_set(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    limiter = rls.get_rate_limiter_service()
    assert limiter.backend_name == "UnavailableRateLimiterBackend"
    result = limiter.check_limit("rl:auth:anon:one", _rule())
    assert result.allowed is False
    assert result.backend == "shared_unavailable"
    assert result.error_code == "RATE_LIMIT_BACKEND_UNAVAILABLE"
    assert result.retry_after_seconds > 0
    assert "REDIS_URL" not in repr(result)


def test_explicit_shared_mode_blocks_staging_without_redis(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("RATE_LIMIT_REQUIRE_SHARED", "1")
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    result = rls.get_rate_limiter_service().check_limit("rl:auth:one", _rule())
    assert result.allowed is False
    assert result.error_code == "RATE_LIMIT_BACKEND_UNAVAILABLE"


def test_local_development_memory_remains_available(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("RATE_LIMIT_REQUIRE_SHARED", raising=False)
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    result = rls.get_rate_limiter_service().check_limit("rl:auth:local", _rule())
    assert result.allowed is True
    assert result.backend == "memory_fallback"


class BrokenRedis:
    def eval(self, *_args):
        raise ConnectionError("SYNTHETIC_REDIS_URL_AND_CREDENTIALS_NOT_LOGGED")

    def delete(self, *_args):
        raise ConnectionError("SYNTHETIC")


class HealthyRedis:
    def __init__(self):
        self.calls = 0

    def eval(self, lua, keys_count, key, ttl):
        assert "redis.call('INCR', KEYS[1])" in lua
        assert "redis.call('EXPIRE', KEYS[1]" in lua
        assert keys_count == 1 and ttl >= 1
        self.calls += 1
        return [self.calls, int(ttl)]

    def delete(self, *_args):
        return 1


def test_production_redis_outage_fail_closed_without_resetting_counters(monkeypatch):
    limiter = rls.RedisRateLimiterBackend(
        "redis://127.0.0.1:1/0", require_shared=True,
    )
    healthy = HealthyRedis()
    limiter._client = healthy
    rule = _rule()
    first = limiter.check("rl:auth:anon:shared", rule)
    assert first.allowed and first.backend == "redis"

    limiter._client = BrokenRedis()
    down_a = limiter.check("rl:auth:anon:shared", rule)
    down_b = limiter.check("rl:auth:anon:shared", rule)
    assert not down_a.allowed and not down_b.allowed
    assert down_a.error_code == down_b.error_code == "RATE_LIMIT_BACKEND_UNAVAILABLE"
    assert limiter._fallback is None

    # On recovery, counter is not silently restarted in a new local silo.
    limiter._client = healthy
    restored = limiter.check("rl:auth:anon:shared", rule)
    assert restored.backend == "redis" and restored.allowed
    assert restored.remaining == rule.limit - 2


def test_production_broken_redis_reset_is_not_silent():
    limiter = rls.RedisRateLimiterBackend(
        "redis://127.0.0.1:1/0", require_shared=True,
    )
    limiter._client = BrokenRedis()
    with pytest.raises(RuntimeError, match="Shared quota reset unavailable"):
        limiter.reset("rl:auth:synthetic:one")


def test_strict_backend_init_failure_does_not_use_memory(monkeypatch):
    def broken_backend(*_args, **_kwargs):
        raise ValueError("synthetic")

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(rls, "RedisRateLimiterBackend", broken_backend)
    service = rls.get_rate_limiter_service()
    assert service.backend_name == "UnavailableRateLimiterBackend"
    assert not service.check_limit("rl:auth:anon", _rule()).allowed


def test_atomic_lua_contains_increment_and_ttl_in_same_script():
    lua = rls._REDIS_FIXED_WINDOW_LUA
    assert "redis.call('INCR', KEYS[1])" in lua
    assert "redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))" in lua
    assert "redis.call('TTL', KEYS[1])" in lua


@pytest.mark.parametrize("path", [
    "/auth/forgot-password", "/auth/reset-password", "/auth/change-password",
])
def test_password_recovery_paths_are_auth_category(path):
    assert classify_rate_limit_category(path, "POST") == RateLimitCategory.AUTH


def _request(path="/auth/login"):
    return Request({
        "type": "http", "method": "POST", "path": path,
        "raw_path": path.encode("ascii"), "headers": [],
        "query_string": b"", "client": ("127.0.0.171", 17171),
        "server": ("127.0.0.1", 8000), "scheme": "http",
        "http_version": "1.1",
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/auth/login", "/auth/forgot-password", "/posting/apply/1"])
async def test_unavailable_shared_limiter_yields_503_not_429(monkeypatch, path):
    async def should_never_run(_request):
        raise AssertionError("Protected request must never reach handler")

    monkeypatch.setattr(
        rate_mw, "get_rate_limiter_service",
        lambda: rls.RateLimiterService(rls.UnavailableRateLimiterBackend()),
    )
    response = await rate_mw.rate_limit_middleware(_request(path), should_never_run)
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["ok"] is False
    assert body["error"]["code"] == "RATE_LIMIT_BACKEND_UNAVAILABLE"
    assert body["error"]["details"] is None
    assert response.headers["Retry-After"] == "5"
    assert response.headers["Cache-Control"] == "no-store"
    assert "REDIS_URL" not in response.body.decode()
