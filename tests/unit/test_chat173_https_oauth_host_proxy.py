"""Chat173: synthetic Host / forwarded-proto / OAuth callback protections.

No external requests, SQL or real OAuth credentials. Production is not touched.
"""
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.api import routes_oauth
from app.api.trusted_request_origin import (
    configured_oauth_origin, trusted_https_redirect_target,
    trusted_public_origin,
)


@pytest.fixture(autouse=True)
def no_implicit_proxy_trust(monkeypatch):
    for name in (
        "OAUTH_REDIRECT_BASE_URL", "APP_BASE_URL",
        "HTTPS_REDIRECT_ENABLED", "HTTPS_REDIRECT_TRUSTED_PROXY_CIDRS",
        "TEST_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")


def request(
    *, host="bridge.example.test", xfp=None, peer="198.51.100.11",
    duplicate_xfp=False, duplicate_host=False, path="/auth/login",
    query=b"next=local", raw_path=None,
):
    headers = [(b"host", host.encode("ascii"))]
    if duplicate_host:
        headers.append((b"host", b"evil.example.test"))
    if xfp is not None:
        headers.append((b"x-forwarded-proto", xfp.encode("ascii")))
        if duplicate_xfp:
            headers.append((b"x-forwarded-proto", b"https"))
    scope = {
        "type": "http", "method": "POST", "scheme": "http",
        "http_version": "1.1", "path": path,
        "raw_path": raw_path if raw_path is not None else path.encode("ascii"),
        "query_string": query,
        "headers": headers, "client": (peer, 40173),
        "server": ("127.0.0.1", 8080),
    }
    return Request(scope)


@pytest.mark.parametrize("candidate,expected", [
    ("https://bridge.example.test", "https://bridge.example.test"),
    ("https://BRIDGE.EXAMPLE.TEST/", "https://bridge.example.test"),
    ("https://bridge.example.test:443/", "https://bridge.example.test:443"),
    ("https://[2001:db8::1]/", "https://[2001:db8::1]"),
    ("https://127.0.0.1:8443", "https://127.0.0.1:8443"),
])
def test_only_explicit_valid_public_origins_are_accepted(candidate, expected):
    assert trusted_public_origin(candidate) == expected


@pytest.mark.parametrize("candidate", [
    "", "https://", "//evil.example", "javascript:alert(1)",
    "http://bridge.example.test", "https://user:pass@bridge.example.test",
    "https://bridge.example.test@evil.example",
    "https://bridge.example.test/path", "https://bridge.example.test/#x",
    "https://bridge.example.test/?token=secret",
    "https://bridge.example.test:invalid",
    "https://bridge.example.test:65536",
    "https://bridge%0a.example.test", "https://bad_host.example",
    "https://bridge.example.test\\@evil.example",
    "https://bridge.example.test\r\nX-Injected: yep",
    " https://bridge.example.test ",
    "https://bridge.example.test.",
])
def test_unsafe_origins_rejected(candidate):
    with pytest.raises(ValueError):
        trusted_public_origin(candidate)


def test_plain_http_only_explicit_local_test_mode_not_production(monkeypatch):
    with pytest.raises(ValueError):
        trusted_public_origin("http://localhost:8000")
    monkeypatch.setenv("TEST_MODE", "1")
    assert trusted_public_origin("http://localhost:8000") == "http://localhost:8000"
    with pytest.raises(ValueError):
        trusted_public_origin("http://bridge.example.test")
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError):
        trusted_public_origin("http://localhost:8000")


def test_oauth_origin_requires_config_and_invalid_override_fails_closed(monkeypatch):
    with pytest.raises(ValueError):
        configured_oauth_origin()
    monkeypatch.setenv("APP_BASE_URL", "https://bridge.example.test")
    assert configured_oauth_origin() == "https://bridge.example.test"
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "https://sso.example.test/")
    assert configured_oauth_origin() == "https://sso.example.test"
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "https://evil.example.test/path")
    with pytest.raises(ValueError):
        configured_oauth_origin()


@pytest.mark.asyncio
async def test_oauth_login_missing_origin_does_not_issue_state(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "synthetic-client-only")
    issue = AsyncMock(side_effect=AssertionError("must not issue state"))
    monkeypatch.setattr(routes_oauth, "_issue_state", issue)
    forged = request(host="evil.example.test", xfp="https")
    result = await routes_oauth.oauth_login("google", forged, tenant_id="t_alpha")
    assert result.status_code == 503
    assert b"OAUTH_ORIGIN_UNTRUSTED" in result.body
    issue.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_login_ignores_host_and_forwarded_headers(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "synthetic-client-only")
    monkeypatch.setenv("APP_BASE_URL", "https://bridge.example.test")
    issue = AsyncMock(return_value="synthetic-state-173")
    monkeypatch.setattr(routes_oauth, "_issue_state", issue)
    forged = request(host="malicious-attacker.example", xfp="http")
    result = await routes_oauth.oauth_login("google", forged, tenant_id="t_alpha")
    assert result.status_code == 307
    location = result.headers["location"]
    assert location.startswith("https://accounts.google.com/")
    assert "malicious-attacker" not in location
    qs = parse_qs(urlsplit(location).query)
    assert qs["redirect_uri"] == [
        "https://bridge.example.test/auth/oauth/google/callback"
    ]
    assert qs["state"] == ["synthetic-state-173"]
    issue.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_callback_invalid_origin_does_not_consume_state(monkeypatch):
    consume = AsyncMock(side_effect=AssertionError("must not consume state"))
    monkeypatch.setattr(routes_oauth, "_consume_state", consume)
    result = await routes_oauth.oauth_callback(
        "google", request(host="evil.example.test"),
        code="synthetic-code", state="synthetic-state",
    )
    assert result.status_code == 503
    assert b"OAUTH_ORIGIN_UNTRUSTED" in result.body
    consume.assert_not_awaited()


def test_https_redirect_is_disabled_by_default_despite_header_spoofing(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://bridge.example.test")
    forged = request(xfp="http", peer="192.0.2.10")
    assert trusted_https_redirect_target(forged) is None


def _enable_redirect(monkeypatch):
    monkeypatch.setenv("HTTPS_REDIRECT_ENABLED", "1")
    monkeypatch.setenv("HTTPS_REDIRECT_TRUSTED_PROXY_CIDRS", "192.0.2.10/32")
    monkeypatch.setenv("APP_BASE_URL", "https://bridge.example.test")


def test_verified_proxy_redirect_uses_canonical_origin_only(monkeypatch):
    _enable_redirect(monkeypatch)
    valid = request(xfp="http", peer="192.0.2.10",
                    path="/documents/upload", query=b"next=local")
    assert trusted_https_redirect_target(valid) == (
        "https://bridge.example.test/documents/upload?next=local"
    )
    assert trusted_https_redirect_target(request(
        xfp="http", peer="192.0.2.10", path="/health"
    )) is None


def test_host_poisoning_or_untrusted_peer_never_triggers_redirect(monkeypatch):
    _enable_redirect(monkeypatch)
    assert trusted_https_redirect_target(request(
        host="attacker.example.test", xfp="http", peer="192.0.2.10"
    )) is None
    assert trusted_https_redirect_target(request(
        host="bridge.example.test", xfp="http", peer="198.51.100.11"
    )) is None
    assert trusted_https_redirect_target(request(
        host="bridge.example.test", xfp="http", peer="192.0.2.10",
        duplicate_host=True
    )) is None


@pytest.mark.parametrize("xfp", [
    "https", "HTTP", "http,https", "https,http", "ftp", "http http",
])
def test_noncanonical_forwarded_proto_is_ignored(monkeypatch, xfp):
    _enable_redirect(monkeypatch)
    assert trusted_https_redirect_target(request(
        xfp=xfp, peer="192.0.2.10",
    )) is None


def test_duplicate_forwarded_proto_is_ignored(monkeypatch):
    _enable_redirect(monkeypatch)
    assert trusted_https_redirect_target(request(
        xfp="http", peer="192.0.2.10", duplicate_xfp=True
    )) is None


@pytest.mark.parametrize("cidrs", ["", "0.0.0.0/0", "not-an-ip"])
def test_missing_or_invalid_proxy_allowlist_fails_closed(monkeypatch, cidrs):
    _enable_redirect(monkeypatch)
    monkeypatch.setenv("HTTPS_REDIRECT_TRUSTED_PROXY_CIDRS", cidrs)
    assert trusted_https_redirect_target(request(
        xfp="http", peer="192.0.2.10",
    )) is None


def test_missing_or_misconfigured_app_origin_fails_closed(monkeypatch):
    _enable_redirect(monkeypatch)
    monkeypatch.setenv("APP_BASE_URL", "http://evil.example.test")
    assert trusted_https_redirect_target(request(
        xfp="http", peer="192.0.2.10",
    )) is None


@pytest.mark.parametrize("raw_path,query", [
    (b"//evil.example", b"x=1"),
    (b"/safe\r\nLocation: https://evil.example", b"x=1"),
    (b"/a#b", b"x=1"),
    (b"/safe", b"x=1\r\nBad: yes"),
    (b"/safe", b"#fragment"),
])
def test_redirect_rejects_malformed_paths_and_queries(monkeypatch, raw_path, query):
    _enable_redirect(monkeypatch)
    assert trusted_https_redirect_target(request(
        xfp="http", peer="192.0.2.10", raw_path=raw_path, query=query,
    )) is None


def test_main_no_longer_redirects_using_untrusted_request_url():
    from pathlib import Path
    source = Path("main.py").read_text(encoding="utf-8")
    assert "trusted_https_redirect_target(request)" in source
    assert 'request.headers.get("X-Forwarded-Proto"' not in source
    assert 'str(request.url).replace("http://", "https://"' not in source
