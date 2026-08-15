"""Sprint 2 — Cross-reference AI tool tests.

Tests get_contracts, get_payroll_status, get_posting_log,
get_monthly_close_status, and the enhanced ai_context_builder.

All DB calls are mocked; no real database required.
"""
from __future__ import annotations

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

class _FR(dict):
    """Fake asyncpg Record — dict subclass so dict(row) returns self."""


def _conn_returning(*row_lists):
    """Build a mock async context-manager connection.
    row_lists[0] → first fetch/fetchrow/fetchval call, etc.
    For simplicity, conn.fetch always returns the first list,
    conn.fetchrow always returns the first item of the first list,
    conn.fetchval returns a scalar.
    """
    conn = AsyncMock()

    async def _fetch(sql, *args, **kw):
        return row_lists[0] if row_lists else []

    async def _fetchrow(sql, *args, **kw):
        rows = row_lists[0] if row_lists else []
        return rows[0] if rows else None

    async def _fetchval(sql, *args, **kw):
        return row_lists[1] if len(row_lists) > 1 else 0

    conn.fetch = _fetch
    conn.fetchrow = _fetchrow
    conn.fetchval = _fetchval
    return conn


def _ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


TENANT = "test-tenant"

# ─────────────────────────────────────────────────────────────
# Tool registry imports
# ─────────────────────────────────────────────────────────────

from app.api.services.ai_tool_registry import (
    _TOOL_MAP,
    TOOL_DESCRIPTIONS,
    run_tool,
)


# ─────────────────────────────────────────────────────────────
# 1. Tool registration — Sprint 2 entries must exist
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "get_contracts",
    "get_payroll_status",
    "get_posting_log",
    "get_monthly_close_status",
])
def test_sprint2_tools_in_tool_map(name):
    assert name in _TOOL_MAP, f"{name} missing from _TOOL_MAP"


@pytest.mark.parametrize("name", [
    "get_contracts",
    "get_payroll_status",
    "get_posting_log",
    "get_monthly_close_status",
])
def test_sprint2_tools_in_descriptions(name):
    assert name in TOOL_DESCRIPTIONS


def test_total_tool_count():
    # 13 original + 4 sprint 2
    assert len(_TOOL_MAP) == 17


# ─────────────────────────────────────────────────────────────
# 2. get_contracts
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_contracts_returns_list():
    contract_row = _FR({
        "id": 1, "contract_number": "C-001", "title": "IT Services",
        "party_name": "TechCorp", "party_tax_id": "123456789",
        "contract_type": "service", "status": "active",
        "value": 15000.0, "currency": "GEL",
        "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31),
        "payment_terms": "30 days", "auto_renew": False,
        "created_at": datetime(2026, 1, 1), "overdue_milestones": 0,
    })

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[contract_row])
    conn.fetchval = AsyncMock(return_value=1)

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_contracts"]({}, TENANT)

    assert result["count"] == 1
    assert result["approval_required"] is False
    c = result["contracts"][0]
    assert c["party_name"] == "TechCorp"
    assert c["value"] == 15000.0


@pytest.mark.asyncio
async def test_get_contracts_empty():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=0)

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_contracts"]({}, TENANT)

    assert result["count"] == 0
    assert result["contracts"] == []


@pytest.mark.asyncio
async def test_get_contracts_overdue_milestones():
    row = _FR({
        "id": 2, "contract_number": "C-002", "title": "Cleaning",
        "party_name": "CleanCo", "party_tax_id": None,
        "contract_type": "service", "status": "active",
        "value": 3000.0, "currency": "GEL",
        "start_date": date(2025, 1, 1), "end_date": date(2026, 12, 31),
        "payment_terms": None, "auto_renew": False,
        "created_at": datetime(2025, 1, 1), "overdue_milestones": 2,
    })

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[row])
    conn.fetchval = AsyncMock(return_value=1)

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_contracts"]({}, TENANT)

    assert result["overdue_milestones_total"] == 2
    assert "ვადაგადაცილებული" in result["summary"]


@pytest.mark.asyncio
async def test_get_contracts_via_run_tool():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=0)

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await run_tool("get_contracts", {}, TENANT)

    assert "contracts" in result


# ─────────────────────────────────────────────────────────────
# 3. get_payroll_status
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_payroll_status_accepted():
    sub_row = _FR({
        "id": 10, "run_id": 5, "period": "2026-07",
        "status": "accepted", "submission_ref": "RS-2026-07-001",
        "submitted_at": datetime(2026, 7, 25),
        "resolved_at": datetime(2026, 7, 26),
        "notes": None, "created_at": datetime(2026, 7, 25),
        "updated_at": datetime(2026, 7, 26),
    })

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[sub_row])

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_payroll_status"]({"period": "2026-07"}, TENANT)

    assert result["found"] is True
    assert result["latest_status"] == "accepted"
    assert result["status_georgian"] == "მიღებულია RS.ge-ზე"
    assert result["submission_ref"] == "RS-2026-07-001"


@pytest.mark.asyncio
async def test_get_payroll_status_not_found():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_payroll_status"]({"period": "2025-01"}, TENANT)

    assert result["found"] is False
    assert "ვერ მოიძებნა" in result["message"]


@pytest.mark.asyncio
async def test_get_payroll_status_draft():
    sub_row = _FR({
        "id": 11, "run_id": 6, "period": "2026-08",
        "status": "draft", "submission_ref": None,
        "submitted_at": None, "resolved_at": None,
        "notes": None, "created_at": datetime(2026, 8, 1),
        "updated_at": datetime(2026, 8, 1),
    })

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[sub_row])

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_payroll_status"]({}, TENANT)

    assert result["latest_status"] == "draft"
    assert result["status_georgian"] == "მომზადებულია"


@pytest.mark.asyncio
async def test_get_payroll_status_rejected():
    sub_row = _FR({
        "id": 12, "run_id": 7, "period": "2026-06",
        "status": "rejected", "submission_ref": "RS-BAD",
        "submitted_at": datetime(2026, 6, 25),
        "resolved_at": datetime(2026, 6, 26),
        "notes": "ველი 12 არასწორია", "created_at": datetime(2026, 6, 25),
        "updated_at": datetime(2026, 6, 26),
    })

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[sub_row])

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_payroll_status"]({"period": "2026-06"}, TENANT)

    assert result["status_georgian"] == "უარყოფილია RS.ge-ზე"
    assert result["notes"] == "ველი 12 არასწორია"


# ─────────────────────────────────────────────────────────────
# 4. get_posting_log
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_posting_log_requires_draft_id():
    result = await _TOOL_MAP["get_posting_log"]({}, TENANT)
    assert "error" in result
    assert "draft_id" in result["error"]


@pytest.mark.asyncio
async def test_get_posting_log_success_entry():
    log_row = _FR({
        "id": 99, "draft_id": 42, "target_system": "balance_ge",
        "status": "success", "error_message": None,
        "mode": "live", "actor": "admin", "connector": "balance_ge",
        "created_at": datetime(2026, 8, 10),
        "draft_description": "შეტანა — ელ. ტექნიკა",
        "draft_amount": 5000.0, "draft_status": "posted",
    })

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[log_row])

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_posting_log"]({"draft_id": 42}, TENANT)

    assert result["count"] == 1
    assert result["last_success"] is not None
    assert result["last_failure"] is None
    log0 = result["logs"][0]
    assert log0["status_georgian"] == "წარმატებულია"


@pytest.mark.asyncio
async def test_get_posting_log_failed_entry():
    log_row = _FR({
        "id": 100, "draft_id": 43, "target_system": "balance_ge",
        "status": "failed", "error_message": "timeout",
        "mode": "live", "actor": "admin", "connector": "balance_ge",
        "created_at": datetime(2026, 8, 11),
        "draft_description": "ჩამოწერა", "draft_amount": 1200.0,
        "draft_status": "approved",
    })

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[log_row])

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_posting_log"]({"draft_id": 43}, TENANT)

    assert result["last_failure"] is not None
    assert result["last_success"] is None
    assert result["logs"][0]["status_georgian"] == "წარუმატებელია"


@pytest.mark.asyncio
async def test_get_posting_log_empty():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=_ctx(conn)):
        result = await _TOOL_MAP["get_posting_log"]({"draft_id": 999}, TENANT)

    assert result["count"] == 0
    assert "ცარიელია" in result["summary"]


# ─────────────────────────────────────────────────────────────
# 5. get_monthly_close_status
# ─────────────────────────────────────────────────────────────

_CHECKLIST_ALL_OK = [
    {"id": "unposted_drafts", "name": "All transactions posted or rejected",
     "status": "ok", "detail": "No unposted drafts", "value": 0},
    {"id": "reconciliation_rate", "name": "Bank reconciliation ≥ 90%",
     "status": "ok", "detail": "Reconciliation rate: 95%", "value": 95.0},
    {"id": "opening_balances", "name": "Opening balances verified",
     "status": "ok", "detail": "Balanced: 100000.00 = 100000.00", "value": True},
    {"id": "payroll_submitted", "name": "Payroll RS.ge submission",
     "status": "ok", "detail": "Payroll submission status: accepted", "value": "accepted"},
    {"id": "trial_balance", "name": "Trial balance balanced",
     "status": "ok", "detail": "Balanced: 200000.00 = 200000.00", "value": True},
]

_CHECKLIST_WITH_FAILURE = [
    {"id": "unposted_drafts", "name": "All transactions posted or rejected",
     "status": "failed", "detail": "3 unposted drafts remain", "value": 3},
    {"id": "reconciliation_rate", "name": "Bank reconciliation ≥ 90%",
     "status": "ok", "detail": "Reconciliation rate: 92%", "value": 92.0},
    {"id": "opening_balances", "name": "Opening balances verified",
     "status": "warning", "detail": "No opening balances data", "value": False},
    {"id": "payroll_submitted", "name": "Payroll RS.ge submission",
     "status": "warning", "detail": "No payroll submission found", "value": None},
    {"id": "trial_balance", "name": "Trial balance balanced",
     "status": "failed", "detail": "Unbalanced: debit=50.00 credit=0.00 diff=50.0000", "value": False},
]


@pytest.mark.asyncio
async def test_get_monthly_close_all_ok():
    with patch(
        "app.api.services.monthly_close_service.run_checklist",
        new=AsyncMock(return_value=_CHECKLIST_ALL_OK),
    ):
        result = await _TOOL_MAP["get_monthly_close_status"](
            {"month": "2026-07"}, TENANT
        )

    assert result["ok_count"] == 5
    assert result["failed_count"] == 0
    assert result["warning_count"] == 0
    assert "შესაძლებელია" in result["overall_status"]


@pytest.mark.asyncio
async def test_get_monthly_close_with_failures():
    with patch(
        "app.api.services.monthly_close_service.run_checklist",
        new=AsyncMock(return_value=_CHECKLIST_WITH_FAILURE),
    ):
        result = await _TOOL_MAP["get_monthly_close_status"](
            {"month": "2026-08"}, TENANT
        )

    assert result["failed_count"] == 2
    assert result["warning_count"] == 2
    assert "შეუძლებელია" in result["overall_status"]
    assert "All transactions posted or rejected" in result["failed_items"]


@pytest.mark.asyncio
async def test_get_monthly_close_default_month():
    """When no month param given, should default to current YYYY-MM."""
    from datetime import date as _dt
    expected_month = f"{_dt.today().year}-{_dt.today().month:02d}"

    captured = {}

    async def fake_checklist(tenant_id, month):
        captured["month"] = month
        return _CHECKLIST_ALL_OK

    with patch(
        "app.api.services.monthly_close_service.run_checklist",
        new=AsyncMock(side_effect=fake_checklist),
    ):
        await _TOOL_MAP["get_monthly_close_status"]({}, TENANT)

    assert captured["month"] == expected_month


@pytest.mark.asyncio
async def test_get_monthly_close_checklist_in_result():
    with patch(
        "app.api.services.monthly_close_service.run_checklist",
        new=AsyncMock(return_value=_CHECKLIST_ALL_OK),
    ):
        result = await _TOOL_MAP["get_monthly_close_status"](
            {"month": "2026-07"}, TENANT
        )

    assert "checklist" in result
    assert len(result["checklist"]) == 5


# ─────────────────────────────────────────────────────────────
# 6. Enhanced context builder
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_builder_includes_bank_summary():
    from app.api.services.ai_context_builder import build_ai_context

    async def fake_bank(tenant_id):
        return {"unreconciled_count": 5, "total_transactions_90d": 42}

    async def fake_contracts(tenant_id):
        return [{"party_name": "TechCorp", "value": 5000.0}]

    async def fake_patterns(tenant_id):
        return []

    async def fake_drafts(tenant_id, limit=10):
        return []

    with patch("app.api.services.ai_context_builder.get_bank_summary", new=fake_bank), \
         patch("app.api.services.ai_context_builder.get_active_contracts_summary", new=fake_contracts), \
         patch("app.api.services.ai_context_builder.get_vendor_patterns", new=fake_patterns), \
         patch("app.api.services.ai_context_builder.get_recent_drafts_summary", new=fake_drafts):
        ctx = await build_ai_context(TENANT)

    assert "bank_summary" in ctx
    assert ctx["bank_summary"]["unreconciled_count"] == 5
    assert "active_contracts" in ctx
    assert ctx["active_contracts"][0]["party_name"] == "TechCorp"


@pytest.mark.asyncio
async def test_context_builder_includes_all_keys():
    from app.api.services.ai_context_builder import build_ai_context

    with patch("app.api.services.ai_context_builder.get_bank_summary",
               new=AsyncMock(return_value={})), \
         patch("app.api.services.ai_context_builder.get_active_contracts_summary",
               new=AsyncMock(return_value=[])), \
         patch("app.api.services.ai_context_builder.get_vendor_patterns",
               new=AsyncMock(return_value=[])), \
         patch("app.api.services.ai_context_builder.get_recent_drafts_summary",
               new=AsyncMock(return_value=[])):
        ctx = await build_ai_context(TENANT)

    for key in ("tenant_id", "chart_of_accounts", "tax_rules",
                "vendor_patterns", "recent_drafts", "bank_summary", "active_contracts"):
        assert key in ctx, f"Missing key: {key}"
