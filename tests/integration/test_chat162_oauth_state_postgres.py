"""Chat162: migration 014 and OAuth/refresh on disposable PostgreSQL 15/16 only.

Never connect to a non-local or production DB. No external OAuth, Cloud Run,
Cloud SQL or production credentials are required.
"""
import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg
import pytest

from app.api import db, routes_oauth
from app.api.services import auth_service


DB_HOST = "127.0.0.1"
DB_PORT = 55442
DB_NAME = "bridge_hub_chat162_test"
DB_USER = "chat162_test_user"
MIGRATION = Path("app/storage/migrations/014_durable_oauth_login_states.sql")


def _safe_local_dsn():
    dsn = os.getenv("CHAT162_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("CHAT162_TEST_DATABASE_URL not provided; real DB test skipped")
    u = urlparse(dsn)
    if (
        u.scheme not in ("postgres", "postgresql")
        or u.hostname != DB_HOST
        or u.port != DB_PORT
        or u.path != "/" + DB_NAME
        or u.username != DB_USER
    ):
        raise RuntimeError("Chat162 refuses any non-disposable PostgreSQL target")
    return dsn


@pytest.fixture
async def postgres(monkeypatch):
    dsn = _safe_local_dsn()
    schema = "chat162_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    pool = None
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=5,
            server_settings={"search_path": schema},
        )
        sql = MIGRATION.read_text(encoding="utf-8")
        async with pool.acquire() as conn:
            # Real forward migration, then idempotence check.
            await conn.execute(sql)
            await conn.execute(sql)
            await conn.execute(
                """
                CREATE TABLE users (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    UNIQUE (email, tenant_id)
                )
                """
            )

        async def test_pool():
            return pool

        # Real application get_conn/SQL placeholder conversion/tenant context,
        # backed by the disposable pool, not by DATABASE_URL or Cloud SQL.
        monkeypatch.setattr(db, "get_pool", test_pool)
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        try:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_migration_creates_expected_schema_and_index(postgres):
    async with postgres.acquire() as conn:
        columns = {
            r["column_name"]: r["is_nullable"]
            for r in await conn.fetch(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name='oauth_login_states'"
            )
        }
        assert {"state_hash", "tenant_id", "provider", "expires_at", "created_at"} <= set(columns)
        assert all(columns[key] == "NO" for key in ("state_hash", "tenant_id", "provider", "expires_at"))
        index = await conn.fetchval(
            "SELECT to_regclass('idx_oauth_login_states_expires_at') IS NOT NULL"
        )
        assert index is True
        # Real DB and PostgreSQL major version, never silently skipped in CI.
        assert int(await conn.fetchval("SHOW server_version_num")) >= 150000


@pytest.mark.asyncio
async def test_state_is_hashed_provider_bound_and_single_use(postgres):
    state = await routes_oauth._issue_state("t_alpha", "google")
    digest = hashlib.sha256(state.encode("ascii")).hexdigest()
    assert len(state) > 35
    async with postgres.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state_hash, tenant_id, provider FROM oauth_login_states WHERE state_hash=$1",
            digest,
        )
    assert row is not None
    assert row["state_hash"].strip() == digest
    assert row["tenant_id"] == "t_alpha"
    assert row["provider"] == "google"
    assert state != digest
    assert await routes_oauth._consume_state(state, "microsoft") is None
    assert await routes_oauth._consume_state(state, "google") == "t_alpha"
    assert await routes_oauth._consume_state(state, "google") is None


@pytest.mark.asyncio
async def test_parallel_callback_can_consume_state_exactly_once(postgres):
    state = await routes_oauth._issue_state("t_alpha", "google")
    values = await asyncio.gather(*[
        routes_oauth._consume_state(state, "google") for _ in range(5)
    ])
    assert values.count("t_alpha") == 1
    assert values.count(None) == 4


@pytest.mark.asyncio
async def test_expired_state_denied_and_cleanup_works(postgres):
    state = await routes_oauth._issue_state("t_alpha", "google")
    digest = hashlib.sha256(state.encode("ascii")).hexdigest()
    async with postgres.acquire() as conn:
        await conn.execute(
            "UPDATE oauth_login_states SET expires_at=NOW()-INTERVAL '1 second' "
            "WHERE state_hash=$1", digest
        )
    assert await routes_oauth._consume_state(state, "google") is None
    async with postgres.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM oauth_login_states WHERE state_hash=$1", digest
        ) == 1  # fail closed, but requires scheduled expiry cleanup
        await conn.execute("DELETE FROM oauth_login_states WHERE expires_at < NOW()")
        assert await conn.fetchval(
            "SELECT count(*) FROM oauth_login_states WHERE state_hash=$1", digest
        ) == 0


@pytest.mark.asyncio
async def test_table_constraints_reject_invalid_tenant_provider_and_hash(postgres):
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    samples = [
        ("g" * 64, "t_alpha", "google"),
        ("a" * 64, "default", "google"),
        ("a" * 64, "DEFAULT", "google"),
        ("a" * 64, " t_alpha ", "google"),
        ("a" * 64, "", "google"),
        ("a" * 64, "t_alpha", "untrusted_provider"),
    ]
    async with postgres.acquire() as conn:
        for digest, tenant, provider in samples:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO oauth_login_states "
                    "(state_hash,tenant_id,provider,expires_at) VALUES ($1,$2,$3,$4)",
                    digest, tenant, provider, expires,
                )
        await conn.execute(
            "INSERT INTO oauth_login_states "
            "(state_hash,tenant_id,provider,expires_at) VALUES ($1,$2,$3,$4)",
            "a" * 64, "t_alpha", "google", expires,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO oauth_login_states "
                "(state_hash,tenant_id,provider,expires_at) VALUES ($1,$2,$3,$4)",
                "a" * 64, "t_alpha", "google", expires,
            )


@pytest.mark.asyncio
async def test_real_db_refresh_checks_live_user_and_revocation(postgres, monkeypatch):
    # Do not use a real JWT key; tests issue and verify synthetic signed JWTs.
    monkeypatch.setattr(
        auth_service, "_get_secret_key",
        lambda: "chat162-synthetic-jwt-key-for-tests-only-2026",
    )
    email = "member-chat162@example.test"
    async with postgres.acquire() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (email, role, tenant_id, is_active) "
            "VALUES ($1,'accountant','t_alpha',TRUE) RETURNING id",
            email,
        )
    token = auth_service.create_refresh_token({
        "sub": str(user_id),
        "email": email,
        "role": "accountant",
        "tenant_id": "t_alpha",
    })
    result = await auth_service.refresh_token(token)
    assert result is not None
    claims = auth_service.verify_token(result["access_token"], expected_type="access")
    assert claims["sub"] == str(user_id)
    assert claims["tenant_id"] == "t_alpha"
    assert claims["role"] == "accountant"

    async with postgres.acquire() as conn:
        await conn.execute("UPDATE users SET is_active=FALSE WHERE id=$1", user_id)
    assert await auth_service.refresh_token(token) is None

    async with postgres.acquire() as conn:
        await conn.execute("UPDATE users SET is_active=TRUE, role='viewer' WHERE id=$1", user_id)
    assert await auth_service.refresh_token(token) is None

    async with postgres.acquire() as conn:
        await conn.execute("UPDATE users SET role='accountant', tenant_id='t_beta' WHERE id=$1", user_id)
    assert await auth_service.refresh_token(token) is None

    # Tenant DB context is transaction-local; no request leakage after reuse.
    async with postgres.acquire() as conn:
        assert await conn.fetchval("SELECT current_setting('app.current_tenant_id', true)") in ("", None)


@pytest.mark.asyncio
async def test_chat163_new_oauth_login_purges_only_one_expired_batch(postgres):
    # Populate 133 synthetic expired states. The first new OAuth login may
    # delete at most 128; a later login purges the remaining five.
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with postgres.acquire() as conn:
        await conn.executemany(
            "INSERT INTO oauth_login_states "
            "(state_hash,tenant_id,provider,expires_at) VALUES ($1,$2,$3,$4)",
            [(f"{n:064x}", "t_alpha", "google", expired) for n in range(1, 134)],
        )

    first_state = await routes_oauth._issue_state("t_alpha", "google")
    assert first_state
    async with postgres.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM oauth_login_states WHERE expires_at <= NOW()"
        ) == 5

    second_state = await routes_oauth._issue_state("t_alpha", "google")
    assert second_state
    async with postgres.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM oauth_login_states WHERE expires_at <= NOW()"
        ) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM oauth_login_states WHERE expires_at > NOW()"
        ) == 2


@pytest.mark.asyncio
async def test_chat163_cleanup_skips_locked_expired_row(postgres):
    # Real PostgreSQL row-lock proof: opportunistic cleanup must not block
    # OAuth login while another transaction owns a stale state row.
    digest = "e" * 64
    async with postgres.acquire() as conn:
        await conn.execute(
            "INSERT INTO oauth_login_states "
            "(state_hash,tenant_id,provider,expires_at) "
            "VALUES ($1,'t_alpha','google',NOW()-INTERVAL '30 seconds')",
            digest,
        )

    async with postgres.acquire() as blocker:
        async with blocker.transaction():
            await blocker.fetchrow(
                "SELECT state_hash FROM oauth_login_states WHERE state_hash=$1 FOR UPDATE",
                digest,
            )
            fresh = await asyncio.wait_for(
                routes_oauth._issue_state("t_alpha", "google"), timeout=3
            )
            assert fresh
            async with postgres.acquire() as check:
                assert await check.fetchval(
                    "SELECT count(*) FROM oauth_login_states WHERE state_hash=$1", digest
                ) == 1

    await routes_oauth._issue_state("t_alpha", "google")
    async with postgres.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM oauth_login_states WHERE state_hash=$1", digest
        ) == 0
