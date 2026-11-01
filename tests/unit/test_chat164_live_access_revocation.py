"""Chat164: access JWT revalidation / revocation, synthetic only.

Before release the flag is intentionally off. These tests enable the flag
explicitly and never access any production service, user or credentials.
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse

from app.api import db
from app.api.middleware import auth_middleware as auth_module
from app.api.middleware import rbac_middleware as rbac_module
from app.api.services import auth_service


def claims():
    return {
        "sub": "42",
        "email": "member@example.test",
        "role": "accountant",
        "tenant_id": "t_alpha",
        "type": "access",
    }


def member_row():
    return {
        "id": 42,
        "email": "member@example.test",
        "role": "accountant",
        "tenant_id": "t_alpha",
    }


@pytest.fixture
def fake_db(monkeypatch):
    state = {"row": member_row(), "tenant": None, "queries": [], "fail": False}

    @asynccontextmanager
    async def fake_tenant(tenant):
        state["tenant"] = tenant
        yield

    class FakeConn:
        async def fetchrow(self, statement, *args):
            state["queries"].append((statement, args))
            if state["fail"]:
                raise ConnectionError("synthetic database unavailable")
            return state["row"]

    @asynccontextmanager
    async def fake_get_conn():
        yield FakeConn()

    monkeypatch.setattr(db, "tenant_db_context", fake_tenant)
    monkeypatch.setattr(db, "get_conn", fake_get_conn)
    monkeypatch.setattr(db, "_q", lambda q: q)
    return state


@pytest.mark.asyncio
async def test_live_member_allows_signed_claim_and_queries_active_tenant(fake_db):
    assert await auth_service.verify_live_access_membership(claims()) is True
    sql, args = fake_db["queries"][0]
    assert "is_active=TRUE" in sql
    assert args == (42, "t_alpha")
    assert fake_db["tenant"] == "t_alpha"


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [
    None,
    {"id": 42, "email": "member@example.test", "role": "viewer", "tenant_id": "t_alpha"},
    {"id": 42, "email": "member@example.test", "role": "accountant", "tenant_id": "t_beta"},
    {"id": 42, "email": "changed@example.test", "role": "accountant", "tenant_id": "t_alpha"},
])
async def test_revoked_or_modified_member_denied(fake_db, row):
    fake_db["row"] = row
    assert await auth_service.verify_live_access_membership(claims()) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("modified", [
    {"sub": "member@example.test"},
    {"sub": "0"},
    {"sub": "-2"},
    {"tenant_id": "default"},
    {"tenant_id": " t_alpha "},
    {"role": ""},
    {"email": ""},
])
async def test_malformed_access_claims_denied_before_db(fake_db, modified):
    assert await auth_service.verify_live_access_membership({**claims(), **modified}) is False
    assert fake_db["queries"] == []


@pytest.mark.asyncio
async def test_db_outage_is_not_an_authorization_success(fake_db):
    fake_db["fail"] = True
    with pytest.raises(ConnectionError):
        await auth_service.verify_live_access_membership(claims())


def req(path="/posting/apply/10", token="synthetic-access-token", query=False):
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        method="GET",
        headers={} if query else {"Authorization": "Bearer " + token},
        query_params={"token": token} if query else {},
        state=SimpleNamespace(tenant_id="spoofed-header-tenant"),
    )


@pytest.mark.asyncio
async def test_private_route_allows_current_member_with_verified_tenant(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(auth_module, "verify_token", lambda value, expected_type: claims())
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_module, "verify_live_access_membership", check)

    async def next_handler(request):
        assert request.state.authenticated is True
        assert request.state.tenant_id == "t_alpha"
        assert db.require_current_tenant_id() == "t_alpha"
        return JSONResponse({"ok": True})

    response = await auth_module.auth_middleware(req(), next_handler)
    assert response.status_code == 200
    check.assert_awaited_once()
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("path,query", [
    ("/posting/apply/10", False),
    ("/api/documents/download/10", True),
    ("/auth/company-profile", False),
    ("/auth/signature", False),
    ("/auth/me", False),
])
async def test_revoked_member_denied_before_any_business_handler(monkeypatch, path, query):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(auth_module, "verify_token", lambda value, expected_type: claims())
    check = AsyncMock(return_value=False)
    monkeypatch.setattr(auth_module, "verify_live_access_membership", check)
    final = AsyncMock(return_value=JSONResponse({"unsafe": True}))
    response = await auth_module.auth_middleware(req(path, query=query), final)
    assert response.status_code == 401
    assert b"AUTH_MEMBERSHIP_REVOKED" in response.body
    final.assert_not_awaited()


@pytest.mark.asyncio
async def test_db_failure_returns_503_without_entering_handler(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(auth_module, "verify_token", lambda value, expected_type: claims())
    async def db_failure(payload):
        raise ConnectionError("synthetic")
    monkeypatch.setattr(auth_module, "verify_live_access_membership", db_failure)
    final = AsyncMock()
    result = await auth_module.auth_middleware(req(), final)
    assert result.status_code == 503
    assert b"AUTH_MEMBERSHIP_UNAVAILABLE" in result.body
    final.assert_not_awaited()


@pytest.mark.asyncio
async def test_auth_protected_endpoint_rejects_no_token(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    final = AsyncMock()
    result = await auth_module.auth_middleware(
        SimpleNamespace(
            url=SimpleNamespace(path="/auth/company-profile"),
            method="GET",
            headers={},
            query_params={},
            state=SimpleNamespace(tenant_id="spoof"),
        ),
        final,
    )
    assert result.status_code == 401
    final.assert_not_awaited()


@pytest.mark.asyncio
async def test_rbac_cannot_reaccept_signed_download_query_token(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(auth_module, "verify_token", lambda value, expected_type: claims())
    monkeypatch.setattr(auth_module, "verify_live_access_membership", AsyncMock(return_value=False))
    r = req("/api/documents/download/10", query=True)
    handler = AsyncMock(return_value=JSONResponse({"unsafe": True}))

    async def next_middleware(request):
        return await rbac_module.rbac_middleware(request, handler)

    response = await auth_module.auth_middleware(r, next_middleware)
    assert response.status_code == 401
    handler.assert_not_awaited()

    # RBAC itself must never call a raw signature-only verifier.
    r.state.authenticated = False
    monkeypatch.setattr(auth_service, "verify_token", MagicMock(side_effect=AssertionError("bypass")))
    direct = await rbac_module.rbac_middleware(r, handler)
    assert direct.status_code == 401
    handler.assert_not_awaited()


def test_release_flag_is_off_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", raising=False)
    assert auth_service.access_membership_check_enabled() is False
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    assert auth_service.access_membership_check_enabled() is True
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "true")
    assert auth_service.access_membership_check_enabled() is False
