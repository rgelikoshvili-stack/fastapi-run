"""Chat165 — model-backed, nonproduction JWT guard and DB load preflight.

Safety: requires a LOCAL disposable PostgreSQL service on 127.0.0.1:55442,
a fixed synthetic account/database, and no real finance/customer data.
Creates unique short-lived schemas; never touches Cloud SQL or staging itself.
"""
import asyncio
import json
import os
import statistics
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest
from fastapi.responses import JSONResponse

from app.api import db
from app.api.middleware import auth_middleware as auth_module
from app.api.models.user import create_users_table
from app.api.services import auth_service


def _require_disposable_url():
    dsn = os.getenv("CHAT162_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("CHAT162_TEST_DATABASE_URL absent: disposable DB test skipped")
    parsed = urlsplit(dsn)
    if (
        parsed.scheme not in ("postgres", "postgresql")
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 55442
        or parsed.username != "chat162_test_user"
        or parsed.path != "/bridge_hub_chat162_test"
    ):
        raise RuntimeError("Chat165 will NEVER connect to a non-disposable DB")
    return dsn


@pytest.fixture
async def model_db(monkeypatch):
    dsn = _require_disposable_url()
    schema = "chat165_" + uuid4().hex
    owner = await asyncpg.connect(dsn)
    pool = None
    try:
        await owner.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=8,
            server_settings={"search_path": schema},
        )

        async def local_pool():
            return pool

        monkeypatch.setattr(db, "get_pool", local_pool)
        # Use the SAME create_users_table DDL as the application, rather than
        # the simplified fixture from previous CI tests.
        await create_users_table()
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        try:
            await owner.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await owner.close()


async def create_synthetic_user(pool, email, tenant, role="accountant"):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO users(email,password_hash,tenant_id,role,is_active) "
            "VALUES($1,'synthetic-hash-not-a-password',$2,$3,TRUE) RETURNING id",
            email, tenant, role,
        )


def signed_claims(user_id, email, tenant, role="accountant"):
    return {
        "sub": str(user_id), "email": email,
        "tenant_id": tenant, "role": role,
    }


@pytest.mark.asyncio
async def test_application_created_users_table_has_live_jwt_required_columns(model_db):
    async with model_db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='users'"
        )
        columns = {r["column_name"]: (r["data_type"], r["is_nullable"]) for r in rows}
        assert {
            "id", "email", "password_hash", "role", "tenant_id",
            "is_active", "created_at", "last_login",
        } <= set(columns)
        assert columns["is_active"][0] == "boolean"
        assert columns["role"][0] in ("character varying", "text")
        assert columns["tenant_id"][0] in ("character varying", "text")
        indexes = await conn.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname=current_schema() AND tablename='users'"
        )
        assert any(r["indexname"] == "users_pkey" for r in indexes)


@pytest.mark.asyncio
async def test_two_tenants_same_email_are_isolated_by_user_id_and_tenant(model_db, monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    email = "shared+chat165@example.test"
    alpha = await create_synthetic_user(model_db, email, "t_alpha")
    beta = await create_synthetic_user(model_db, email, "t_beta")
    assert alpha != beta
    assert await auth_service.verify_live_access_membership(
        signed_claims(alpha, email, "t_alpha")
    )
    assert await auth_service.verify_live_access_membership(
        signed_claims(beta, email, "t_beta")
    )
    assert not await auth_service.verify_live_access_membership(
        signed_claims(alpha, email, "t_beta")
    )
    async with model_db.acquire() as conn:
        await conn.execute("UPDATE users SET is_active=FALSE WHERE id=$1", alpha)
    assert not await auth_service.verify_live_access_membership(
        signed_claims(alpha, email, "t_alpha")
    )
    # Revoking tenant A must not revoke the *different* tenant B member.
    assert await auth_service.verify_live_access_membership(
        signed_claims(beta, email, "t_beta")
    )


@pytest.mark.asyncio
async def test_real_model_auth_middleware_respects_enabled_flag(model_db, monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(
        auth_service, "_get_secret_key",
        lambda: "chat165-test-secret-for-disposable-ci-only-2026",
    )
    email = "verified+chat165@example.test"
    user_id = await create_synthetic_user(model_db, email, "t_alpha")
    token = auth_service.create_access_token(signed_claims(user_id, email, "t_alpha"))

    def request():
        return SimpleNamespace(
            url=SimpleNamespace(path="/posting/approved-drafts"),
            method="GET",
            headers={"Authorization": "Bearer " + token, "X-Tenant-ID": "t_beta"},
            query_params={},
            state=SimpleNamespace(tenant_id="t_beta"),
        )

    passed = []
    async def handler(r):
        passed.append(r.state.user_id)
        assert db.require_current_tenant_id() == "t_alpha"
        return JSONResponse({"ok": True})

    assert (await auth_module.auth_middleware(request(), handler)).status_code == 200

    async with model_db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET role='reviewer' WHERE id=$1", user_id
        )
    assert (await auth_module.auth_middleware(request(), handler)).status_code == 401
    assert passed == [str(user_id)]
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
async def test_model_backed_auth_check_local_latency_diagnostic(model_db):
    """Performance *measurement*; NOT a production latency SLA.

    Local container CPU, network, Cloud SQL IAM/proxy and concurrency differ
    from production. Fail only for correctness, never a hard timing threshold.
    """
    email = "perf+chat165@example.test"
    user_id = await create_synthetic_user(model_db, email, "t_alpha")
    claims = signed_claims(user_id, email, "t_alpha")
    sequential = []
    for _ in range(60):
        start = time.perf_counter()
        assert await auth_service.verify_live_access_membership(claims)
        sequential.append((time.perf_counter() - start) * 1000)

    limit = asyncio.Semaphore(8)
    async def concurrent_one():
        async with limit:
            start = time.perf_counter()
            authorized = await auth_service.verify_live_access_membership(claims)
            return authorized, (time.perf_counter() - start) * 1000

    concurrent_results = await asyncio.gather(*(concurrent_one() for _ in range(80)))
    assert all(authorized for authorized, _ in concurrent_results)
    concurrent_ms = sorted(latency for _, latency in concurrent_results)

    def metrics(values):
        ordered = sorted(values)
        return {
            "count": len(ordered),
            "p50_ms": round(statistics.median(ordered), 3),
            "p95_ms": round(ordered[min(len(ordered)-1, int(len(ordered)*0.95))], 3),
            "max_ms": round(max(ordered), 3),
        }

    async with model_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id',true)"
        ) in (None, "")

    print("CHAT165_LOCAL_POSTGRES_AUTH_BENCHMARK " + json.dumps({
        "context": "disposable local PostgreSQL, not Cloud SQL or real staging",
        "application_users_schema": True,
        "pool_max_connections": 8,
        "sequential": metrics(sequential),
        "concurrent_8_workers": metrics(concurrent_ms),
        "correct_authorizations": 140,
        "cloud_sql_latency_not_certified": True,
    }, sort_keys=True))
