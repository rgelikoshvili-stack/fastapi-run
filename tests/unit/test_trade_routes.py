from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _async_conn(fetchrow_result=None, fetch_result=None, fetchval_result=0):
    conn = MagicMock()

    async def fetchrow(*args):
        conn.fetchrow_args = args
        return fetchrow_result

    async def fetch(*args):
        conn.fetch_args = args
        return fetch_result or []

    async def fetchval(*args):
        conn.fetchval_args = args
        return fetchval_result

    conn.fetchrow = fetchrow
    conn.fetch = fetch
    conn.fetchval = fetchval

    @asynccontextmanager
    async def _ctx():
        yield conn

    return _ctx, conn


def test_supplier_crud_is_tenant_scoped(client):
    row = {
        "id": 11,
        "name": "Supplier LLC",
        "email": None,
        "phone": None,
        "company": None,
        "type": "supplier",
        "tax_id": "123456789",
        "address": None,
        "notes": None,
        "status": "active",
    }
    ctx, conn = _async_conn(fetchrow_result=row)

    with patch("app.api.routes_trade.get_conn", ctx):
        response = client.post("/trade/suppliers", json={"name": "Supplier LLC", "tax_id": "123456789"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["tenant_id"] == "test"
    assert conn.fetchrow_args[1] == "test"
    assert conn.fetchrow_args[6] == "supplier"


def test_customer_crud_is_tenant_scoped(client):
    row = {
        "id": 12,
        "name": "Customer LLC",
        "email": None,
        "phone": None,
        "company": None,
        "type": "customer",
        "tax_id": "987654321",
        "address": None,
        "notes": None,
        "status": "active",
    }
    ctx, conn = _async_conn(fetchrow_result=row)

    with patch("app.api.routes_trade.get_conn", ctx):
        response = client.post("/trade/customers", json={"name": "Customer LLC", "tax_id": "987654321"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["tenant_id"] == "test"
    assert conn.fetchrow_args[1] == "test"
    assert conn.fetchrow_args[6] == "customer"


def test_purchase_order_status_flow_is_tenant_scoped(client):
    row = {"id": 5, "po_number": "PO-5", "status": "sent", "tenant_id": "test"}
    ctx, conn = _async_conn(fetchrow_result=row)

    with patch("app.api.routes_trade.get_conn", ctx):
        response = client.patch("/trade/purchase-orders/5/status", json={"status": "sent"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["purchase_order"]["status"] == "sent"
    assert conn.fetchrow_args[1:] == ("sent", 5, "test")


def test_sales_invoice_creates_journal_draft_only(client):
    fake_conn = MagicMock()
    draft = {"id": 21, "status": "draft"}
    finalized = {
        "invoice_id": 21,
        "invoice_number": "INV-2026-001",
        "journal_draft_id": 77,
        "total_amount": 118,
    }

    with patch("app.api.routes_trade.get_db", return_value=fake_conn) as db_mock, \
         patch("app.api.routes_trade.create_draft", return_value=draft) as create_mock, \
         patch("app.api.routes_trade.finalize", return_value=finalized) as finalize_mock:
        response = client.post("/trade/sales-invoices", json={
            "invoice_type": "service",
            "buyer_name": "Customer LLC",
            "line_items": [{"description": "Service", "qty": 1, "unit_price": 100}],
        })

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["tenant_id"] == "test"
    assert payload["data"]["journal_draft_id"] == 77
    assert payload["data"]["posted"] is False
    db_mock.assert_called_once_with("test")
    create_mock.assert_called_once()
    finalize_mock.assert_called_once_with(fake_conn, "test", 21)


def test_trade_unauthenticated_gets_401_or_403():
    from main import app

    unauthenticated = TestClient(app)

    responses = [
        unauthenticated.get("/trade/suppliers"),
        unauthenticated.get("/trade/purchase-orders"),
        unauthenticated.post("/trade/sales-invoices", json={}),
    ]

    assert all(r.status_code in (401, 403) for r in responses)


def test_trade_routes_do_not_directly_post_sales_invoice():
    import inspect
    from app.api import routes_trade

    source = inspect.getsource(routes_trade.trade_create_sales_invoice)

    assert "finalize(" in source
    assert "journal_draft_id" in source
    assert "posted\": False" in source
    assert "apply_posting_service" not in source
    assert "post_draft_to" not in source
