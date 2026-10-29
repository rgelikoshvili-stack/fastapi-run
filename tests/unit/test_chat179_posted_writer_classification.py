"""Exercise the actual posted writer; no connector, DB or external calls."""
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected", [
    ("6110", "income"), ("7210", "expense"), ("1120", "asset"),
    ("1520", "asset"), ("3110", "liability"), ("4110", "equity"),
    ("custom_unmapped", None),
])
async def test_writer_persists_canonical_classification_not_caller_hint(code, expected):
    from app.api.services.posting_service import _write_ledger_entries

    conn = AsyncMock()
    conn.fetchval.side_effect = [None, "synthetic-header"]
    draft = {
        "id": "synthetic-draft", "date": "2026-10-29", "currency": "GEL",
        "lines": [{"account_code": code, "debit": 10, "credit": 0,
                   "account_type": "caller-forged"},
                  {"account_code": "1120", "debit": 0, "credit": 10}],
    }
    await _write_ledger_entries(conn, draft, {}, "t_alpha", "test", "synthetic")
    calls = [c for c in conn.execute.call_args_list
             if "INSERT INTO journal_entry_lines" in c.args[0]]
    assert len(calls) == 2
    sql, *values = calls[0].args
    assert "account_type" in sql
    assert values[-1] == expected


def test_direct_salary_payment_is_an_operating_cash_outflow():
    from app.api.services.cashflow_classification_service import build_cashflow_from_posted_ledger_rows

    rows = [
        {"header_id": "synthetic", "account_code": "7210", "account_type": "expense",
         "debit": 400, "credit": 0},
        {"header_id": "synthetic", "account_code": "1120", "account_type": "asset",
         "debit": 0, "credit": 400},
    ]
    report = build_cashflow_from_posted_ledger_rows(rows)
    assert report["operating"]["outflows"] == 400
    assert report["net_change_in_cash"] == -400
    assert not report["unknown"]["lines"]
