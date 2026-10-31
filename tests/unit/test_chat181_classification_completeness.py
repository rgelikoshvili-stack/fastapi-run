"""FIN-04: unknown classifications cannot silently erase official money."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

CODE="LEDGER_CLASSIFICATION_INCOMPLETE"


@pytest.mark.asyncio
async def test_writer_refuses_unmapped_account_before_any_insert():
    from app.api.services.posting_service import _write_ledger_entries
    conn=AsyncMock();conn.is_in_transaction=lambda:True
    conn.fetchval.side_effect=[None,uuid4()]
    draft={"id":"coa181","date":"2026-10-30","currency":"GEL","lines":[
        {"account_code":"1120","debit":10},
        {"account_code":"custom_unmapped","credit":10,"account_type":"income"}]}
    with pytest.raises(ValueError,match="LEDGER_ACCOUNT_UNCLASSIFIED"):
        await _write_ledger_entries(conn,draft,{},"t_alpha","test","hash")
    assert not any("INSERT" in c.args[0] for c in conn.fetchval.call_args_list+conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_bridge_authority_payload_rejects_unmapped_account_before_dispatch(monkeypatch):
    from app.api.services import posting_service as posting
    monkeypatch.setenv("POSTED_LEDGER_WRITES_ENABLED","true")
    draft={"id":"coa181","date":"2026-10-30","currency":"GEL","amount":10,"lines":[
        {"account_code":"1120","debit":10},{"account_code":"custom_unmapped","credit":10}]}
    with pytest.raises(ValueError,match="LEDGER_ACCOUNT_UNCLASSIFIED"):
        await posting._draft_to_posting_payload(draft)


@pytest.mark.asyncio
@pytest.mark.parametrize("reader",["pnl","balance","cashflow","trial","asof"])
async def test_incomplete_classification_is_unavailable_not_partial(monkeypatch,reader):
    from app.api.services import financial_statements_service as finance,ledger_service as ledger
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED","1")
    row={"account_code":"1120","account_type":"asset","total_debit":10,"total_credit":0,
         "debit":10,"credit":0,"cashflow_category":"operating","line_id":"l","header_id":"h",
         "fx_invalid_count":0,"classification_invalid_count":1}
    @asynccontextmanager
    async def connection():
        conn=AsyncMock();conn.fetch.return_value=[row];yield conn
    monkeypatch.setattr(finance,"get_conn",connection);monkeypatch.setattr(ledger,"get_conn",connection)
    if reader=="asof":
        with pytest.raises(ValueError,match=CODE):await finance._get_posted_trial_balance_as_of("t_alpha",None)
    else:
        result=await {"pnl":finance.build_profit_and_loss,"balance":finance.build_balance_sheet,
                      "cashflow":finance.build_cashflow_statement,"trial":ledger.get_trial_balance}[reader]("t_alpha")
        assert (result.get("error") if reader=="trial" else (result.get("error") or {}).get("code"))==CODE


@pytest.mark.asyncio
@pytest.mark.parametrize("reader",["pnl","balance"])
async def test_unmapped_legacy_account_cannot_disappear_from_statements(monkeypatch,reader):
    from app.api.services import financial_statements_service as finance
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED",raising=False)
    @asynccontextmanager
    async def connection():
        conn=AsyncMock();conn.fetch.return_value=[{"account_code":"CUSTOM_UNKNOWN","side":"credit","total":100}];yield conn
    monkeypatch.setattr(finance,"get_conn",connection)
    result=await {"pnl":finance.build_profit_and_loss,"balance":finance.build_balance_sheet}[reader]("t_alpha")
    assert not result["ok"] and result["error"]["code"]==CODE
