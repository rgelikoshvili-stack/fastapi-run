"""Chat172: true two-client SlowAPI decorator quota on disposable Redis 7.

Runs ONLY with CHAT171_TEST_REDIS_URL set to local 127.0.0.1:56379/14.
No production Redis or other network. Never invokes FLUSHDB/FLUSHALL.
"""
import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import redis
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.security import rate_limit_exceeded_handler
from app.api.slowapi_shared_guard import (
    GuardedSlowAPILimiter,
    SharedRateLimitStoreUnavailable,
    shared_rate_limit_unavailable_handler,
)


def disposable_dsn():
    url = os.environ.get("CHAT171_TEST_REDIS_URL", "")
    if not url:
        pytest.skip("Requires dedicated disposable Redis test container")
    p = urlsplit(url)
    if (
        p.scheme != "redis" or p.hostname != "127.0.0.1"
        or p.port != 56379 or p.path != "/14"
        or p.username or p.password or p.query or p.fragment
    ):
        raise RuntimeError("Refusing to connect SlowAPI test to non-disposable Redis")
    return url


def app_with_limiter(limiter, path):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(
        SharedRateLimitStoreUnavailable, shared_rate_limit_unavailable_handler
    )
    app.add_middleware(SlowAPIMiddleware)

    @app.get(path)
    @limiter.limit("3/minute")
    async def check(request: Request):
        return {"ok": True}
    return app


def test_two_independent_slowapi_instances_share_decorator_quota(monkeypatch):
    dsn = disposable_dsn()
    monkeypatch.setenv("ENVIRONMENT", "production")
    prefix = "chat172-synthetic-" + uuid4().hex
    path = "/chat172-" + uuid4().hex
    probe = redis.Redis.from_url(dsn)
    assert probe.ping() is True

    limiter_a = GuardedSlowAPILimiter(
        key_func=lambda request: request.client.host,
        storage_uri=dsn, key_prefix=prefix,
        in_memory_fallback_enabled=False,
        swallow_errors=False,
    )
    limiter_b = GuardedSlowAPILimiter(
        key_func=lambda request: request.client.host,
        storage_uri=dsn, key_prefix=prefix,
        in_memory_fallback_enabled=False,
        swallow_errors=False,
    )
    assert limiter_a._storage is not limiter_b._storage
    assert not limiter_a._in_memory_fallback_enabled
    assert not limiter_b._in_memory_fallback_enabled
    try:
        with TestClient(app_with_limiter(limiter_a, path)) as a, TestClient(
            app_with_limiter(limiter_b, path)
        ) as b:
            statuses = [
                a.get(path).status_code,
                b.get(path).status_code,
                a.get(path).status_code,
                b.get(path).status_code,
            ]
        assert statuses == [200, 200, 200, 429]
    finally:
        # Only keys associated with this one test's random namespace.
        keys = [
            key for key in probe.scan_iter(match="*chat172-synthetic-*")
            if prefix.encode() in key
        ]
        if keys:
            probe.delete(*keys)
        probe.close()
