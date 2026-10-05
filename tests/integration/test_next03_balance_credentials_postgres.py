"""NEXT-03 credential isolation and atomicity tests against disposable PostgreSQL."""
from contextlib import asynccontextmanager
import os
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg
import psycopg2
import pytest

from app.api.services import balance_credentials_service as credentials


EXPECTED_HOST = "127.0.0.1"
EXPECTED_PORT = 55438
EXPECTED_DATABASE = "bridge_hub_next03_test"


def _validate_disposable_dsn(dsn: str) -> None:
    parsed = urlparse(dsn)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != EXPECTED_HOST
        or parsed.port != EXPECTED_PORT
        or parsed.path.lstrip("/") != EXPECTED_DATABASE
    ):
        raise ValueError("Refusing database target; NEXT-03 requires its disposable PostgreSQL service.")


@pytest.fixture
async def credential_db(monkeypatch):
    dsn = os.environ.get("NEXT03_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("NEXT03_TEST_DATABASE_URL is not configured for disposable PostgreSQL")
    _validate_disposable_dsn(dsn)
    monkeypatch.setenv("TEST_MODE", "1")
    schema = f"next03_credentials_{uuid4().hex}"
    admin = await asyncpg.connect(dsn)
    pool = None
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=3, server_settings={"search_path": schema}
        )
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE credential_vault_credentials (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    credential_type TEXT NOT NULL,
                    encrypted_value TEXT NOT NULL,
                    key_version TEXT NOT NULL,
                    masked_hint TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    company_id TEXT,
                    api_base TEXT,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    last_test_status TEXT,
                    last_tested_at TIMESTAMPTZ,
                    last_accessed_at TIMESTAMPTZ,
                    rotated_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    created_by TEXT,
                    updated_by TEXT,
                    UNIQUE (tenant_id, provider, credential_type)
                );
                CREATE TABLE credential_vault_audit_events (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    credential_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT,
                    purpose TEXT,
                    result TEXT NOT NULL,
                    key_version TEXT,
                    request_id TEXT,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE tenant_balance_credentials (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL UNIQUE,
                    api_key TEXT,
                    company_id TEXT,
                    api_base TEXT DEFAULT 'https://api.balance.ge',
                    masked_hint TEXT,
                    credential_status TEXT DEFAULT 'legacy_plaintext',
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

        @asynccontextmanager
        async def test_get_conn():
            async with pool.acquire() as conn:
                yield conn

        def test_get_db(tenant_id=None):
            # Exact synthetic DSN plus schema search_path; never reads DATABASE_URL.
            return psycopg2.connect(dsn, options=f"-c search_path={schema}")

        monkeypatch.setattr(credentials, "get_conn", test_get_conn)
        monkeypatch.setattr(credentials, "get_db", test_get_db)
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()


@pytest.mark.asyncio
async def test_vault_save_persists_only_ciphertext_and_safe_metadata(credential_db):
    raw = "synthetic_balance_credential_tenant_a"
    assert await credentials.save_balance_credentials("tenant-A", raw, "COMP-A")
    async with credential_db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT v.encrypted_value, b.api_key, b.company_id, b.credential_status
            FROM credential_vault_credentials v
            JOIN tenant_balance_credentials b USING (tenant_id)
            WHERE v.tenant_id = 'tenant-A'
        """)
    assert row["encrypted_value"] != raw
    assert row["api_key"] is None
    assert row["company_id"] == "COMP-A"
    assert row["credential_status"] == "vault"


@pytest.mark.asyncio
async def test_vault_failure_denies_save_without_plaintext_or_partial_config(credential_db):
    async with credential_db.acquire() as conn:
        await conn.execute("""
            CREATE FUNCTION reject_vault_insert() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic vault outage'; END $$;
            CREATE TRIGGER reject_vault BEFORE INSERT ON credential_vault_credentials
            FOR EACH ROW EXECUTE FUNCTION reject_vault_insert();
        """)
    with pytest.raises(RuntimeError, match="BALANCE_CREDENTIAL_SAVE_FAILED"):
        await credentials.save_balance_credentials("tenant-fail", "synthetic_vault_failure_key")
    async with credential_db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM credential_vault_credentials") == 0
        assert await conn.fetchval("SELECT count(*) FROM tenant_balance_credentials") == 0


@pytest.mark.asyncio
async def test_metadata_failure_rolls_back_vault_credential(credential_db):
    async with credential_db.acquire() as conn:
        await conn.execute("""
            CREATE FUNCTION reject_metadata_insert() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic metadata outage'; END $$;
            CREATE TRIGGER reject_metadata BEFORE INSERT ON tenant_balance_credentials
            FOR EACH ROW EXECUTE FUNCTION reject_metadata_insert();
        """)
    with pytest.raises(RuntimeError, match="BALANCE_CREDENTIAL_SAVE_FAILED"):
        await credentials.save_balance_credentials("tenant-rollback", "synthetic_rollback_key")
    async with credential_db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM credential_vault_credentials") == 0
        assert await conn.fetchval("SELECT count(*) FROM tenant_balance_credentials") == 0


@pytest.mark.asyncio
async def test_tenant_reads_are_scoped_and_missing_tenant_never_uses_shared_key(credential_db, monkeypatch):
    key_a = "synthetic_vault_credential_tenant_a"
    key_b = "synthetic_vault_credential_tenant_b"
    await credentials.save_balance_credentials("tenant-A", key_a)
    await credentials.save_balance_credentials("tenant-B", key_b)
    monkeypatch.setenv("BALANCE_API_KEY", "synthetic_shared_global_key")

    a = await credentials.get_balance_credentials("tenant-A")
    b = await credentials.get_balance_credentials("tenant-B")
    missing = await credentials.get_balance_credentials("tenant-missing")
    sync_a = credentials.get_balance_credentials_sync("tenant-A")
    sync_b = credentials.get_balance_credentials_sync("tenant-B")
    sync_missing = credentials.get_balance_credentials_sync("tenant-missing")

    assert a["api_key"] == sync_a["api_key"] == key_a
    assert b["api_key"] == sync_b["api_key"] == key_b
    assert a["api_key"] != b["api_key"]
    assert missing["api_key"] == sync_missing["api_key"] == ""
    assert missing["source"] == sync_missing["source"] == "none"


@pytest.mark.asyncio
async def test_legacy_raw_row_is_never_returned_and_is_rotation_required(credential_db):
    async with credential_db.acquire() as conn:
        await conn.execute("""
            INSERT INTO tenant_balance_credentials
                (tenant_id, api_key, credential_status)
            VALUES ('tenant-legacy', 'synthetic_legacy_only_key', 'legacy_plaintext')
        """)
    result = await credentials.get_balance_credentials("tenant-legacy")
    sync_result = credentials.get_balance_credentials_sync("tenant-legacy")
    status = await credentials.get_vault_status("tenant-legacy")

    assert result["api_key"] == sync_result["api_key"] == ""
    assert result["credential_status"] == sync_result["credential_status"] == "rotation_required"
    assert status["configured"] is False
    assert status["status"] == "rotation_required"
    assert "synthetic_legacy_only_key" not in str(status)
