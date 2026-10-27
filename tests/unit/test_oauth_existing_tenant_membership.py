"""OAuth tenant membership security regression tests (no DB or network)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import routes_oauth


class FakeProviderResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.fetchrow_calls = []
        self.execute = AsyncMock(side_effect=AssertionError("OAuth must never write to the database"))

    async def fetchrow(self, query, email, tenant_id):
        self.fetchrow_calls.append((email, tenant_id))
        return self.row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def provider_setup(monkeypatch, row, *, state_tenant="t_alpha", info=None):
    if info is None:
        info = {"email": "person@example.test", "email_verified": True, "name": "Person"}
    conn = FakeConnection(row)
    monkeypatch.setattr(routes_oauth, "_consume_state", AsyncMock(return_value=state_tenant))
    monkeypatch.setattr(routes_oauth, "get_conn", lambda: conn)
    monkeypatch.setattr(routes_oauth._http, "post", lambda *args, **kwargs:
                        FakeProviderResponse({"access_token": "synthetic-provider-token"}))
    monkeypatch.setattr(routes_oauth._http, "get", lambda *args, **kwargs:
                        FakeProviderResponse(info))
    monkeypatch.setattr(routes_oauth, "create_access_token", MagicMock(return_value="synthetic-access"))
    monkeypatch.setattr(routes_oauth, "create_refresh_token", MagicMock(return_value="synthetic-refresh"))
    return conn


def request():
    return SimpleNamespace(base_url="https://bridge.example.test/")


@pytest.mark.asyncio
async def test_unlisted_identity_cannot_join_tenant(monkeypatch):
    conn = provider_setup(monkeypatch, None)
    response = await routes_oauth.oauth_callback("google", request(), code="synthetic-code", state="synthetic-state")
    assert response.status_code == 403
    assert b"OAUTH_MEMBERSHIP_REQUIRED" in response.body
    assert conn.fetchrow_calls == [("person@example.test", "t_alpha")]
    conn.execute.assert_not_called()
    routes_oauth.create_access_token.assert_not_called()


@pytest.mark.asyncio
async def test_existing_member_uses_database_user_id_and_complete_refresh_claims(monkeypatch):
    conn = provider_setup(monkeypatch, {"id": 42, "role": "accountant"})
    response = await routes_oauth.oauth_callback("google", request(), code="synthetic-code", state="synthetic-state")
    assert response.status_code == 200
    expected_claims = {"sub": "42", "tenant_id": "t_alpha", "role": "accountant", "email": "person@example.test"}
    routes_oauth.create_access_token.assert_called_once_with(expected_claims)
    routes_oauth.create_refresh_token.assert_called_once_with(expected_claims)
    assert conn.fetchrow_calls == [("person@example.test", "t_alpha")]
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_unverified_google_email_cannot_authenticate(monkeypatch):
    conn = provider_setup(monkeypatch, {"id": 42, "role": "accountant"},
                          info={"email": "person@example.test", "email_verified": False})
    response = await routes_oauth.oauth_callback("google", request(), code="synthetic-code", state="synthetic-state")
    assert response.status_code == 403
    assert b"OAUTH_EMAIL_NOT_VERIFIED" in response.body
    assert conn.fetchrow_calls == []
    routes_oauth.create_access_token.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant_id", ["default", "", " t_alpha ", "DEFAULT"])
async def test_default_or_malformed_tenant_state_denied_before_provider_request(monkeypatch, tenant_id):
    conn = provider_setup(monkeypatch, {"id": 42, "role": "accountant"}, state_tenant=tenant_id)
    response = await routes_oauth.oauth_callback("google", request(), code="synthetic-code", state="synthetic-state")
    assert response.status_code == 403
    assert conn.fetchrow_calls == []
    routes_oauth.create_access_token.assert_not_called()


@pytest.mark.asyncio
async def test_oauth_display_name_is_html_escaped(monkeypatch):
    dangerous = '<img src=x onerror=alert(1)>'
    provider_setup(monkeypatch, {"id": 42, "role": "admin"},
                   info={"email": "person@example.test", "email_verified": True, "name": dangerous})
    response = await routes_oauth.oauth_callback("google", request(), code="synthetic-code", state="synthetic-state")
    assert response.status_code == 200
    assert dangerous.encode() not in response.body
    assert b"&lt;img" in response.body
