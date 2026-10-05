"""NEXT-01 regression tests for tenant membership enrollment boundaries."""

from contextlib import asynccontextmanager
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from main import app
from app.api import routes_auth, routes_rbac
from app.api import security
from app.api.middleware import audit_log_middleware
from app.api.routes_rbac import UserCreate


@pytest.fixture(autouse=True)
def isolate_auth_request_side_effects(monkeypatch):
    # Keep HTTP tests independent of Redis/local rate-limit state and databases.
    security.limiter._storage.reset()
    monkeypatch.setattr(audit_log_middleware, "log_event", lambda **_kwargs: None)


@pytest.mark.parametrize("tenant_id", ["tenant-a", "tenant-b", "unknown-tenant"])
def test_public_register_fails_closed_without_database_access(monkeypatch, caplog, tenant_id):
    async def unexpected_call(*args, **kwargs):
        raise AssertionError("public register must not touch membership persistence")

    monkeypatch.setattr(routes_auth, "create_users_table", unexpected_call)
    monkeypatch.setattr(routes_auth, "create_user", unexpected_call)
    client = TestClient(app)
    response = client.post(
        "/auth/register",
        json={"email": "new@example.test", "password": "StrongPass123!", "tenant_id": tenant_id},
    )
    client.close()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_MEMBERSHIP_FORBIDDEN"
    assert tenant_id not in response.text
    assert "public_tenant_registration_denied" in caplog.text


def test_public_register_rejects_invalid_invitation_field(monkeypatch):
    async def unexpected_call(*args, **kwargs):
        raise AssertionError("no invitation mechanism is implemented on public register")

    monkeypatch.setattr(routes_auth, "create_users_table", unexpected_call)
    monkeypatch.setattr(routes_auth, "create_user", unexpected_call)
    client = TestClient(app)
    response = client.post(
        "/auth/register",
        json={
            "email": "new@example.test",
            "password": "StrongPass123!",
            "tenant_id": "tenant-a",
            "invitation_token": "invalid-or-unknown",
        },
    )
    client.close()
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_MEMBERSHIP_FORBIDDEN"


def test_tenant_a_user_cannot_self_enroll_in_tenant_b(monkeypatch):
    from app.api.services.auth_service import create_access_token

    async def unexpected_call(*args, **kwargs):
        raise AssertionError("self-enrollment must be denied before persistence")

    monkeypatch.setattr(routes_auth, "create_users_table", unexpected_call)
    monkeypatch.setattr(routes_auth, "create_user", unexpected_call)
    token = create_access_token({"sub": "user-a", "role": "admin", "tenant_id": "tenant-a"})
    client = TestClient(app)
    response = client.post(
        "/auth/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "attacker@example.test", "password": "StrongPass123!", "tenant_id": "tenant-b"},
    )
    client.close()
    assert response.status_code == 403


def test_repeated_public_register_cannot_create_duplicate_membership(monkeypatch):
    create_calls = []

    async def unexpected_create(*args, **kwargs):
        create_calls.append((args, kwargs))

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes_auth, "create_users_table", no_op)
    monkeypatch.setattr(routes_auth, "create_user", unexpected_create)
    client = TestClient(app)
    results = [client.post(
        "/auth/register",
        json={"email": "same@example.test", "password": "StrongPass123!", "tenant_id": "tenant-a"},
    ) for _ in range(2)]
    client.close()
    assert [r.status_code for r in results] == [403, 403]
    assert create_calls == []


@pytest.mark.asyncio
async def test_tenant_admin_can_create_user_only_in_own_tenant(monkeypatch):
    inserted = []

    class FakeConnection:
        async def fetchval(self, query, *args):
            inserted.append(args)
            return 101

    @asynccontextmanager
    async def fake_get_conn():
        yield FakeConnection()

    async def fake_get_user_by_key(_api_key):
        return {"role": "admin", "tenant_id": 10}

    monkeypatch.setattr(routes_rbac, "get_conn", fake_get_conn)
    monkeypatch.setattr(routes_rbac, "get_user_by_key", fake_get_user_by_key)
    request = Request({"type": "http", "method": "POST", "path": "/rbac/users/create", "headers": []})
    request.state.authenticated = True
    request.state.role = "admin"
    request.state.auth_tenant_id = "10"

    result = await routes_rbac.create_user(
        UserCreate(name="New User", email="new@example.test", role="accountant", tenant_id=10),
        request,
        x_api_key="test-key-not-a-secret",
    )

    assert result["ok"] is True
    assert len(inserted) == 1


@pytest.mark.asyncio
async def test_tenant_admin_duplicate_membership_returns_conflict(monkeypatch):
    class FakeConnection:
        async def fetchval(self, _query, *_args):
            return None  # ON CONFLICT (email, tenant_id) DO NOTHING

    @asynccontextmanager
    async def fake_get_conn():
        yield FakeConnection()

    async def fake_get_user_by_key(_api_key):
        return {"role": "admin", "tenant_id": 10}

    monkeypatch.setattr(routes_rbac, "get_conn", fake_get_conn)
    monkeypatch.setattr(routes_rbac, "get_user_by_key", fake_get_user_by_key)
    request = Request({"type": "http", "method": "POST", "path": "/rbac/users/create", "headers": []})
    request.state.authenticated = True
    request.state.role = "admin"
    request.state.auth_tenant_id = "10"

    result = await routes_rbac.create_user(
        UserCreate(name="Existing User", email="existing@example.test", role="accountant", tenant_id=10),
        request,
        x_api_key="test-key-not-a-secret",
    )

    assert result.status_code == 409
    assert b"MEMBERSHIP_EXISTS" in result.body


@pytest.mark.asyncio
async def test_tenant_admin_cannot_create_user_in_another_tenant(monkeypatch, caplog):
    async def fake_get_user_by_key(_api_key):
        return {"role": "admin", "tenant_id": 10}

    async def unexpected_get_conn():
        raise AssertionError("cross-tenant denial must occur before persistence")

    monkeypatch.setattr(routes_rbac, "get_user_by_key", fake_get_user_by_key)
    monkeypatch.setattr(routes_rbac, "get_conn", unexpected_get_conn)
    request = Request({"type": "http", "method": "POST", "path": "/rbac/users/create", "headers": []})
    request.state.authenticated = True
    request.state.role = "admin"
    request.state.auth_tenant_id = "10"

    result = await routes_rbac.create_user(
        UserCreate(name="New User", email="new@example.test", role="accountant", tenant_id=20),
        request,
        x_api_key="test-key-not-a-secret",
    )

    assert result.status_code == 403
    assert result.body.find(b"TENANT_MEMBERSHIP_FORBIDDEN") >= 0
    assert "tenant_membership_admin_create_denied" in caplog.text


def test_new_tenant_signup_remains_supported(monkeypatch):
    class FakeConnection:
        async def fetchrow(self, *_args):
            return None

    @asynccontextmanager
    async def fake_get_conn():
        yield FakeConnection()

    async def no_existing_inn(_inn):
        return False

    async def no_op(*_args, **_kwargs):
        return None

    async def fake_create_user(email, _password, tenant_id, role):
        return {"id": 1001, "email": email, "tenant_id": tenant_id, "role": role}

    monkeypatch.setattr(routes_auth, "get_conn", fake_get_conn)
    monkeypatch.setattr(routes_auth, "_tenant_exists_by_inn", no_existing_inn)
    monkeypatch.setattr(routes_auth, "_create_tenant", no_op)
    monkeypatch.setattr(routes_auth, "create_users_table", no_op)
    monkeypatch.setattr(routes_auth, "create_user", fake_create_user)

    client = TestClient(app)
    response = client.post(
        "/auth/signup",
        json={
            "company_type": "legal_entity",
            "company_inn": "123456789",
            "company_name_legal": "Test Company",
            "email": "owner@example.test",
            "password": "StrongPass123!",
        },
    )
    client.close()
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["user"]["role"] == "admin"
