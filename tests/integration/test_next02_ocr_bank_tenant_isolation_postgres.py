"""Tenant-isolation regression tests using only disposable PostgreSQL."""

from contextlib import asynccontextmanager
import json
import os
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import routes_export, routes_ocr, routes_system
from app.api.db import authenticated_tenant_context
from app.api.services import system_service


EXPECTED_HOST = "127.0.0.1"
EXPECTED_PORT = 55437
EXPECTED_DATABASE = "bridge_hub_next02_test"


def _validate_disposable_dsn(dsn: str) -> None:
    parsed = urlparse(dsn)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != EXPECTED_HOST
        or parsed.port != EXPECTED_PORT
        or parsed.path.lstrip("/") != EXPECTED_DATABASE
    ):
        raise ValueError(
            "Refusing database target; NEXT-02 tests require only "
            "127.0.0.1:55437/bridge_hub_next02_test."
        )


@pytest.fixture
async def tenant_history_db(monkeypatch):
    dsn = os.environ.get("NEXT02_TEST_DATABASE_URL", "")
    if not dsn:
        pytest.skip("NEXT02_TEST_DATABASE_URL is not configured for disposable PostgreSQL")
    _validate_disposable_dsn(dsn)

    import asyncpg

    schema = f"next02_tenant_history_{uuid4().hex}"
    admin_conn = await asyncpg.connect(dsn)
    pool = None
    try:
        await admin_conn.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn,
            min_size=1,
            max_size=3,
            server_settings={"search_path": schema},
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE pipeline_runs (
                    id BIGSERIAL PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    state TEXT NOT NULL,
                    extraction JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE processed_bank_files (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'csv',
                    total_rows INTEGER NOT NULL DEFAULT 0,
                    drafted_count INTEGER NOT NULL DEFAULT 0,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    inserted_count INTEGER NOT NULL DEFAULT 0,
                    skipped_duplicates INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE journal_drafts (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'drafted',
                    review_required BOOLEAN NOT NULL DEFAULT FALSE,
                    bank_file_id BIGINT,
                    date TEXT,
                    description TEXT,
                    partner TEXT,
                    amount NUMERIC(18, 2),
                    debit_account TEXT,
                    credit_account TEXT,
                    account_code TEXT,
                    reason TEXT,
                    confidence NUMERIC(5, 4),
                    source_type TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE bank_transactions (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    amount NUMERIC(18, 2) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            await conn.execute(
                "INSERT INTO bank_transactions (tenant_id, amount) VALUES "
                "('tenant-A', 5.00), ('tenant-B', 500.00)"
            )

            for tenant_id, docs in (
                ("tenant-A", [("a-old.pdf", "DONE", -2), ("a-mid.pdf", "DONE", -1), ("a-new.pdf", "PENDING", 0)]),
                ("tenant-B", [("b-secret.pdf", "REJECTED", 1)]),
            ):
                for filename, state, minute_offset in docs:
                    await conn.execute(
                        """
                        INSERT INTO pipeline_runs (run_id, tenant_id, filename, state, created_at)
                        VALUES ($1, $2, $3, $4, NOW() + ($5 * INTERVAL '1 minute'))
                        """,
                        f"{tenant_id}-{filename}", tenant_id, filename, state, minute_offset,
                    )

            bank_ids = {}
            for tenant_id, filename, file_hash, rows, minute_offset in (
                ("tenant-A", "shared.csv", "same-business-file-hash", 11, 0),
                ("tenant-A", "a-only.csv", "a-hash", 5, -1),
                ("tenant-B", "shared.csv", "same-business-file-hash", 99, 1),
            ):
                bank_ids[tenant_id, filename] = await conn.fetchval(
                    """
                    INSERT INTO processed_bank_files
                        (tenant_id, filename, file_hash, total_rows, created_at)
                    VALUES ($1, $2, $3, $4, NOW() + ($5 * INTERVAL '1 minute'))
                    RETURNING id
                    """,
                    tenant_id, filename, file_hash, rows, minute_offset,
                )

            await conn.execute(
                "INSERT INTO journal_drafts (tenant_id, bank_file_id, description) VALUES ('tenant-B', $1, 'secret draft')",
                bank_ids["tenant-B", "shared.csv"],
            )

        @asynccontextmanager
        async def test_get_conn():
            async with pool.acquire() as conn:
                yield conn

        monkeypatch.setattr(routes_ocr, "get_conn", test_get_conn)
        monkeypatch.setattr(system_service, "get_conn", test_get_conn)
        monkeypatch.setattr(routes_export, "get_conn", test_get_conn)
        yield {"pool": pool, "bank_ids": bank_ids}
    finally:
        if pool is not None:
            await pool.close()
        await admin_conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin_conn.close()


def _request(path: str, *, tenant_id: str = "tenant-A", role: str = "admin", authenticated: bool = True):
    request = Request({"type": "http", "method": "GET", "path": path, "headers": []})
    request.state.authenticated = authenticated
    request.state.role = role
    request.state.tenant_id = tenant_id
    return request


async def _response_bytes(response) -> bytes:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.encode() if isinstance(chunk, str) else chunk)
    return b"".join(chunks)


@pytest.mark.asyncio
async def test_ocr_history_list_count_pagination_and_rbac_are_tenant_scoped(tenant_history_db):
    with pytest.raises(HTTPException) as denied:
        await routes_ocr.ocr_history(_request("/ocr/history", authenticated=False))
    assert denied.value.status_code == 401

    result = await routes_ocr.ocr_history(_request("/ocr/history"), limit=1, offset=1)
    assert result["tenant_id"] == "tenant-A"
    assert result["total"] == 3
    assert result["count"] == 1
    assert [item["filename"] for item in result["items"]] == ["a-mid.pdf"]
    assert all(not item["filename"].startswith("b-") for item in result["items"])


@pytest.mark.asyncio
async def test_ocr_exports_do_not_bypass_history_tenant_scope(tenant_history_db):
    request = _request("/export/documents/csv")
    csv_response = await routes_export.export_documents_csv(request)
    csv_body = (await _response_bytes(csv_response)).decode()
    assert "a-new.pdf" in csv_body
    assert "b-secret.pdf" not in csv_body

    report_response = await routes_export.export_full_report_json(
        _request("/export/report/json")
    )
    report = json.loads(await _response_bytes(report_response))
    assert report["tenant_id"] == "tenant-A"
    assert report["summary"]["total_documents"] == 3
    assert report["summary"]["status_breakdown"] == {"DONE": 2, "PENDING": 1}
    assert report["summary"]["total_inflow_gel"] == 5.0


@pytest.mark.asyncio
async def test_bank_history_count_pagination_and_shared_identifiers_are_scoped(tenant_history_db):
    with authenticated_tenant_context("tenant-A"):
        result = await routes_system.get_bank_files_history(
            _request("/system/bank-files"), limit=1, offset=1
        )
        assert result["ok"] is True
        assert result["data"]["count"] == 2
        assert len(result["data"]["items"]) == 1
        assert result["data"]["items"][0]["filename"] == "a-only.csv"
        assert all(item["id"] != tenant_history_db["bank_ids"]["tenant-B", "shared.csv"]
                   for item in result["data"]["items"])

        own_id = tenant_history_db["bank_ids"]["tenant-A", "shared.csv"]
        own_detail = await routes_system.get_bank_file_detail(
            _request("/system/bank-files/detail"), own_id
        )
        assert own_detail["ok"] is True
        assert own_detail["data"]["id"] == own_id


@pytest.mark.asyncio
async def test_guessed_cross_tenant_bank_ids_return_safe_404_without_mutation(tenant_history_db):
    pool = tenant_history_db["pool"]
    guessed_id = tenant_history_db["bank_ids"]["tenant-B", "shared.csv"]
    async with pool.acquire() as conn:
        before = await conn.fetchrow(
            "SELECT (SELECT count(*) FROM processed_bank_files) AS files, "
            "(SELECT count(*) FROM journal_drafts) AS drafts"
        )

    with authenticated_tenant_context("tenant-A"):
        detail = await routes_system.get_bank_file_detail(
            _request("/system/bank-files/detail"), guessed_id
        )
        assert detail.status_code == 404
        assert b"tenant-B" not in detail.body
        assert b"shared.csv" not in detail.body

        metadata = await routes_system.get_bank_file_drafts(
            _request("/system/bank-files/drafts"), guessed_id, limit=10, offset=0
        )
        assert metadata.status_code == 404
        assert b"tenant-B" not in metadata.body
        assert b"shared.csv" not in metadata.body

    async with pool.acquire() as conn:
        after = await conn.fetchrow(
            "SELECT (SELECT count(*) FROM processed_bank_files) AS files, "
            "(SELECT count(*) FROM journal_drafts) AS drafts"
        )
    assert dict(after) == dict(before)


@pytest.mark.asyncio
async def test_bank_summary_and_overview_metadata_are_tenant_scoped(tenant_history_db):
    with authenticated_tenant_context("tenant-A"):
        summary = await routes_system.get_system_summary(
            _request("/system/summary")
        )
        assert summary["data"]["bank_files_processed"] == 2
        assert summary["data"]["file_stats"]["total_rows_sum"] == 16

        overview = await routes_system.get_system_overview(
            _request("/system/overview")
        )
        assert overview["data"]["summary"]["bank_files"]["total_bank_files"] == 2
        assert {row["filename"] for row in overview["data"]["latest_bank_files"]} == {
            "shared.csv", "a-only.csv"
        }


@pytest.mark.asyncio
async def test_bank_history_and_detail_routes_require_authorization(tenant_history_db):
    with pytest.raises(HTTPException) as unauthenticated:
        await routes_system.get_bank_files_history(
            _request("/system/bank-files", authenticated=False)
        )
    assert unauthenticated.value.status_code == 401

    with pytest.raises(HTTPException) as unauthorized_role:
        await routes_system.get_bank_file_detail(
            _request("/system/bank-files/1", role="viewer"), 1
        )
    assert unauthorized_role.value.status_code == 403


def test_ocr_routes_do_not_expose_an_unscoped_record_detail_path():
    route_paths = {route.path for route in routes_ocr.router.routes}
    assert "/ocr/history" in route_paths
    assert not any(
        path.startswith("/ocr/") and "{" in path
        for path in route_paths
    )
