from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
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
    type: str  # call, email, meeting, invoice, payment
    note: Optional[str] = None
    amount: Optional[float] = 0
    created_by: Optional[str] = None

@router.get("/customers")
def list_customers(request: Request, type: Optional[str] = None, status: Optional[str] = None):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM customers WHERE tenant_id=%s"
        params = [tenant_id]
        if type:
            query += " AND type=%s"; params.append(type)
        if status:
            query += " AND status=%s"; params.append(status)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        customers = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Customers", {"count": len(customers), "tenant_id": tenant_id, "customers": customers})

@router.post("/customers/create")
def create_customer(data: CustomerCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO customers (tenant_id, name, email, phone, company, type, tax_id, address, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (tenant_id, data.name, data.email, data.phone, data.company,
              data.type, data.tax_id, data.address, data.notes))
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Customer created", {"id": new_id, "name": data.name, "type": data.type, "tenant_id": tenant_id})

@router.get("/customers/{customer_id}")
def get_customer(customer_id: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM customers WHERE id=%s AND tenant_id=%s",
            (customer_id, tenant_id),
        )
        customer = cur.fetchone()
        if not customer:
            return error_response("Not found", "NOT_FOUND", "")

        cur.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as total FROM invoices WHERE partner=%s AND tenant_id=%s",
            (customer["name"], tenant_id),
        )
        inv = cur.fetchone()

        cur.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM expenses WHERE partner=%s AND tenant_id=%s",
            (customer["name"], tenant_id),
        )
        exp = cur.fetchone()

        cur.execute(
            "SELECT * FROM customer_interactions WHERE customer_id=%s ORDER BY created_at DESC LIMIT 10",
            (customer_id,),
        )
        interactions = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    return ok_response("Customer", {
        **dict(customer),
        "stats": {
            "invoice_count": inv["cnt"], "invoice_total": float(inv["total"]),
            "expense_count": exp["cnt"], "expense_total": float(exp["total"]),
        },
        "interactions": interactions,
    })

@router.post("/customers/{customer_id}/interactions")
def add_interaction(customer_id: int, data: InteractionCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    valid = ["call", "email", "meeting", "invoice", "payment", "note"]
    if data.type not in valid:
        return error_response("Invalid type", "VALIDATION_ERROR", f"Use: {valid}")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM customers WHERE id=%s AND tenant_id=%s",
            (customer_id, tenant_id),
        )
        if not cur.fetchone():
            return error_response("Not found", "NOT_FOUND", "Customer not found for this tenant")
        cur.execute("""
            INSERT INTO customer_interactions (customer_id, type, note, amount, created_by)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (customer_id, data.type, data.note, data.amount, data.created_by))
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Interaction added", {"id": new_id, "customer_id": customer_id, "type": data.type})

@router.get("/summary")
def crm_summary(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT type, COUNT(*) as cnt FROM customers WHERE tenant_id=%s GROUP BY type",
            (tenant_id,),
        )
        by_type = {r["type"]: r["cnt"] for r in cur.fetchall()}
        cur.execute(
            "SELECT COUNT(*) as cnt FROM customers WHERE status='active' AND tenant_id=%s",
            (tenant_id,),
        )
        active = cur.fetchone()["cnt"]
        cur.execute("""
            SELECT COUNT(*) as cnt FROM customer_interactions ci
            JOIN customers c ON c.id=ci.customer_id
            WHERE c.tenant_id=%s
        """, (tenant_id,))
        interactions = cur.fetchone()["cnt"]
        cur.execute("""
            SELECT c.name, COUNT(i.id) as inv_count, COALESCE(SUM(i.total),0) as revenue
            FROM customers c
            LEFT JOIN invoices i ON i.partner=c.name AND i.tenant_id=c.tenant_id
            WHERE c.type='client' AND c.tenant_id=%s
            GROUP BY c.name ORDER BY revenue DESC LIMIT 5
        """, (tenant_id,))
        top_clients = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("CRM summary", {
        "tenant_id": tenant_id,
        "by_type": by_type,
        "active_customers": active,
        "total_interactions": interactions,
        "top_clients": top_clients,
    })
