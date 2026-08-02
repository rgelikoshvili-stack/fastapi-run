"""tests/unit/test_year_close_service.py — Year-Close Service unit tests."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.year_close_service import (
    build_year_close_checklist,
    generate_closing_entries,
    get_year_close_status,
    lock_fiscal_year,
    run_year_checklist,
    save_year_close_signoff,
)

YEAR = "2025"
TENANT = "tenant-test"


# ---------------------------------------------------------------------------
# build_year_close_checklist — pure
# ---------------------------------------------------------------------------

def test_build_year_close_checklist_returns_all_items():
    items = build_year_close_checklist()
    assert len(items) == 6
    ids = [i["id"] for i in items]
    assert "all_months_closed" in ids
    assert "trial_balance_balanced" in ids
    assert "no_unposted_drafts" in ids
    for item in items:
        assert item["status"] == "pending"
        assert item["detail"] is None


# ---------------------------------------------------------------------------
# run_year_checklist — async, mocked conn
# ---------------------------------------------------------------------------

def _make_conn(records: dict):
    """Build a fake asyncpg connection where each SQL keyword maps to a row."""
    conn = AsyncMock()

    async def fetchrow(sql, *args):
        sql_lower = sql.lower()
        for key, row in records.items():
            if key in sql_lower:
                return row
        return None

    async def fetch(sql, *args):
        sql_lower = sql.lower()
        for key, rows in records.items():
            if key in sql_lower and isinstance(rows, list):
                return rows
        return []

    conn.fetchrow = fetchrow
    conn.fetch = fetch
    return conn


def _make_cm(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def test_run_year_checklist_all_ok():
    mock_rows = {
        "monthly_close_signoffs": MagicMock(**{"__getitem__.return_value": 1, "get": lambda k, d=None: 1}),
        "journal_drafts": MagicMock(**{"__getitem__.return_value": 0, "get": lambda k, d=None: 0}),
        "total_debit": None,  # will be handled per-key
    }

    conn = AsyncMock()

    async def fetchrow(sql, *args):
        if "monthly_close_signoffs" in sql:
            row = {"cnt": 1}
            return row
        if "status in" in sql.lower() and "drafted" in sql.lower():
            return {"cnt": 0}
        if "total_debit" in sql.lower():
            return {"total_debit": "1000.00", "total_credit": "1000.00"}
        if "depreciation" in sql.lower() or "7%" in sql:
            return {"cnt": 5}
        return None

    async def fetch(sql, *args):
        if "payroll_submissions" in sql:
            return [{"period": f"2025-{i:02d}"} for i in range(1, 13)]
        if "3350" in sql:
            return [{"month": f"2025-{i:02d}"} for i in range(1, 13)]
        return []

    conn.fetchrow = fetchrow
    conn.fetch = fetch

    with patch("app.api.services.year_close_service.get_conn", return_value=_make_cm(conn)):
        items = asyncio.run(run_year_checklist(TENANT, YEAR))

    assert len(items) == 6
    for item in items:
        assert item["status"] in ("ok", "warning", "unknown"), f"{item['id']} = {item['status']}"


def test_run_year_checklist_unposted_drafts_fail():
    conn = AsyncMock()

    async def fetchrow(sql, *args):
        if "monthly_close_signoffs" in sql:
            return {"cnt": 12}
        if "drafted" in sql.lower():
            return {"cnt": 3}
        if "total_debit" in sql.lower():
            return {"total_debit": "500.00", "total_credit": "500.00"}
        if "depreciation" in sql.lower():
            return {"cnt": 1}
        return None

    async def fetch(sql, *args):
        if "payroll_submissions" in sql:
            return [{"period": f"2025-{i:02d}"} for i in range(1, 13)]
        if "3350" in sql:
            return [{"month": f"2025-{i:02d}"} for i in range(1, 13)]
        return []

    conn.fetchrow = fetchrow
    conn.fetch = fetch

    with patch("app.api.services.year_close_service.get_conn", return_value=_make_cm(conn)):
        items = asyncio.run(run_year_checklist(TENANT, YEAR))

    unposted = next(i for i in items if i["id"] == "no_unposted_drafts")
    assert unposted["status"] == "fail"
    assert unposted["value"] == 3


# ---------------------------------------------------------------------------
# generate_closing_entries
# ---------------------------------------------------------------------------

def test_generate_closing_entries_net_income():
    conn = AsyncMock()

    async def fetchrow(sql, *args):
        return {
            "revenue_debit": "0",
            "revenue_credit": "50000",
            "expense_debit": "30000",
            "expense_credit": "0",
        }

    conn.fetchrow = fetchrow

    with patch("app.api.services.year_close_service.get_conn", return_value=_make_cm(conn)):
        result = asyncio.run(generate_closing_entries(TENANT, YEAR))

    assert result["ok"] is True
    assert result["net_income"] == 20000.0
    assert len(result["closing_lines"]) == 2
    assert result["closing_lines"][0]["debit"] == 20000.0
    assert result["closing_lines"][1]["credit"] == 20000.0


def test_generate_closing_entries_net_loss():
    conn = AsyncMock()

    async def fetchrow(sql, *args):
        return {
            "revenue_debit": "0",
            "revenue_credit": "10000",
            "expense_debit": "15000",
            "expense_credit": "0",
        }

    conn.fetchrow = fetchrow

    with patch("app.api.services.year_close_service.get_conn", return_value=_make_cm(conn)):
        result = asyncio.run(generate_closing_entries(TENANT, YEAR))

    assert result["ok"] is True
    assert result["net_income"] == -5000.0
    assert len(result["closing_lines"]) == 2
    assert result["closing_lines"][0]["debit"] == 5000.0


def test_generate_closing_entries_breakeven():
    conn = AsyncMock()

    async def fetchrow(sql, *args):
        return {
            "revenue_debit": "0",
            "revenue_credit": "10000",
            "expense_debit": "10000",
            "expense_credit": "0",
        }

    conn.fetchrow = fetchrow

    with patch("app.api.services.year_close_service.get_conn", return_value=_make_cm(conn)):
        result = asyncio.run(generate_closing_entries(TENANT, YEAR))

    assert result["ok"] is True
    assert result["net_income"] == 0.0
    assert result["closing_lines"] == []


# ---------------------------------------------------------------------------
# save_year_close_signoff
# ---------------------------------------------------------------------------

def test_save_year_close_signoff_valid_roles():
    for role in ("accountant", "cfo", "board"):
        conn = AsyncMock()
        row = {"id": 1, "tenant_id": TENANT, "year": YEAR, "role": role, "signed_by": "user1", "signed_at": None, "notes": None}

        async def fetchrow(sql, *args, _row=row):
            return _row

        conn.fetchrow = fetchrow

        with patch("app.api.services.year_close_service.get_conn", return_value=_make_cm(conn)):
            result = asyncio.run(save_year_close_signoff(TENANT, YEAR, role, "user1"))

        assert result.get("role") == role


def test_save_year_close_signoff_invalid_role():
    with pytest.raises(ValueError, match="Invalid role"):
        asyncio.run(save_year_close_signoff(TENANT, YEAR, "intern", "user1"))


# ---------------------------------------------------------------------------
# lock_fiscal_year
# ---------------------------------------------------------------------------

def test_lock_fiscal_year_already_locked():
    async def mock_status(*a, **kw):
        return {
            "is_locked": True,
            "critical_checks_passed": True,
            "roles_signed": ["cfo"],
        }

    with patch("app.api.services.year_close_service.get_year_close_status", side_effect=mock_status):
        result = asyncio.run(lock_fiscal_year(TENANT, YEAR, "user1"))

    assert result["ok"] is False
    assert "already locked" in result["error"]


def test_lock_fiscal_year_missing_cfo():
    async def mock_status(*a, **kw):
        return {
            "is_locked": False,
            "critical_checks_passed": True,
            "roles_signed": ["accountant"],
        }

    with patch("app.api.services.year_close_service.get_year_close_status", side_effect=mock_status):
        result = asyncio.run(lock_fiscal_year(TENANT, YEAR, "user1"))

    assert result["ok"] is False
    assert "CFO" in result["error"]


def test_lock_fiscal_year_critical_checks_fail():
    async def mock_status(*a, **kw):
        return {
            "is_locked": False,
            "critical_checks_passed": False,
            "roles_signed": ["cfo"],
        }

    with patch("app.api.services.year_close_service.get_year_close_status", side_effect=mock_status):
        result = asyncio.run(lock_fiscal_year(TENANT, YEAR, "user1"))

    assert result["ok"] is False
    assert "critical" in result["error"].lower()


def test_lock_fiscal_year_success():
    async def mock_status(*a, **kw):
        return {
            "is_locked": False,
            "critical_checks_passed": True,
            "roles_signed": ["accountant", "cfo"],
        }

    conn = AsyncMock()
    conn.execute = AsyncMock()

    with patch("app.api.services.year_close_service.get_year_close_status", side_effect=mock_status):
        with patch("app.api.services.year_close_service.get_conn", return_value=_make_cm(conn)):
            result = asyncio.run(lock_fiscal_year(TENANT, YEAR, "user1"))

    assert result["ok"] is True
    assert result["year"] == YEAR
    assert result["locked_by"] == "user1"
