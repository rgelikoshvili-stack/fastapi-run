from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/crm", tags=["crm"])

class CustomerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    type: Optional[str] = "client"
    tax_id: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

class InteractionCreate(BaseModel):
    type: str
    note: Optional[str] = None
    amount: Optional[float] = 0
    created_by: Optional[str] = None

@router.get("/customers")
async def list_customers(request: Request, type: Optional[str] = None, status: Optional[str] = None):
    tenant_id = getattr(request.state, "tenant_id", "default")
    sql = "SELECT * FROM customers WHERE tenant_id=$1"
    params: list = [tenant_id]
    if type:
        params.append(type); sql += f" AND type=${len(params)}"
    if status:
        params.append(status); sql += f" AND status=${len(params)}"
    sql += " ORDER BY created_at DESC"
    async with get_conn() as conn:
        customers = [dict(r) for r in await conn.fetch(sql, *params)]
    return ok_response("Customers", {"count": len(customers), "tenant_id": tenant_id, "customers": customers})

@router.post("/customers/create")
async def create_customer(data: CustomerCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        try:
            new_id = await conn.fetchval(_q("""
                INSERT INTO customers (tenant_id, name, email, phone, company, type, tax_id, address, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """), tenant_id, data.name, data.email, data.phone, data.company,
                data.type, data.tax_id, data.address, data.notes)
        except Exception as e:
            return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Customer created", {"id": new_id, "name": data.name, "tenant_id": tenant_id})

@router.get("/customers/{customer_id}")
async def get_customer(customer_id: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT * FROM customers WHERE id=%s AND tenant_id=%s"), customer_id, tenant_id)
        if not row:
            return error_response("Not found", "NOT_FOUND", "")
        interactions = [dict(r) for r in await conn.fetch(_q("""
            SELECT * FROM customer_interactions WHERE customer_id=%s AND tenant_id=%s ORDER BY created_at DESC LIMIT 20
        """), customer_id, tenant_id)]
    return ok_response("Customer", {**dict(row), "interactions": interactions})

@router.post("/customers/{customer_id}/interaction")
async def add_interaction(customer_id: int, data: InteractionCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        owner = await conn.fetchrow(_q("SELECT id FROM customers WHERE id=%s AND tenant_id=%s"), customer_id, tenant_id)
        if not owner:
            return error_response("Customer not found", "NOT_FOUND", "")
        try:
            new_id = await conn.fetchval(_q("""
                INSERT INTO customer_interactions (customer_id, tenant_id, type, note, amount, created_by)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """), customer_id, tenant_id, data.type, data.note, data.amount, data.created_by)
        except Exception as e:
            return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Interaction added", {"id": new_id, "customer_id": customer_id})

@router.get("/stats")
async def crm_stats(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        total = await conn.fetchval(_q("SELECT COUNT(*) FROM customers WHERE tenant_id=%s"), tenant_id) or 0
        by_type = {r["type"]: r["cnt"] for r in await conn.fetch(_q(
            "SELECT type, COUNT(*) as cnt FROM customers WHERE tenant_id=%s GROUP BY type"), tenant_id)}
        by_status = {r["status"]: r["cnt"] for r in await conn.fetch(_q(
            "SELECT status, COUNT(*) as cnt FROM customers WHERE tenant_id=%s GROUP BY status"), tenant_id)}
    return ok_response("CRM stats", {"total_customers": total, "by_type": by_type, "by_status": by_status})
