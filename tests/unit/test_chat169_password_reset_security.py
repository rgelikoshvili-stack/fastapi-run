"""Chat169: reset-origin, hashing, and public error non-disclosure tests.

No production network, database, SMTP, Cloud Run or Cloud SQL access.
The disposable PG15/16 forced-RLS tests cover actual token issuance/replay.
"""
from email import message_from_string

import pytest
from starlette.requests import Request

from app.api import routes_auth


def synthetic_request(ip="127.0.0.191"):
    return Request({
        "type": "http", "method": "POST", "scheme": "http",
        "path": "/auth/forgot-password",
        "raw_path": b"/auth/forgot-password", "query_string": b"",
        "headers": [(b"host", b"attacker-controlled.example")],
        "client": (ip, 45678), "server": ("127.0.0.1", 80),
        "http_version": "1.1",
    })


def test_new_reset_token_is_digest_and_fits_existing_column():
    raw = "synthetic-high-entropy-reset-123-PRIVATE"
    stored = routes_auth._reset_token_storage_key(raw)
    assert stored.startswith("sha256:")
    assert len(stored) == len("sha256:") + 64 <= 128
    assert raw not in stored
    assert stored == routes_auth._reset_token_storage_key(raw)
    assert stored != routes_auth._reset_token_storage_key(raw + "x")


def test_configured_https_origin_override_does_not_read_request_host(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://app.bridge.example.test/")
    monkeypatch.setenv("PASSWORD_RESET_BASE_URL", "https://reset.bridge.example.test:443/")
    assert routes_auth._trusted_password_reset_base_url() == (
        "https://reset.bridge.example.test:443"
    )
    monkeypatch.delenv("PASSWORD_RESET_BASE_URL")
    assert routes_auth._trusted_password_reset_base_url() == (
        "https://app.bridge.example.test"
    )


@pytest.mark.parametrize("invalid", [
    "", "http://external.example.test", "javascript:alert(1)",
    "//bridge.example.test", "https://",
    "https://trusted.example.test@attacker.example.test",
    "https://bridge.example.test/private",
    "https://bridge.example.test/?token=unsafe",
    "https://bridge.example.test/#fragment",
    "https://bridge.example.test:bad",
    "https://bridge.example.test:65536",
    "https://bridge.example.test\\@attacker.example.test",
    "https://bridge%0a.example.test",
    "https://bridge.example.test\r\nInjected: yes",
])
def test_untrusted_or_ambiguous_reset_origins_rejected(monkeypatch, invalid):
    monkeypatch.setenv("PASSWORD_RESET_BASE_URL", invalid)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    # Blank override intentionally falls back to APP_BASE_URL, which is absent.
    with pytest.raises(ValueError):
        routes_auth._trusted_password_reset_base_url()


def test_plain_http_only_allowed_on_test_localhost(monkeypatch):
    monkeypatch.setenv("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.delenv("TEST_MODE", raising=False)
    with pytest.raises(ValueError):
        routes_auth._trusted_password_reset_base_url()
    monkeypatch.setenv("TEST_MODE", "1")
    assert routes_auth._trusted_password_reset_base_url() == "http://127.0.0.1:8000"
    monkeypatch.setenv("PASSWORD_RESET_BASE_URL", "http://external.example.test")
    with pytest.raises(ValueError):
        routes_auth._trusted_password_reset_base_url()


@pytest.mark.asyncio
async def test_missing_trusted_origin_never_mints_or_sends_reset_token(monkeypatch):
    monkeypatch.delenv("PASSWORD_RESET_BASE_URL", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)

    async def member(_email, _tenant):
        return {"id": 7, "tenant_id": "t_alpha"}

    async def no_db_access():
        raise AssertionError("No DB insert without trusted reset origin")

    mailed = []
    monkeypatch.setattr(routes_auth, "get_user", member)
    monkeypatch.setattr(routes_auth, "get_conn", no_db_access)
    monkeypatch.setattr(
        routes_auth, "_send_reset_email", lambda *args: mailed.append(args)
    )
    result = await routes_auth.auth_forgot_password(
        routes_auth.ForgotPasswordRequest(
            email="synthetic-member@example.test", tenant_id="t_alpha"
        ),
        synthetic_request("127.0.0.191"),
    )
    assert result["ok"] is True
    assert mailed == []


@pytest.mark.asyncio
async def test_forgot_error_and_unknown_account_same_public_response(monkeypatch):
    async def absent(_email, _tenant):
        return None

    async def db_error(_email, _tenant):
        raise RuntimeError("SYNTHETIC_DB_SECRET_SHOULD_NEVER_APPEAR")

    monkeypatch.setattr(routes_auth, "get_user", absent)
    missing = await routes_auth.auth_forgot_password(
        routes_auth.ForgotPasswordRequest(
            email="absent@example.test", tenant_id="t_alpha"
        ),
        synthetic_request("127.0.0.192"),
    )
    monkeypatch.setattr(routes_auth, "get_user", db_error)
    failed = await routes_auth.auth_forgot_password(
        routes_auth.ForgotPasswordRequest(
            email="exists@example.test", tenant_id="t_alpha"
        ),
        synthetic_request("127.0.0.193"),
    )
    assert missing == failed
    assert missing["ok"] is True
    assert "SYNTHETIC_DB_SECRET" not in repr(failed)


def test_html_email_escapes_query_delimiters_and_quotes(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def login(self, *_args):
            pass

        def sendmail(self, _from, _to, message):
            sent.append(message)

    monkeypatch.setenv("SMTP_USER", "synthetic@example.test")
    monkeypatch.setenv("SMTP_PASS", "synthetic-only-password")
    monkeypatch.setattr(routes_auth.smtplib, "SMTP_SSL", FakeSMTP)
    routes_auth._send_reset_email(
        "recipient@example.test",
        'https://bridge.example.test/reset?token=abc&tenant_id=t_"onmouseover="evil',
    )
    assert len(sent) == 1
    email_msg = message_from_string(sent[0])
    html = email_msg.get_payload(0).get_payload(decode=True).decode("utf-8")
    assert "&amp;" in html
    assert "&quot;" in html
    assert 'href="https://bridge.example.test/reset?' in html
    assert 'onmouseover="evil"' not in html
