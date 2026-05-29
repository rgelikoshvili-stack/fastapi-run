"""tests/unit/test_phase3_15_ask_bridge_hub.py — Task 15: Ask Bridge Hub.

Covers:
  1. parse_intent — query type detection
  2. parse_intent — amount filter extraction
  3. parse_intent — month filter extraction
  4. format_answer — per query type
  5. execute_intent_query (mocked DB) — expenses, revenue, unreconciled, status, summary
  6. ask() full pipeline (mocked DB)
  7. Routes: importable, prefix, permission
  8. Permission map and registry
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ctx(rows=None, total=0, fetchrow=None):
    conn = AsyncMock()
    conn.fetch    = AsyncMock(return_value=rows or [])
    conn.fetchval = AsyncMock(return_value=total)
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# 1. parse_intent — query type
# ---------------------------------------------------------------------------
class TestParseIntentQueryType:
    def test_expenses_english(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("Show me all expenses this month")["query_type"] == "expenses"

    def test_expenses_georgian(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("ამ თვის ხარჯები")["query_type"] == "expenses"

    def test_revenue_english(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("What was revenue for January")["query_type"] == "revenue"

    def test_revenue_sales(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("total sales this month")["query_type"] == "revenue"

    def test_unreconciled(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("which drafts are unreconciled")["query_type"] == "unreconciled"

    def test_drafts_by_status(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("show me posted drafts")["query_type"] == "drafts_by_status"

    def test_balance_summary(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("give me a balance summary")["query_type"] == "balance_summary"

    def test_unknown_falls_back(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("hello world")["query_type"] == "unknown"


# ---------------------------------------------------------------------------
# 2. parse_intent — amount filter
# ---------------------------------------------------------------------------
class TestParseIntentAmount:
    def test_over_amount(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        intent = parse_intent("expenses over 1000 GEL")
        assert intent["filters"]["min_amount"] == 1000.0

    def test_above_amount(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        intent = parse_intent("costs above 500")
        assert intent["filters"]["min_amount"] == 500.0

    def test_under_amount(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        intent = parse_intent("expenses under 200")
        assert intent["filters"]["max_amount"] == 200.0

    def test_no_amount_filter(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        intent = parse_intent("show all expenses")
        assert intent["filters"]["min_amount"] is None
        assert intent["filters"]["max_amount"] is None


# ---------------------------------------------------------------------------
# 3. parse_intent — month filter
# ---------------------------------------------------------------------------
class TestParseIntentMonth:
    def test_this_month(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        from datetime import date
        expected = date.today().strftime("%Y-%m")
        intent = parse_intent("expenses this month")
        assert intent["filters"]["month"] == expected

    def test_named_month(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        intent = parse_intent("revenue for January")
        assert intent["filters"]["month"].endswith("-01")

    def test_yyyy_mm_format(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        intent = parse_intent("show drafts for 2026-03")
        assert intent["filters"]["month"] == "2026-03"

    def test_no_month_filter(self):
        from app.api.services.ask_bridge_hub_service import parse_intent
        assert parse_intent("show all expenses")["filters"]["month"] is None


# ---------------------------------------------------------------------------
# 4. format_answer
# ---------------------------------------------------------------------------
class TestFormatAnswer:
    def _intent(self, qt, month=None, status=None):
        return {"query_type": qt, "filters": {"month": month, "status": status}, "original": "test"}

    def test_expenses_message(self):
        from app.api.services.ask_bridge_hub_service import format_answer
        rows = [{"description": "Office rent", "amount": 2000}]
        msg = format_answer({"rows": rows, "total": 2000}, self._intent("expenses", "2026-01"))
        assert "expense" in msg.lower()
        assert "2,000.00" in msg

    def test_revenue_message(self):
        from app.api.services.ask_bridge_hub_service import format_answer
        msg = format_answer({"rows": [{"amount": 5000}], "total": 5000}, self._intent("revenue"))
        assert "revenue" in msg.lower()

    def test_unreconciled_message(self):
        from app.api.services.ask_bridge_hub_service import format_answer
        msg = format_answer({"rows": [{}], "total": 100}, self._intent("unreconciled"))
        assert "unreconciled" in msg.lower()

    def test_no_rows_message(self):
        from app.api.services.ask_bridge_hub_service import format_answer
        msg = format_answer({"rows": [], "total": 0}, self._intent("expenses"))
        assert "no records" in msg.lower()


# ---------------------------------------------------------------------------
# 5. execute_intent_query (mocked)
# ---------------------------------------------------------------------------
class TestExecuteIntentQuery:
    @pytest.mark.asyncio
    async def test_expenses_query(self):
        from app.api.services.ask_bridge_hub_service import execute_intent_query
        row = {"id": 1, "description": "Rent", "amount": 1000, "account_code": "7310",
               "status": "posted", "created_at": "2026-01-01", "partner": "Landlord"}
        with patch("app.api.services.ask_bridge_hub_service.get_conn", return_value=_ctx(rows=[row], total=1000)):
            result = await execute_intent_query("t1", {"query_type": "expenses", "filters": {}})
        assert result["total"] == 1000.0
        assert len(result["rows"]) == 1

    @pytest.mark.asyncio
    async def test_unknown_returns_empty(self):
        from app.api.services.ask_bridge_hub_service import execute_intent_query
        result = await execute_intent_query("t1", {"query_type": "unknown", "filters": {}})
        assert result["rows"] == []

    @pytest.mark.asyncio
    async def test_unreconciled_query(self):
        from app.api.services.ask_bridge_hub_service import execute_intent_query
        row = {"id": 2, "description": "Invoice", "amount": 500, "status": "posted",
               "created_at": "2026-01-01", "partner": "Client"}
        with patch("app.api.services.ask_bridge_hub_service.get_conn", return_value=_ctx(rows=[row], total=500)):
            result = await execute_intent_query("t1", {"query_type": "unreconciled", "filters": {}})
        assert len(result["rows"]) == 1


# ---------------------------------------------------------------------------
# 6. ask() full pipeline
# ---------------------------------------------------------------------------
class TestAskPipeline:
    @pytest.mark.asyncio
    async def test_returns_question_intent_answer(self):
        from app.api.services.ask_bridge_hub_service import ask
        row = {"id": 1, "description": "Fuel", "amount": 200, "account_code": "7910",
               "status": "posted", "created_at": "2026-01-01", "partner": "Gas station"}
        with patch("app.api.services.ask_bridge_hub_service.get_conn", return_value=_ctx(rows=[row], total=200)):
            result = await ask("t1", "show expenses this month")
        assert "question" in result
        assert "intent" in result
        assert "answer" in result
        assert result["intent"]["query_type"] == "expenses"


# ---------------------------------------------------------------------------
# 7. Routes
# ---------------------------------------------------------------------------
class TestAskRoutes:
    def test_router_importable(self):
        import importlib
        mod = importlib.import_module("app.api.routes_ask_bridge_hub")
        assert hasattr(mod, "router")

    def test_router_prefix(self):
        from app.api.routes_ask_bridge_hub import router
        assert router.prefix == "/ask"

    def test_ask_requires_chat_use(self):
        import ast, pathlib
        src = pathlib.Path("app/api/routes_ask_bridge_hub.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "ask_question":
                assert "chat:use" in ast.unparse(node)
                return
        pytest.fail("ask_question not found")


# ---------------------------------------------------------------------------
# 8. Permission map and registry
# ---------------------------------------------------------------------------
class TestAskRegistration:
    def test_permission_map_has_ask(self):
        import pathlib
        src = pathlib.Path("app/api/policy/permission_map.py").read_text(encoding="utf-8")
        assert '"/ask"' in src or "'/ask'" in src

    def test_router_registered(self):
        import pathlib
        src = pathlib.Path("app/core/router_registry.py").read_text(encoding="utf-8")
        assert "routes_ask_bridge_hub" in src

    def test_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.ask_bridge_hub_service")
        assert hasattr(mod, "parse_intent")
        assert hasattr(mod, "execute_intent_query")
        assert hasattr(mod, "format_answer")
        assert hasattr(mod, "ask")
