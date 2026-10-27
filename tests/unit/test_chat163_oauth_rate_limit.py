"""Chat163: authentication/OAuth rate limits reject untrusted quota partitions.

No real external IP, Redis, OAuth provider, or production database is used.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

from app.api.middleware import rate_limit_middleware as rate_module
from app.api.services.rate_limit_policy_service import (
    RateLimitCategory, classify_rate_limit_category, get_rate_limit_rule,
)
from app.api.services.rate_limiter_service import (
    InMemoryRateLimiterBackend, RateLimiterService,
)


def mock_request(path="/auth/oauth/google/login", tenant="t_alpha", user="u_alpha",
                 xff="203.0.113.1", peer="198.51.100.1", method="GET"):
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        method=method,
        state=SimpleNamespace(tenant_id=tenant, user_id=user),
        client=SimpleNamespace(host=peer) if peer is not None else None,
        headers={"X-Tenant-ID": tenant, "X-Forwarded-For": xff},
    )


async def ok_next(request):
    return JSONResponse({"ok": True})


@pytest.mark.parametrize("path,method", [
    ("/auth/oauth/google/login", "GET"),
    ("/auth/oauth/google/callback", "GET"),
    ("/auth/oauth/microsoft/login", "GET"),
    ("/auth/oauth/microsoft/callback", "GET"),
    ("/auth/oauth/providers", "GET"),
    ("/auth/login", "POST"),
    ("/auth/refresh", "POST"),
])
def test_oauth_endpoints_use_strict_auth_category(path, method):
    assert classify_rate_limit_category(path, method) == RateLimitCategory.AUTH
    assert get_rate_limit_rule(RateLimitCategory.AUTH).limit == 10


@pytest.mark.asyncio
async def test_rotating_untrusted_tenant_and_forwarded_ip_cannot_reset_quota(monkeypatch):
    svc = RateLimiterService(InMemoryRateLimiterBackend())
    monkeypatch.setattr(rate_module, "get_rate_limiter_service", lambda: svc)

    for n in range(10):
        req = mock_request(
            path="/auth/oauth/google/login" if n % 2 == 0 else "/auth/oauth/google/callback",
            tenant=f"spoof_tenant_{n}",
            user=f"arbitrary_user_{n}",
            xff=f"192.0.2.{n+1}",
        )
        response = await rate_module.rate_limit_middleware(req, ok_next)
        assert response.status_code == 200

    blocked = await rate_module.rate_limit_middleware(
        mock_request(tenant="brand_new_tenant", xff="192.0.2.200"),
        ok_next,
    )
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    assert json.loads(blocked.body)["error"]["code"] == "AUTH_RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_new_peer_gets_independent_quota(monkeypatch):
    svc = RateLimiterService(InMemoryRateLimiterBackend())
    monkeypatch.setattr(rate_module, "get_rate_limiter_service", lambda: svc)
    for _ in range(10):
        assert (await rate_module.rate_limit_middleware(
            mock_request(peer="198.51.100.1"), ok_next
        )).status_code == 200

    assert (await rate_module.rate_limit_middleware(
        mock_request(peer="198.51.100.2"), ok_next
    )).status_code == 200


@pytest.mark.asyncio
async def test_no_peer_ignores_untrusted_forwarded_ip(monkeypatch):
    svc = RateLimiterService(InMemoryRateLimiterBackend())
    monkeypatch.setattr(rate_module, "get_rate_limiter_service", lambda: svc)
    for i in range(10):
        assert (await rate_module.rate_limit_middleware(
            mock_request(peer=None, xff=f"203.0.113.{i+1}"), ok_next
        )).status_code == 200

    assert (await rate_module.rate_limit_middleware(
        mock_request(peer=None, xff="203.0.113.254"), ok_next
    )).status_code == 429
