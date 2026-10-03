"""Real PostgreSQL integration coverage for PR #127 cashflow/CFO reports.

This module is opt-in through PR127_TEST_DATABASE_URL. It rejects non-local
hosts and database names that do not clearly identify a disposable test DB.
It creates an isolated schema and never reads the application's DATABASE_URL.
"""
from __future__ import annotations

import os
from datetime import date
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg
import pytest


TEST_DSN = os.getenv("PR127_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_DSN,
    reason="PR127_TEST_DATABASE_URL is reserved for a disposable PostgreSQL DB",
)


def _assert_disposable_local_dsn(dsn: str) -> None:
    parsed = urlparse(dsn)
    database = parsed.path.lstrip("/").lower()
    assert parsed.scheme in {"postgres", "postgresql"}
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1", "postgres"}
    assert any(marker in database for marker in ("test", "disposable", "pr127"))


@pytest.fixture
async def posted_ledger_db(monkeypatch):
    _assert_disposable_local_dsn(TEST_DSN)
    schema = f"pr127_cashflow_{uuid4().hex}"
    admin = await asyncpg.connect(TEST_DSN)
    pool = None
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            TEST_DSN,
            min_size=1,
            max_size=3,
            server_settings={"search_path": schema},
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE journal_entry_headers (
                    id UUID PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entry_date DATE NOT NULL
                );
                CREATE TABLE journal_entry_lines (
                    id UUID PRIMARY KEY,
                    journal_entry_id UUID NOT NULL REFERENCES journal_entry_headers(id),
                    tenant_id TEXT NOT NULL,
                    account_code TEXT NOT NULL,
                    account_type TEXT,
                    cashflow_category TEXT,
                    debit NUMERIC(18,2) NOT NULL DEFAULT 0,
                    credit NUMERIC(18,2) NOT NULL DEFAULT 0,
                    description TEXT
                );
                CREATE TABLE journal_drafts (
                    tenant_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    journal_entries JSONB NOT NULL DEFAULT '[]'::jsonb
                );
                CREATE TABLE rsge_documents (
                    tenant_id TEXT NOT NULL,
                    mismatch_type TEXT,
                    risk_level TEXT
                );
                CREATE TABLE rsge_waybills (
                    tenant_id TEXT NOT NULL,
                    linked_invoice_id TEXT
                );
                CREATE TABLE period_locks (
                    tenant_id TEXT NOT NULL,
                    period_key TEXT NOT NULL
                );
                """
            )

        from app.api import db

        monkeypatch.setattr(db, "_async_pool", pool)
        await _seed_posted_rows(pool)
        yield pool
    finally:
        if pool is not None:
            await pool.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()


async def _seed_posted_rows(pool):
    entries = [
        # Cash category is authoritative even though the counterpart category
        # disagrees; this is an operating inflow of 100.
        ("tenant-a", "posted", "2026-09-01", [
            ("1120", "asset", "operating", 100, 0, "receipt"),
            ("6110", "income", "financing", 0, 100, "revenue"),
        ]),
        ("tenant-a", "posted", "2026-09-10", [
            ("1510", "asset", "investing", 30, 0, "asset purchase"),
            ("1120", "asset", None, 0, 30, "bank payment"),
        ]),
        # Compound entry: one cash movement against two counterpart lines.
        ("tenant-a", "posted", "2026-09-15", [
            ("1120", "asset", "operating", 60, 0, "compound receipt"),
            ("6110", "income", None, 0, 35, "revenue one"),
            ("6120", "income", None, 0, 25, "revenue two"),
        ]),
        # Invalid legacy fallback metadata must remain unclassified, not financing.
        ("tenant-a", "posted", "2026-09-20", [
            ("1120", "asset", None, 7, 0, "guarded fallback"),
            ("3410", "income", None, 0, 7, "incorrect account type"),
        ]),
        ("tenant-a", "posted", "2026-10-02", [
            ("1120", "asset", "financing", 50, 0, "loan receipt"),
            ("3410", "liability", None, 0, 50, "loan"),
        ]),
        ("tenant-b", "posted", "2026-09-12", [
            ("1120", "asset", "financing", 9000, 0, "other tenant receipt"),
            ("3410", "liability", None, 0, 9000, "other tenant loan"),
        ]),
        # A non-posted ledger header must not be treated as official activity.
        ("tenant-a", "reversed", "2026-09-18", [
            ("1120", "asset", "operating", 5000, 0, "reversed receipt"),
            ("6110", "income", None, 0, 5000, "reversed revenue"),
        ]),
    ]
    async with pool.acquire() as conn:
        for tenant_id, status, entry_date, lines in entries:
            header_id = uuid4()
            await conn.execute(
                "INSERT INTO journal_entry_headers (id, tenant_id, status, entry_date) VALUES ($1,$2,$3,$4)",
                header_id, tenant_id, status, date.fromisoformat(entry_date),
            )
            for line_no, (code, account_type, category, debit, credit, description) in enumerate(lines, 1):
                await conn.execute(
                    """INSERT INTO journal_entry_lines
                       (id, journal_entry_id, tenant_id, account_code, account_type,
                        cashflow_category, debit, credit, description)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    uuid4(), header_id, tenant_id, code, account_type, category,
                    debit, credit, description,
                )
        # Deliberately conflicting draft data proves official cashflow and cash
        # position do not quietly substitute journal_drafts values.
        await conn.execute(
            """INSERT INTO journal_drafts (tenant_id, status, journal_entries)
               VALUES ($1, 'draft', $2::jsonb)""",
            "tenant-a", '[{"dr":"1120","amount":"999999"}]',
        )


@pytest.mark.asyncio
async def test_pr127_cashflow_and_cfo_against_disposable_postgres(
    posted_ledger_db, monkeypatch,
):
    from app.api.services import cfo_dashboard_service as dashboard
    from app.api.services import financial_statements_service as statements

    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")

    all_data = await statements.build_cashflow_statement("tenant-a")
    assert all_data["ok"] is True
    assert all_data["data"]["operating"]["inflows"] == 160
    assert all_data["data"]["investing"]["outflows"] == 30
    assert all_data["data"]["financing"]["inflows"] == 50
    assert any(
        line["amount"] == 7 and line["category"] == "unknown"
        for line in all_data["data"]["unknown"]["lines"]
    )
    # The compound journal has one cash line for 60, not a multiplied 120.
    compound_lines = [
        row for section in ("operating", "investing", "financing")
        for row in all_data["data"][section]["lines"]
        if row.get("description") == "compound receipt"
    ]
    assert len(compound_lines) == 1
    assert compound_lines[0]["amount"] == 60
    assert "journal_drafts" not in all_data["data"]

    tenant_b_data = await statements.build_cashflow_statement("tenant-b")
    assert tenant_b_data["data"]["financing"]["inflows"] == 9000
    assert tenant_b_data["data"]["operating"]["inflows"] == 0

    bounded = await statements.build_cashflow_statement(
        "tenant-a", date_from="2026-09-10", date_to="2026-09-30"
    )
    assert bounded["data"]["operating"]["inflows"] == 60
    assert bounded["data"]["investing"]["outflows"] == 30
    assert bounded["data"]["financing"]["inflows"] == 0

    date_to_only = await statements.build_cashflow_statement("tenant-a", date_to="2026-09-10")
    assert date_to_only["data"]["operating"]["inflows"] == 100
    assert date_to_only["data"]["investing"]["outflows"] == 30

    dashboard_result = await dashboard.build_cfo_dashboard(
        "tenant-a", date_to="2026-09-30"
    )
    cash = dashboard_result["cash_position"]
    assert cash["available"] is True
    assert cash["source"] == "posted_ledger"
    assert cash["as_of"] == "2026-09-30"
    assert cash["bank_1120"] == 137
    assert cash["total_liquid"] == 137

    # Force a genuine PostgreSQL query error inside this disposable schema.
    async with posted_ledger_db.acquire() as conn:
        await conn.execute("DROP TABLE journal_entry_lines")
    unavailable = await statements.build_cashflow_statement("tenant-a")
    assert unavailable["ok"] is False
    assert unavailable["error"]["code"] == "POSTED_LEDGER_UNAVAILABLE"
    assert unavailable["data"] is None
