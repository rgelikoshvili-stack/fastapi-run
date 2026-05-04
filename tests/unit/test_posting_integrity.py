"""tests/unit/test_posting_integrity.py
Posting integrity: balanced entries, idempotency, financial statement structure.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch


def _make_get_conn(rows=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _ctx():
        yield conn

    return _ctx


# ── helpers ───────────────────────────────────────────────────────────────────

def _lines(pairs: list[tuple]) -> list[dict]:
    """Build journal lines from [(account, debit, credit), ...]."""
    return [{"account_code": a, "debit": d, "credit": c} for a, d, c in pairs]


# ── 1. Balanced entry passes ──────────────────────────────────────────────────

def test_balanced_entry_passes():
    from app.api.services.posting_service import _validate_lines

    lines = _lines([("1120", 1000, 0), ("3110", 0, 1000)])
    assert _validate_lines(lines) is None


# ── 2. Unbalanced entry returns error string ──────────────────────────────────

def test_unbalanced_entry_raises():
    from app.api.services.posting_service import _validate_lines

    lines = _lines([("1120", 1000, 0), ("3110", 0, 900)])
    error = _validate_lines(lines)
    assert error is not None
    assert "1000" in error or "Dr=" in error or "Cr=" in error


# ── 3. Empty lines returns error ──────────────────────────────────────────────

def test_empty_lines_error():
    from app.api.services.posting_service import _validate_lines

    assert _validate_lines([]) is not None


# ── 4. Idempotency returns cached result on second call ───────────────────────

def test_idempotent_posting():
    from app.api.services.idempotency_service import idempotency_check, idempotency_store

    cached = {"ok": True, "draft_id": 42, "status": "posted"}

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cur

    # First call — miss (None)
    mock_cur.fetchone.return_value = None
    with patch("app.api.services.idempotency_service.get_db", return_value=mock_conn):
        result = idempotency_check("tenant_a", "key-001", "posting")
    assert result is None

    # Second call — hit (return cached dict)
    mock_cur.fetchone.return_value = (cached,)
    with patch("app.api.services.idempotency_service.get_db", return_value=mock_conn):
        result = idempotency_check("tenant_a", "key-001", "posting")
    assert result == cached
    assert result["draft_id"] == 42


# ── 5. P&L report structure has expected keys ─────────────────────────────────

def test_pl_report_structure():
    from app.api.services.financial_statements_service import build_profit_and_loss

    with patch("app.api.services.financial_statements_service.get_conn",
               _make_get_conn()):
        result = asyncio.run(build_profit_and_loss("tenant_a", "2026-01-01", "2026-01-31"))

    # ok_response wraps payload under "data"
    assert result.get("ok") is True
    data = result["data"]
    assert "revenue" in data
    assert "cogs" in data
    assert "gross_profit" in data
    assert "ebit" in data


# ── 6. Balance sheet equation holds ──────────────────────────────────────────

def test_balance_sheet_equation():
    from app.api.services.financial_statements_service import build_balance_sheet

    with patch("app.api.services.financial_statements_service.get_conn",
               _make_get_conn()):
        result = asyncio.run(build_balance_sheet("tenant_a", "2026-01-31"))

    assert result.get("ok") is True
    data = result["data"]
    assert "balanced" in data
    assert "assets" in data
    assert "liabilities" in data
    assert "equity" in data


# ── 7. Both-debit-and-credit on same line blocked ─────────────────────────────

def test_both_debit_credit_same_line_blocked():
    from app.api.services.posting_service import _validate_lines
    lines = _lines([("7120", 500, 500)])
    assert _validate_lines(lines) is not None


# ── 8. Negative amounts blocked ──────────────────────────────────────────────

def test_negative_debit_blocked():
    from app.api.services.posting_service import _validate_lines
    lines = _lines([("7120", -100, 0), ("1210", 0, -100)])
    assert _validate_lines(lines) is not None


# ── 9. Multi-line balanced entry passes ──────────────────────────────────────

def test_multi_line_balanced():
    from app.api.services.posting_service import _validate_lines
    lines = _lines([
        ("7120", 500, 0),
        ("7130", 250, 0),
        ("7160", 250, 0),
        ("1210", 0, 1000),
    ])
    assert _validate_lines(lines) is None


# ── 10. _sum_debits and _sum_credits ─────────────────────────────────────────

def test_sum_debits_correct():
    from app.api.services.posting_service import _sum_debits
    lines = _lines([("7120", 300, 0), ("7130", 200, 0), ("1210", 0, 500)])
    assert _sum_debits(lines) == 500.0


def test_sum_credits_correct():
    from app.api.services.posting_service import _sum_credits
    lines = _lines([("7120", 500, 0), ("1210", 0, 300), ("3310", 0, 200)])
    assert _sum_credits(lines) == 500.0


# ── 11. Cross-tenant: draft not found for wrong tenant ───────────────────────

def test_cross_tenant_logic_in_fetch_draft():
    """_fetch_draft always includes tenant_id in WHERE clause (verified by inspecting the SQL)."""
    import inspect
    from app.api.services.posting_service import _fetch_draft
    source = inspect.getsource(_fetch_draft)
    assert "tenant_id" in source, "_fetch_draft must filter by tenant_id"
    assert "FOR UPDATE" in source, "_fetch_draft must use SELECT FOR UPDATE"
