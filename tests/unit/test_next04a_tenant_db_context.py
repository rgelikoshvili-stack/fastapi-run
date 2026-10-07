from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.api import db
from app.api.middleware import auth_middleware as auth_module


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self):
        self.executions = []

    def transaction(self):
        return _FakeTransaction()

    async def execute(self, query, *args):
        self.executions.append((query, args))


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def _fake_get_pool(conn):
    async def get_pool():
        return _FakePool(conn)
    return get_pool


@pytest.mark.asyncio
async def test_get_conn_sets_verified_context_transaction_locally(monkeypatch):
    conn = _FakeConnection()
    monkeypatch.setattr(db, "get_pool", _fake_get_pool(conn))

    with db.authenticated_tenant_context("tenant-a"):
        async with db.get_conn() as acquired:
            assert acquired is conn

    assert conn.executions == [
        ("SELECT set_config('app.current_tenant_id', $1, true)", ("tenant-a",))
    ]


@pytest.mark.asyncio
async def test_get_conn_without_context_does_not_set_any_tenant(monkeypatch):
    conn = _FakeConnection()
    monkeypatch.setattr(db, "get_pool", _fake_get_pool(conn))
    async with db.get_conn() as acquired:
        assert acquired is conn
    assert conn.executions == []


def test_authenticated_context_rejects_empty_tenant():
    with pytest.raises(ValueError, match="tenant_id"):
        with db.authenticated_tenant_context(""):
            pass


def test_explicit_db_tenant_cannot_create_or_override_authenticated_context():
    with pytest.raises(ValueError, match="match authenticated DB context"):
        db._resolve_tenant_context("tenant-a")
    with db.authenticated_tenant_context("tenant-a"):
        assert db._resolve_tenant_context("tenant-a") == "tenant-a"
        with pytest.raises(ValueError, match="match authenticated DB context"):
            db._resolve_tenant_context("tenant-b")


@pytest.mark.asyncio
async def test_auth_middleware_uses_verified_jwt_tenant_not_client_header(monkeypatch):
    monkeypatch.setattr(
        auth_module,
        "verify_token",
        lambda token, expected_type: {"sub": "user-1", "role": "admin", "tenant_id": "signed-tenant"},
    )
    request = SimpleNamespace(
        url=SimpleNamespace(path="/private/resource"),
        method="GET",
        headers={"Authorization": "Bearer signed-token", "X-Tenant-ID": "attacker-tenant"},
        query_params={},
        state=SimpleNamespace(tenant_id="attacker-tenant"),
    )

    async def call_next(_request):
        assert db._current_tenant_id.get() == "signed-tenant"
        return "response"

    assert await auth_module.auth_middleware(request, call_next) == "response"
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
async def test_auth_middleware_missing_tenant_claim_leaves_db_scope_empty(monkeypatch):
    monkeypatch.setattr(
        auth_module,
        "verify_token",
        lambda token, expected_type: {"sub": "user-1", "role": "admin"},
    )
    request = SimpleNamespace(
        url=SimpleNamespace(path="/private/resource"),
        method="GET",
        headers={"Authorization": "Bearer signed-token", "X-Tenant-ID": "attacker-tenant"},
        query_params={},
        state=SimpleNamespace(tenant_id="attacker-tenant"),
    )

    outer_token = db.set_authenticated_tenant_context("outer-tenant")

    async def call_next(_request):
        assert db._current_tenant_id.get() is None
        return "response"

    try:
        assert await auth_module.auth_middleware(request, call_next) == "response"
    finally:
        db.reset_authenticated_tenant_context(outer_token)
