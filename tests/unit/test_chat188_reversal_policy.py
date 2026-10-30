"""Chat188 FIN-11: correcting draft authorization and date integrity.

Synthetic only. Tests deliberately reproduce existing closed-period override,
simulated-success reversal, and non-posted correction acceptance before repair.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
import pytest

from app.api.services import reversal_service as reversal


@asynccontextmanager
async def fake_conn():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"id": 188}
    yield conn


@pytest.mark.asyncio
@pytest.mark.parametrize("method,kwargs", [
    ("create_reversal_draft", {
        "tenant_id": "tenant-a", "original_draft_id": 41,
        "reversal_date": "2026-10-30", "reason": "Correct posted entry",
        "actor": "accountant", "allow_closed_period": True,
    }),
    ("create_adjustment_draft", {
        "tenant_id": "tenant-a", "original_draft_id": 41,
        "adjustment_date": "2026-10-30", "reason": "Correct posted entry",
        "actor": "accountant", "lines": [
            {"account_code": "1120", "debit": 10, "credit": 0},
            {"account_code": "6110", "debit": 0, "credit": 10},
        ], "allow_closed_period": True,
    }),
])
async def test_service_cannot_bypass_closed_period_by_unverified_flag(method, kwargs):
    with patch.object(reversal, "get_conn", side_effect=AssertionError("no DB allowed")) as conn:
        with pytest.raises(ValueError, match="CLOSED_PERIOD_OVERRIDE_DISABLED"):
            await getattr(reversal, method)(**kwargs)
    conn.assert_not_called()


@pytest.mark.asyncio
async def test_simulated_success_never_eligible_for_real_reversal():
    with patch.object(reversal, "get_conn", fake_conn), \
         patch.object(reversal, "_fetch_draft", new_callable=AsyncMock,
                      return_value={"status": "simulated_success"}) as original, \
         patch.object(reversal, "_reversal_already_exists",
                      new_callable=AsyncMock) as duplicates:
        with pytest.raises(ValueError, match="only posted"):
            await reversal.create_reversal_draft(
                "tenant-a", 41, "2026-10-30", "not a real posting", "accountant"
            )
    original.assert_awaited_once()
    duplicates.assert_not_awaited()


@pytest.mark.asyncio
async def test_nonposted_original_not_eligible_for_financial_adjustment():
    with patch.object(reversal, "get_conn", fake_conn), \
         patch.object(reversal, "_fetch_draft", new_callable=AsyncMock,
                      return_value={"status": "approved"}) as original, \
         patch.object(reversal, "assert_period_open",
                      new_callable=AsyncMock) as period:
        with pytest.raises(ValueError, match="only posted"):
            await reversal.create_adjustment_draft(
                "tenant-a", 41, "2026-10-30", "not posted", "accountant",
                [{"account_code": "1120", "debit": 10, "credit": 0},
                 {"account_code": "6110", "debit": 0, "credit": 10}],
            )
    original.assert_awaited_once()
    period.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("day", [
    "2026-10-30T22:30:00Z", "2026-10-30junk", "2026-02-30", None,
])
async def test_reversal_dates_are_exact_iso_dates_not_sliced(day):
    with patch.object(reversal, "get_conn", side_effect=AssertionError("no db on invalid date")) as conn:
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            await reversal.create_reversal_draft(
                "tenant-a", 41, day, "reason", "accountant",
            )
    conn.assert_not_called()


def _request() -> Request:
    request = Request({
        "type": "http", "method": "POST", "path": "/api/journal-entries/41/reverse",
        "headers": [], "query_string": b"",
    })
    request.state.tenant_id = "tenant-a"
    request.state.user_id = "test-actor"
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,payload", [
    ("reverse_journal_entry", {
        "reversal_date": "2026-10-30", "reason": "approved", "allow_closed_period": True
    }),
    ("adjust_journal_entry", {
        "adjustment_date": "2026-10-30", "reason": "approved", "allow_closed_period": True,
        "lines": [{"account_code": "1120", "debit": 1, "credit": 0},
                  {"account_code": "6110", "debit": 0, "credit": 1}],
    }),
])
async def test_route_rejects_closed_period_override_before_service(endpoint,payload):
    from app.api import routes_journal_entries as route
    with patch.object(route, "require_permission"), \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(reversal, "create_reversal_draft", new_callable=AsyncMock) as reverser, \
         patch.object(reversal, "create_adjustment_draft", new_callable=AsyncMock) as adjuster:
        result = await getattr(route, endpoint)(41, _request(), payload)
    assert result["ok"] is False
    assert result["error"]["code"] == "CLOSED_PERIOD_OVERRIDE_DISABLED"
    reverser.assert_not_called()
    adjuster.assert_not_called()
