"""Chat161 durable OAuth state contract tests (no real PostgreSQL/network)."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api import routes_oauth


class FakeConn:
    def __init__(self):
        self.inserts = []
        self.deletes = []
        self.cleanup_calls = []
        self.states = {}

    async def execute(self, sql, *args):
        if "WITH stale AS" in sql:
            self.cleanup_calls.append((sql, args))
            return "DELETE 0"
        self.inserts.append((sql, args))
        digest, tenant, provider, expiry = args
        self.states[(digest, provider)] = (tenant, expiry)

    async def fetchrow(self, sql, digest, provider):
        self.deletes.append((sql, digest, provider))
        value = self.states.pop((digest, provider), None)
        return {"tenant_id": value[0]} if value else None


@pytest.fixture
def state_store(monkeypatch):
    conn = FakeConn()

    @asynccontextmanager
    async def get_conn():
        yield conn

    monkeypatch.setattr(routes_oauth, "get_conn", get_conn)
    monkeypatch.setattr(routes_oauth, "_q", lambda sql: sql)
    return conn


@pytest.mark.asyncio
async def test_state_is_hashed_and_consumed_once_for_provider(state_store):
    state = await routes_oauth._issue_state("t_alpha", "google")
    assert state != state_store.inserts[0][1][0]
    assert len(state_store.inserts[0][1][0]) == 64
    assert state_store.inserts[0][1][1:3] == ("t_alpha", "google")
    assert await routes_oauth._consume_state(state, "microsoft") is None
    assert await routes_oauth._consume_state(state, "google") == "t_alpha"
    assert await routes_oauth._consume_state(state, "google") is None
    assert "DELETE FROM oauth_login_states" in state_store.deletes[0][0]
    assert "expires_at > NOW()" in state_store.deletes[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_tenant", ["default", "", " t_alpha "])
async def test_login_rejects_default_or_invalid_tenant_before_state_creation(monkeypatch, bad_tenant):
    issue_state = MagicMock(side_effect=AssertionError("must not issue state"))
    monkeypatch.setattr(routes_oauth, "_issue_state", issue_state)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "synthetic-client")
    result = await routes_oauth.oauth_login("google", SimpleNamespace(base_url="https://example.test/"), tenant_id=bad_tenant)
    assert result.status_code == 403
    issue_state.assert_not_called()


@pytest.mark.asyncio
async def test_login_fails_closed_when_state_store_is_missing(monkeypatch):
    async def broken_state(tenant_id, provider):
        raise RuntimeError("migration not applied")

    monkeypatch.setattr(routes_oauth, "_issue_state", broken_state)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "synthetic-client")
    result = await routes_oauth.oauth_login("google", SimpleNamespace(base_url="https://example.test/"), tenant_id="t_alpha")
    assert result.status_code == 503

@pytest.mark.asyncio
async def test_issue_state_cleans_only_a_bounded_expired_batch(state_store):
    await routes_oauth._issue_state("t_alpha", "google")
    assert len(state_store.cleanup_calls) == 1
    sql, args = state_store.cleanup_calls[0]
    assert args == (128,)
    assert "expires_at <= NOW()" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "ORDER BY expires_at" in sql
    assert len(state_store.inserts) == 1

