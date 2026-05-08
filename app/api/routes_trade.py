"""ERP purchases and sales task routes.

This router intentionally reuses existing CRM, inventory purchase order, and
outgoing invoice primitives instead of replacing their behavior.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.api.authz import require_permission
from app.api.db import _q, get_conn, get_db
from app.api.response_utils import error_response, http_error, ok_response
from app.api.services.invoice_creator import create_draft, finalize
from app.api.services.inventory_service import (
    create_purchase_order,
    get_purchase_order,
    list_purchase_orders,
)
from app.api.tenant_context import resolve_tenant_id


router = APIRouter(prefix="/trade", tags=["trade"])

PARTNER_TYPES = {"customer", "supplier"}
PARTNER_STATUSES = {"active", "inactive"}
PO_STATUSES = {"draft", "sent", "partial", "received", "cancelled"}


class PartnerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    status: str = Field("active", pattern="^(active|inactive)$")


class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")


class PurchaseOrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(draft|sent|partial|received|cancelled)$")


class PurchaseOrderLine(BaseModel):
    item_id: int
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    line_number: Optional[int] = None
    notes: Optional[str] = None


class PurchaseOrderCreate(BaseModel):
    supplier_name: str
    supplier_inn: Optional[str] = None
    po_number: Optional[str] = None
    po_date: Optional[str] = None
    expected_date: Optional[str] = None
    notes: Optional[str] = None
    lines: List[PurchaseOrderLine]


class SalesInvoiceLine(BaseModel):
    description: str
    qty: float = Field(1, gt=0)
    unit_price: float = Field(..., ge=0)


class SalesInvoiceCreate(BaseModel):
    invoice_type: str = Field("service", pattern="^(goods|service)$")
    buyer_name: str
    buyer_inn: Optional[str] = None
    buyer_email: Optional[str] = None
    buyer_address: Optional[str] = None
    buyer_phone: Optional[str] = None
    invoice_date: Optional[str] = None
    delivery_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: str = Field("GEL", pattern="^(GEL|USD|EUR|GBP|TRY|RUB|CHF)$")
    comment: Optional[str] = None
    line_items: List[SalesInvoiceLine]


def _partner_type_from_kind(kind: str) -> str:
    if kind not in PARTNER_TYPES:
        raise ValueError("INVALID_PARTNER_TYPE")
    return kind


async def _list_partners(kind: str, request: Request, status: Optional[str], limit: int, offset: int):
    require_permission(request, "crm:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    partner_type = _partner_type_from_kind(kind)
    params: list = [tenant_id, partner_type]
    where = ["tenant_id = %s", "type = %s"]
    if status:
        if status not in PARTNER_STATUSES:
            return http_error(422, "Invalid partner status", "INVALID_STATUS")
        params.append(status)
        where.append("status = %s")
    params.extend([limit, offset])
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, name, email, phone, company, type, tax_id, address, notes, status, created_at
            FROM customers
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """), *params)]
        total = await conn.fetchval(_q(f"""
            SELECT COUNT(*) FROM customers WHERE {" AND ".join(where)}
        """), *params[:-2]) or 0
    return ok_response(f"{kind.title()}s", {"tenant_id": tenant_id, "total": total, "items": rows})


async def _create_partner(kind: str, data: PartnerCreate, request: Request):
    require_permission(request, "crm:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    partner_type = _partner_type_from_kind(kind)
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            INSERT INTO customers
                (tenant_id, name, email, phone, company, type, tax_id, address, notes, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id, name, email, phone, company, type, tax_id, address, notes, status
        """), tenant_id, data.name, data.email, data.phone, data.company,
            partner_type, data.tax_id, data.address, data.notes, data.status)
    return ok_response(f"{kind.title()} created", {"tenant_id": tenant_id, "partner": dict(row)})


async def _update_partner(kind: str, partner_id: int, data: PartnerUpdate, request: Request):
    require_permission(request, "crm:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    partner_type = _partner_type_from_kind(kind)
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        return http_error(422, "No changes requested", "NO_CHANGES")
    allowed = ["name", "email", "phone", "company", "tax_id", "address", "notes", "status"]
    sets = []
    params = []
    for field in allowed:
        if field in payload:
            sets.append(f"{field} = %s")
            params.append(payload[field])
    params.extend([partner_id, tenant_id, partner_type])
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(f"""
            UPDATE customers
            SET {", ".join(sets)}
            WHERE id = %s AND tenant_id = %s AND type = %s
            RETURNING id, name, email, phone, company, type, tax_id, address, notes, status
        """), *params)
    if not row:
        return http_error(404, f"{kind.title()} not found", "NOT_FOUND")
    return ok_response(f"{kind.title()} updated", {"tenant_id": tenant_id, "partner": dict(row)})


async def _deactivate_partner(kind: str, partner_id: int, request: Request):
    require_permission(request, "crm:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    partner_type = _partner_type_from_kind(kind)
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            UPDATE customers
            SET status = 'inactive'
            WHERE id = %s AND tenant_id = %s AND type = %s
            RETURNING id, name, type, status
        """), partner_id, tenant_id, partner_type)
    if not row:
        return http_error(404, f"{kind.title()} not found", "NOT_FOUND")
    return ok_response(f"{kind.title()} deactivated", {"tenant_id": tenant_id, "partner": dict(row)})


@router.get("/suppliers")
async def list_suppliers(request: Request, status: Optional[str] = None,
                         limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
    return await _list_partners("supplier", request, status, limit, offset)


@router.post("/suppliers")
async def create_supplier(data: PartnerCreate, request: Request):
    return await _create_partner("supplier", data, request)


@router.patch("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: int, data: PartnerUpdate, request: Request):
    return await _update_partner("supplier", supplier_id, data, request)


@router.delete("/suppliers/{supplier_id}")
async def deactivate_supplier(supplier_id: int, request: Request):
    return await _deactivate_partner("supplier", supplier_id, request)


@router.get("/customers")
async def list_customers(request: Request, status: Optional[str] = None,
                         limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
    return await _list_partners("customer", request, status, limit, offset)


@router.post("/customers")
async def create_customer(data: PartnerCreate, request: Request):
    return await _create_partner("customer", data, request)


@router.patch("/customers/{customer_id}")
async def update_customer(customer_id: int, data: PartnerUpdate, request: Request):
    return await _update_partner("customer", customer_id, data, request)


@router.delete("/customers/{customer_id}")
async def deactivate_customer(customer_id: int, request: Request):
    return await _deactivate_partner("customer", customer_id, request)


@router.get("/purchase-orders")
async def trade_purchase_orders(request: Request, status: Optional[str] = None,
                                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return ok_response("Purchase orders", await list_purchase_orders(tenant_id, status=status, limit=limit, offset=offset))


@router.post("/purchase-orders")
async def trade_create_purchase_order(data: PurchaseOrderCreate, request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    po = await create_purchase_order(tenant_id, {**data.model_dump(), "lines": [line.model_dump() for line in data.lines]})
    return ok_response("Purchase order created", {"tenant_id": tenant_id, "purchase_order": po})


@router.get("/purchase-orders/{po_id}")
async def trade_purchase_order_detail(po_id: int, request: Request):
    require_permission(request, "inventory:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    order = await get_purchase_order(tenant_id, po_id)
    if not order:
        return http_error(404, "Purchase order not found", "NOT_FOUND")
    return ok_response("Purchase order", {"tenant_id": tenant_id, "purchase_order": order})


@router.patch("/purchase-orders/{po_id}/status")
async def trade_purchase_order_status(po_id: int, data: PurchaseOrderStatusUpdate, request: Request):
    require_permission(request, "inventory:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            UPDATE purchase_orders
            SET status = %s,
                updated_at = NOW()
            WHERE id = %s AND tenant_id = %s
            RETURNING id, po_number, status, tenant_id
        """), data.status, po_id, tenant_id)
    if not row:
        return http_error(404, "Purchase order not found", "NOT_FOUND")
    return ok_response("Purchase order status updated", {"tenant_id": tenant_id, "purchase_order": dict(row)})


@router.post("/sales-invoices")
async def trade_create_sales_invoice(data: SalesInvoiceCreate, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    try:
        draft = create_draft(conn, tenant_id, {**data.model_dump(), "line_items": [line.model_dump() for line in data.line_items]})
        finalized = finalize(conn, tenant_id, draft["id"])
    except ValueError as exc:
        return http_error(422, str(exc), "VALIDATION_ERROR")
    except LookupError as exc:
        return http_error(404, str(exc), "NOT_FOUND")
    except Exception as exc:
        return error_response("Sales invoice creation failed", "SALES_INVOICE_ERROR", str(exc))
    finally:
        conn.close()
    return ok_response("Sales invoice created", {
        "tenant_id": tenant_id,
        "draft": draft,
        "invoice": finalized,
        "journal_draft_id": finalized.get("journal_draft_id"),
        "posted": False,
    })


@router.get("/credit-status")
async def trade_credit_status(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q("""
            SELECT partner, status, COUNT(*) AS count, COALESCE(SUM(total),0) AS total_amount
            FROM invoices
            WHERE tenant_id = %s AND status IN ('sent','overdue')
            GROUP BY partner, status
            ORDER BY total_amount DESC
        """), tenant_id)]
    return ok_response("Credit status", {"tenant_id": tenant_id, "items": rows})
