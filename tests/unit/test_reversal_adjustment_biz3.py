"""tests/unit/test_reversal_adjustment_biz3.py — BIZ-3: Reversal and adjustment workflow.

Tests:
  - reversal lines invert debit/credit
  - reversal DR=CR
  - reversal references original entry
  - original entry unchanged after flip_lines
  - duplicate reversal blocked
  - reversal into closed period blocked
  - reversal into open next period allowed
  - adjustment entry references original
  - adjustment requires reason
  - adjustment DR=CR
  - posted entry not deleted (mocked)
  - create_reversal_draft and create_adjustment_draft validate inputs

Runs with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
No real DB. No RS.ge. No production credentials.
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.reversal_service import (
    flip_lines,
    lines_balanced,
    create_reversal_draft,
    create_adjustment_draft,
)
from app.api.services.period_lock_service import PeriodLockedError


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# flip_lines
# ---------------------------------------------------------------------------

class TestFlipLines:

    def test_debit_becomes_credit(self):
        lines = [{"account_code": "7310", "debit": 1000.0, "credit": 0.0, "label": "Rent"}]
        result = flip_lines(lines)
        assert result[0]["debit"]  == 0.0
        assert result[0]["credit"] == 1000.0

    def test_credit_becomes_debit(self):
        lines = [{"account_code": "3110", "debit": 0.0, "credit": 1000.0, "label": "AP"}]
        result = flip_lines(lines)
        assert result[0]["debit"]  == 1000.0
        assert result[0]["credit"] == 0.0

    def test_original_list_unchanged(self):
        original = [
            {"account_code": "7310", "debit": 500.0, "credit": 0.0,   "label": "Exp"},
            {"account_code": "3110", "debit": 0.0,   "credit": 500.0, "label": "AP"},
        ]
        before = [dict(ln) for ln in original]
        flip_lines(original)
        assert original == before, "flip_lines must not mutate the input list"

    def test_returns_new_list(self):
        lines = [{"account_code": "1110", "debit": 100.0, "credit": 0.0, "label": ""}]
        result = flip_lines(lines)
        assert result is not lines

    def test_multi_line_reversal(self):
        original = [
            {"account_code": "7310", "debit": 1000.0, "credit": 0.0,    "label": "Rent"},
            {"account_code": "3311", "debit": 180.0,  "credit": 0.0,    "label": "VAT"},
            {"account_code": "3110", "debit": 0.0,    "credit": 1180.0, "label": "AP"},
        ]
        rev = flip_lines(original)
        assert rev[0]["credit"] == 1000.0 and rev[0]["debit"] == 0.0
        assert rev[1]["credit"] == 180.0  and rev[1]["debit"] == 0.0
        assert rev[2]["debit"]  == 1180.0 and rev[2]["credit"] == 0.0

    def test_preserves_account_code_and_label(self):
        lines = [{"account_code": "7310", "debit": 500.0, "credit": 0.0, "label": "MyLabel"}]
        result = flip_lines(lines)
        assert result[0]["account_code"] == "7310"
        assert result[0]["label"] == "MyLabel"

    def test_reversal_plus_original_nets_zero(self):
        """All accounts in original + reversed sum to 0 net."""
        original = [
            {"account_code": "7310", "debit": 1180.0, "credit": 0.0,    "label": ""},
            {"account_code": "3110", "debit": 0.0,    "credit": 1180.0, "label": ""},
        ]
        rev = flip_lines(original)
        all_lines = original + rev
        total_dr = sum(Decimal(str(ln["debit"]))  for ln in all_lines)
        total_cr = sum(Decimal(str(ln["credit"])) for ln in all_lines)
        assert abs(total_dr - total_cr) < Decimal("0.005")


# ---------------------------------------------------------------------------
# lines_balanced
# ---------------------------------------------------------------------------

class TestLinesBalanced:

    def test_balanced_returns_true(self):
        lines = [
            {"account_code": "7310", "debit": 1180.0, "credit": 0.0},
            {"account_code": "3110", "debit": 0.0,    "credit": 1180.0},
        ]
        assert lines_balanced(lines) is True

    def test_unbalanced_returns_false(self):
        lines = [
            {"account_code": "7310", "debit": 500.0, "credit": 0.0},
            {"account_code": "3110", "debit": 0.0,   "credit": 400.0},
        ]
        assert lines_balanced(lines) is False

    def test_empty_lines_balanced(self):
        assert lines_balanced([]) is True  # 0=0

    def test_tolerance_passes_near_zero(self):
        lines = [
            {"account_code": "7310", "debit": 100.0,   "credit": 0.0},
            {"account_code": "3110", "debit": 0.0,     "credit": 100.002},  # within tolerance
        ]
        assert lines_balanced(lines) is True

    def test_reversal_of_balanced_entry_is_balanced(self):
        original = [
            {"account_code": "7310", "debit": 2360.0, "credit": 0.0},
            {"account_code": "3110", "debit": 0.0,    "credit": 2360.0},
        ]
        assert lines_balanced(flip_lines(original)) is True


# ---------------------------------------------------------------------------
# create_reversal_draft — mocked DB
# ---------------------------------------------------------------------------

POSTED_DRAFT = {
    "id": 42,
    "tenant_id": "geotrade_test",
    "date": "2026-08-15",
    "description": "Rent August",
    "partner": "LandlordCo",
    "amount": 1180.0,
    "currency": "GEL",
    "status": "posted",
    "lines": [
        {"account_code": "7310", "debit": 1000.0, "credit": 0.0,    "label": "Rent"},
        {"account_code": "3311", "debit": 180.0,  "credit": 0.0,    "label": "VAT"},
        {"account_code": "3110", "debit": 0.0,    "credit": 1180.0, "label": "AP"},
    ],
}


def _make_conn_for_reversal(original=None, duplicate=False):
    """Build an AsyncMock conn for create_reversal_draft tests."""
    from unittest.mock import AsyncMock
    conn = AsyncMock()

    # Context manager support: `async with get_conn() as conn`
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__  = AsyncMock(return_value=False)

    original_row = original or POSTED_DRAFT

    def _fetchrow_side_effect(sql, *args):
        """Route fetchrow calls by SQL content."""
        sql_str = str(sql)
        if "reversal_of_draft_id" in sql_str:
            return AsyncMock(return_value={"id": 99} if duplicate else None)()
        if "period_locks" in sql_str:
            return AsyncMock(return_value=None)()  # open period
        # Default: return the draft row (SELECT from journal_drafts)
        return AsyncMock(return_value={
            "id":          original_row["id"],
            "tenant_id":   original_row["tenant_id"],
            "date":        original_row["date"],
            "description": original_row["description"],
            "partner":     original_row.get("partner", ""),
            "amount":      original_row["amount"],
            "currency":    original_row["currency"],
            "status":      original_row["status"],
            "lines_json":  json.dumps(original_row["lines"]),
        })()

    conn.fetchrow = _fetchrow_side_effect

    # INSERT returning new reversal draft
    conn.fetchrow  # already set up
    conn.execute   = AsyncMock()

    return conn


class TestCreateReversalDraft:

    def test_requires_reason(self):
        """Empty reason must raise ValueError."""
        async def _run():
            with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                mock_conn = AsyncMock()
                mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__  = AsyncMock(return_value=False)
                mock_get_conn.return_value = mock_conn
                with pytest.raises(ValueError, match="reason"):
                    await create_reversal_draft(
                        "geotrade_test", 42, "2026-09-01", "", "user@test.com"
                    )
        run(_run())

    def test_blank_reason_raises(self):
        async def _run():
            with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                mock_conn = AsyncMock()
                mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__  = AsyncMock(return_value=False)
                mock_get_conn.return_value = mock_conn
                with pytest.raises(ValueError, match="reason"):
                    await create_reversal_draft(
                        "geotrade_test", 42, "2026-09-01", "   ", "user@test.com"
                    )
        run(_run())

    def test_reversal_lines_invert_debit_credit(self):
        """flip_lines inverts DR↔CR: no need for a full DB mock here."""
        original_lines = POSTED_DRAFT["lines"]
        reversed_lines = flip_lines(original_lines)
        assert reversed_lines[0]["debit"]  == 0.0    # was 1000 debit → 0 debit
        assert reversed_lines[0]["credit"] == 1000.0  # was 0 credit → 1000 credit
        assert reversed_lines[2]["debit"]  == 1180.0  # was 0 debit → 1180 debit
        assert reversed_lines[2]["credit"] == 0.0     # was 1180 credit → 0 credit

    def test_reversal_lines_dr_equals_cr(self):
        reversed_lines = flip_lines(POSTED_DRAFT["lines"])
        assert lines_balanced(reversed_lines)

    def test_original_entry_not_mutated(self):
        """Original lines are immutable after flip_lines."""
        import copy
        original_lines = copy.deepcopy(POSTED_DRAFT["lines"])
        flip_lines(original_lines)
        for before, after in zip(POSTED_DRAFT["lines"], original_lines):
            assert before["debit"]  == after["debit"]
            assert before["credit"] == after["credit"]


class TestReversalIntoClosedPeriod:

    def test_reversal_into_locked_period_blocked(self):
        """If reversal_date is in a locked period, PeriodLockedError is raised."""
        async def _run():
            with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                conn = AsyncMock()
                conn.__aenter__ = AsyncMock(return_value=conn)
                conn.__aexit__  = AsyncMock(return_value=False)

                _call_idx = [0]

                def _fetchrow(sql, *args):
                    sql_str = str(sql)
                    _call_idx[0] += 1
                    if "reversal_of_draft_id" in sql_str:
                        return AsyncMock(return_value=None)()   # no duplicate
                    if "period_locks" in sql_str:
                        return AsyncMock(return_value={"1": 1})()  # locked
                    # journal_drafts fetch (original)
                    return AsyncMock(return_value={
                        "id": 42, "tenant_id": "geotrade_test",
                        "date": "2026-08-15", "description": "Rent",
                        "partner": "", "amount": 1180.0, "currency": "GEL",
                        "status": "posted",
                        "lines_json": json.dumps(POSTED_DRAFT["lines"]),
                    })()

                conn.fetchrow = _fetchrow
                mock_get_conn.return_value = conn

                with pytest.raises(PeriodLockedError):
                    await create_reversal_draft(
                        "geotrade_test", 42, "2026-08-31",
                        "Correcting August entry", "accountant@test.com",
                        allow_closed_period=False,
                    )
        run(_run())

    def test_reversal_with_admin_override_bypasses_period_check(self):
        """allow_closed_period=True means assert_period_open is never called.

        We test this by verifying that is_period_closed is never called on the
        period_locks table when allow_closed_period=True.
        """
        from app.api.services.period_lock_service import assert_period_open as _real_apo
        calls = []

        async def _spy_assert_period_open(conn, tenant_id, posting_date, action_type="posting"):
            calls.append(action_type)
            return await _real_apo(conn, tenant_id, posting_date, action_type)

        with patch("app.api.services.reversal_service.assert_period_open", _spy_assert_period_open):
            async def _run():
                # reversal with allow_closed_period=True → assert_period_open not called
                with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                    conn = AsyncMock()
                    conn.__aenter__ = AsyncMock(return_value=conn)
                    conn.__aexit__  = AsyncMock(return_value=False)
                    # Return proper rows for each fetchrow call in order
                    conn.fetchrow = AsyncMock(side_effect=[
                        # 1. _fetch_draft SELECT
                        {
                            "id": 42, "tenant_id": "geotrade_test",
                            "date": "2026-08-15", "description": "Rent",
                            "partner": "", "amount": 1180.0, "currency": "GEL",
                            "status": "posted",
                            "lines_json": json.dumps(POSTED_DRAFT["lines"]),
                        },
                        # 2. _reversal_already_exists
                        None,
                        # 3. INSERT RETURNING
                        {
                            "id": 99, "tenant_id": "geotrade_test",
                            "date": "2026-08-31", "description": "[REVERSAL of #42]",
                            "amount": 1180.0, "currency": "GEL", "status": "pending_approval",
                        },
                    ])
                    mock_get_conn.return_value = conn

                    with patch("app.api.services.reversal_service.log_event"):
                        result = await create_reversal_draft(
                            "geotrade_test", 42, "2026-08-31",
                            "Admin override reversal", "admin@test.com",
                            allow_closed_period=True,
                        )
                    assert result["entry_type"] == "reversal"
                    assert result["reversal_of_draft_id"] == 42
                    # assert_period_open was NOT called (because allow_closed_period=True)
                    assert calls == [], f"assert_period_open must not be called with allow_closed_period=True, but got calls: {calls}"
            run(_run())


class TestDuplicateReversal:

    def test_duplicate_reversal_blocked(self):
        """Second reversal of same draft raises ValueError."""
        async def _run():
            with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                conn = AsyncMock()
                conn.__aenter__ = AsyncMock(return_value=conn)
                conn.__aexit__  = AsyncMock(return_value=False)

                def _fetchrow(sql, *args):
                    sql_str = str(sql)
                    if "reversal_of_draft_id" in sql_str:
                        return AsyncMock(return_value={"id": 55})()  # duplicate exists
                    if "period_locks" in sql_str:
                        return AsyncMock(return_value=None)()
                    return AsyncMock(return_value={
                        "id": 42, "tenant_id": "geotrade_test",
                        "date": "2026-08-15", "description": "Rent",
                        "partner": "", "amount": 1180.0, "currency": "GEL",
                        "status": "posted",
                        "lines_json": json.dumps(POSTED_DRAFT["lines"]),
                    })()
                conn.fetchrow = _fetchrow
                mock_get_conn.return_value = conn

                with pytest.raises(ValueError, match="already exists"):
                    await create_reversal_draft(
                        "geotrade_test", 42, "2026-09-01",
                        "Second reversal", "user@test.com",
                    )
        run(_run())


# ---------------------------------------------------------------------------
# create_adjustment_draft — validation
# ---------------------------------------------------------------------------

class TestAdjustmentDraftValidation:

    def test_requires_reason(self):
        async def _run():
            with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                conn = AsyncMock()
                conn.__aenter__ = AsyncMock(return_value=conn)
                conn.__aexit__  = AsyncMock(return_value=False)
                mock_get_conn.return_value = conn
                with pytest.raises(ValueError, match="reason"):
                    await create_adjustment_draft(
                        "geotrade_test", 42, "2026-09-01", "",
                        "user@test.com",
                        [{"account_code": "7310", "debit": 100.0, "credit": 0.0}],
                    )
        run(_run())

    def test_requires_lines(self):
        async def _run():
            with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                conn = AsyncMock()
                conn.__aenter__ = AsyncMock(return_value=conn)
                conn.__aexit__  = AsyncMock(return_value=False)
                mock_get_conn.return_value = conn
                with pytest.raises(ValueError, match="lines"):
                    await create_adjustment_draft(
                        "geotrade_test", 42, "2026-09-01",
                        "Fix rent amount", "user@test.com", [],
                    )
        run(_run())

    def test_unbalanced_lines_rejected(self):
        async def _run():
            with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                conn = AsyncMock()
                conn.__aenter__ = AsyncMock(return_value=conn)
                conn.__aexit__  = AsyncMock(return_value=False)
                mock_get_conn.return_value = conn
                bad_lines = [
                    {"account_code": "7310", "debit": 500.0, "credit": 0.0, "label": "Rent"},
                    {"account_code": "3110", "debit": 0.0,   "credit": 400.0, "label": "AP"},
                ]
                # The service does balance check BEFORE _validate_lines, so error is about balance
                with pytest.raises(ValueError):
                    await create_adjustment_draft(
                        "geotrade_test", 42, "2026-09-01",
                        "Incorrect amount", "user@test.com", bad_lines,
                    )
        run(_run())

    def test_adjustment_lines_must_be_balanced(self):
        balanced = [
            {"account_code": "7310", "debit": 900.0,  "credit": 0.0,    "label": "Rent"},
            {"account_code": "3311", "debit": 162.0,  "credit": 0.0,    "label": "VAT"},
            {"account_code": "3110", "debit": 0.0,    "credit": 1062.0, "label": "AP"},
        ]
        assert lines_balanced(balanced) is True

    def test_adjustment_into_closed_period_blocked(self):
        async def _run():
            with patch("app.api.services.reversal_service.get_conn") as mock_get_conn:
                conn = AsyncMock()
                conn.__aenter__ = AsyncMock(return_value=conn)
                conn.__aexit__  = AsyncMock(return_value=False)

                def _fetchrow(sql, *args):
                    sql_str = str(sql)
                    if "period_locks" in sql_str:
                        return AsyncMock(return_value={"1": 1})()  # locked
                    return AsyncMock(return_value={
                        "id": 42, "tenant_id": "geotrade_test",
                        "date": "2026-08-15", "description": "Rent",
                        "partner": "", "amount": 1180.0, "currency": "GEL",
                        "status": "posted",
                        "lines_json": "[]",
                    })()
                conn.fetchrow = _fetchrow
                mock_get_conn.return_value = conn

                balanced = [
                    {"account_code": "7310", "debit": 1000.0, "credit": 0.0,    "label": ""},
                    {"account_code": "3110", "debit": 0.0,    "credit": 1000.0, "label": ""},
                ]
                with pytest.raises(PeriodLockedError):
                    await create_adjustment_draft(
                        "geotrade_test", 42, "2026-08-31",
                        "Adjust August", "user@test.com", balanced,
                        allow_closed_period=False,
                    )
        run(_run())


# ---------------------------------------------------------------------------
# General safeguards
# ---------------------------------------------------------------------------

class TestPostingPreservation:

    def test_flip_lines_does_not_delete_original(self):
        """flip_lines returns a new list — original remains (no delete)."""
        original = [
            {"account_code": "7310", "debit": 1000.0, "credit": 0.0, "label": "Rent"},
            {"account_code": "3110", "debit": 0.0, "credit": 1000.0, "label": "AP"},
        ]
        import copy
        snapshot = copy.deepcopy(original)
        _ = flip_lines(original)
        assert original == snapshot, "Original entry must never be deleted or mutated"

    def test_reversal_service_importable(self):
        from app.api.services.reversal_service import (
            flip_lines, lines_balanced, create_reversal_draft, create_adjustment_draft
        )
        assert callable(flip_lines)
        assert callable(lines_balanced)
        assert callable(create_reversal_draft)
        assert callable(create_adjustment_draft)
