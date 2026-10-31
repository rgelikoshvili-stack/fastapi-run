"""Actual writer -> disposable forced-RLS PG15/16 -> balanced equity.

Reuses only the dedicated localhost disposable fixture. No provider dispatch,
live schema, role grant, migration or financial data is accessed.
"""
from datetime import date
from uuid import uuid4

import pytest

from app.api import db
from app.api.services import financial_statements_service as finance
from app.api.services.posting_service import _write_ledger_entries
from tests.integration.test_chat167_auth_forced_rls_postgres import (
    auth_db, _chat179_prepare_ledger,
)


@pytest.mark.asyncio
async def test_unclosed_fx_profit_closing_entries_asof_and_tenant_isolation(auth_db, monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 31)

    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    monkeypatch.setattr(finance, "date", FixedDate)
    await _chat179_prepare_ledger(auth_db)

    async def post(tenant, day, dr, cr, amount, currency="GEL", rate="1"):
        with db.authenticated_tenant_context(tenant):
            async with db.get_conn() as conn:
                await _write_ledger_entries(conn, {
                    "id": str(uuid4()), "date": day, "currency": currency,
                    "lines": [{"account_code": dr, "debit": amount},
                              {"account_code": cr, "credit": amount}],
                }, {"exchange_rate": rate}, tenant, "synthetic", "fin08")

    await post("t_alpha", "2026-09-01", "1120", "4110", "50")
    await post("t_alpha", "2026-09-02", "1120", "4210", "40")
    await post("t_alpha", "2026-10-10", "1120", "6110", "100", "USD", "2.5")
    await post("t_alpha", "2026-10-20", "7210", "1120", "30")
    await post("t_alpha", "2099-01-01", "1120", "6110", "90000")
    await post("t_beta", "2026-10-10", "1120", "6110", "9999")

    async with auth_db["admin"].acquire() as conn:
        before = await conn.fetch("SELECT * FROM journal_entry_lines ORDER BY id")
    with db.authenticated_tenant_context("t_alpha"):
        for asof in ("2026-10-30", None):
            result = await finance.build_balance_sheet("t_alpha", asof)
            assert result["ok"], result
            data = result["data"]
            assert data["assets"]["total"] == 310
            assert data["equity"]["total"] == 310
            assert data["equity"]["unclosed_result"] == 220
            assert data["balanced"] is True
        pnl = await finance.build_profit_and_loss("t_alpha", None, "2026-10-30")
        assert pnl["ok"] and pnl["data"]["ebit"] == 220
        opening = await finance.build_balance_sheet("t_alpha", "2026-10-09")
        assert opening["ok"] and opening["data"]["equity"]["total"] == 90
        assert opening["data"]["equity"]["unclosed_result"] == 0
    async with auth_db["admin"].acquire() as conn:
        assert await conn.fetch("SELECT * FROM journal_entry_lines ORDER BY id") == before

    # Closing entries transfer existing earnings to 4210; no inferred journal.
    await post("t_alpha", "2026-10-31", "6110", "4210", "100", "USD", "2.5")
    await post("t_alpha", "2026-10-31", "4210", "7210", "30")
    with db.authenticated_tenant_context("t_alpha"):
        closed = await finance.build_balance_sheet("t_alpha", "2026-10-31")
        assert closed["ok"], closed
        assert closed["data"]["equity"]["unclosed_result"] == 0
        assert closed["data"]["equity"]["total"] == 310
        assert closed["data"]["assets"]["total"] == 310
        assert closed["data"]["balanced"] is True
    with db.authenticated_tenant_context("t_beta"):
        other = await finance.build_balance_sheet("t_beta", "2026-10-31")
        assert other["ok"] and other["data"]["equity"]["total"] == 9999
        assert other["data"]["equity"]["unclosed_result"] == 9999
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM journal_entry_lines") == 0
