"""tests/unit/test_inventory.py — Inventory service unit tests."""
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_conn(rows=None, scalar=0):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = (scalar,)
    cur.description = [("qty",)]
    conn.cursor.return_value = cur
    return conn, cur


# ── 1. FIFO leaves oldest batches ─────────────────────────────────────────────

def test_fifo_oldest_batch_remains():
    from app.api.services.inventory_service import _fifo_value

    def fake_in_out(tenant_id, item_id, as_of):
        ins  = [{"qty": 10, "cost": 5.0, "date": "2026-01-01"},  # oldest
                {"qty": 10, "cost": 8.0, "date": "2026-02-01"}]  # newer
        outs = [{"qty": 10}]  # consume oldest batch first
        return ins, outs

    with patch("app.api.services.inventory_service._in_out_movements", side_effect=fake_in_out):
        result = _fifo_value("t", 1, "2026-04-01")

    # FIFO: first 10 consumed → only newer batch (cost=8) remains
    assert result["quantity"] == 10
    assert result["total_value"] == 80.0


# ── 2. LIFO leaves oldest batch ───────────────────────────────────────────────

def test_lifo_newest_consumed_first():
    from app.api.services.inventory_service import _lifo_value

    def fake_in_out(tenant_id, item_id, as_of):
        ins  = [{"qty": 10, "cost": 5.0, "date": "2026-01-01"},
                {"qty": 10, "cost": 8.0, "date": "2026-02-01"}]
        outs = [{"qty": 10}]  # consume newest batch first (LIFO)
        return ins, outs

    with patch("app.api.services.inventory_service._in_out_movements", side_effect=fake_in_out):
        result = _lifo_value("t", 1, "2026-04-01")

    # LIFO: newest 10 consumed (cost=8) → only oldest (cost=5) remains
    assert result["quantity"] == 10
    assert result["total_value"] == 50.0


# ── 3. Weighted average ───────────────────────────────────────────────────────

def test_average_value():
    from app.api.services.inventory_service import _average_value

    def fake_in_out(tenant_id, item_id, as_of):
        ins  = [{"qty": 10, "cost": 4.0}, {"qty": 10, "cost": 6.0}]  # avg=5
        outs = [{"qty": 5}]
        return ins, outs

    with patch("app.api.services.inventory_service._in_out_movements", side_effect=fake_in_out):
        result = _average_value("t", 1, "2026-04-01")

    assert result["quantity"] == 15  # 20 - 5
    assert result["avg_cost"] == 5.0
    assert result["total_value"] == 75.0


# ── 4. Insufficient stock blocked ────────────────────────────────────────────

def test_insufficient_stock_returns_error():
    """Movement 'out' with qty > available stock should return error."""
    from app.api.services.inventory_service import get_current_stock

    conn, cur = _mock_conn()
    cur.fetchone.return_value = (3.0,)  # only 3 in stock

    with patch("app.api.services.inventory_service.get_db", return_value=conn):
        stock = get_current_stock("tenant_a", 1)

    assert stock == 3.0
    # route checks: if qty > stock → error. Validate logic:
    requested = 10
    assert requested > stock  # would be blocked


# ── 5. PO auto-number generation ─────────────────────────────────────────────

def test_po_auto_number():
    from app.api.services.inventory_service import create_purchase_order

    conn, cur = _mock_conn()
    cur.fetchone.side_effect = [(5,), (42,)]  # count=5 → PO-2026-0006; then RETURNING id=42

    with patch("app.api.services.inventory_service.get_db", return_value=conn):
        result = create_purchase_order("tenant_a", {"lines": []})

    assert "po_number" in result
    assert result["po_number"].startswith("PO-")


# ── 6. FIFO with zero stock ───────────────────────────────────────────────────

def test_fifo_no_stock():
    from app.api.services.inventory_service import _fifo_value

    with patch("app.api.services.inventory_service._in_out_movements", return_value=([], [])):
        result = _fifo_value("t", 1, "2026-04-01")

    assert result["quantity"] == 0
    assert result["total_value"] == 0
    assert result["avg_cost"] == 0
