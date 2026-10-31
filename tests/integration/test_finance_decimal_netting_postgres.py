"""Actual NUMERIC -> reports/AI under disposable nonowner FORCE RLS only."""
import json
from uuid import uuid4

import pytest

from app.api import db
from app.api.services import financial_statements_service as finance
from app.api.services import ledger_service as ledger
from app.api.services import chat_context_service as chat
from app.api.services.ai_tool_registry import run_tool
from app.api.services.posting_service import _write_ledger_entries
from tests.integration.test_chat167_auth_forced_rls_postgres import auth_db, _chat179_prepare_ledger


@pytest.mark.parametrize("posted", [True, False], ids=["posted-ledger", "legacy-gel"])
async def test_large_offsetting_turnovers_keep_one_cent_across_reports_and_ai(auth_db, monkeypatch, posted):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1" if posted else "0")
    await _chat179_prepare_ledger(auth_db)
    async with auth_db["admin"].acquire() as conn:
        await conn.execute("""
            CREATE TABLE journal_drafts (
                id SERIAL PRIMARY KEY, tenant_id TEXT, status TEXT, date TEXT,
                currency TEXT, journal_entries JSONB, confidence NUMERIC, amount NUMERIC);
            CREATE TABLE bank_accounts (tenant_id TEXT, name TEXT, balance NUMERIC, currency TEXT);
        """)
        for table in ("journal_drafts", "bank_accounts"):
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            await conn.execute(f'GRANT SELECT ON {table} TO "{auth_db["role"]}"')
            await conn.execute(f"""CREATE POLICY decimal_netting_tenant ON {table}
                USING (tenant_id=current_setting('app.current_tenant_id',true))""")

    async def post(tenant, dr, cr, amount, day="2026-10-15"):
        if posted:
            with db.authenticated_tenant_context(tenant):
                async with db.get_conn() as conn:
                    await _write_ledger_entries(conn, {
                        "id": str(uuid4()), "date": day, "currency": "GEL",
                        "lines": [{"account_code": dr, "debit": amount},
                                  {"account_code": cr, "credit": amount}],
                    }, {}, tenant, "synthetic", "decimal-netting")
        else:
            async with auth_db["admin"].acquire() as conn:
                await conn.execute("""INSERT INTO journal_drafts
                    (tenant_id,status,date,currency,journal_entries)
                    VALUES ($1,'posted',$2,'GEL',$3::jsonb)""", tenant, day,
                    json.dumps([{"dr": dr, "amount": amount}, {"cr": cr, "amount": amount}]))

    await post("t_alpha", "1120", "6110", "9007199254740992.01")
    await post("t_alpha", "6110", "1120", "9007199254740992.00")
    await post("t_beta", "1120", "6110", "999.99")
    source_table = "journal_entry_lines" if posted else "journal_drafts"
    async with auth_db["admin"].acquire() as conn:
        before = await conn.fetch(f"SELECT * FROM {source_table} ORDER BY id")
    with db.authenticated_tenant_context("t_alpha"):
        pnl = await finance.build_profit_and_loss("t_alpha", None, "2026-10-31")
        bs = await finance.build_balance_sheet("t_alpha", "2026-10-31")
        trial = await ledger.get_trial_balance("t_alpha", None, "2026-10-31")
        assert pnl["ok"] and pnl["data"]["ebit"] == 0.01, pnl
        assert bs["ok"] and bs["data"]["assets"]["total"] == 0.01, bs
        assert bs["data"]["equity"]["unclosed_result"] == 0.01
        assert bs["data"]["balanced"] is True
        nets = {r["account_code"]: r["net"] for r in trial["accounts"]}
        assert nets == {"1120": 0.01, "6110": -0.01}
        assert trial["balanced"] is True and trial["closing_total"] == 0
        if posted:
            balances = await finance._get_posted_trial_balance_as_of("t_alpha", "2026-10-31")
            assert balances == {"1120": 0.01, "6110": -0.01}
            context = await chat.build_chat_context("t_alpha", "P&L")
            tool = await run_tool("financial_summary", {}, "t_alpha")
            assert context["reports_summary"]["profit"] == 0.01
            assert tool["preview"]["profit"] == "0.01 GEL", tool
    with db.authenticated_tenant_context("t_beta"):
        other = await finance.build_profit_and_loss("t_beta", None, "2026-10-31")
        assert other["ok"] and other["data"]["ebit"] == 999.99
    async with auth_db["admin"].acquire() as conn:
        assert await conn.fetch(f"SELECT * FROM {source_table} ORDER BY id") == before
    async with auth_db["runtime"].acquire() as conn:
        assert await conn.fetchval(f"SELECT count(*) FROM {source_table}") == 0
