"""tests/unit/test_period_lock_enforcement_biz3.py — BIZ-3: Period lock enforcement.

Tests:
  - open period allows posting
  - closed period blocks posting
  - locked period blocks posting
  - lock check happens before DB write (no partial write)
  - draft approval into locked period blocked
  - manual journal into locked period blocked
  - correct error message returned
  - PeriodLockedError carries correct fields

Runs with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
No real DB. No RS.ge. No production credentials.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.period_lock_service import (
    PeriodLockedError,
    assert_period_open,
    is_period_closed,
    is_period_closed_sync,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_locked_conn():
    """AsyncMock that simulates a locked period (fetchrow returns a row)."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"1": 1})
    conn.execute  = AsyncMock()
    return conn


def _make_open_conn():
    """AsyncMock that simulates an open period (fetchrow returns None)."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute  = AsyncMock()
    return conn


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# is_period_closed — async
# ---------------------------------------------------------------------------

class TestIsPeriodClosed:

    def test_open_period_returns_false(self):
        conn = _make_open_conn()
        result = run(is_period_closed(conn, "tenant_a", date(2026, 9, 1)))
        assert result is False

    def test_locked_period_returns_true(self):
        conn = _make_locked_conn()
        result = run(is_period_closed(conn, "tenant_a", date(2026, 8, 31)))
        assert result is True

    def test_none_date_returns_false(self):
        conn = _make_open_conn()
        result = run(is_period_closed(conn, "tenant_a", None))
        assert result is False

    def test_empty_string_date_returns_false(self):
        conn = _make_open_conn()
        result = run(is_period_closed(conn, "tenant_a", ""))
        assert result is False

    def test_accepts_string_date(self):
        conn = _make_locked_conn()
        result = run(is_period_closed(conn, "tenant_a", "2026-08-31"))
        assert result is True

    def test_accepts_date_object(self):
        conn = _make_locked_conn()
        result = run(is_period_closed(conn, "tenant_a", date(2026, 8, 1)))
        assert result is True


# ---------------------------------------------------------------------------
# assert_period_open — async (raises PeriodLockedError when closed)
# ---------------------------------------------------------------------------

class TestAssertPeriodOpen:

    def test_open_period_does_not_raise(self):
        conn = _make_open_conn()
        run(assert_period_open(conn, "tenant_a", date(2026, 9, 1), "posting"))
        # No exception raised

    def test_locked_period_raises_period_locked_error(self):
        conn = _make_locked_conn()
        with pytest.raises(PeriodLockedError) as exc_info:
            run(assert_period_open(conn, "tenant_a", date(2026, 8, 31), "posting"))
        err = exc_info.value
        assert err.tenant_id    == "tenant_a"
        assert err.period_year  == 2026
        assert err.period_month == 8
        assert err.action_type  == "posting"

    def test_action_type_preserved_in_error(self):
        conn = _make_locked_conn()
        with pytest.raises(PeriodLockedError) as exc_info:
            run(assert_period_open(conn, "tenant_a", "2026-08-31", "reversal"))
        assert exc_info.value.action_type == "reversal"

    def test_lock_check_before_db_write(self):
        """assert_period_open raises BEFORE any execute (write) is called."""
        conn = _make_locked_conn()
        with pytest.raises(PeriodLockedError):
            run(assert_period_open(conn, "tenant_a", date(2026, 8, 31), "posting"))
        conn.execute.assert_not_called()

    def test_none_date_does_not_raise(self):
        conn = _make_locked_conn()
        run(assert_period_open(conn, "tenant_a", None, "posting"))

    def test_draft_approval_blocked_for_closed_period(self):
        """Simulates approval_service calling assert_period_open — must raise."""
        conn = _make_locked_conn()
        with pytest.raises(PeriodLockedError) as exc_info:
            run(assert_period_open(conn, "tenant_a", date(2026, 8, 15), "approval"))
        assert exc_info.value.action_type == "approval"

    def test_manual_journal_blocked_for_closed_period(self):
        conn = _make_locked_conn()
        with pytest.raises(PeriodLockedError) as exc_info:
            run(assert_period_open(conn, "tenant_a", date(2026, 8, 1), "manual_journal"))
        assert "locked" in str(exc_info.value).lower() or "closed" in str(exc_info.value).lower()

    def test_bank_posting_blocked_for_closed_period(self):
        conn = _make_locked_conn()
        with pytest.raises(PeriodLockedError):
            run(assert_period_open(conn, "tenant_a", "2026-08-05", "bank_posting"))

    def test_payroll_posting_blocked_for_closed_period(self):
        conn = _make_locked_conn()
        with pytest.raises(PeriodLockedError):
            run(assert_period_open(conn, "tenant_a", "2026-08-31", "payroll_posting"))

    def test_depreciation_posting_blocked_for_closed_period(self):
        conn = _make_locked_conn()
        with pytest.raises(PeriodLockedError):
            run(assert_period_open(conn, "tenant_a", "2026-08-31", "depreciation_posting"))


# ---------------------------------------------------------------------------
# is_period_closed_sync — sync (psycopg2 cursor)
# ---------------------------------------------------------------------------

class TestIsPeriodClosedSync:

    def test_locked_returns_true(self):
        class LockedCur:
            def execute(self, sql, params): pass
            def fetchone(self): return {"1": 1}

        assert is_period_closed_sync(LockedCur(), "tenant_a", date(2026, 8, 31)) is True

    def test_open_returns_false(self):
        class OpenCur:
            def execute(self, sql, params): pass
            def fetchone(self): return None

        assert is_period_closed_sync(OpenCur(), "tenant_a", date(2026, 9, 1)) is False

    def test_none_date_returns_false(self):
        class DummyCur:
            def execute(self, sql, params): pass
            def fetchone(self): return None

        assert is_period_closed_sync(DummyCur(), "tenant_a", None) is False

    def test_accepts_string_date(self):
        class LockedCur:
            def execute(self, sql, params): self.params = params
            def fetchone(self): return {"1": 1}

        cur = LockedCur()
        result = is_period_closed_sync(cur, "tenant_a", "2026-08-31")
        assert result is True
        assert cur.params == ("tenant_a", 2026, 8)

    def test_passes_correct_params(self):
        class RecordCur:
            def execute(self, sql, params): self.params = params
            def fetchone(self): return None

        cur = RecordCur()
        is_period_closed_sync(cur, "mycompany", date(2026, 5, 15))
        assert cur.params == ("mycompany", 2026, 5)


# ---------------------------------------------------------------------------
# PeriodLockedError
# ---------------------------------------------------------------------------

class TestPeriodLockedError:

    def test_is_exception(self):
        err = PeriodLockedError("t", 2026, 8, "posting")
        assert isinstance(err, Exception)

    def test_fields(self):
        err = PeriodLockedError("geotrade_test", 2026, 8, "reversal")
        assert err.tenant_id    == "geotrade_test"
        assert err.period_year  == 2026
        assert err.period_month == 8
        assert err.action_type  == "reversal"

    def test_message_contains_guidance(self):
        err = PeriodLockedError("t", 2026, 8, "posting")
        msg = str(err)
        assert any(kw in msg.lower() for kw in ["locked", "closed"])
        assert any(kw in msg.lower() for kw in ["adjustment", "unlock"])

    def test_message_contains_period_label(self):
        err = PeriodLockedError("t", 2026, 8, "posting")
        msg = str(err)
        assert "August 2026" in msg

    def test_full_year_lock_label(self):
        err = PeriodLockedError("t", 2026, 0, "posting")
        msg = str(err)
        assert "2026" in msg

    def test_catchable_as_exception(self):
        try:
            raise PeriodLockedError("t", 2026, 8, "posting")
        except Exception as e:
            assert isinstance(e, PeriodLockedError)

    def test_proper_error_message_text(self):
        """Error message must guide user toward adjustment or unlock."""
        err = PeriodLockedError("t", 2026, 8, "posting")
        msg = str(err)
        assert "adjustment" in msg.lower() or "unlock" in msg.lower()


# ---------------------------------------------------------------------------
# Routes import check
# ---------------------------------------------------------------------------

class TestRoutesJournalEntriesImport:

    def test_routes_journal_entries_importable(self):
        import importlib
        spec = importlib.util.find_spec("app.api.routes_journal_entries")
        assert spec is not None

    def test_routes_journal_entries_has_router(self):
        import app.api.routes_journal_entries as mod
        assert hasattr(mod, "router")

    def test_period_lock_service_importable(self):
        from app.api.services.period_lock_service import (
            PeriodLockedError, is_period_closed, assert_period_open, is_period_closed_sync
        )
        assert True
