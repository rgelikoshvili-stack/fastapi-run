"""Chat161: JWT refresh must not outlive an active tenant membership.

All cases use synthetic identities and mocks; no production DB connection.
"""
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from app.api.services import auth_service
from app.api import db as database


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return self.row


@pytest.fixture
def db_mock(monkeypatch):
    state = {"row": None, "conn": None, "tenant": None, "queries": 0}

    @asynccontextmanager
    async def fake_conn():
        state["queries"] += 1
        state["conn"] = FakeConnection(state["row"])
        yield state["conn"]

    @asynccontextmanager
    async def fake_tenant_context(tenant_id):
        state["tenant"] = tenant_id
        yield

    monkeypatch.setattr(database, "get_conn", fake_conn)
    monkeypatch.setattr(database, "tenant_db_context", fake_tenant_context)
    monkeypatch.setattr(database, "_q", lambda sql: sql)
    monkeypatch.setattr(auth_service, "_create_access_token", MagicMock(return_value="fresh-access"))
    monkeypatch.setattr(auth_service, "_create_refresh_token", MagicMock(return_value="fresh-refresh"))
    return state


def valid_payload():
    return {
        "sub": "42",
        "email": "member@example.test",
        "role": "accountant",
        "tenant_id": "t_alpha",
        "type": "refresh",
    }


def active_row():
    return {
        "id": 42,
        "email": "member@example.test",
        "role": "accountant",
        "tenant_id": "t_alpha",
    }


@pytest.mark.asyncio
async def test_active_member_gets_new_refresh_pair(monkeypatch, db_mock):
    monkeypatch.setattr(auth_service, "verify_token", lambda token, expected_type: valid_payload())
    db_mock["row"] = active_row()
    out = await auth_service.refresh_token("synthetic-refresh")
    assert out["access_token"] == "fresh-access"
    assert out["refresh_token"] == "fresh-refresh"
    assert db_mock["tenant"] == "t_alpha"
    assert db_mock["conn"].calls[0][1] == (42, "t_alpha")
    assert "is_active=TRUE" in db_mock["conn"].calls[0][0]
    assert auth_service._create_access_token.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [
    None,
    {"id": 42, "email": "member@example.test", "role": "viewer", "tenant_id": "t_alpha"},
    {"id": 42, "email": "member@example.test", "role": "accountant", "tenant_id": "t_beta"},
    {"id": 42, "email": "other@example.test", "role": "accountant", "tenant_id": "t_alpha"},
])
async def test_revoked_or_changed_membership_denied(monkeypatch, db_mock, row):
    monkeypatch.setattr(auth_service, "verify_token", lambda token, expected_type: valid_payload())
    db_mock["row"] = row
    assert await auth_service.refresh_token("synthetic-refresh") is None
    auth_service._create_access_token.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", [
    {"sub": "user-email@example.test"},
    {"sub": "0"},
    {"sub": "-3"},
    {"tenant_id": "default"},
    {"tenant_id": " t_alpha "},
    {"role": ""},
    {"email": ""},
])
async def test_malformed_refresh_claims_denied_without_db(monkeypatch, db_mock, mutation):
    claims = {**valid_payload(), **mutation}
    monkeypatch.setattr(auth_service, "verify_token", lambda token, expected_type: claims)
    assert await auth_service.refresh_token("synthetic-refresh") is None
    assert db_mock["queries"] == 0


@pytest.mark.asyncio
async def test_invalid_refresh_token_denied_without_db(monkeypatch, db_mock):
    monkeypatch.setattr(auth_service, "verify_token", lambda token, expected_type: None)
    assert await auth_service.refresh_token("bad") is None
    assert db_mock["queries"] == 0
