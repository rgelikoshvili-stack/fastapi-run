"""Safety contract tests for BIZ-2 posted-ledger cashflow/CFO reporting."""
import asyncio
from contextlib import asynccontextmanager

from app.api.services import cashflow_classification_service as classification
from app.api.services import financial_statements_service as statements


def _line(header, code, debit=0, credit=0, *, category=None, account_type=None, description=""):
    return {
        "header_id": header,
        "account_code": code,
        "debit": debit,
        "credit": credit,
        "cashflow_category": category,
        "account_type": account_type,
        "description": description,
    }


class FakeConn:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.calls = []

    async def fetch(self, query, *params):
        self.calls.append((query, params))
        if self.error:
            raise self.error
        if "SUM(jel.debit) AS total_debit" in query and "GROUP BY jel.account_code" in query:
            return self.rows
        if "journal_entry_lines" in query:
            return self.rows
        return []

    async def fetchval(self, query, *params):
        self.calls.append((query, params))
        return 0

    async def fetchrow(self, query, *params):
        self.calls.append((query, params))
        return {"monthly_depr": 0}


def _install_conn(monkeypatch, conn):
    @asynccontextmanager
    async def get_conn():
        yield conn
    monkeypatch.setattr("app.api.db.get_conn", get_conn)
    monkeypatch.setattr(statements, "get_conn", get_conn)


def test_classification_prefers_structured_category_and_guards_account_type():
    structured = classification.classify_cashflow_line(
        "1120", "9999", 50, cashflow_category="investing", counterpart_account_type="asset"
    )
    assert structured["category"] == "investing"

    mismatched = classification.classify_cashflow_line(
        "1120", "3410", 50, counterpart_account_type="income"
    )
    assert mismatched["category"] == "unknown"


def test_compound_entry_counts_each_cash_movement_once():
    rows = [
        _line("h1", "1120", debit=100, account_type="asset"),
        _line("h1", "6110", credit=60, account_type="income"),
        _line("h1", "6120", credit=40, account_type="income"),
    ]
    result = classification.build_cashflow_from_posted_ledger_rows(rows)
    assert result["operating"]["inflows"] == 100
    assert len(result["operating"]["lines"]) == 1


def test_cashflow_category_on_cash_line_is_authoritative_once():
    rows = [
        _line("h2", "1120", debit=100, category="financing", account_type="asset"),
        _line("h2", "6110", credit=60, account_type="income"),
        _line("h2", "6120", credit=40, account_type="income"),
    ]
    result = classification.build_cashflow_from_posted_ledger_rows(rows)
    assert result["financing"]["inflows"] == 100
    assert result["operating"]["inflows"] == 0


def test_empty_cashflow_is_zeroed():
    result = classification.build_cashflow_from_posted_ledger_rows([])
    assert result["net_change_in_cash"] == 0
    assert result["operating"]["inflows"] == 0


def test_cashflow_query_binds_tenant_and_date_to_without_date_from():
    sql, params = statements._build_cashflow_posted_ledger_query("tenant-a", None, "2026-09-30")
    assert "jeh.tenant_id = $1" in sql
    assert "jeh.entry_date <= $3" in sql
    assert "journal_drafts" not in sql
    assert params == ["tenant-a", list(statements.STANDARD_NET_STATUSES), "2026-09-30"]


def test_cashflow_query_binds_both_date_bounds_and_tenant():
    sql, params = statements._build_cashflow_posted_ledger_query("tenant-a", "2026-09-01", "2026-09-30")
    assert "jeh.tenant_id = $1" in sql
    assert "jeh.entry_date >= $3" in sql
    assert "jeh.entry_date <= $4" in sql
    assert params[-2:] == ["2026-09-01", "2026-09-30"]


def test_cashflow_query_rejects_missing_tenant():
    try:
        statements._build_cashflow_posted_ledger_query("", None, None)
    except ValueError as exc:
        assert "tenant_id is required" in str(exc)
    else:
        raise AssertionError("missing tenant must fail closed")


def test_cashflow_uses_posted_ledger_and_does_not_fallback_to_drafts(monkeypatch):
    conn = FakeConn(rows=[
        _line("h1", "1120", debit=50, category="operating", account_type="asset"),
        _line("h1", "6110", credit=50, account_type="income"),
    ])
    _install_conn(monkeypatch, conn)
    response = asyncio.run(statements.build_cashflow_statement("tenant-a", date_to="2026-09-30"))
    query, params = conn.calls[0]
    assert "journal_entry_headers" in query and "journal_entry_lines" in query
    assert "journal_drafts" not in query
    assert "jeh.tenant_id = $1" in query and params[0] == "tenant-a"
    assert "jeh.entry_date <= $3" in query and params[-1] == "2026-09-30"
    assert response["ok"] is True
    assert response["data"]["operating"]["inflows"] == 50


def test_cashflow_db_query_isolates_tenant_rows(monkeypatch):
    all_rows = [
        {**_line("tenant-a-header", "1120", debit=40, category="operating"), "tenant_id": "tenant-a"},
        {**_line("tenant-a-header", "6110", credit=40, account_type="income"), "tenant_id": "tenant-a"},
        {**_line("tenant-b-header", "1120", debit=9000, category="financing"), "tenant_id": "tenant-b"},
        {**_line("tenant-b-header", "3410", credit=9000, account_type="liability"), "tenant_id": "tenant-b"},
    ]

    class TenantScopedConn(FakeConn):
        async def fetch(self, query, *params):
            self.calls.append((query, params))
            assert "jeh.tenant_id = $1" in query
            return [row for row in all_rows if row["tenant_id"] == params[0]]

    conn = TenantScopedConn()
    _install_conn(monkeypatch, conn)
    response = asyncio.run(statements.build_cashflow_statement("tenant-a"))
    assert response["ok"] is True
    assert response["data"]["operating"]["inflows"] == 40
    assert response["data"]["financing"]["inflows"] == 0


def test_cashflow_posted_ledger_failure_is_unavailable_not_draft_fallback(monkeypatch):
    conn = FakeConn(error=RuntimeError("ledger unavailable"))
    _install_conn(monkeypatch, conn)
    response = asyncio.run(statements.build_cashflow_statement("tenant-a"))
    assert len(conn.calls) == 1
    assert "journal_entry_lines" in conn.calls[0][0]
    assert "journal_drafts" not in conn.calls[0][0]
    assert response["ok"] is False
    assert response["error"]["code"] == "POSTED_LEDGER_UNAVAILABLE"


def test_posted_trial_balance_query_is_tenant_and_as_of_scoped(monkeypatch):
    conn = FakeConn(rows=[{"account_code": "1120", "total_debit": 300, "total_credit": 100}])
    _install_conn(monkeypatch, conn)
    balance = asyncio.run(statements._get_posted_trial_balance_as_of("tenant-a", "2026-09-30"))
    query, params = conn.calls[0]
    assert "jeh.tenant_id = $1" in query
    assert "jeh.entry_date <= $3" in query
    assert "journal_drafts" not in query
    assert params[0] == "tenant-a" and params[-1] == "2026-09-30"
    assert balance == {"1120": 200}


def test_cfo_cash_position_uses_as_of_posted_balance_and_marks_source(monkeypatch):
    from app.api.services import cfo_dashboard_service as dashboard

    calls = []

    async def posted_balance(tenant_id, as_of):
        calls.append((tenant_id, as_of))
        return {"1110": 25, "1120": 75}

    async def pnl(*args):
        return {"ok": True, "data": {"revenue": {"total": 0}, "cogs": {"total": 0}, "gross_profit": 0, "opex": {"total": 0}, "ebit": 0}}

    async def cashflow(*args):
        return {"ok": True, "data": {"operating": {"net": 0}, "investing": {"net": 0}, "financing": {"net": 0}, "net_change_in_cash": 0}}

    class DashboardConn(FakeConn):
        async def fetch(self, query, *params):
            self.calls.append((query, params))
            return []

    conn = DashboardConn()
    _install_conn(monkeypatch, conn)
    monkeypatch.setattr(statements, "_get_posted_trial_balance_as_of", posted_balance)
    monkeypatch.setattr(statements, "build_profit_and_loss", pnl)
    monkeypatch.setattr(statements, "build_cashflow_statement", cashflow)

    result = asyncio.run(dashboard.build_cfo_dashboard("tenant-a", as_of="2026-09-30"))
    position = result["cash_position"]
    assert calls == [("tenant-a", "2026-09-30")]
    assert position["available"] is True
    assert position["source"] == "posted_ledger"
    assert position["as_of"] == "2026-09-30"
    assert position["total_liquid"] == 100


def test_cfo_cash_position_is_unavailable_when_posted_ledger_read_fails():
    result = __import__(
        "app.api.services.cfo_dashboard_service", fromlist=["build_cfo_dashboard_from_data"]
    ).build_cfo_dashboard_from_data(
        trial_balance=None,
        pnl={"revenue": {"total": 0}, "cogs": {"total": 0}, "gross_profit": 0, "opex": {"total": 0}, "ebit": 0},
        as_of="2026-09-30",
    )
    position = result["cash_position"]
    assert position["available"] is False
    assert position["source"] == "unavailable"
    assert position["total_liquid"] is None
