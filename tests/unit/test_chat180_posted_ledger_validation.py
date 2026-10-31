"""Actual writer boundary: invalid ledger data must never become INSERTs."""
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


def draft(lines=None):
    return {"id": "synthetic-180", "tenant_id": "t_alpha", "date": "2026-10-29",
            "currency": "GEL", "lines": lines if lines is not None else [
                {"account_code": "1120", "debit": "10.00", "credit": 0},
                {"account_code": "6110", "debit": 0, "credit": "10.00"},
            ]}


@pytest.mark.asyncio
@pytest.mark.parametrize("changes,code", [
    ({"lines": []}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "", "debit": 10}, {"account_code": "6110", "credit": 10}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": "invalid"}, {"account_code": "6110", "credit": 10}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": "NaN"}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": "Infinity"}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": -1}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": 1, "credit": 1}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": 10, "credit": ".001"}, {"account_code": "6110", "credit": 10}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": True}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": "0.004"}]}, "LEDGER_LINES_INVALID"),
    ({"lines": [{"account_code": "1120", "debit": 10}]}, "LEDGER_UNBALANCED"),
    ({"lines": [{"account_code": "1120", "debit": ".005"},
                {"account_code": "1130", "debit": ".005"},
                {"account_code": "6110", "credit": ".01"}]}, "LEDGER_UNBALANCED"),
    ({"id": ""}, "LEDGER_SOURCE_REQUIRED"),
    ({"id": None}, "LEDGER_SOURCE_REQUIRED"),
    ({"date": ""}, "LEDGER_DATE_INVALID"),
    ({"date": "2026-02-30"}, "LEDGER_DATE_INVALID"),
    ({"tenant_id": "t_beta"}, "LEDGER_TENANT_MISMATCH"),
    ({"currency": "USD"}, "FX_RATE_INVALID"),
])
async def test_invalid_writer_input_has_no_insert(changes, code):
    from app.api.services.posting_service import _write_ledger_entries

    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    conn.fetchval.side_effect = [None, uuid4()]
    data = draft()
    data.update(changes)
    with pytest.raises(ValueError, match=code):
        await _write_ledger_entries(conn, data, {}, "t_alpha", "test", "hash")
    assert not any("INSERT" in c.args[0] for c in conn.fetchval.call_args_list)
    assert not any("INSERT" in c.args[0] for c in conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_decimal_precision_survives_header_line_and_gel_bindings():
    from app.api.services.posting_service import _write_ledger_entries

    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    conn.fetchval.side_effect = [None, uuid4()]
    value = Decimal("9007199254740993.01")
    data = draft([{"account_code": "1120", "debit": str(value)},
                  {"account_code": "6110", "credit": str(value)}])
    await _write_ledger_entries(conn, data, {}, "t_alpha", "test", "hash")
    header = conn.fetchval.call_args_list[-1].args
    assert header[7] == value and isinstance(header[7], Decimal)
    assert header[8] == value and isinstance(header[8], Decimal)
    first_line = next(c for c in conn.execute.call_args_list if "INSERT INTO journal_entry_lines" in c.args[0])
    assert first_line.args[5] == value and isinstance(first_line.args[5], Decimal)
    assert first_line.args[9] == value and isinstance(first_line.args[9], Decimal)


@pytest.mark.asyncio
async def test_autocommit_is_rejected_before_any_database_operation():
    from app.api.services.posting_service import _write_ledger_entries

    conn = AsyncMock()
    conn.is_in_transaction = lambda: False
    with pytest.raises(ValueError, match="LEDGER_TRANSACTION_REQUIRED"):
        await _write_ledger_entries(conn, draft(), {}, "t_alpha", "test", "hash")
    conn.execute.assert_not_called()
    conn.fetchval.assert_not_called()
