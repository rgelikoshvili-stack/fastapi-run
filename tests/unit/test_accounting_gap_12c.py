"""tests/unit/test_accounting_gap_12c.py — Task 12C: Inventory FIFO/WACG COGS.

Covers:
  1. Pure FIFO COGS calculation (fifo_cogs)
  2. Pure WACG COGS calculation (wacg_cogs)
  3. compute_cogs dispatcher
  4. Edge cases: zero stock, partial match, single batch
  5. Async compute_dispatch_cogs (mocked DB)
  6. cogs_journal_lines shape
  7. inventory_service.record_movement uses costing engine for "out"
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. FIFO pure function
# ---------------------------------------------------------------------------
class TestFifoCogs:
    def test_single_batch_full_dispatch(self):
        from app.api.services.inventory_costing_service import fifo_cogs
        result = fifo_cogs([{"qty": 10.0, "cost": 5.0}], 10.0)
        assert result["cogs"] == 50.0
        assert result["unmatched_qty"] == 0.0

    def test_fifo_oldest_first(self):
        from app.api.services.inventory_costing_service import fifo_cogs
        purchases = [
            {"qty": 5.0, "cost": 10.0},
            {"qty": 5.0, "cost": 20.0},
        ]
        result = fifo_cogs(purchases, 5.0)
        assert result["cogs"] == 50.0   # takes from oldest batch first

    def test_fifo_spans_two_batches(self):
        from app.api.services.inventory_costing_service import fifo_cogs
        purchases = [
            {"qty": 3.0, "cost": 10.0},
            {"qty": 7.0, "cost": 20.0},
        ]
        result = fifo_cogs(purchases, 5.0)
        # 3 units @ 10 + 2 units @ 20 = 70
        assert result["cogs"] == 70.0
        assert len(result["layers_consumed"]) == 2

    def test_fifo_partial_stock(self):
        from app.api.services.inventory_costing_service import fifo_cogs
        purchases = [{"qty": 3.0, "cost": 10.0}]
        result = fifo_cogs(purchases, 5.0)
        assert result["cogs"] == 30.0
        assert result["unmatched_qty"] == 2.0

    def test_fifo_zero_purchases(self):
        from app.api.services.inventory_costing_service import fifo_cogs
        result = fifo_cogs([], 5.0)
        assert result["cogs"] == 0.0
        assert result["unmatched_qty"] == 5.0

    def test_fifo_unit_cost_calculated(self):
        from app.api.services.inventory_costing_service import fifo_cogs
        purchases = [{"qty": 4.0, "cost": 5.0}, {"qty": 6.0, "cost": 10.0}]
        result = fifo_cogs(purchases, 4.0)
        assert result["unit_cost"] == 5.0


# ---------------------------------------------------------------------------
# 2. WACG pure function
# ---------------------------------------------------------------------------
class TestWacgCogs:
    def test_single_batch(self):
        from app.api.services.inventory_costing_service import wacg_cogs
        result = wacg_cogs([{"qty": 10.0, "cost": 8.0}], 5.0)
        assert result["cogs"] == 40.0
        assert result["avg_purchase_cost"] == 8.0

    def test_weighted_average_two_batches(self):
        from app.api.services.inventory_costing_service import wacg_cogs
        purchases = [
            {"qty": 10.0, "cost": 10.0},
            {"qty": 10.0, "cost": 20.0},
        ]
        result = wacg_cogs(purchases, 10.0)
        # avg = (100 + 200) / 20 = 15.0
        assert result["avg_purchase_cost"] == 15.0
        assert result["cogs"] == 150.0

    def test_wacg_partial_stock(self):
        from app.api.services.inventory_costing_service import wacg_cogs
        result = wacg_cogs([{"qty": 5.0, "cost": 10.0}], 8.0)
        assert result["unmatched_qty"] == 3.0
        assert result["cogs"] == 50.0

    def test_wacg_zero_purchases(self):
        from app.api.services.inventory_costing_service import wacg_cogs
        result = wacg_cogs([], 5.0)
        assert result["cogs"] == 0.0
        assert result["avg_purchase_cost"] == 0.0


# ---------------------------------------------------------------------------
# 3. compute_cogs dispatcher
# ---------------------------------------------------------------------------
class TestComputeCogs:
    def test_dispatches_fifo(self):
        from app.api.services.inventory_costing_service import compute_cogs
        r = compute_cogs("fifo", [{"qty": 10.0, "cost": 5.0}], 5.0)
        assert r["method"] == "fifo"
        assert r["cogs"] == 25.0

    def test_dispatches_average(self):
        from app.api.services.inventory_costing_service import compute_cogs
        r = compute_cogs("average", [{"qty": 10.0, "cost": 5.0}], 5.0)
        assert r["method"] == "average"
        assert r["cogs"] == 25.0

    def test_lifo_falls_back_to_fifo(self):
        from app.api.services.inventory_costing_service import compute_cogs
        purchases = [{"qty": 5.0, "cost": 10.0}, {"qty": 5.0, "cost": 20.0}]
        r = compute_cogs("lifo", purchases, 5.0)
        # falls back to FIFO: takes oldest batch first
        assert r["cogs"] == 50.0


# ---------------------------------------------------------------------------
# 4. Async compute_dispatch_cogs
# ---------------------------------------------------------------------------
class TestComputeDispatchCogs:
    @pytest.mark.asyncio
    async def test_fetches_item_and_purchases(self):
        from app.api.services.inventory_costing_service import compute_dispatch_cogs

        mock_item = {"costing_method": "fifo"}
        mock_purchases = [
            {"quantity": "10", "unit_cost": "5.00"},
            {"quantity": "5",  "unit_cost": "8.00"},
        ]

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_item)
        mock_conn.fetch    = AsyncMock(return_value=[
            MagicMock(**{"__getitem__": lambda s, k: {"quantity": "10", "unit_cost": "5.00"}[k],
                         "quantity": "10", "unit_cost": "5.00"}),
            MagicMock(**{"__getitem__": lambda s, k: {"quantity": "5", "unit_cost": "8.00"}[k],
                         "quantity": "5", "unit_cost": "8.00"}),
        ])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)

        with patch("app.api.services.inventory_costing_service.get_conn", return_value=mock_ctx):
            result = await compute_dispatch_cogs("t1", 1, 10.0, "2026-01-01")

        assert result["costing_method"] == "fifo"
        assert result["dispatch_qty"] == 10.0
        assert result["item_id"] == 1
        assert result["as_of_date"] == "2026-01-01"
        assert "cogs" in result

    @pytest.mark.asyncio
    async def test_defaults_to_fifo_if_no_item(self):
        from app.api.services.inventory_costing_service import compute_dispatch_cogs

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.fetch    = AsyncMock(return_value=[])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)

        with patch("app.api.services.inventory_costing_service.get_conn", return_value=mock_ctx):
            result = await compute_dispatch_cogs("t1", 999, 5.0, "2026-01-01")

        assert result["costing_method"] == "fifo"
        assert result["cogs"] == 0.0


# ---------------------------------------------------------------------------
# 5. cogs_journal_lines
# ---------------------------------------------------------------------------
class TestCogsJournalLines:
    def test_returns_two_lines(self):
        from app.api.services.inventory_costing_service import cogs_journal_lines
        lines = cogs_journal_lines(500.0)
        assert len(lines) == 2

    def test_cogs_debit_7110(self):
        from app.api.services.inventory_costing_service import cogs_journal_lines
        lines = cogs_journal_lines(500.0)
        cogs = next(l for l in lines if l["account_code"] == "7110")
        assert cogs["debit"] == 500.0
        assert cogs["credit"] == 0.0

    def test_inventory_credit_1310(self):
        from app.api.services.inventory_costing_service import cogs_journal_lines
        lines = cogs_journal_lines(500.0)
        inv = next(l for l in lines if l["account_code"] == "1310")
        assert inv["credit"] == 500.0
        assert inv["debit"] == 0.0

    def test_balanced_journal(self):
        from app.api.services.inventory_costing_service import cogs_journal_lines
        lines = cogs_journal_lines(1234.56)
        total_debit  = sum(l["debit"]  for l in lines)
        total_credit = sum(l["credit"] for l in lines)
        assert total_debit == total_credit


# ---------------------------------------------------------------------------
# 6. inventory_service integration: "out" uses costing engine
# ---------------------------------------------------------------------------
class TestInventoryServiceUsesCosting:
    def test_record_movement_imports_costing(self):
        import ast, pathlib
        src = pathlib.Path("app/api/services/inventory_service.py").read_text(encoding="utf-8")
        assert "inventory_costing_service" in src

    def test_record_movement_uses_compute_dispatch_cogs(self):
        import ast, pathlib
        src = pathlib.Path("app/api/services/inventory_service.py").read_text(encoding="utf-8")
        assert "compute_dispatch_cogs" in src

    def test_record_movement_uses_cogs_journal_lines(self):
        import ast, pathlib
        src = pathlib.Path("app/api/services/inventory_service.py").read_text(encoding="utf-8")
        assert "cogs_journal_lines" in src

    def test_costing_service_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.inventory_costing_service")
        assert hasattr(mod, "fifo_cogs")
        assert hasattr(mod, "wacg_cogs")
        assert hasattr(mod, "compute_cogs")
        assert hasattr(mod, "compute_dispatch_cogs")
        assert hasattr(mod, "cogs_journal_lines")
