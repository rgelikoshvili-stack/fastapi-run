"""app/api/routes_inventory.py — Inventory management endpoints."""
from fastapi import APIRouter, Request, Query
from typing import Optional

from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response
from app.api.services.inventory_service import (
    ensure_inventory_tables,
    list_items, get_item, create_item, update_item,
    record_movement, get_movements, get_current_stock,
    calculate_valuation,
    create_purchase_order, list_purchase_orders, receive_purchase_order,
    list_warehouses, list_categories,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])

# ── Items ─────────────────────────────────────────────────────────────────────

@router.get("/items")
def get_items(
    request: Request,
    search: str = Query(""),
    category_id: Optional[int] = None,
    low_stock: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    ensure_inventory_tables()
    try:
        result = list_items(tenant_id, search=search, category_id=category_id,
                            low_stock=low_stock, limit=limit, offset=offset)
        return ok_response("Inventory items", result)
    except Exception as e:
        return error_response("Failed to load items", "DB_ERROR", str(e))


@router.get("/items/{item_id}")
def get_single_item(item_id: int, request: Request):
    require_permission(request, "read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    item = get_item(tenant_id, item_id)
    if not item:
        return error_response("Item not found", "NOT_FOUND")
    stock = get_current_stock(tenant_id, item_id)
    return ok_response("Item", {**item, "current_stock": stock})


@router.post("/items")
def add_item(request: Request):
    require_permission(request, "write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    ensure_inventory_tables()
    try:
        import json
        body = json.loads(request.state._body) if hasattr(request.state, "_body") else {}
    except Exception:
        body = {}
    if not body.get("item_code") or not body.get("item_name"):
        return error_response("item_code and item_name are required", "VALIDATION_ERROR")
    try:
        item = create_item(tenant_id, body)
        return ok_response("Item created", item)
    except Exception as e:
        if "unique" in str(e).lower():
            return error_response(f"Item code '{body.get('item_code')}' already exists", "DUPLICATE")
        return error_response("Failed to create item", "DB_ERROR", str(e))


@router.post("/items/create")
async def add_item_body(request: Request):
    require_permission(request, "write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    ensure_inventory_tables()
    try:
        body = await request.json()
    except Exception:
        return error_response("Invalid JSON body", "VALIDATION_ERROR")
    if not body.get("item_code") or not body.get("item_name"):
        return error_response("item_code and item_name are required", "VALIDATION_ERROR")
    try:
        item = create_item(tenant_id, body)
        return ok_response("Item created", item)
    except Exception as e:
        if "unique" in str(e).lower():
            return error_response(f"Item code '{body.get('item_code')}' already exists", "DUPLICATE")
        return error_response("Failed to create item", "DB_ERROR", str(e))


@router.put("/items/{item_id}")
async def edit_item(item_id: int, request: Request):
    require_permission(request, "write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    item = update_item(tenant_id, item_id, body)
    if not item:
        return error_response("Item not found", "NOT_FOUND")
    return ok_response("Item updated", item)


# ── Stock Movements ───────────────────────────────────────────────────────────

@router.post("/movements")
async def add_movement(request: Request):
    require_permission(request, "write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()

    required = ["item_id", "movement_type", "quantity"]
    for f in required:
        if f not in body:
            return error_response(f"'{f}' is required", "VALIDATION_ERROR")

    # stock-out validation
    if body["movement_type"] == "out":
        available = get_current_stock(tenant_id, int(body["item_id"]))
        if available < float(body["quantity"]):
            return error_response(
                f"Insufficient stock. Available: {available}, Requested: {body['quantity']}",
                "INSUFFICIENT_STOCK",
            )

    try:
        mv = record_movement(tenant_id, body)
        return ok_response("Movement recorded", mv)
    except Exception as e:
        return error_response("Failed to record movement", "DB_ERROR", str(e))


@router.get("/movements")
def get_movement_history(
    request: Request,
    item_id: Optional[int] = None,
    movement_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        result = get_movements(tenant_id, item_id=item_id, movement_type=movement_type,
                               date_from=date_from, date_to=date_to,
                               limit=limit, offset=offset)
        return ok_response("Stock movements", result)
    except Exception as e:
        return error_response("Failed to load movements", "DB_ERROR", str(e))


# ── Valuation ─────────────────────────────────────────────────────────────────

@router.get("/valuation")
def get_valuation(
    request: Request,
    method: str = Query("fifo", pattern="^(fifo|lifo|average)$"),
    as_of: Optional[str] = None,
):
    require_permission(request, "read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        result = calculate_valuation(tenant_id, method=method, as_of_date=as_of)
        return ok_response("Inventory valuation", result)
    except Exception as e:
        return error_response("Valuation failed", "DB_ERROR", str(e))


# ── Purchase Orders ───────────────────────────────────────────────────────────

@router.get("/purchase-orders")
def get_purchase_orders(
    request: Request,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        result = list_purchase_orders(tenant_id, status=status, limit=limit, offset=offset)
        return ok_response("Purchase orders", result)
    except Exception as e:
        return error_response("Failed to load purchase orders", "DB_ERROR", str(e))


@router.post("/purchase-orders")
async def new_purchase_order(request: Request):
    require_permission(request, "write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    try:
        po = create_purchase_order(tenant_id, body)
        return ok_response("Purchase order created", po)
    except Exception as e:
        return error_response("Failed to create PO", "DB_ERROR", str(e))


@router.post("/purchase-orders/{po_id}/receive")
async def receive_po(po_id: int, request: Request):
    require_permission(request, "write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    lines = body.get("lines", [])
    if not lines:
        return error_response("'lines' array required", "VALIDATION_ERROR")
    try:
        result = receive_purchase_order(tenant_id, po_id, lines)
        return ok_response("PO received", result)
    except Exception as e:
        return error_response("Failed to receive PO", "DB_ERROR", str(e))


# ── Warehouses & Categories ───────────────────────────────────────────────────

@router.get("/warehouses")
def get_warehouses(request: Request):
    require_permission(request, "read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return ok_response("Warehouses", list_warehouses(tenant_id))


@router.post("/warehouses")
async def add_warehouse(request: Request):
    require_permission(request, "write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    from app.api.db import get_db as _get_db
    conn = _get_db(tenant_id)
    cur = conn.cursor()
    try:
        ensure_inventory_tables(conn)
        cur.execute(
            "INSERT INTO warehouses (tenant_id, code, name, address, is_default) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (tenant_id, body["code"], body["name"],
             body.get("address"), body.get("is_default", False)),
        )
        wh_id = cur.fetchone()[0]
        conn.commit()
        return ok_response("Warehouse created", {**body, "id": wh_id})
    except Exception as e:
        conn.rollback()
        return error_response("Failed to create warehouse", "DB_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/categories")
def get_categories(request: Request):
    require_permission(request, "read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return ok_response("Categories", list_categories(tenant_id))


@router.post("/categories")
async def add_category(request: Request):
    require_permission(request, "write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    from app.api.db import get_db as _get_db
    conn = _get_db(tenant_id)
    cur = conn.cursor()
    try:
        ensure_inventory_tables(conn)
        cur.execute(
            "INSERT INTO inventory_categories (tenant_id, code, name, parent_id) "
            "VALUES (%s,%s,%s,%s) RETURNING id",
            (tenant_id, body["code"], body["name"], body.get("parent_id")),
        )
        cat_id = cur.fetchone()[0]
        conn.commit()
        return ok_response("Category created", {**body, "id": cat_id})
    except Exception as e:
        conn.rollback()
        return error_response("Failed to create category", "DB_ERROR", str(e))
    finally:
        cur.close()
        conn.close()
