"""Chat167: isolated PostgreSQL 15/16 nonowner, forced-RLS authentication proof.

Requires ONLY a disposable localhost database with the dedicated synthetic
CHAT162_TEST_DATABASE_URL. No Cloud SQL, Production or external credentials.
The users policy in this test is an intentionally strict hypothetical staging
policy; current Production users RLS policy is NOT established by this test.
The legacy password_reset_tokens table is not tenant-RLS-protected here.
"""
from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest
from starlette.requests import Request

from app.api import db, routes_auth
from app.api.models.user import create_users_table, hash_password, verify_password
from app.api.services import auth_service


_EMAIL = "shared.chat167@example.test"
_OLD_PASSWORD = "Chat167OldPassword123!"
_ROLE_PASSWORD = "chat167-disposable-postgresql-only"


def disposable_dsn():
    import os

    dsn = os.environ.get("CHAT162_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("No disposable localhost PostgreSQL URL")
    u = urlsplit(dsn)
    if (
        u.scheme not in ("postgres", "postgresql")
        or u.hostname != "127.0.0.1" or u.port != 55442
        or u.path != "/bridge_hub_chat162_test"
        or u.username != "chat162_test_user"
    ):
        raise RuntimeError("Refusing Chat167 forced-RLS test outside disposable localhost")
    return dsn


def request(path, ip):
    return Request({
        "type": "http", "method": "POST", "scheme": "http",
        "path": path, "raw_path": path.encode("ascii"),
        "query_string": b"", "headers": [],
        "client": (ip, 43167), "server": ("127.0.0.1", 80),
        "http_version": "1.1",
    })


@pytest.fixture
async def auth_db(monkeypatch):
    dsn = disposable_dsn()
    suffix = uuid4().hex
    schema = "chat167_" + suffix
    role = "chat167_runtime_" + suffix
    admin = await asyncpg.connect(dsn)
    admin_pool = None
    runtime_pool = None
    schema_created = False
    role_created = False
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        schema_created = True
        await admin.execute(
            f'CREATE ROLE "{role}" LOGIN PASSWORD '
            f"'{_ROLE_PASSWORD}' NOSUPERUSER NOBYPASSRLS"
        )
        role_created = True
        admin_pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=3, server_settings={"search_path": schema},
        )

        async def admin_pool_getter():
            return admin_pool

        monkeypatch.setattr(db, "get_pool", admin_pool_getter)
        await create_users_table()
        migration = __import__("pathlib").Path(
            "app/storage/migrations/015_user_auth_version.sql"
        ).read_text(encoding="utf-8")
        async with admin_pool.acquire() as conn:
            await conn.execute(migration)
            await conn.execute(migration)
            await conn.execute(routes_auth._CREATE_RESET_TOKENS)
            old_hash = hash_password(_OLD_PASSWORD)
            alpha = await conn.fetchval(
                "INSERT INTO users(email,password_hash,tenant_id,role,is_active)"
                "VALUES($1,$2,'t_alpha','accountant',TRUE) RETURNING id",
                _EMAIL, old_hash,
            )
            beta = await conn.fetchval(
                "INSERT INTO users(email,password_hash,tenant_id,role,is_active)"
                "VALUES($1,$2,'t_beta','accountant',TRUE) RETURNING id",
                _EMAIL, old_hash,
            )
            await conn.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
            await conn.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
            await conn.execute("""
                CREATE POLICY chat167_strict_users_tenant ON users FOR ALL
                USING (
                    nullif(current_setting('app.current_tenant_id',true),'')
                    IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id',true)
                )
                WITH CHECK (
                    nullif(current_setting('app.current_tenant_id',true),'')
                    IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id',true)
                )
            """)
            await conn.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
            await conn.execute(
                f'GRANT SELECT,INSERT,UPDATE,DELETE '
                f'ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"'
            )
            await conn.execute(
                f'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" '
                f'TO "{role}"'
            )

        runtime_pool = await asyncpg.create_pool(
            host="127.0.0.1", port=55442, database="bridge_hub_chat162_test",
            user=role, password=_ROLE_PASSWORD, min_size=1, max_size=8,
            server_settings={"search_path": schema},
        )

        async def runtime_pool_getter():
            return runtime_pool

        monkeypatch.setattr(db, "get_pool", runtime_pool_getter)
        monkeypatch.setenv("JWT_SESSION_VERSION_ENABLED", "1")
        monkeypatch.delenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", raising=False)
        monkeypatch.setattr(
            auth_service, "_get_secret_key",
            lambda: "chat167-ephemeral-test-signing-key-only-not-real",
        )
        yield {
            "runtime": runtime_pool, "admin": admin_pool,
            "schema": schema, "role": role,
            "alpha": alpha, "beta": beta,
        }
    finally:
        if runtime_pool is not None:
            await runtime_pool.close()
        if admin_pool is not None:
            await admin_pool.close()
        try:
            if schema_created:
                await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            if role_created:
                await admin.execute(f'DROP ROLE "{role}"')
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_nonowner_forced_rls_fails_closed_without_tenant(auth_db):
    async with auth_db["runtime"].acquire() as conn:
        identity = await conn.fetchrow(
            "SELECT current_user AS role, row_security_active('users') AS active"
        )
        assert identity["role"] == auth_db["role"]
        assert identity["active"] is True
        flags = await conn.fetchrow(
            "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        assert flags["rolsuper"] is False
        assert flags["rolbypassrls"] is False
        owner = await conn.fetchval(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='users'::regclass"
        )
        assert owner != auth_db["role"]
        assert await conn.fetchval("SELECT count(*) FROM users") == 0
    async with db.tenant_db_context("t_alpha"):
        async with db.get_conn() as conn:
            assert await conn.fetchval("SELECT count(*) FROM users") == 1
            assert await conn.fetchval(
                "SELECT count(*) FROM users WHERE tenant_id='t_beta'"
            ) == 0
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id',true)"
        ) in (None, "")


@pytest.mark.asyncio
async def test_password_login_and_refresh_use_nonowner_tenant_scope(auth_db):
    result = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_alpha")
    assert result["ok"] is True
    access_claims = auth_service.verify_token(result["access_token"])
    assert access_claims["auth_version"] == 1
    assert access_claims["tenant_id"] == "t_alpha"
    assert await auth_service.verify_live_access_membership(access_claims)
    refreshed = await auth_service.refresh_token(result["refresh_token"])
    assert refreshed and refreshed["access_token"]
    async with db.tenant_db_context("t_alpha"):
        async with db.get_conn() as conn:
            assert await conn.fetchval(
                "SELECT last_login IS NOT NULL FROM users WHERE id=$1",
                auth_db["alpha"],
            ) is True


@pytest.mark.asyncio
async def test_password_change_revokes_only_own_tenant_under_forced_rls(auth_db):
    from app.api.routes_auth import ChangePasswordRequest

    a = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_alpha")
    b = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_beta")
    assert a["ok"] and b["ok"]
    changed = await routes_auth.auth_change_password(
        ChangePasswordRequest(
            current_password=_OLD_PASSWORD,
            new_password="Chat167ChangedAlphaPassword!",
        ),
        request("/auth/change-password", "127.0.0.167"),
        "Bearer " + a["access_token"],
    )
    assert changed["ok"] is True
    assert not await auth_service.verify_live_access_membership(
        auth_service.verify_token(a["access_token"])
    )
    assert await auth_service.refresh_token(a["refresh_token"]) is None
    assert await auth_service.verify_live_access_membership(
        auth_service.verify_token(b["access_token"])
    )
    assert await auth_service.refresh_token(b["refresh_token"])
    assert (await auth_service.login(
        _EMAIL, "Chat167ChangedAlphaPassword!", "t_alpha"
    ))["ok"] is True


@pytest.mark.asyncio
async def test_forgot_and_reset_nonowner_forced_rls_preserves_other_tenant(auth_db, monkeypatch):
    from app.api.routes_auth import ForgotPasswordRequest, ResetPasswordRequest

    sent = []
    monkeypatch.setattr(
        routes_auth, "_send_reset_email", lambda email, link: sent.append((email, link))
    )
    forgot = await routes_auth.auth_forgot_password(
        ForgotPasswordRequest(email=_EMAIL, tenant_id="t_alpha"),
        request("/auth/forgot-password", "127.0.0.168"),
    )
    assert forgot["ok"] is True
    assert len(sent) == 1
    async with auth_db["admin"].acquire() as conn:
        token = await conn.fetchval(
            "SELECT token FROM password_reset_tokens "
            "WHERE email=$1 AND tenant_id='t_alpha'",
            _EMAIL,
        )
        assert token
    a = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_alpha")
    b = await auth_service.login(_EMAIL, _OLD_PASSWORD, "t_beta")
    reset = await routes_auth.auth_reset_password(
        ResetPasswordRequest(token=token, new_password="Chat167ResetAlphaPassword!"),
        request("/auth/reset-password", "127.0.0.169"),
    )
    assert reset["ok"] is True
    assert await auth_service.refresh_token(a["refresh_token"]) is None
    assert await auth_service.refresh_token(b["refresh_token"])
    replay = await routes_auth.auth_reset_password(
        ResetPasswordRequest(token=token, new_password="IllegalReplayPassword!"),
        request("/auth/reset-password", "127.0.0.169"),
    )
    assert replay["ok"] is False
    assert replay["error"]["code"] == "TOKEN_USED"
    async with auth_db["admin"].acquire() as conn:
        rows = await conn.fetch(
            "SELECT id,auth_version,password_hash FROM users ORDER BY id"
        )
        assert len(rows) == 2
        by_id = {row["id"]: row for row in rows}
        assert by_id[auth_db["alpha"]]["auth_version"] == 2
        assert verify_password(
            "Chat167ResetAlphaPassword!", by_id[auth_db["alpha"]]["password_hash"]
        )
        assert by_id[auth_db["beta"]]["auth_version"] == 1
        assert verify_password(
            _OLD_PASSWORD, by_id[auth_db["beta"]]["password_hash"]
        )
