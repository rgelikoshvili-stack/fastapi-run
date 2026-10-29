"""Chat174: global Host allowlist regression contract, localhost synthetic only.

No Production config changes. A strict Host policy must be deliberately
enabled with an audited set of actual ingress, custom domain and probe hosts.
"""
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

from app.api.trusted_host_guard import (
    _canonical_authority,
    _parse_explicit_hosts,
    trusted_host_decision,
    trusted_host_guard_middleware,
)


@pytest.fixture(autouse=True)
def unset_host_gate(monkeypatch):
    monkeypatch.delenv("BRIDGE_TRUSTED_HOSTS_ENFORCE", raising=False)
    monkeypatch.delenv("BRIDGE_TRUSTED_HOSTS", raising=False)


def _request(hosts=(), other_headers=()):
    headers = [(b"host", item) for item in hosts]
    headers.extend(other_headers)
    return StarletteRequest({
        "type": "http", "method": "GET", "scheme": "http",
        "path": "/health", "raw_path": b"/health",
        "query_string": b"", "headers": headers,
        "http_version": "1.1", "client": ("198.51.100.9", 5174),
        "server": ("127.0.0.1", 8080),
    })


def _enable(monkeypatch, allowlist="bridge.example.test,internal.run.app:8080"):
    monkeypatch.setenv("BRIDGE_TRUSTED_HOSTS_ENFORCE", "1")
    monkeypatch.setenv("BRIDGE_TRUSTED_HOSTS", allowlist)


def test_disabled_gate_preserves_legacy_behavior():
    assert trusted_host_decision(_request([b"attacker.example.test"])) == (
        True, 200, ""
    )


@pytest.mark.parametrize("host,canon", [
    ("BRIDGE.EXAMPLE.TEST", "bridge.example.test"),
    ("bridge.example.test:443", "bridge.example.test:443"),
    ("127.0.0.1:8080", "127.0.0.1:8080"),
    ("[2001:db8::1]:8443", "[2001:db8::1]:8443"),
    ("localhost", "localhost"),
])
def test_canonical_authority_accepts_literal_explicit_hosts(host, canon):
    assert _canonical_authority(host) == canon


@pytest.mark.parametrize("bad", [
    "", "*", "*.bridge.example.test", "http://bridge.example.test",
    "bridge.example.test/", "bridge.example.test?x=1",
    "bridge.example.test#frag", "bridge.example.test@evil.example",
    "bridge.example.test\evil.example", "bridge.example.test:65536",
    "bridge.example.test:0", "bridge.example.test:0443",
    "bridge.example.test:bad", "bridge..example.test",
    "bridge.example.test.", "bridge_example.test",
    "bridge.example.test,evil.example.test",
    " bridge.example.test", "bridge.example.test ",
    "bridge.example.test\r\nX-Injected: 1",
    "[2001:db8::1", "2001:db8::1",
])
def test_invalid_host_authority_refused(bad):
    with pytest.raises(ValueError):
        _canonical_authority(bad)


@pytest.mark.parametrize("bad", [
    "", ",", "bridge.example.test,",
    "bridge.example.test,bridge.example.test",
    "bridge.example.test,BRIDGE.EXAMPLE.TEST",
    "*", "*.example.test", "https://bridge.example.test",
    "bridge.example.test:65536",
    ",".join(f"host{i}.example.test" for i in range(33)),
])
def test_invalid_or_overbroad_allowlist_rejected(bad):
    with pytest.raises(ValueError):
        _parse_explicit_hosts(bad)


@pytest.mark.parametrize("invalid_flag", ["true", "TRUE", "false", "on", "yes", "2"])
def test_mistyped_activation_flag_fails_closed(monkeypatch, invalid_flag):
    monkeypatch.setenv("BRIDGE_TRUSTED_HOSTS_ENFORCE", invalid_flag)
    monkeypatch.setenv("BRIDGE_TRUSTED_HOSTS", "bridge.example.test")
    assert trusted_host_decision(_request([b"bridge.example.test"])) == (
        False, 503, "HOST_POLICY_UNAVAILABLE"
    )


def test_host_gate_denies_missing_policy_not_fail_open(monkeypatch):
    monkeypatch.setenv("BRIDGE_TRUSTED_HOSTS_ENFORCE", "1")
    assert trusted_host_decision(_request([b"bridge.example.test"])) == (
        False, 503, "HOST_POLICY_UNAVAILABLE"
    )
    monkeypatch.setenv("BRIDGE_TRUSTED_HOSTS", "*.example.test")
    assert trusted_host_decision(_request([b"bridge.example.test"])) == (
        False, 503, "HOST_POLICY_UNAVAILABLE"
    )


@pytest.mark.parametrize("host", [
    b"bridge.example.test", b"BRIDGE.EXAMPLE.TEST",
    b"internal.run.app:8080",
])
def test_exact_authorized_host_allowed(monkeypatch, host):
    _enable(monkeypatch)
    assert trusted_host_decision(_request([host])) == (True, 200, "")


@pytest.mark.parametrize("hosts", [
    [],
    [b"attacker.example.test"],
    [b"bridge.example.test.evil.example"],
    [b"bridge.example.test:444"],
    [b"bridge.example.test", b"attacker.example.test"],
    [b"bridge.example.test", b"bridge.example.test"],
    [b"bridge.example.test\x00evil"],
    [b"\xff"],
])
def test_invalid_duplicate_or_unlisted_host_denied(monkeypatch, hosts):
    _enable(monkeypatch)
    assert trusted_host_decision(_request(hosts)) == (
        False, 400, "HOST_UNTRUSTED"
    )


def test_x_forwarded_host_cannot_override_actual_host(monkeypatch):
    _enable(monkeypatch)
    headers = [(b"x-forwarded-host", b"bridge.example.test")]
    assert trusted_host_decision(_request(
        [b"attacker.example.test"], headers
    )) == (False, 400, "HOST_UNTRUSTED")
    assert trusted_host_decision(_request(
        [b"bridge.example.test"],
        [(b"x-forwarded-host", b"attacker.example.test")],
    )) == (True, 200, "")


def test_allowlist_change_rechecked_and_no_wildcard_cache(monkeypatch):
    _enable(monkeypatch, "bridge.example.test")
    req = _request([b"internal.run.app"])
    assert trusted_host_decision(req)[0] is False
    monkeypatch.setenv("BRIDGE_TRUSTED_HOSTS", "internal.run.app")
    assert trusted_host_decision(req)[0] is True
    monkeypatch.setenv("BRIDGE_TRUSTED_HOSTS", "bridge.example.test")
    assert trusted_host_decision(req)[0] is False


def _app_with_guard():
    app = FastAPI()
    called = {"value": 0}

    @app.get("/health")
    async def health():
        called["value"] += 1
        return {"ok": True}

    app.middleware("http")(trusted_host_guard_middleware)
    return app, called


def test_real_middleware_denies_before_health_handler(monkeypatch):
    _enable(monkeypatch, "bridge.example.test")
    app, called = _app_with_guard()
    with TestClient(app) as client:
        denied = client.get("/health", headers={"host": "attacker.example.test"})
        accepted = client.get("/health", headers={"host": "bridge.example.test"})
    assert denied.status_code == 400
    assert denied.json()["error"] == {
        "code": "HOST_UNTRUSTED", "details": None,
    }
    assert denied.headers["Cache-Control"] == "no-store"
    assert "attacker.example.test" not in denied.text
    assert accepted.status_code == 200
    assert called["value"] == 1


def test_invalid_config_middleware_returns_503_not_unfiltered_200(monkeypatch):
    _enable(monkeypatch, "*.example.test")
    app, called = _app_with_guard()
    with TestClient(app) as client:
        response = client.get("/health", headers={"host": "bridge.example.test"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "HOST_POLICY_UNAVAILABLE"
    assert called["value"] == 0


def test_main_registers_guard_as_outermost_before_sensitive_handlers():
    # Inspect the wiring without importing main.py's background startup loops.
    source = Path("main.py").read_text(encoding="utf-8")
    last = source.index('app.middleware("http")(trusted_host_guard_middleware)')
    for existing in (
        'app.middleware("http")(tenant_middleware)',
        'app.middleware("http")(auth_middleware)',
        'app.middleware("http")(rbac_middleware)',
        'app.middleware("http")(rate_limit_middleware)',
        'async def https_redirect(',
        'async def prometheus_middleware(',
    ):
        assert source.index(existing) < last
