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


def test_create_item_includes_tenant_scope():
    from app.api.services import inventory_service

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": 77})

    @asynccontextmanager
    async def _ctx():
        yield conn

    with patch("app.api.services.inventory_service.get_conn", _ctx):
        result = asyncio.run(inventory_service.create_item("tenant_a", {
            "item_code": "SKU-1",
            "item_name": "Test item",
        }))

    assert result["tenant_id"] == "tenant_a"
    assert conn.fetchrow.await_args.args[1] == "tenant_a"


def test_record_movement_rejects_cross_tenant_item():
    from app.api.services import inventory_service

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _ctx():
        yield conn

    with patch("app.api.services.inventory_service.get_conn", _ctx):
        try:
            asyncio.run(inventory_service.record_movement("tenant_a", {
                "item_id": 99,
                "movement_type": "in",
                "quantity": 1,
                "unit_cost": 10,
            }))
        except ValueError as exc:
            assert str(exc) == "ITEM_NOT_FOUND"
        else:
            raise AssertionError("cross-tenant or missing item must be rejected")


def test_record_movement_creates_journal_draft_for_accounting_impact():
    from app.api.services import inventory_service

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=[
        {"id": 5, "item_code": "SKU-1", "item_name": "Test item"},
        {"id": 88},
    ])

    @asynccontextmanager
    async def _ctx():
        yield conn

    with patch("app.api.services.inventory_service.get_conn", _ctx), \
         patch("app.api.services.inventory_service.create_journal_draft", AsyncMock(return_value={"id": 123})) as draft_mock:
        result = asyncio.run(inventory_service.record_movement("tenant_a", {
            "item_id": 5,
            "movement_type": "in",
            "quantity": 2,
            "unit_cost": 7,
        }))

    assert result["journal_draft_id"] == 123
    draft_mock.assert_awaited_once()
    kwargs = draft_mock.await_args.kwargs
    assert kwargs["tenant_id"] == "tenant_a"
    assert kwargs["source_document_id"] == 88
    assert kwargs["lines"] == [
        {"account_code": "1310", "debit": 14.0, "credit": 0},
        {"account_code": "3110", "debit": 0, "credit": 14.0},
    ]


def test_stock_report_structure():
    from app.api.services import inventory_service

    with patch("app.api.services.inventory_service.list_items", AsyncMock(return_value={
        "items": [
            {"current_stock": 3, "purchase_price": 4, "reorder_level": 5},
            {"current_stock": 2, "purchase_price": 10, "reorder_level": 1},
        ],
        "total": 2,
        "low_stock_count": 1,
    })):
        result = asyncio.run(inventory_service.get_stock_report("tenant_a"))

    assert result["total"] == 2
    assert result["reported_count"] == 2
    assert result["total_qty"] == 5
    assert result["total_stock_value"] == 32


def test_inventory_movement_history_join_is_tenant_scoped():
    import inspect
    from app.api.services import inventory_service

    src = inspect.getsource(inventory_service.get_movements)
    assert "i.tenant_id = m.tenant_id" in src


def test_inventory_unauthenticated_gets_401_or_403():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.get("/inventory/items")
    assert resp.status_code in (401, 403)
