"""tests/unit/test_sprint5_cockpit.py

Sprint 5 unit tests — Chief Accountant Cockpit.
No live DB; asyncpg connections are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_conn(
    fetchval_seq: list | None = None,
    fetch_seq: list | None = None,
    fetchrow_seq: list | None = None,
):
    fv = iter(fetchval_seq or [])
    fc = iter(fetch_seq or [[]])
    fr = iter(fetchrow_seq or [None])

    async def fake_fetchval(*a, **k): return next(fv, 0)
    async def fake_fetch(*a, **k):    return next(fc, [])
    async def fake_fetchrow(*a, **k): return next(fr, None)

    conn = AsyncMock()
    conn.fetchval  = AsyncMock(side_effect=fake_fetchval)
    conn.fetch     = AsyncMock(side_effect=fake_fetch)
    conn.fetchrow  = AsyncMock(side_effect=fake_fetchrow)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__  = AsyncMock(return_value=False)
    return conn


def _row(**kwargs): return kwargs


def _make_request(tenant_id="t1"):
    req = MagicMock()
    req.state.tenant_id = tenant_id
    req.state.role = "accountant"
    req.state.authenticated = True
    return req


# ─────────────────────────────────────────────────────────────────────────────
# _safe serialiser
# ─────────────────────────────────────────────────────────────────────────────

class TestSafe:
    def test_decimal(self):
        import decimal
        from app.api.services.cockpit_service import _safe
        result = _safe({"amount": decimal.Decimal("1234.56")})
        assert isinstance(result["amount"], float)

    def test_date(self):
        import datetime
        from app.api.services.cockpit_service import _safe
        result = _safe({"d": datetime.date(2025, 6, 1)})
        assert isinstance(result["d"], str)

    def test_none(self):
        from app.api.services.cockpit_service import _safe
        assert _safe(None) == {}


# ─────────────────────────────────────────────────────────────────────────────
# get_cockpit_brief
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_brief_all_clear():
    from app.api.services.cockpit_service import get_cockpit_brief

    conn = _make_conn(fetchval_seq=[0, 0, 0, 0])
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit_brief("t1")

    assert result["alert_level"] == "OK"
    assert result["all_clear"] is True
    assert result["pending_approvals"] == 0
    assert result["phantom_posts"] == 0
    assert result["ledger_health_score"] == 100


@pytest.mark.asyncio
async def test_brief_warning_on_pending():
    from app.api.services.cockpit_service import get_cockpit_brief

    conn = _make_conn(fetchval_seq=[5, 0, 0, 0])  # 5 pending
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit_brief("t1")

    assert result["pending_approvals"] == 5
    assert result["alert_level"] in ("WARNING", "OK")   # pending alone = not CRITICAL
    assert not result["all_clear"]
    assert any("pending" in a for a in result["alerts"])


@pytest.mark.asyncio
async def test_brief_critical_on_phantom():
    from app.api.services.cockpit_service import get_cockpit_brief

    conn = _make_conn(fetchval_seq=[0, 0, 6, 0])  # 6 phantom posts → score 0
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit_brief("t1")

    assert result["phantom_posts"] == 6
    assert result["alert_level"] == "CRITICAL"
    assert result["ledger_health_score"] == 0


@pytest.mark.asyncio
async def test_brief_risk_drafts():
    from app.api.services.cockpit_service import get_cockpit_brief

    conn = _make_conn(fetchval_seq=[0, 3, 0, 0])  # 3 risk drafts
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit_brief("t1")

    assert result["high_risk_drafts"] == 3
    assert any("high-risk" in a for a in result["alerts"])


# ─────────────────────────────────────────────────────────────────────────────
# get_cockpit (full)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_cockpit_clean():
    from app.api.services.cockpit_service import get_cockpit

    empty_fetch    = [[], [], [], []]  # risks, pending items, postings, approvals
    empty_fetchval = [0, 0, 0, 0, 0]  # pending total, phantom, failed, total_txn, unreconciled
    empty_fetchrow = [_row(
        posted_count=10, approved_count=2, pending_count=0,
        rejected_count=1, posted_gel=50000.0, approved_gel=2000.0,
    )]

    conn = _make_conn(
        fetchval_seq=empty_fetchval,
        fetch_seq=empty_fetch,
        fetchrow_seq=empty_fetchrow,
    )
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit("t1")

    assert "risks" in result
    assert "pending" in result
    assert "recent_actions" in result
    assert "ledger_health" in result
    assert "bank_reconciliation" in result
    assert "period_stats" in result
    assert "alert_level" in result
    assert "alerts" in result
    assert "summary" in result


@pytest.mark.asyncio
async def test_full_cockpit_risk_items():
    from app.api.services.cockpit_service import get_cockpit

    risk_row = _row(
        id=1, description="Test", amount=8000.0, partner=None,
        account_code=None, debit_account="1310", credit_account="6100",
        status="approved", confidence=None, source_type="manual",
        date="2025-06-01", created_at="2025-06-01T00:00:00",
        risk_reason="missing_partner",
    )

    conn = _make_conn(
        # _get_risks fetch, _get_pending fetch, postings fetch, approvals fetch
        fetch_seq=[[risk_row], [], [], []],
        fetchval_seq=[1, 0, 0, 0, 0],  # pending total, phantom, failed, total, unreconciled
        fetchrow_seq=[{}],
    )
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit("t1")

    assert result["risks"]["count"] == 1
    assert result["risks"]["items"][0]["id"] == 1


@pytest.mark.asyncio
async def test_full_cockpit_pending_items():
    from app.api.services.cockpit_service import get_cockpit

    pending_row = _row(
        id=5, description="Salary", amount=3000.0, partner="Employee",
        status="awaiting_cfo", confidence=0.9, source_type="manual",
        date="2025-06-01", created_at="2025-06-01T00:00:00",
    )

    conn = _make_conn(
        fetch_seq=[[], [pending_row], [], []],
        fetchval_seq=[1, 0, 0, 0, 0],   # total=1 pending, phantom=0, failed=0, ...
        fetchrow_seq=[{}],
    )
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit("t1")

    assert result["pending"]["total"] == 1
    assert result["pending"]["awaiting_cfo"] == 1
    assert result["pending"]["items"][0]["id"] == 5


@pytest.mark.asyncio
async def test_full_cockpit_recent_postings():
    from app.api.services.cockpit_service import get_cockpit

    posting_row = _row(
        id=100, draft_id=42, target_system="balance_ge", status="success",
        error_message=None, mode="live", actor="system",
        created_at="2025-06-02T10:00:00",
        description="Sale", amount=1000.0, partner="Acme",
    )

    conn = _make_conn(
        fetch_seq=[[], [], [posting_row], []],
        fetchval_seq=[0, 0, 0, 0, 0],
        fetchrow_seq=[{}],
    )
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit("t1")

    postings = result["recent_actions"]["postings"]
    assert len(postings) == 1
    assert postings[0]["event_type"] == "posting_success"


@pytest.mark.asyncio
async def test_full_cockpit_alert_level_warning():
    from app.api.services.cockpit_service import get_cockpit

    conn = _make_conn(
        fetch_seq=[[], [], [], []],
        # phantom=1 → health_score 80 → WARNING
        fetchval_seq=[0, 1, 0, 0, 0],
        fetchrow_seq=[{}],
    )
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await get_cockpit("t1")

    assert result["alert_level"] in ("WARNING", "CRITICAL")
    assert any("phantom" in a for a in result["alerts"])


# ─────────────────────────────────────────────────────────────────────────────
# Route handlers
# ─────────────────────────────────────────────────────────────────────────────

def _full_cockpit_result():
    return {
        "alert_level": "OK",
        "alerts": [],
        "risks": {"count": 0, "items": []},
        "pending": {"total": 0, "items": []},
        "recent_actions": {"postings": [], "approvals": []},
        "ledger_health": {"health_score": 100, "health_label": "HEALTHY",
                          "phantom_posts": 0, "failed_unretried": 0},
        "bank_reconciliation": {"total_bank_transactions": 0, "unreconciled_estimate": 0},
        "period_stats": {},
        "summary": "Cockpit: OK — ყველაფერი კარგადაა",
    }


def _brief_cockpit_result():
    return {
        "alert_level": "OK",
        "pending_approvals": 0,
        "high_risk_drafts": 0,
        "phantom_posts": 0,
        "failed_postings": 0,
        "ledger_health_score": 100,
        "alerts": [],
        "all_clear": True,
        "summary": "Cockpit: ყველაფერი კარგადაა",
    }


@pytest.mark.asyncio
async def test_cockpit_full_route():
    from app.api.routes_cockpit import cockpit_full
    handler = getattr(cockpit_full, "__wrapped__", cockpit_full)

    with patch("app.api.routes_cockpit.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_cockpit.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_cockpit.get_cockpit", new_callable=AsyncMock, return_value=_full_cockpit_result()):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert response["data"]["alert_level"] == "OK"


@pytest.mark.asyncio
async def test_cockpit_brief_route():
    from app.api.routes_cockpit import cockpit_brief
    handler = getattr(cockpit_brief, "__wrapped__", cockpit_brief)

    with patch("app.api.routes_cockpit.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_cockpit.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_cockpit.get_cockpit_brief", new_callable=AsyncMock, return_value=_brief_cockpit_result()):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert response["data"]["all_clear"] is True


@pytest.mark.asyncio
async def test_cockpit_risks_route():
    from app.api.routes_cockpit import cockpit_risks
    handler = getattr(cockpit_risks, "__wrapped__", cockpit_risks)

    with patch("app.api.routes_cockpit.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_cockpit.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_cockpit.get_cockpit", new_callable=AsyncMock, return_value=_full_cockpit_result()):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert "count" in response["data"]


@pytest.mark.asyncio
async def test_cockpit_pending_route():
    from app.api.routes_cockpit import cockpit_pending
    handler = getattr(cockpit_pending, "__wrapped__", cockpit_pending)

    with patch("app.api.routes_cockpit.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_cockpit.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_cockpit.get_cockpit", new_callable=AsyncMock, return_value=_full_cockpit_result()):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert "total" in response["data"]


# ─────────────────────────────────────────────────────────────────────────────
# Router structure
# ─────────────────────────────────────────────────────────────────────────────

def test_router_prefix():
    from app.api.routes_cockpit import router
    assert router.prefix == "/cockpit"


def test_routes_registered():
    from app.api.routes_cockpit import router
    paths = [r.path for r in router.routes]
    assert "/cockpit" in paths
    assert "/cockpit/brief" in paths
    assert "/cockpit/risks" in paths
    assert "/cockpit/pending" in paths


# ─────────────────────────────────────────────────────────────────────────────
# AI tool — get_cockpit_summary
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cockpit_tool_brief():
    from app.api.services.ai_tool_registry import run_tool

    conn = _make_conn(fetchval_seq=[0, 0, 0, 0])
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await run_tool("get_cockpit_summary", {}, "t1")

    assert result["approval_required"] is False
    assert "alert_level" in result
    assert "pending_approvals" in result


@pytest.mark.asyncio
async def test_cockpit_tool_full():
    from app.api.services.ai_tool_registry import run_tool

    conn = _make_conn(
        fetchval_seq=[0, 0, 0, 0, 0],
        fetch_seq=[[], [], [], []],
        fetchrow_seq=[{}],
    )
    with patch("app.api.services.cockpit_service.get_conn", return_value=conn):
        result = await run_tool("get_cockpit_summary", {"full": "true"}, "t1")

    assert result["approval_required"] is False
    assert "risks" in result
    assert "pending" in result


def test_cockpit_tool_in_registry():
    from app.api.services.ai_tool_registry import TOOL_DESCRIPTIONS, _TOOL_MAP
    assert "get_cockpit_summary" in TOOL_DESCRIPTIONS
    assert "get_cockpit_summary" in _TOOL_MAP


def test_total_tool_count():
    from app.api.services.ai_tool_registry import _TOOL_MAP
    # 13 original + 4 sprint 2 + 1 sprint 3A + 1 sprint 3C + 1 sprint 4 + 1 sprint 5
    assert len(_TOOL_MAP) == 21
