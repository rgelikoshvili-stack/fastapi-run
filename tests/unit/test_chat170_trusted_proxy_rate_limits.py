"""Chat170: proxy spoofing and shared IP identity regression proofs.

No real proxy, database, Redis, Cloud SQL, or network access.
Validates IP selection for both SlowAPI and Bridge Hub category middleware.
"""
from pathlib import Path

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.client_ip import (
    _trusted_proxy_networks, client_ip_for_rate_limit,
)
from app.api.middleware import rate_limit_middleware as rate_mw
from app.api.security import _real_ip
from app.api.services.rate_limiter_service import (
    InMemoryRateLimiterBackend, RateLimiterService,
)


def make_request(peer="198.51.100.11", path="/auth/login", xff=None, duplicate=False):
    headers = [(b"host", b"bridge.example.test")]
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("ascii")))
        if duplicate:
            headers.append((b"x-forwarded-for", b"198.51.100.199"))
    scope = {
        "type": "http", "method": "POST", "path": path,
        "raw_path": path.encode("ascii"), "query_string": b"",
        "headers": headers, "client": (peer, 54321),
        "server": ("127.0.0.1", 8000), "scheme": "http",
        "http_version": "1.1",
    }
    request = Request(scope)
    request.state.tenant_id = "t_alpha"
    request.state.user_id = None
    return request


@pytest.fixture(autouse=True)
def no_implicit_trust(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", raising=False)


@pytest.mark.parametrize("xff", [
    "203.0.113.77", "203.0.113.88, 198.51.100.45",
    "unknown", "not-an-ip", "1.2.3.4:123", " 203.0.113.77 ",
])
def test_direct_peer_ignores_untrusted_forwarded_header(xff):
    request = make_request(xff=xff)
    assert client_ip_for_rate_limit(request) == "198.51.100.11"
    assert _real_ip(request) == "198.51.100.11"
    assert rate_mw._get_client_ip(request) == "198.51.100.11"


def test_only_valid_explicit_proxy_can_supply_ip(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    verified_proxy = make_request(peer="192.0.2.10", xff="198.51.100.72")
    assert client_ip_for_rate_limit(verified_proxy) == "198.51.100.72"
    assert _real_ip(verified_proxy) == rate_mw._get_client_ip(verified_proxy)

    untrusted_peer = make_request(peer="198.51.100.11", xff="198.51.100.72")
    assert client_ip_for_rate_limit(untrusted_peer) == "198.51.100.11"


def test_trusted_proxy_chain_is_evaluated_from_right_not_left(monkeypatch):
    monkeypatch.setenv(
        "RATE_LIMIT_TRUSTED_PROXY_CIDRS", "192.0.2.0/24,2001:db8:10::/64"
    )
    request = make_request(
        peer="192.0.2.10",
        xff="203.0.113.99, 198.51.100.73, 192.0.2.20",
    )
    # 203.0.113.99 can be an attacker-supplied LEFTMOST spoof.
    assert client_ip_for_rate_limit(request) == "198.51.100.73"
    request_v6 = make_request(
        peer="2001:db8:10::1",
        xff="203.0.113.99, 2001:db8:beef::2, 2001:db8:10::2",
    )
    assert client_ip_for_rate_limit(request_v6) == "2001:db8:beef::2"


@pytest.mark.parametrize("xff", [
    "203.0.113.90, unknown",
    "203.0.113.90,,198.51.100.34",
    "203.0.113.90:1234",
    "[2001:db8::9]:1234",
    " " * 50,
    ",".join("198.51.100.11" for _ in range(17)),
    "198.51.100.1" * 100,
])
def test_malformed_trusted_proxy_chain_uses_socket_peer(monkeypatch, xff):
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    req = make_request(peer="192.0.2.15", xff=xff)
    assert client_ip_for_rate_limit(req) == "192.0.2.15"


def test_duplicate_forwarded_headers_use_socket_peer(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    request = make_request(peer="192.0.2.10", xff="198.51.100.11", duplicate=True)
    assert client_ip_for_rate_limit(request) == "192.0.2.10"


def test_all_forwarded_hops_claim_to_be_proxies_falls_back(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    request = make_request(peer="192.0.2.10", xff="192.0.2.20,192.0.2.30")
    assert client_ip_for_rate_limit(request) == "192.0.2.10"


@pytest.mark.parametrize("config", [
    "0.0.0.0/0", "::/0",
    "192.0.2.0/24,", ",192.0.2.0/24",
    "some-host.example.com", "192.0.2.999/24",
    "192.0.2.0/24, 0.0.0.0/0",
    ",".join("192.0.2.1" for _ in range(33)),
])
def test_invalid_trust_configuration_never_trusts_header(monkeypatch, config):
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", config)
    assert client_ip_for_rate_limit(
        make_request(peer="192.0.2.11", xff="198.51.100.74")
    ) == "192.0.2.11"


def test_config_changes_recomputed_without_restart(monkeypatch):
    req = make_request(peer="192.0.2.15", xff="198.51.100.77")
    assert client_ip_for_rate_limit(req) == "192.0.2.15"
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "192.0.2.15/32")
    assert client_ip_for_rate_limit(req) == "198.51.100.77"
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS")
    assert client_ip_for_rate_limit(req) == "192.0.2.15"


def test_missing_peer_cannot_use_forwarded_header(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    req = make_request(xff="203.0.113.11")
    req.scope["client"] = None
    assert client_ip_for_rate_limit(req) == "unknown"


async def ok_next(request):
    return JSONResponse({"ok": True}, status_code=200)


@pytest.mark.asyncio
async def test_auth_quota_cannot_be_bypassed_by_rotating_untrusted_xff(monkeypatch):
    service = RateLimiterService(InMemoryRateLimiterBackend())
    monkeypatch.setattr(rate_mw, "get_rate_limiter_service", lambda: service)
    for n in range(1, 13):
        req = make_request(xff=f"203.0.113.{n}")
        response = await rate_mw.rate_limit_middleware(req, ok_next)
        assert response.status_code == (200 if n <= 10 else 429)


@pytest.mark.asyncio
async def test_anonymous_non_auth_quota_cannot_rotate_untrusted_xff(monkeypatch):
    service = RateLimiterService(InMemoryRateLimiterBackend())
    monkeypatch.setattr(rate_mw, "get_rate_limiter_service", lambda: service)
    for n in range(1, 33):
        req = make_request(path="/posting/apply/123", xff=f"203.0.113.{n}")
        response = await rate_mw.rate_limit_middleware(req, ok_next)
        assert response.status_code == (200 if n <= 30 else 429)


@pytest.mark.asyncio
async def test_trusted_proxy_provides_distinct_client_quotas(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "192.0.2.10/32")
    service = RateLimiterService(InMemoryRateLimiterBackend())
    monkeypatch.setattr(rate_mw, "get_rate_limiter_service", lambda: service)
    for n in range(11):
        req = make_request(peer="192.0.2.10", xff="198.51.100.21")
        response = await rate_mw.rate_limit_middleware(req, ok_next)
        assert response.status_code == (200 if n < 10 else 429)
    other = make_request(peer="192.0.2.10", xff="198.51.100.22")
    assert (await rate_mw.rate_limit_middleware(other, ok_next)).status_code == 200


def test_all_entrypoints_disable_implicit_proxy_header_rewrite():
    assert "--no-proxy-headers" in Path("Dockerfile").read_text(encoding="utf-8-sig")
    assert "--no-proxy-headers" in Path("Procfile").read_text(encoding="utf-8")
