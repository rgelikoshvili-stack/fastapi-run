"""tests/unit/test_sprint4_ledger_truth.py

Sprint 4 unit tests — Posted Ledger Truth.
No live DB; asyncpg connections are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_conn(
    fetchval_returns: list | None = None,
    fetch_returns: list | None = None,
    fetchrow_returns: list | None = None,
):
    """Build a mock asyncpg connection."""
    fv_iter = iter(fetchval_returns or [])
    fr_iter = iter(fetch_returns or [[]])
    frr_iter = iter(fetchrow_returns or [None])

    async def fake_fetchval(*a, **k):
        return next(fv_iter, 0)

    async def fake_fetch(*a, **k):
        return next(fr_iter, [])

    async def fake_fetchrow(*a, **k):
        return next(frr_iter, None)

    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=fake_fetchval)
    conn.fetch = AsyncMock(side_effect=fake_fetch)
    conn.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    return conn


def _row(**kwargs):
    """Minimal asyncpg-like row for mocking."""
    return kwargs


# ─────────────────────────────────────────────────────────────────────────────
# _health_score
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthScore:
    def test_no_issues(self):
        from app.api.services.ledger_truth_service import _health_score
        assert _health_score([]) == 100

    def test_one_phantom(self):
        from app.api.services.ledger_truth_service import _health_score
        issues = [{"type": "PHANTOM_POST", "count": 1}]
        assert _health_score(issues) == 80

    def test_one_duplicate(self):
        from app.api.services.ledger_truth_service import _health_score
        issues = [{"type": "DUPLICATE_POST", "count": 1}]
        assert _health_score(issues) == 75

    def test_multiple_issues_clamped(self):
        from app.api.services.ledger_truth_service import _health_score
        issues = [
            {"type": "PHANTOM_POST", "count": 5},
            {"type": "DUPLICATE_POST", "count": 5},
        ]
        assert _health_score(issues) == 0  # clamped to 0

    def test_failed_unretried(self):
        from app.api.services.ledger_truth_service import _health_score
        issues = [{"type": "FAILED_UNRETRIED", "count": 1}]
        assert _health_score(issues) == 90

    def test_sync_mismatch(self):
        from app.api.services.ledger_truth_service import _health_score
        issues = [{"type": "SYNC_MISMATCH", "count": 1}]
        assert _health_score(issues) == 85


# ─────────────────────────────────────────────────────────────────────────────
# _safe serialiser
# ─────────────────────────────────────────────────────────────────────────────

class TestSafe:
    def test_decimal_becomes_float(self):
        import decimal
        from app.api.services.ledger_truth_service import _safe
        row = {"amount": decimal.Decimal("1234.56")}
        result = _safe(row)
        assert isinstance(result["amount"], float)
        assert abs(result["amount"] - 1234.56) < 0.001

    def test_date_becomes_string(self):
        import datetime
        from app.api.services.ledger_truth_service import _safe
        row = {"date": datetime.date(2025, 1, 1)}
        result = _safe(row)
        assert isinstance(result["date"], str)
        assert "2025" in result["date"]

    def test_none_row(self):
        from app.api.services.ledger_truth_service import _safe
        assert _safe(None) == {}

    def test_plain_dict_passthrough(self):
        from app.api.services.ledger_truth_service import _safe
        row = {"id": 1, "partner": "Acme", "amount": 100.0}
        result = _safe(row)
        assert result["partner"] == "Acme"


# ─────────────────────────────────────────────────────────────────────────────
# run_ledger_truth — happy path (all clean)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_ledger_truth_clean():
    from app.api.services.ledger_truth_service import run_ledger_truth

    conn = _make_conn(
        fetch_returns=[[], [], [], [], []],   # 5 issue queries return empty
        fetchrow_returns=[_row(               # stats row
            total_posted=10,
            total_approved_unposted=2,
            total_rejected=1,
            posted_gel=50000.0,
            approved_unposted_gel=1000.0,
        )],
    )

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await run_ledger_truth("tenant1")

    assert result["health_score"] == 100
    assert result["health_label"] == "HEALTHY"
    assert result["issue_count"] == 0
    assert result["issues"] == []
    assert "stats" in result


@pytest.mark.asyncio
async def test_run_ledger_truth_with_period_filter():
    from app.api.services.ledger_truth_service import run_ledger_truth

    conn = _make_conn(
        fetch_returns=[[], [], [], [], []],
        fetchrow_returns=[{}],
    )

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await run_ledger_truth("tenant1", period_from="2025-01-01", period_to="2025-12-31")

    assert result["period_from"] == "2025-01-01"
    assert result["period_to"] == "2025-12-31"
    assert result["health_score"] == 100


@pytest.mark.asyncio
async def test_run_ledger_truth_phantom_post_found():
    from app.api.services.ledger_truth_service import run_ledger_truth

    phantom_row = _row(
        id=42, description="Sale", amount=5000.0, partner="Acme",
        date="2025-06-01", debit_account="1310", credit_account="6100",
        status="posted", created_at="2025-06-01T12:00:00",
    )

    # fetch calls: phantom=1 row, sync=[], failed=[], dup=[], large=[]
    # fetchrow: stats
    conn = _make_conn(
        fetch_returns=[[phantom_row], [], [], [], []],
        fetchrow_returns=[_row(total_posted=5, total_approved_unposted=0,
                               total_rejected=0, posted_gel=5000.0,
                               approved_unposted_gel=0.0)],
    )

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await run_ledger_truth("tenant1")

    phantom_issue = next((i for i in result["issues"] if i["type"] == "PHANTOM_POST"), None)
    assert phantom_issue is not None
    assert phantom_issue["severity"] == "HIGH"
    assert phantom_issue["count"] == 1
    assert result["health_score"] < 100
    assert result["high_severity"] >= 1


@pytest.mark.asyncio
async def test_run_ledger_truth_duplicate_post_found():
    from app.api.services.ledger_truth_service import run_ledger_truth

    dup_row = _row(
        id=7, description="Dup", amount=1000.0, partner="Test",
        date="2025-05-01", success_count=2, systems="balance_ge, balance_ge",
    )

    conn = _make_conn(
        fetch_returns=[[], [], [], [dup_row], []],
        fetchrow_returns=[{}],
    )

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await run_ledger_truth("tenant1")

    dup_issue = next((i for i in result["issues"] if i["type"] == "DUPLICATE_POST"), None)
    assert dup_issue is not None
    assert dup_issue["severity"] == "HIGH"
    assert dup_issue["count"] == 1


@pytest.mark.asyncio
async def test_run_ledger_truth_severity_order():
    """HIGH issues come before MEDIUM in the issues list."""
    from app.api.services.ledger_truth_service import run_ledger_truth

    # FAILED_UNRETRIED (MEDIUM) is returned first in fetch order;
    # PHANTOM_POST (HIGH) second — final list must be HIGH first.
    failed_row = _row(id=1, description="F", amount=100.0, partner="X",
                      date="2025-01-01", draft_status="approved",
                      target_system="balance_ge", error_message="timeout",
                      failed_at="2025-01-01T00:00:00")
    phantom_row = _row(id=2, description="P", amount=200.0, partner="Y",
                       date="2025-01-02", debit_account="1310",
                       credit_account="6100", status="posted",
                       created_at="2025-01-02T00:00:00")

    conn = _make_conn(
        # phantom(idx=0), sync(idx=1), failed(idx=2), dup(idx=3), large(idx=4)
        fetch_returns=[[phantom_row], [], [failed_row], [], []],
        fetchrow_returns=[{}],
    )

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await run_ledger_truth("tenant1")

    severities = [i["severity"] for i in result["issues"]]
    # HIGH must come before MEDIUM
    if "HIGH" in severities and "MEDIUM" in severities:
        assert severities.index("HIGH") < severities.index("MEDIUM")


# ─────────────────────────────────────────────────────────────────────────────
# quick_ledger_health
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quick_health_all_clear():
    from app.api.services.ledger_truth_service import quick_ledger_health

    conn = _make_conn(fetchval_returns=[0, 0, 0, 0])

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await quick_ledger_health("tenant1")

    assert result["health_score"] == 100
    assert result["health_label"] == "HEALTHY"
    assert result["all_clear"] is True
    assert result["phantom_posts"] == 0


@pytest.mark.asyncio
async def test_quick_health_phantom():
    from app.api.services.ledger_truth_service import quick_ledger_health

    conn = _make_conn(fetchval_returns=[2, 0, 0, 0])  # 2 phantom posts

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await quick_ledger_health("tenant1")

    assert result["phantom_posts"] == 2
    assert result["health_score"] == 60   # 100 - 2*20
    assert result["all_clear"] is False
    assert "phantom" in result["issues"][0]


@pytest.mark.asyncio
async def test_quick_health_duplicate():
    from app.api.services.ledger_truth_service import quick_ledger_health

    conn = _make_conn(fetchval_returns=[0, 0, 0, 1])  # 1 duplicate

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await quick_ledger_health("tenant1")

    assert result["duplicate_posts"] == 1
    assert result["health_score"] == 75   # 100 - 1*25
    assert result["health_label"] == "WARNING"


@pytest.mark.asyncio
async def test_quick_health_critical():
    from app.api.services.ledger_truth_service import quick_ledger_health

    conn = _make_conn(fetchval_returns=[3, 2, 1, 2])  # many issues

    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await quick_ledger_health("tenant1")

    assert result["health_label"] == "CRITICAL"
    assert result["health_score"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Route handlers
# ─────────────────────────────────────────────────────────────────────────────

def _make_request(tenant_id="t1"):
    req = MagicMock()
    req.state.tenant_id = tenant_id
    req.state.role = "accountant"
    req.state.authenticated = True
    return req


def _clean_result():
    return {
        "health_score": 100,
        "health_label": "HEALTHY",
        "issue_count": 0,
        "high_severity": 0,
        "medium_severity": 0,
        "issues": [],
        "stats": {},
        "period_from": None,
        "period_to": None,
        "summary": "Posted Ledger: 100/100 — ყველაფერი კარგადაა",
    }


@pytest.mark.asyncio
async def test_report_route_ok():
    from app.api.routes_ledger_truth import ledger_truth_report
    handler = getattr(ledger_truth_report, "__wrapped__", ledger_truth_report)

    with patch("app.api.routes_ledger_truth.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_ledger_truth.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_ledger_truth.run_ledger_truth", new_callable=AsyncMock, return_value=_clean_result()):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert response["data"]["health_score"] == 100


@pytest.mark.asyncio
async def test_health_route_ok():
    from app.api.routes_ledger_truth import ledger_quick_health
    handler = getattr(ledger_quick_health, "__wrapped__", ledger_quick_health)

    quick = {
        "health_score": 100, "health_label": "HEALTHY",
        "phantom_posts": 0, "sync_mismatches": 0,
        "failed_unretried": 0, "duplicate_posts": 0,
        "issues": [], "all_clear": True,
        "summary": "Posted Ledger health: 100/100 — ყველაფერი კარგადაა",
    }

    with patch("app.api.routes_ledger_truth.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_ledger_truth.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_ledger_truth.quick_ledger_health", new_callable=AsyncMock, return_value=quick):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert response["data"]["all_clear"] is True


@pytest.mark.asyncio
async def test_unverified_route_no_phantoms():
    from app.api.routes_ledger_truth import ledger_unverified
    handler = getattr(ledger_unverified, "__wrapped__", ledger_unverified)

    with patch("app.api.routes_ledger_truth.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_ledger_truth.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_ledger_truth.run_ledger_truth", new_callable=AsyncMock, return_value=_clean_result()):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert response["data"]["count"] == 0
    assert response["data"]["drafts"] == []


@pytest.mark.asyncio
async def test_unverified_route_with_phantoms():
    from app.api.routes_ledger_truth import ledger_unverified
    handler = getattr(ledger_unverified, "__wrapped__", ledger_unverified)

    result_with_phantom = {
        **_clean_result(),
        "health_score": 80,
        "issue_count": 1,
        "high_severity": 1,
        "issues": [{
            "type": "PHANTOM_POST",
            "severity": "HIGH",
            "count": 1,
            "description": "1 draft(s) marked 'posted' but no posting_log success record",
            "drafts": [{"id": 99, "description": "Phantom", "amount": 5000.0}],
        }],
    }

    with patch("app.api.routes_ledger_truth.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_ledger_truth.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_ledger_truth.run_ledger_truth", new_callable=AsyncMock, return_value=result_with_phantom):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert response["data"]["count"] == 1
    assert len(response["data"]["drafts"]) == 1


@pytest.mark.asyncio
async def test_failed_postings_route_no_failures():
    from app.api.routes_ledger_truth import ledger_failed_postings
    handler = getattr(ledger_failed_postings, "__wrapped__", ledger_failed_postings)

    with patch("app.api.routes_ledger_truth.require_permission", new_callable=AsyncMock), \
         patch("app.api.routes_ledger_truth.resolve_tenant_id", new_callable=AsyncMock, return_value="t1"), \
         patch("app.api.routes_ledger_truth.run_ledger_truth", new_callable=AsyncMock, return_value=_clean_result()):
        response = await handler(request=_make_request())

    assert response["ok"] is True
    assert response["data"]["count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Router structure
# ─────────────────────────────────────────────────────────────────────────────

def test_router_prefix():
    from app.api.routes_ledger_truth import router
    assert router.prefix == "/ledger-truth"


def test_routes_registered():
    from app.api.routes_ledger_truth import router
    paths = [r.path for r in router.routes]
    assert "/ledger-truth/report" in paths
    assert "/ledger-truth/health" in paths
    assert "/ledger-truth/unverified" in paths
    assert "/ledger-truth/failed-postings" in paths


# ─────────────────────────────────────────────────────────────────────────────
# AI tool — get_ledger_truth
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ledger_truth_tool_quick():
    from app.api.services.ai_tool_registry import run_tool

    conn = _make_conn(fetchval_returns=[0, 0, 0, 0])
    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await run_tool("get_ledger_truth", {"quick": "true"}, "tenant1")

    assert result["approval_required"] is False
    assert "health_score" in result
    assert result["health_score"] == 100


@pytest.mark.asyncio
async def test_get_ledger_truth_tool_full():
    from app.api.services.ai_tool_registry import run_tool

    conn = _make_conn(
        fetch_returns=[[], [], [], [], []],
        fetchrow_returns=[_row(total_posted=5, total_approved_unposted=0,
                               total_rejected=0, posted_gel=5000.0,
                               approved_unposted_gel=0.0)],
    )
    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await run_tool("get_ledger_truth", {}, "tenant1")

    assert result["approval_required"] is False
    assert result["health_score"] == 100
    assert "issues" in result


@pytest.mark.asyncio
async def test_get_ledger_truth_tool_with_period():
    from app.api.services.ai_tool_registry import run_tool

    conn = _make_conn(
        fetch_returns=[[], [], [], [], []],
        fetchrow_returns=[{}],
    )
    with patch("app.api.services.ledger_truth_service.get_conn", return_value=conn):
        result = await run_tool(
            "get_ledger_truth",
            {"period_from": "2025-01-01", "period_to": "2025-12-31"},
            "tenant1"
        )

    assert result["approval_required"] is False
    assert result.get("period_from") == "2025-01-01"


def test_get_ledger_truth_in_registry():
    from app.api.services.ai_tool_registry import TOOL_DESCRIPTIONS, _TOOL_MAP
    assert "get_ledger_truth" in TOOL_DESCRIPTIONS
    assert "get_ledger_truth" in _TOOL_MAP


def test_total_tool_count():
    from app.api.services.ai_tool_registry import _TOOL_MAP
    # 13 original + 4 sprint 2 + 1 sprint 3A + 1 sprint 3C + 1 sprint 4 + 1 sprint 5
    assert len(_TOOL_MAP) == 21
