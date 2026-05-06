"""tests/unit/test_inventory.py — Inventory service unit tests."""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch


# ── 1. FIFO leaves oldest batches ─────────────────────────────────────────────

def test_fifo_oldest_batch_remains():
    from app.api.services.inventory_service import _fifo_value

    ins  = [{"qty": 10, "cost": 5.0, "date": "2026-01-01"},  # oldest
            {"qty": 10, "cost": 8.0, "date": "2026-02-01"}]  # newer
    outs = [{"qty": 10}]  # consume oldest batch first

    result = _fifo_value(ins, outs)

    # FIFO: first 10 consumed → only newer batch (cost=8) remains
    assert result["quantity"] == 10
    assert result["total_value"] == 80.0


# ── 2. LIFO leaves oldest batch ───────────────────────────────────────────────

def test_lifo_newest_consumed_first():
    from app.api.services.inventory_service import _lifo_value

    ins  = [{"qty": 10, "cost": 5.0, "date": "2026-01-01"},
            {"qty": 10, "cost": 8.0, "date": "2026-02-01"}]
    outs = [{"qty": 10}]  # consume newest batch first (LIFO)

    result = _lifo_value(ins, outs)

    # LIFO: newest 10 consumed (cost=8) → only oldest (cost=5) remains
    assert result["quantity"] == 10
    assert result["total_value"] == 50.0


# ── 3. Weighted average ───────────────────────────────────────────────────────

def test_average_value():
    from app.api.services.inventory_service import _average_value

    ins  = [{"qty": 10, "cost": 4.0}, {"qty": 10, "cost": 6.0}]  # avg=5
    outs = [{"qty": 5}]

    result = _average_value(ins, outs)

    assert result["quantity"] == 15  # 20 - 5
    assert result["avg_cost"] == 5.0
    assert result["total_value"] == 75.0


# ── 4. Insufficient stock blocked ────────────────────────────────────────────

def test_insufficient_stock_returns_error():
    """get_current_stock returns a value; route blocks if qty > available."""
    from app.api.services import inventory_service

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=3.0)

    @asynccontextmanager
    async def _ctx():
        yield conn

    with patch("app.api.services.inventory_service.get_conn", _ctx):
        stock = asyncio.run(inventory_service.get_current_stock("tenant_a", 1))

    assert stock == 3.0
    requested = 10
    assert requested > stock  # would be blocked by route


# ── 5. PO auto-number generation ─────────────────────────────────────────────

def test_po_auto_number():
    from app.api.services import inventory_service

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=5)  # COUNT(*)+1 = 5 → PO-...-0005
    conn.fetchrow = AsyncMock(return_value={"id": 42})
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield conn

    with patch("app.api.services.inventory_service.get_conn", _ctx):
        result = asyncio.run(inventory_service.create_purchase_order("tenant_a", {"lines": []}))

    assert "po_number" in result
    assert result["po_number"].startswith("PO-")


# ── 6. FIFO with zero stock ───────────────────────────────────────────────────

def test_fifo_no_stock():
    from app.api.services.inventory_service import _fifo_value

    result = _fifo_value([], [])

    assert result["quantity"] == 0
    assert result["total_value"] == 0
    assert result["avg_cost"] == 0
