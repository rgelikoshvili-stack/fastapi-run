"""tests/unit/test_reports_routes.py
Financial reports structural unit tests.
"""
import inspect
from unittest.mock import MagicMock, patch


def _mock_db(rows=None):
    """Return a mock psycopg2 connection that returns `rows` from fetchall."""
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


# ── 1. P&L endpoint exists in financial_statements router ────────────────────

def test_pnl_endpoint_exists():
    import app.api.routes_financial_statements as mod
    src = inspect.getsource(mod)
    assert "pnl" in src or "profit" in src.lower()


# ── 2. P&L service returns ok=True with mocked empty DB ──────────────────────

def test_pnl_service_returns_ok_with_empty_db():
    with patch("app.api.services.financial_statements_service.get_db", return_value=_mock_db()):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = build_profit_and_loss("test_tenant", None, None)
    assert result.get("ok") is True
    data = result.get("data", {})
    assert "revenue" in data
    assert "ebit" in data or "gross_profit" in data


# ── 3. Balance Sheet returns balanced flag with empty DB ──────────────────────

def test_balance_sheet_has_balanced_flag_with_empty_db():
    with patch("app.api.services.financial_statements_service.get_db", return_value=_mock_db()):
        from app.api.services.financial_statements_service import build_balance_sheet
        result = build_balance_sheet("test_tenant", None)
    assert result.get("ok") is True
    data = result.get("data", {})
    assert "balanced" in data
    assert "assets" in data
    assert "liabilities" in data
    assert "equity" in data


# ── 4. Balance Sheet: empty DB → all zero → balanced ─────────────────────────

def test_balance_sheet_zero_is_balanced():
    with patch("app.api.services.financial_statements_service.get_db", return_value=_mock_db()):
        from app.api.services.financial_statements_service import build_balance_sheet
        result = build_balance_sheet("test_tenant", None)
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
    with patch("app.api.services.financial_statements_service.get_db", return_value=_mock_db()):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = build_profit_and_loss("test_tenant", None, None)
    data = result.get("data", {})
    rev = data.get("revenue", {})
    assert "lines" in rev
    assert "total" in rev
    assert rev["total"] == 0.0


# ── 8. Balance Sheet sub-sections with empty DB ──────────────────────────────

def test_balance_sheet_subsections_empty():
    with patch("app.api.services.financial_statements_service.get_db", return_value=_mock_db()):
        from app.api.services.financial_statements_service import build_balance_sheet
        result = build_balance_sheet("test_tenant", None)
    data = result.get("data", {})
    assets = data.get("assets", {})
    assert "current" in assets
    assert "non_current" in assets
    assert "total" in assets
    assert assets["total"] == 0.0
