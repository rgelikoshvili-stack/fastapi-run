"""NEXT-01 membership persistence checks against disposable PostgreSQL only."""

from contextlib import asynccontextmanager
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import routes_auth, routes_rbac
from app.api.routes_auth import RegisterRequest
from app.api.routes_rbac import UserCreate


EXPECTED_HOST = "127.0.0.1"
EXPECTED_PORT = 55436
EXPECTED_DATABASE = "bridge_hub_next01_test"
ADMIN_API_KEY = "synthetic-next01-admin-api-key"


def _validate_disposable_dsn(dsn: str) -> None:
    parsed = urlparse(dsn)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != EXPECTED_HOST
        or parsed.port != EXPECTED_PORT
        or parsed.path.lstrip("/") != EXPECTED_DATABASE
    ):
        raise ValueError(
            "Refusing database target; NEXT-01 tests require only "
            "127.0.0.1:55436/bridge_hub_next01_test."
        )


@pytest.fixture
async def disposable_membership_db(monkeypatch):
    import os

    dsn = os.environ.get("NEXT01_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("NEXT01_TEST_DATABASE_URL is not configured for disposable PostgreSQL")
    _validate_disposable_dsn(dsn)

    import asyncpg

    schema = f"next01_membership_{uuid4().hex}"
    admin_conn = await asyncpg.connect(dsn)
    pool = None
    try:
        await admin_conn.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn,
            min_size=1,
            max_size=2,
            server_settings={"search_path": schema},
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE users (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    tenant_id BIGINT NOT NULL,
                    api_key TEXT UNIQUE,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    UNIQUE (email, tenant_id)
                )
                """
            )
            await conn.execute(
                """INSERT INTO users (name, email, role, tenant_id, api_key)
                   VALUES ('Synthetic tenant A admin', 'admin-a@example.test', 'admin', 101, $1)""",
                ADMIN_API_KEY,
            )
            await conn.execute(
                "CREATE TABLE membership_side_effects (email TEXT NOT NULL)"
            )

        @asynccontextmanager
        async def test_get_conn():
            async with pool.acquire() as conn:
                yield conn

        monkeypatch.setattr(routes_rbac, "get_conn", test_get_conn)
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        await admin_conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin_conn.close()


def _request(*, tenant_id=None, role=None, authenticated=False):
    request = Request(
        {"type": "http", "method": "POST", "path": "/rbac/users/create", "headers": []}
    )
    request.state.authenticated = authenticated
    request.state.role = role
    request.state.auth_tenant_id = str(tenant_id) if tenant_id is not None else None
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant_id", ["101", "202"])
async def test_public_existing_or_other_tenant_join_is_denied_and_not_persisted(
    disposable_membership_db, tenant_id
):
    result = await routes_auth.auth_register(
        RegisterRequest(
            email="public-join@example.test",
            password="TestOnlyPassword123!",
            tenant_id=tenant_id,
        ),
        _request(tenant_id=101, role="admin", authenticated=False),
    )

    assert result.status_code == 403
    assert b"TENANT_MEMBERSHIP_FORBIDDEN" in result.body
    async with disposable_membership_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM users WHERE email = $1", "public-join@example.test"
        ) == 0


@pytest.mark.asyncio
async def test_tenant_a_cannot_self_enroll_into_tenant_b(disposable_membership_db):
    result = await routes_auth.auth_register(
        RegisterRequest(
            email="tenant-a-to-b@example.test",
            password="TestOnlyPassword123!",
            tenant_id="202",
        ),
        _request(tenant_id=101, role="admin", authenticated=True),
    )

    assert result.status_code == 403
    async with disposable_membership_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM users WHERE email = $1", "tenant-a-to-b@example.test"
        ) == 0


@pytest.mark.asyncio
async def test_admin_membership_requires_auth_and_authorization(disposable_membership_db):
    with pytest.raises(HTTPException) as unauthenticated:
        await routes_rbac.create_user(
            UserCreate(name="Denied", email="unauth@example.test", tenant_id=101),
            _request(tenant_id=101, role="admin", authenticated=False),
            x_api_key=ADMIN_API_KEY,
        )
    assert unauthenticated.value.status_code == 401

    with pytest.raises(HTTPException) as unauthorized_role:
        await routes_rbac.create_user(
            UserCreate(name="Denied", email="role@example.test", tenant_id=101),
            _request(tenant_id=101, role="accountant", authenticated=True),
            x_api_key=ADMIN_API_KEY,
        )
    assert unauthorized_role.value.status_code == 403


@pytest.mark.asyncio
async def test_valid_admin_membership_persists_and_is_tenant_isolated(disposable_membership_db):
    result = await routes_rbac.create_user(
        UserCreate(
            name="Synthetic tenant A member",
            email="member-a@example.test",
            role="accountant",
            tenant_id=101,
        ),
        _request(tenant_id=101, role="admin", authenticated=True),
        x_api_key=ADMIN_API_KEY,
    )

    assert result["ok"] is True
    async with disposable_membership_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM users WHERE email = $1 AND tenant_id = 101",
            "member-a@example.test",
        ) == 1
        assert await conn.fetchval(
            "SELECT count(*) FROM users WHERE email = $1 AND tenant_id = 202",
            "member-a@example.test",
        ) == 0

        cross_tenant = await routes_rbac.create_user(
            UserCreate(
                name="Must be denied",
                email="member-b@example.test",
                role="accountant",
                tenant_id=202,
            ),
            _request(tenant_id=101, role="admin", authenticated=True),
            x_api_key=ADMIN_API_KEY,
        )
        assert cross_tenant.status_code == 403
        assert await conn.fetchval(
            "SELECT count(*) FROM users WHERE email = $1",
            "member-b@example.test",
        ) == 0


@pytest.mark.asyncio
async def test_duplicate_admin_membership_is_prevented(disposable_membership_db):
    args = (
        UserCreate(
            name="Synthetic member",
            email="duplicate@example.test",
            role="accountant",
            tenant_id=101,
        ),
        _request(tenant_id=101, role="admin", authenticated=True),
    )
    first = await routes_rbac.create_user(*args, x_api_key=ADMIN_API_KEY)
    second = await routes_rbac.create_user(*args, x_api_key=ADMIN_API_KEY)

    assert first["ok"] is True
    assert second.status_code == 409
    async with disposable_membership_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM users WHERE email = $1 AND tenant_id = 101",
            "duplicate@example.test",
        ) == 1


@pytest.mark.asyncio
async def test_failed_membership_insert_leaves_no_partial_rows(disposable_membership_db):
    async with disposable_membership_db.acquire() as conn:
        await conn.execute(
            """
            CREATE FUNCTION reject_next01_membership() RETURNS trigger AS $$
            BEGIN
                INSERT INTO membership_side_effects (email) VALUES (NEW.email);
                RAISE EXCEPTION 'synthetic membership failure';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        await conn.execute(
            "CREATE TRIGGER reject_next01_membership BEFORE INSERT ON users "
            "WHEN (NEW.email = 'rollback@example.test') "
            "EXECUTE FUNCTION reject_next01_membership()"
        )

    result = await routes_rbac.create_user(
        UserCreate(
            name="Must roll back",
            email="rollback@example.test",
            role="accountant",
            tenant_id=101,
        ),
        _request(tenant_id=101, role="admin", authenticated=True),
        x_api_key=ADMIN_API_KEY,
    )

    assert result["ok"] is False
    async with disposable_membership_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM users WHERE email = $1", "rollback@example.test"
        ) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM membership_side_effects WHERE email = $1",
            "rollback@example.test",
        ) == 0
