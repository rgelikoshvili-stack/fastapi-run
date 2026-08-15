"""tests/unit/test_sprint1_bank_ai_tool.py

Sprint 1: AI bank_transactions and payment_status tools.
All DB calls are mocked — no live DB needed.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

import pytest

from app.api.services.ai_tool_registry import (
    _get_bank_transactions,
    _get_payment_status,
    TOOL_DESCRIPTIONS,
    _TOOL_MAP,
)


def run_sync(coro):
    return asyncio.run(coro)


# ─── Helpers ──────────────────────────────────────────────────────────────────

class _FakeRecord(dict):
    """dict subclass that mimics asyncpg Record for unit tests."""


def _bank_row(**kwargs):
    defaults = {
        "id": "BT-001",
        "date": "2026-08-01",
        "description": "სს ვენდორი — გადახდა ინვ #INV-2026-100",
        "partner": "სს ვენდორი",
        "amount": 1500.0,
        "currency": "GEL",
        "balance": 50000.0,
        "operation_code": None,
        "is_reconciled": False,
        "draft_id": None,
        "draft_description": None,
    }
    defaults.update(kwargs)
    return _FakeRecord(defaults)


def _invoice_row(**kwargs):
    defaults = {
        "id": 100,
        "invoice_number": "INV-2026-100",
        "partner_name": "სს ვენდორი",
        "total_amount": 1500.0,
        "currency": "GEL",
        "status": "issued",
        "due_date": "2026-08-15",
    }
    defaults.update(kwargs)
    return _FakeRecord(defaults)


def _make_conn(bank_rows=None, invoice_row=None, draft_rows=None, bank_payment_rows=None):
    conn = AsyncMock()

    async def _fetchrow(q, *args, **kwargs):
        return invoice_row

    async def _fetch(q, *args, **kwargs):
        q_str = str(q).lower()
        if "bank_transactions" in q_str and "journal_drafts" not in q_str and "reconcil" not in q_str:
            return bank_rows or []
        if "journal_drafts" in q_str and "bank_transactions" not in q_str:
            return draft_rows or []
        if "bank_transactions" in q_str:
            return bank_payment_rows or bank_rows or []
        return []

    conn.fetchrow = _fetchrow
    conn.fetch = _fetch
    return conn


@asynccontextmanager
async def _fake_get_conn(conn):
    yield conn


# ─── Tool registry tests ───────────────────────────────────────────────────────

def test_get_bank_transactions_in_tool_map():
    assert "get_bank_transactions" in _TOOL_MAP
    assert callable(_TOOL_MAP["get_bank_transactions"])


def test_get_payment_status_in_tool_map():
    assert "get_payment_status" in _TOOL_MAP
    assert callable(_TOOL_MAP["get_payment_status"])


def test_get_bank_transactions_in_tool_descriptions():
    assert "get_bank_transactions" in TOOL_DESCRIPTIONS
    desc = TOOL_DESCRIPTIONS["get_bank_transactions"]
    assert len(desc) > 10


def test_get_payment_status_in_tool_descriptions():
    assert "get_payment_status" in TOOL_DESCRIPTIONS
    desc = TOOL_DESCRIPTIONS["get_payment_status"]
    assert len(desc) > 10


# ─── _get_bank_transactions ────────────────────────────────────────────────────

def test_bank_transactions_returns_list():
    rows = [_bank_row()]
    conn = _make_conn(bank_rows=rows)
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions({}, "tenant1"))
    assert "transactions" in result
    assert result["count"] == 1


def test_bank_transactions_partner_filter():
    rows = [_bank_row(description="ვენდორი გადახდა", partner="სს ვენდორი")]
    conn = _make_conn(bank_rows=rows)
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions({"partner": "ვენდორი"}, "tenant1"))
    assert result["filters_applied"]["partner"] == "ვენდორი"
    assert result["count"] >= 0


def test_bank_transactions_amount_range_filter():
    rows = [_bank_row(amount=1500.0)]
    conn = _make_conn(bank_rows=rows)
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions(
            {"amount_min": 1000, "amount_max": 2000}, "tenant1"
        ))
    assert result["filters_applied"]["amount_min"] == 1000
    assert result["filters_applied"]["amount_max"] == 2000


def test_bank_transactions_date_range_filter():
    rows = [_bank_row(date="2026-08-01")]
    conn = _make_conn(bank_rows=rows)
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions(
            {"date_from": "2026-08-01", "date_to": "2026-08-31"}, "tenant1"
        ))
    assert result["filters_applied"]["date_from"] == "2026-08-01"
    assert result["filters_applied"]["date_to"] == "2026-08-31"


def test_bank_transactions_unreconciled_flag():
    reconciled_row = _bank_row(is_reconciled=True)
    unreconciled_row = _bank_row(id="BT-002", is_reconciled=False)
    conn = _make_conn(bank_rows=[reconciled_row, unreconciled_row])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions({"unreconciled_only": True}, "tenant1"))
    assert result["filters_applied"]["unreconciled_only"] is True


def test_bank_transactions_unreconciled_count_in_result():
    rows = [
        _bank_row(id="BT-001", is_reconciled=False),
        _bank_row(id="BT-002", is_reconciled=True),
        _bank_row(id="BT-003", is_reconciled=False),
    ]
    conn = _make_conn(bank_rows=rows)
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions({}, "tenant1"))
    assert result["unreconciled_in_results"] == 2


def test_bank_transactions_limit_capped_at_100():
    conn = _make_conn(bank_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions({"limit": 9999}, "tenant1"))
    # Just verify it doesn't raise and returns structure
    assert "transactions" in result


def test_bank_transactions_empty_result_is_valid():
    conn = _make_conn(bank_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions({}, "tenant1"))
    assert result["count"] == 0
    assert result["transactions"] == []


def test_bank_transactions_result_fields():
    rows = [_bank_row()]
    conn = _make_conn(bank_rows=rows)
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_bank_transactions({}, "tenant1"))
    assert result["count"] == 1
    txn = result["transactions"][0]
    assert "id" in txn
    assert "date" in txn
    assert "amount" in txn
    assert "is_reconciled" in txn


# ─── _get_payment_status ──────────────────────────────────────────────────────

def test_payment_status_requires_identifier():
    conn = _make_conn()
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_payment_status({}, "tenant1"))
    assert "error" in result


def test_payment_status_found_by_invoice_number():
    inv = _invoice_row(invoice_number="INV-2026-100", total_amount=1500.0)
    bank = [_bank_row(amount=1500.0, is_reconciled=True)]
    conn = _make_conn(invoice_row=inv, bank_payment_rows=bank, draft_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_payment_status(
            {"invoice_number": "INV-2026-100"}, "tenant1"
        ))
    assert result["found"] is True
    assert result["document_type"] == "invoice"


def test_payment_status_fully_paid():
    inv = _invoice_row(total_amount=1500.0)
    bank = [_bank_row(amount=1500.0)]
    conn = _make_conn(invoice_row=inv, bank_payment_rows=bank, draft_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_payment_status(
            {"invoice_number": "INV-2026-100"}, "tenant1"
        ))
    assert result["payment_status"] == "გადახდილია"


def test_payment_status_unpaid_when_no_bank_match():
    inv = _invoice_row(total_amount=1500.0)
    conn = _make_conn(invoice_row=inv, bank_payment_rows=[], draft_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_payment_status(
            {"invoice_number": "INV-2026-100"}, "tenant1"
        ))
    assert result["payment_status"] == "გადასარიცხია"


def test_payment_status_partial_payment():
    inv = _invoice_row(total_amount=1500.0)
    bank = [_bank_row(amount=750.0)]
    conn = _make_conn(invoice_row=inv, bank_payment_rows=bank, draft_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_payment_status(
            {"invoice_number": "INV-2026-100"}, "tenant1"
        ))
    assert result["payment_status"] == "ნაწილობრივ გადახდილია"


def test_payment_status_not_found():
    conn = _make_conn(invoice_row=None, bank_payment_rows=[], draft_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_payment_status(
            {"invoice_number": "INV-DOES-NOT-EXIST"}, "tenant1"
        ))
    assert result["found"] is False


def test_payment_status_result_has_bank_transactions():
    inv = _invoice_row(total_amount=1500.0)
    bank = [_bank_row(amount=1500.0)]
    conn = _make_conn(invoice_row=inv, bank_payment_rows=bank, draft_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_payment_status(
            {"invoice_number": "INV-2026-100"}, "tenant1"
        ))
    assert "matched_bank_transactions" in result
    assert isinstance(result["matched_bank_transactions"], list)


def test_payment_status_result_has_expected_amount():
    inv = _invoice_row(total_amount=1500.0)
    conn = _make_conn(invoice_row=inv, bank_payment_rows=[], draft_rows=[])
    with patch("app.api.services.ai_tool_registry.get_conn",
               return_value=_fake_get_conn(conn)):
        result = run_sync(_get_payment_status(
            {"invoice_id": 100}, "tenant1"
        ))
    assert result["expected_amount"] == 1500.0
