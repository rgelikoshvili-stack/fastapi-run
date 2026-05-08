"""app/api/routes_inventory.py — Inventory management endpoints."""
import csv
import io
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response
from app.api.services.inventory_service import (
    ensure_inventory_tables,
    list_items, get_item, create_item, update_item,
    record_movement, get_movements, get_current_stock,
    calculate_valuation, get_stock_report,
    create_purchase_order, list_purchase_orders, get_purchase_order, receive_purchase_order,
    list_warehouses, list_categories, create_warehouse, create_category,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _inventory_error(message: str, exc: Exception):
    code = str(exc)
    if code in {"ITEM_NOT_FOUND", "INVALID_MOVEMENT_TYPE", "INVALID_QUANTITY", "INVALID_UNIT_COST", "INVALID_UNIT_PRICE"}:
        return error_response(message, code, code)
    if code == "INSUFFICIENT_STOCK":
        return error_response("Insufficient stock", "INSUFFICIENT_STOCK", code)
    return error_response(message, "DB_ERROR", code)

# ── Items ─────────────────────────────────────────────────────────────────────

@router.get("/items")
async def get_items(
    request: Request,
    search: str = Query(""),
    category_id: Optional[int] = None,
    low_stock: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    ensure_inventory_tables()
    try:
        result = await list_items(tenant_id, search=search, category_id=category_id,
                                  low_stock=low_stock, limit=limit, offset=offset)
        return ok_response("Inventory items", result)
    except Exception as e:
        return error_response("Failed to load items", "DB_ERROR", str(e))


@router.get("/items/{item_id}")
async def get_single_item(item_id: int, request: Request):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    item = await get_item(tenant_id, item_id)
    if not item:
        return error_response("Item not found", "NOT_FOUND")
    stock = await get_current_stock(tenant_id, item_id)
    return ok_response("Item", {**item, "current_stock": stock})


@router.post("/items")
async def add_item(request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    ensure_inventory_tables()
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not body.get("item_code") or not body.get("item_name"):
        return error_response("item_code and item_name are required", "VALIDATION_ERROR")
    try:
        item = await create_item(tenant_id, body)
        return ok_response("Item created", item)
    except Exception as e:
        if "unique" in str(e).lower():
            return error_response(f"Item code '{body.get('item_code')}' already exists", "DUPLICATE")
        return error_response("Failed to create item", "DB_ERROR", str(e))


@router.post("/items/create")
async def add_item_body(request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        body = await request.json()
    except Exception:
        return error_response("Invalid JSON body", "VALIDATION_ERROR")
    if not body.get("item_code") or not body.get("item_name"):
        return error_response("item_code and item_name are required", "VALIDATION_ERROR")
    try:
        item = await create_item(tenant_id, body)
        return ok_response("Item created", item)
    except Exception as e:
        if "unique" in str(e).lower():
            return error_response(f"Item code '{body.get('item_code')}' already exists", "DUPLICATE")
        return error_response("Failed to create item", "DB_ERROR", str(e))


@router.put("/items/{item_id}")
async def edit_item(item_id: int, request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    item = await update_item(tenant_id, item_id, body)
    if not item:
        return error_response("Item not found", "NOT_FOUND")
    return ok_response("Item updated", item)


# ── Stock Movements ───────────────────────────────────────────────────────────

@router.post("/movements")
async def add_movement(request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()

    required = ["item_id", "movement_type", "quantity"]
    for f in required:
        if f not in body:
            return error_response(f"'{f}' is required", "VALIDATION_ERROR")

    if body["movement_type"] == "out":
        available = await get_current_stock(tenant_id, int(body["item_id"]))
        if available < float(body["quantity"]):
            return error_response(
                f"Insufficient stock. Available: {available}, Requested: {body['quantity']}",
                "INSUFFICIENT_STOCK",
            )

    try:
        mv = await record_movement(tenant_id, body)
        return ok_response("Movement recorded", mv)
    except Exception as e:
        return _inventory_error("Failed to record movement", e)


@router.get("/movements")
async def get_movement_history(
    request: Request,
    item_id: Optional[int] = None,
    movement_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        result = await get_movements(tenant_id, item_id=item_id, movement_type=movement_type,
                                     date_from=date_from, date_to=date_to,
                                     limit=limit, offset=offset)
        return ok_response("Stock movements", result)
    except Exception as e:
        return error_response("Failed to load movements", "DB_ERROR", str(e))


@router.get("/stock-report")
async def stock_report(request: Request, low_stock: bool = False):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        result = await get_stock_report(tenant_id, low_stock_only=low_stock)
        return ok_response("Inventory stock report", result)
    except Exception as e:
        return error_response("Stock report failed", "DB_ERROR", str(e))


# ── Valuation ─────────────────────────────────────────────────────────────────

@router.get("/valuation")
async def get_valuation(
    request: Request,
    method: str = Query("fifo", pattern="^(fifo|lifo|average)$"),
    as_of: Optional[str] = None,
):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        result = await calculate_valuation(tenant_id, method=method, as_of_date=as_of)
        return ok_response("Inventory valuation", result)
    except Exception as e:
        return error_response("Valuation failed", "DB_ERROR", str(e))


# ── Purchase Orders ───────────────────────────────────────────────────────────

@router.get("/purchase-orders")
async def get_purchase_orders(
    request: Request,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        result = await list_purchase_orders(tenant_id, status=status, limit=limit, offset=offset)
        return ok_response("Purchase orders", result)
    except Exception as e:
        return error_response("Failed to load purchase orders", "DB_ERROR", str(e))


@router.post("/purchase-orders")
async def new_purchase_order(request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    try:
        po = await create_purchase_order(tenant_id, body)
        return ok_response("Purchase order created", po)
    except Exception as e:
        return _inventory_error("Failed to create PO", e)


@router.get("/purchase-orders/{po_id}")
async def get_purchase_order_detail(po_id: int, request: Request):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        order = await get_purchase_order(tenant_id, po_id)
        if not order:
            return error_response("Purchase order not found", "NOT_FOUND")
        return ok_response("Purchase order", order)
    except Exception as e:
        return error_response("Failed to load purchase order", "DB_ERROR", str(e))


@router.post("/purchase-orders/{po_id}/receive")
async def receive_po(po_id: int, request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    lines = body.get("lines", [])
    if not lines:
        return error_response("'lines' array required", "VALIDATION_ERROR")
    try:
        result = await receive_purchase_order(tenant_id, po_id, lines)
        return ok_response("PO received", result)
    except Exception as e:
        return error_response("Failed to receive PO", "DB_ERROR", str(e))


# ── Warehouses & Categories ───────────────────────────────────────────────────

@router.get("/warehouses")
async def get_warehouses(request: Request):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return ok_response("Warehouses", await list_warehouses(tenant_id))


@router.post("/warehouses")
async def add_warehouse(request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    try:
        wh = await create_warehouse(tenant_id, body)
        return ok_response("Warehouse created", wh)
    except Exception as e:
        return error_response("Failed to create warehouse", "DB_ERROR", str(e))


@router.get("/categories")
async def get_categories(request: Request):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return ok_response("Categories", await list_categories(tenant_id))


@router.get("/reorder-report")
async def get_reorder_report(request: Request):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await list_items(tenant_id, low_stock=True, limit=500, offset=0)
    items = result.get("items", [])
    suggestions = [
        {
            "item_id": it["id"],
            "item_code": it["item_code"],
            "item_name": it["item_name"],
            "current_stock": it.get("current_stock", 0),
            "reorder_level": it.get("reorder_level", 0),
            "suggested_qty": max(
                (it.get("reorder_level", 0) * 2) - it.get("current_stock", 0), 1
            ),
            "unit_of_measure": it.get("unit_of_measure", ""),
            "purchase_price": it.get("purchase_price", 0),
        }
        for it in items
    ]
    return ok_response("Reorder report", {
        "low_stock_count": len(suggestions),
        "items": suggestions,
        "total_reorder_value": sum(
            s["suggested_qty"] * s["purchase_price"] for s in suggestions
        ),
    })


@router.get("/export")
async def export_inventory_csv(request: Request):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await list_items(tenant_id, limit=10000, offset=0)
    items = result.get("items", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Item Code", "Item Name", "Category", "Unit",
        "Current Stock", "Reorder Level", "Purchase Price", "Selling Price",
        "Total Value", "Costing Method", "Active"
    ])
    for it in items:
        writer.writerow([
            it.get("item_code", ""),
            it.get("item_name", ""),
            it.get("category_name", ""),
            it.get("unit_of_measure", ""),
            it.get("current_stock", 0),
            it.get("reorder_level", 0),
            it.get("purchase_price", 0),
            it.get("selling_price", 0),
            round(float(it.get("current_stock", 0)) * float(it.get("selling_price", 0)), 2),
            it.get("costing_method", "fifo"),
            it.get("is_active", True),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inventory.csv"},
    )


@router.post("/categories")
async def add_category(request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    body = await request.json()
    try:
        cat = await create_category(tenant_id, body)
        return ok_response("Category created", cat)
    except Exception as e:
        return error_response("Failed to create category", "DB_ERROR", str(e))
