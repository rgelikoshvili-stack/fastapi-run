"""NEXT-03 credential isolation and atomicity tests against disposable PostgreSQL."""
from contextlib import asynccontextmanager
import os
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg
import json
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
                CREATE TABLE journal_drafts (
                    id BIGINT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    date DATE,
                    description TEXT,
                    partner TEXT,
                    amount NUMERIC,
                    status TEXT,
                    currency TEXT,
                    lines_json JSONB NOT NULL DEFAULT '[]'::jsonb
                );
                CREATE TABLE period_locks (
                    tenant_id TEXT NOT NULL,
                    period_year INTEGER NOT NULL,
                    period_month INTEGER NOT NULL,
                    unlocked_at TIMESTAMPTZ
                );
                CREATE TABLE posting_logs (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    draft_id BIGINT NOT NULL,
                    target_system TEXT NOT NULL,
                    payload_json JSONB,
                    response_json JSONB,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    entry_hash TEXT,
                    source_draft_id BIGINT,
                    mode TEXT,
                    actor TEXT,
                    connector TEXT,
                    idempotency_key TEXT
                );
                CREATE UNIQUE INDEX posting_logs_entry_hash_unique
                    ON posting_logs (entry_hash) WHERE entry_hash IS NOT NULL;
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


@pytest.mark.asyncio
@pytest.mark.parametrize("test_mode, expected_mode", [("0", "unavailable"), ("1", "demo")])
async def test_missing_balance_credential_never_creates_successful_posting_state(
    credential_db, monkeypatch, test_mode, expected_mode
):
    """The production posting workflow stops at connector readiness when the vault is empty."""
    monkeypatch.setenv("TEST_MODE", test_mode)
    async with credential_db.acquire() as conn:
        await conn.execute("""
            INSERT INTO journal_drafts
                (id, tenant_id, status, amount, currency, lines_json)
            VALUES
                (9001, 'tenant-empty', 'approved', 25.00, 'GEL',
                 '[{"account_code":"1000","debit":25,"credit":0},'
                 '{"account_code":"3000","debit":0,"credit":25}]'::jsonb)
        """)

    from unittest.mock import AsyncMock, patch
    from app.api.services import posting_service

    with patch.object(posting_service, "get_conn", credentials.get_conn), \
         patch.object(posting_service, "_is_connector_disabled", new_callable=AsyncMock, return_value=False), \
         patch.object(posting_service, "log_event"), \
         patch.object(posting_service, "structured_log"), \
         patch("app.api.connectors.balance_connector.requests.post") as live_post, \
         patch("app.api.connectors.balance_connector.requests.get") as live_get:
        result = await posting_service.apply_posting_service(9001, "balance", "tenant-empty")

    assert result["ok"] is False
    assert result["error"]["code"] == "CONNECTOR_NOT_READY"
    live_post.assert_not_called()
    live_get.assert_not_called()
    async with credential_db.acquire() as conn:
        draft_status = await conn.fetchval(
            "SELECT status FROM journal_drafts WHERE id = 9001 AND tenant_id = 'tenant-empty'"
        )
        rows = await conn.fetch(
            "SELECT status, response_json FROM posting_logs WHERE draft_id = 9001"
        )
        vault_rows = await conn.fetchval(
            "SELECT count(*) FROM credential_vault_credentials WHERE tenant_id = 'tenant-empty'"
        )
        metadata_rows = await conn.fetchval(
            "SELECT count(*) FROM tenant_balance_credentials WHERE tenant_id = 'tenant-empty'"
        )

    assert draft_status == "approved"
    assert len(rows) == 1
    assert rows[0]["status"] == "config_missing"
    response = rows[0]["response_json"]
    if isinstance(response, str):
        response = json.loads(response)
    assert response["status"].get("mode") == expected_mode
    assert "erp_id" not in response and "external_id" not in response
    assert vault_rows == 0
    assert metadata_rows == 0


@pytest.mark.asyncio
async def test_missing_vault_reference_is_invalid_even_when_test_demo_is_enabled(credential_db, monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    async with credential_db.acquire() as conn:
        await conn.execute("""
            INSERT INTO tenant_balance_credentials
                (tenant_id, company_id, credential_status)
            VALUES ('tenant-stale-ref', 'COMP-STALE', 'vault')
        """)

    async_result = await credentials.get_balance_credentials("tenant-stale-ref")
    sync_result = credentials.get_balance_credentials_sync("tenant-stale-ref")

    from app.api.connectors.balance_connector import BalanceConnector
    from unittest.mock import patch
    with patch("app.api.connectors.balance_connector.requests.post") as live_post:
        connector = BalanceConnector(tenant_id="tenant-stale-ref")
        result = connector.post({"account_dr": "1000", "account_cr": "2000", "amount": 1})

    assert async_result["api_key"] == sync_result["api_key"] == ""
    assert async_result["credential_status"] == sync_result["credential_status"] == "invalid_reference"
    assert connector.mode == "unavailable"
    assert result["success"] is False
    assert result["erp_id"] is None
    live_post.assert_not_called()
    async with credential_db.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM tenant_balance_credentials WHERE tenant_id = 'tenant-stale-ref'"
        ) == 1
        assert await conn.fetchval(
            "SELECT count(*) FROM credential_vault_credentials WHERE tenant_id = 'tenant-stale-ref'"
        ) == 0
