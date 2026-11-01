"""Chat166: password reset/change revokes all previous JWT families.

Real PostgreSQL 15/16 tests use only disposable localhost synthetic databases.
No Cloud SQL, Production, customer financial records, or real identity provider.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from starlette.requests import Request
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest

from app.api import db, routes_auth
from app.api.models.user import create_users_table, hash_password, verify_password
from app.api.services import auth_service


def _disposable_dsn():
    value = __import__("os").environ.get("CHAT162_TEST_DATABASE_URL", "")
    if not value:
        pytest.skip("disposable PostgreSQL DSN is not available")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("postgres", "postgresql")
        or parsed.hostname != "127.0.0.1" or parsed.port != 55442
        or parsed.path != "/bridge_hub_chat162_test"
        or parsed.username != "chat162_test_user"
    ):
        raise RuntimeError("Refusing Chat166 test against anything but disposable localhost")
    return value


@pytest.fixture
async def session_db(monkeypatch):
    dsn = _disposable_dsn()
    namespace = "chat166_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    pool = None
    try:
        await admin.execute(f'CREATE SCHEMA "{namespace}"')
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=8,
            server_settings={"search_path": namespace},
        )

        async def test_pool():
            return pool

        monkeypatch.setattr(db, "get_pool", test_pool)
        await create_users_table()
        sql = Path("app/storage/migrations/015_user_auth_version.sql").read_text(encoding="utf8")
        async with pool.acquire() as conn:
            await conn.execute(sql)
            await conn.execute(sql)  # every migration must be safely repeatable
            reset_sql = Path(
                "app/storage/migrations/016_password_reset_tokens.sql"
            ).read_text(encoding="utf8")
            await conn.execute(reset_sql)
            await conn.execute(reset_sql)  # idempotent, migration-role fixture

        monkeypatch.setenv("JWT_SESSION_VERSION_ENABLED", "1")
        monkeypatch.delenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", raising=False)
        monkeypatch.setattr(
            auth_service, "_get_secret_key",
            lambda: "chat166-disposable-only-synthetic-session-secret-2026",
        )
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        try:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{namespace}" CASCADE')
        finally:
            await admin.close()


async def synthetic_user(pool, email="member-chat166@example.test", tenant="t_alpha", password="OldStrongPassword456!"):
    hashed = hash_password(password)
    async with pool.acquire() as conn:
        uid = await conn.fetchval(
            "INSERT INTO users (email,password_hash,tenant_id,role,is_active) "
            "VALUES ($1,$2,$3,'accountant',TRUE) RETURNING id",
            email, hashed, tenant,
        )
    return uid


def synthetic_request(path: str, client_host: str = "127.0.0.1") -> Request:
    """Real Starlette request so the rate limiter can inspect the peer."""
    return Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": (client_host, 41002),
        "server": ("127.0.0.1", 80),
        "http_version": "1.1",
    })


def claims(uid, email, tenant, version=1):
    return {
        "sub": str(uid), "email": email, "role": "accountant",
        "tenant_id": tenant, "auth_version": version,
    }


def issue(uid, email, tenant, version=1):
    c = claims(uid, email, tenant, version)
    return (
        auth_service.create_access_token(c),
        auth_service.create_refresh_token(c),
    )


@pytest.mark.asyncio
async def test_migration_idempotent_and_auth_version_positive_constraint(session_db):
    async with session_db.acquire() as conn:
        version = await conn.fetchval("SHOW server_version_num")
        assert int(version) >= 150000
        cols = await conn.fetch(
            "SELECT column_name, column_default, is_nullable, data_type "
            "FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='users' "
            "AND column_name='auth_version'"
        )
        assert len(cols) == 1
        assert cols[0]["is_nullable"] == "NO"
        assert cols[0]["data_type"] == "bigint"
        assert "1" in cols[0]["column_default"]
        constraint = await conn.fetchval(
            "SELECT count(*) FROM pg_constraint "
            "WHERE conrelid='users'::regclass AND conname='users_auth_version_positive'"
        )
        assert constraint == 1

    uid = await synthetic_user(session_db)
    async with session_db.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "UPDATE users SET auth_version=0 WHERE id=$1", uid
            )
        assert await conn.fetchval(
            "SELECT auth_version FROM users WHERE id=$1", uid
        ) == 1


@pytest.mark.asyncio
async def test_legacy_signed_jwt_must_relogin_after_version_flag_activation(session_db, monkeypatch):
    uid = await synthetic_user(session_db)
    email = "member-chat166@example.test"
    monkeypatch.setenv("JWT_SESSION_VERSION_ENABLED", "0")
    legacy_access = auth_service.create_access_token(
        {key: value for key, value in claims(uid, email, "t_alpha").items()
         if key != "auth_version"}
    )
    legacy_refresh = auth_service.create_refresh_token(
        {key: value for key, value in claims(uid, email, "t_alpha").items()
         if key != "auth_version"}
    )

    monkeypatch.setenv("JWT_SESSION_VERSION_ENABLED", "1")
    assert auth_service.access_membership_check_enabled() is True
    assert auth_service.jwt_session_version_enabled() is True
    assert not await auth_service.verify_live_access_membership(
        auth_service.verify_token(legacy_access, "access")
    )
    assert await auth_service.refresh_token(legacy_refresh) is None
    with pytest.raises((KeyError, ValueError)):
        auth_service.create_access_token(
            {key: value for key, value in claims(uid, email, "t_alpha").items()
             if key != "auth_version"}
        )


@pytest.mark.asyncio
async def test_password_change_revokes_both_tokens_and_preserves_other_tenant(session_db):
    from app.api.routes_auth import ChangePasswordRequest

    email = "same-address@example.test"
    uid_a = await synthetic_user(session_db, email=email, tenant="t_alpha")
    uid_b = await synthetic_user(session_db, email=email, tenant="t_beta")
    old_access_a, old_refresh_a = issue(uid_a, email, "t_alpha")
    old_access_b, old_refresh_b = issue(uid_b, email, "t_beta")
    assert await auth_service.verify_live_access_membership(
        auth_service.verify_token(old_access_a)
    )

    result = await routes_auth.auth_change_password(
        ChangePasswordRequest(
            current_password="OldStrongPassword456!",
            new_password="NewStrongPassword987!",
        ),
        synthetic_request("/auth/change-password"),
        "Bearer " + old_access_a,
    )
    assert result["ok"] is True
    async with session_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT auth_version,password_hash FROM users WHERE id=$1", uid_a
        )
    assert row["auth_version"] == 2
    assert verify_password("NewStrongPassword987!", row["password_hash"])
    assert not await auth_service.verify_live_access_membership(
        auth_service.verify_token(old_access_a)
    )
    assert await auth_service.refresh_token(old_refresh_a) is None

    # Same-email account in the other tenant must remain unaffected.
    assert await auth_service.verify_live_access_membership(
        auth_service.verify_token(old_access_b)
    )
    assert (await auth_service.refresh_token(old_refresh_b))["access_token"]

    renewed = await auth_service.login(
        email, "NewStrongPassword987!", "t_alpha"
    )
    assert renewed["ok"] is True
    assert auth_service.verify_token(renewed["access_token"])["auth_version"] == 2
    assert auth_service.verify_token(renewed["refresh_token"], "refresh")["auth_version"] == 2


@pytest.mark.asyncio
async def test_wrong_old_password_does_not_revoke_or_modify(session_db):
    from app.api.routes_auth import ChangePasswordRequest

    uid = await synthetic_user(session_db)
    access, refresh = issue(uid, "member-chat166@example.test", "t_alpha")
    result = await routes_auth.auth_change_password(
        ChangePasswordRequest(
            current_password="Incorrect1234!",
            new_password="ChangedButForbidden234!",
        ),
        synthetic_request("/auth/change-password"),
        "Bearer " + access,
    )
    assert result["ok"] is False
    async with session_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT auth_version FROM users WHERE id=$1", uid
        ) == 1
    assert await auth_service.verify_live_access_membership(
        auth_service.verify_token(access)
    )
    assert (await auth_service.refresh_token(refresh))["access_token"]


@pytest.mark.asyncio
async def test_reset_consumes_once_and_revokes_access_and_refresh(session_db):
    from app.api.routes_auth import ResetPasswordRequest

    uid = await synthetic_user(session_db)
    access, refresh = issue(uid, "member-chat166@example.test", "t_alpha")
    reset_code = "synthetic-reset-code-chat166"
    async with session_db.acquire() as conn:
        await conn.execute(
            "INSERT INTO password_reset_tokens "
            "(token,email,tenant_id,expires_at,used) VALUES ($1,$2,$3,$4,FALSE)",
            reset_code, "member-chat166@example.test", "t_alpha",
            datetime.utcnow() + timedelta(minutes=10),
        )

    action = await routes_auth.auth_reset_password(
        ResetPasswordRequest(token=reset_code, new_password="ResetNewPassword789!"),
        synthetic_request("/auth/reset-password"),
    )
    assert action["ok"] is True
    async with session_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT auth_version,password_hash FROM users WHERE id=$1", uid
        )
        used = await conn.fetchval(
            "SELECT used FROM password_reset_tokens WHERE token=$1", reset_code
        )
    assert used is True
    assert row["auth_version"] == 2
    assert verify_password("ResetNewPassword789!", row["password_hash"])
    assert not await auth_service.verify_live_access_membership(
        auth_service.verify_token(access)
    )
    assert await auth_service.refresh_token(refresh) is None

    second = await routes_auth.auth_reset_password(
        ResetPasswordRequest(token=reset_code, new_password="IllegalSecondPass111!"),
        synthetic_request("/auth/reset-password"),
    )
    assert second["ok"] is False
    assert second["error"]["code"] == "TOKEN_USED"


@pytest.mark.asyncio
async def test_concurrent_reuse_of_reset_link_can_only_succeed_once(session_db):
    from app.api.routes_auth import ResetPasswordRequest

    uid = await synthetic_user(session_db)
    code = "race-protected-synthetic-reset-chat166"
    async with session_db.acquire() as conn:
        await conn.execute(
            "INSERT INTO password_reset_tokens "
            "(token,email,tenant_id,expires_at,used) VALUES "
            "($1,'member-chat166@example.test','t_alpha',$2,FALSE)",
            code, datetime.utcnow() + timedelta(minutes=10),
        )

    async def reset(password):
        return await routes_auth.auth_reset_password(
            ResetPasswordRequest(token=code, new_password=password),
            synthetic_request("/auth/reset-password"),
        )

    results = await asyncio.gather(
        reset("ConcurrentNewPassword111!"),
        reset("ConcurrentNewPassword222!"),
    )
    assert [x["ok"] for x in results].count(True) == 1
    assert sorted(x["error"]["code"] for x in results if not x["ok"]) == ["TOKEN_USED"]
    async with session_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT auth_version FROM users WHERE id=$1", uid
        ) == 2


@pytest.mark.asyncio
async def test_reset_rolls_back_password_and_version_when_token_consume_fails(session_db):
    from app.api.routes_auth import ResetPasswordRequest

    uid = await synthetic_user(session_db)
    access, refresh = issue(uid, "member-chat166@example.test", "t_alpha")
    code = "rollback-reset-code-chat166"
    async with session_db.acquire() as conn:
        await conn.execute(
            "INSERT INTO password_reset_tokens "
            "(token,email,tenant_id,expires_at,used) VALUES "
            "($1,'member-chat166@example.test','t_alpha',$2,FALSE)",
            code, datetime.utcnow() + timedelta(minutes=10),
        )
        await conn.execute(
            """
            CREATE FUNCTION deny_synthetic_reset_consume()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'synthetic reset consume storage failure';
            END $$;
            """
        )
        await conn.execute(
            "CREATE TRIGGER deny_reset_update BEFORE UPDATE ON password_reset_tokens "
            "FOR EACH ROW EXECUTE FUNCTION deny_synthetic_reset_consume()"
        )
    failed = await routes_auth.auth_reset_password(
        ResetPasswordRequest(token=code, new_password="ShouldRollbackNew111!"),
        synthetic_request("/auth/reset-password"),
    )
    assert failed["ok"] is False
    async with session_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT auth_version,password_hash FROM users WHERE id=$1", uid
        )
        used = await conn.fetchval(
            "SELECT used FROM password_reset_tokens WHERE token=$1", code
        )
    assert row["auth_version"] == 1
    assert verify_password("OldStrongPassword456!", row["password_hash"])
    assert used is False
    assert await auth_service.verify_live_access_membership(
        auth_service.verify_token(access)
    )
    assert (await auth_service.refresh_token(refresh))["access_token"]


@pytest.mark.asyncio
async def test_reset_binds_token_tenant_for_rls_scoped_user_update(session_db):
    """A reset for tenant A sets a transaction-local scope before touching users.

    The synthetic trigger acts as an RLS context assertion; this alone does
    NOT certify actual forced-RLS production role behavior.
    """
    from app.api.routes_auth import ResetPasswordRequest

    email = "shared-reset-chat167@example.test"
    uid_a = await synthetic_user(session_db, email=email, tenant="t_alpha")
    uid_b = await synthetic_user(session_db, email=email, tenant="t_beta")
    async with session_db.acquire() as conn:
        await conn.execute("""
            CREATE FUNCTION check_chat167_user_update_tenant()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF current_setting('app.current_tenant_id', true)
                   IS DISTINCT FROM OLD.tenant_id THEN
                    RAISE EXCEPTION 'user update missing tenant context';
                END IF;
                RETURN NEW;
            END $$;
        """)
        await conn.execute(
            "CREATE TRIGGER chat167_user_update_tenant "
            "BEFORE UPDATE OF password_hash ON users "
            "FOR EACH ROW EXECUTE FUNCTION check_chat167_user_update_tenant()"
        )
        await conn.execute(
            "INSERT INTO password_reset_tokens "
            "(token,email,tenant_id,expires_at,used) VALUES ($1,$2,$3,$4,FALSE)",
            "chat167-alpha-reset-code", email, "t_alpha",
            datetime.utcnow() + timedelta(minutes=10),
        )

    result = await routes_auth.auth_reset_password(
        ResetPasswordRequest(
            token="chat167-alpha-reset-code",
            new_password="ChangedInAlphaOnly123!",
        ),
        synthetic_request("/auth/reset-password", client_host="127.0.0.166"),
    )
    assert result["ok"] is True
    async with session_db.acquire() as conn:
        alpha = await conn.fetchrow(
            "SELECT password_hash,auth_version FROM users WHERE id=$1", uid_a
        )
        beta = await conn.fetchrow(
            "SELECT password_hash,auth_version FROM users WHERE id=$1", uid_b
        )
        assert await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id',true)"
        ) in (None, "")
    assert alpha["auth_version"] == 2
    assert verify_password("ChangedInAlphaOnly123!", alpha["password_hash"])
    assert beta["auth_version"] == 1
    assert verify_password("OldStrongPassword456!", beta["password_hash"])
