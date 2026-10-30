"""Chat187 FIN-11: protect a posting vs closing race and fail CLOSED on storage loss.

The tests exercise the narrow period gate and assert actual app call sites.
All PostgreSQL tests run only in the disposable CHAT162 localhost sandbox.
"""
from datetime import date
from unittest.mock import AsyncMock
import inspect
import pytest


@pytest.mark.asyncio
async def test_posting_gate_requires_an_explicit_open_transaction():
    from app.api.services.period_transaction_gate import acquire_posting_gate, PeriodGateUnavailable
    conn = AsyncMock()
    conn.is_in_transaction = lambda: False
    with pytest.raises(PeriodGateUnavailable, match="TRANSACTION"):
        await acquire_posting_gate(conn, "t_alpha", date(2026, 10, 30))
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_month_post_and_month_close_use_shared_year_then_matching_month_modes():
    from app.api.services.period_transaction_gate import acquire_posting_gate, acquire_close_gate
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    await acquire_posting_gate(conn, "t_alpha", "2026-10-30")
    assert len(conn.execute.await_args_list) == 2
    assert all("pg_advisory_xact_lock_shared" in a.args[0] for a in conn.execute.await_args_list)
    keys = [a.args[1] for a in conn.execute.await_args_list]
    conn.execute.reset_mock()
    await acquire_close_gate(conn, "t_alpha", 2026, 10)
    assert len(conn.execute.await_args_list) == 2
    assert "pg_advisory_xact_lock_shared" in conn.execute.await_args_list[0].args[0]
    assert "pg_advisory_xact_lock(" in conn.execute.await_args_list[1].args[0]
    assert keys == [a.args[1] for a in conn.execute.await_args_list]
    conn.execute.reset_mock()
    await acquire_close_gate(conn, "t_alpha", 2026, 0)
    assert len(conn.execute.await_args_list) == 1
    assert "pg_advisory_xact_lock(" in conn.execute.await_args_list[0].args[0]
    assert conn.execute.await_args_list[0].args[1] == keys[0]


@pytest.mark.asyncio
async def test_invalid_date_or_tenant_refuses_before_database_access():
    from app.api.services.period_transaction_gate import acquire_posting_gate, PeriodGateUnavailable
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    for tenant, day in [
        ("default", "2026-10-30"), ("t_alpha", None),
        ("t_alpha", "2026-10-30junk"), ("t_alpha", "2026-02-30"),
    ]:
        with pytest.raises(PeriodGateUnavailable):
            await acquire_posting_gate(conn, tenant, day)
    conn.execute.assert_not_called()


def test_mutation_call_sites_must_share_the_gate_and_fail_closed():
    from app.api.services import posting_service
    from app.api import routes_period_lock
    posting = inspect.getsource(posting_service.apply_posting_service)
    closing = inspect.getsource(routes_period_lock.lock_period)
    reopening = inspect.getsource(routes_period_lock.unlock_period)
    assert "await acquire_posting_gate(" in posting
    assert "await acquire_close_gate(" in closing
    assert "await acquire_close_gate(" in reopening
    assert "PERIOD_LOCK_UNAVAILABLE" in posting
    assert "posting proceeding" not in posting


@pytest.mark.asyncio
@pytest.mark.parametrize("day,period_failure", [
    ("2026-10-30", True), (None, False), ("not-a-date", False),
])
async def test_real_posting_aborts_when_period_lookup_fails(day, period_failure):
    """Actual apply_posting_service must NOT call any ERP on period errors."""
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock, patch
    from app.api.services.posting_service import apply_posting_service

    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    conn.transaction = MagicMock(return_value=AsyncMock())
    conn.fetchrow.return_value = {
        "id": 187, "tenant_id": "t_alpha", "date": day,
        "description": "synthetic-only", "partner": "", "amount": 25,
        "status": "approved", "currency": "GEL",
        "lines_json": [{"account_code": "1120", "debit": 25, "credit": 0},
                       {"account_code": "6110", "debit": 0, "credit": 25}],
    }
    conn.fetchval.side_effect = (
        RuntimeError("synthetic period lock table outage") if period_failure else None
    )
    @asynccontextmanager
    async def scoped():
        yield conn

    with patch("app.api.services.posting_service.get_conn", scoped), \
         patch("app.api.services.posting_service._post_via_connector") as outbound, \
         patch("app.api.services.posting_service.log_event") as audit:
        response = await apply_posting_service(187, "mock", "t_alpha", force=True)

    assert response["error"]["code"] == "PERIOD_LOCK_UNAVAILABLE"
    outbound.assert_not_called()
    assert not any("INSERT INTO posting_logs" in str(c.args[0])
                   for c in conn.fetchval.await_args_list)
    assert not any("UPDATE journal_drafts" in str(c.args[0])
                   for c in conn.execute.await_args_list)
