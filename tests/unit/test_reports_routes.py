"""tests/unit/test_reports_routes.py
Financial reports structural unit tests.
"""
import asyncio
import inspect
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch


def _mock_conn(rows=None):
    """Return a mock asyncpg connection."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=None)
    return conn


def _make_get_conn(rows=None):
    """Factory: returns a callable that behaves like get_conn() async ctx mgr."""
    conn = _mock_conn(rows)

    @asynccontextmanager
    async def _ctx():
        yield conn

    return _ctx


# ── 1. P&L endpoint exists in financial_statements router ────────────────────

def test_pnl_endpoint_exists():
    import app.api.routes_financial_statements as mod
    src = inspect.getsource(mod)
    assert "pnl" in src or "profit" in src.lower()


# ── 2. P&L service returns ok=True with mocked empty DB ──────────────────────

def test_pnl_service_returns_ok_with_empty_db():
    with patch("app.api.services.financial_statements_service.get_conn",
               _make_get_conn()):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = asyncio.run(build_profit_and_loss("test_tenant", None, None))
    assert result.get("ok") is True
    data = result.get("data", {})
    assert "revenue" in data
    assert "ebit" in data or "gross_profit" in data


# ── 3. Balance Sheet returns balanced flag with empty DB ──────────────────────

def test_balance_sheet_has_balanced_flag_with_empty_db():
    with patch("app.api.services.financial_statements_service.get_conn",
               _make_get_conn()):
        from app.api.services.financial_statements_service import build_balance_sheet
        result = asyncio.run(build_balance_sheet("test_tenant", None))
    assert result.get("ok") is True
    data = result.get("data", {})
    assert "balanced" in data
    assert "assets" in data
    assert "liabilities" in data
    assert "equity" in data


# ── 4. Balance Sheet: empty DB → all zero → balanced ─────────────────────────

def test_balance_sheet_zero_is_balanced():
    with patch("app.api.services.financial_statements_service.get_conn",
               _make_get_conn()):
        from app.api.services.financial_statements_service import build_balance_sheet
        result = asyncio.run(build_balance_sheet("test_tenant", None))
    data = result.get("data", {})
    assets = data.get("assets", {}).get("total", 0)
    le = data.get("total_liabilities_and_equity", 0)
    assert abs(assets - le) < 0.05


# ── 5. P&L is tenant-isolated (different tenants → independent queries) ───────

def test_pnl_is_tenant_scoped_structurally():
    from app.api.services import financial_statements_service as mod
    src = inspect.getsource(mod)
    assert "tenant_id" in src
    assert src.count("tenant_id") >= 3


# ── 6. Balance Sheet service uses trial balance ───────────────────────────────

def test_balance_sheet_uses_trial_balance():
    from app.api.services import financial_statements_service as mod
    src = inspect.getsource(mod)
    assert "_get_trial_balance" in src


# ── 7. P&L line items structure with empty DB ────────────────────────────────

def test_pnl_line_items_structure_empty():
    with patch("app.api.services.financial_statements_service.get_conn",
               _make_get_conn()):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = asyncio.run(build_profit_and_loss("test_tenant", None, None))
    data = result.get("data", {})
    rev = data.get("revenue", {})
    assert "lines" in rev
    assert "total" in rev
    assert rev["total"] == 0.0


# ── 8. Balance Sheet sub-sections with empty DB ──────────────────────────────

def test_balance_sheet_subsections_empty():
    with patch("app.api.services.financial_statements_service.get_conn",
               _make_get_conn()):
        from app.api.services.financial_statements_service import build_balance_sheet
        result = asyncio.run(build_balance_sheet("test_tenant", None))
    data = result.get("data", {})
    assets = data.get("assets", {})
    assert "current" in assets
    assert "non_current" in assets
    assert "total" in assets
    assert assets["total"] == 0.0


def test_financial_statements_use_posted_entries_only():
    from app.api.services import financial_statements_service as mod
    src = inspect.getsource(mod._get_trial_balance)
    assert "FROM journal_drafts" in src
    assert "jd.status = 'posted'" in src
    assert "approved" not in src
    assert "auto_approved" not in src


def test_monthly_report_filters_pipeline_runs_by_tenant():
    from types import SimpleNamespace
    import app.api.routes_reports as mod

    conn = _mock_conn()

    @asynccontextmanager
    async def _ctx():
        yield conn

    request = SimpleNamespace(
        state=SimpleNamespace(authenticated=True, role="admin", tenant_id="tenant-a")
    )
    with patch("app.api.routes_reports.get_conn", _ctx):
        result = asyncio.run(mod.monthly_report(request))

    assert result["ok"] is True
    first_call = conn.fetch.await_args_list[0]
    sql = first_call.args[0]
    args = first_call.args[1:]
    assert "FROM pipeline_runs" in sql
    assert "tenant_id" in sql
    assert args == ("tenant-a",)


# ── P1-1: annual_report and audit_trail are tenant-isolated ──────────────────

def test_annual_report_filters_by_tenant():
    """annual_report SQL must include WHERE tenant_id = %s."""
    import app.api.routes_reports as mod
    src = inspect.getsource(mod.annual_report)
    assert "FROM pipeline_runs" in src
    assert "tenant_id" in src
    assert "getattr(request.state" in src or "tenant_id" in src


def test_annual_report_passes_tenant_id_to_query():
    """annual_report must pass tenant_id as a positional param (not inline in SQL)."""
    import app.api.routes_reports as mod
    src = inspect.getsource(mod.annual_report)
    assert "WHERE tenant_id = %s" in src
    assert "getattr(request.state" in src


def test_audit_trail_filters_by_tenant():
    """audit_trail SQL must include WHERE tenant_id = %s."""
    import app.api.routes_reports as mod
    src = inspect.getsource(mod.audit_trail)
    assert "FROM pipeline_runs" in src
    assert "WHERE tenant_id = %s" in src
    assert "getattr(request.state" in src


def test_audit_trail_has_rate_limiter():
    """audit_trail must be decorated with @limiter.limit."""
    import inspect as _inspect
    import app.api.routes_reports as mod
    # The module source shows limiter.limit applied to audit_trail
    module_src = _inspect.getsource(mod)
    idx_audit = module_src.index("async def audit_trail")
    snippet = module_src[max(0, idx_audit - 80):idx_audit]
    assert "limiter.limit" in snippet


def test_annual_report_has_rate_limiter():
    """annual_report must be decorated with @limiter.limit."""
    import inspect as _inspect
    import app.api.routes_reports as mod
    module_src = _inspect.getsource(mod)
    idx_annual = module_src.index("async def annual_report")
    snippet = module_src[max(0, idx_annual - 80):idx_annual]
    assert "limiter.limit" in snippet
