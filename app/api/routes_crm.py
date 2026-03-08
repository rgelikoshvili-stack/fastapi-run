from fastapi import APIRouter
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
def list_customers(type: Optional[str] = None, status: Optional[str] = None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM customers WHERE 1=1"
        params = []
        if type:
            query += " AND type=%s"; params.append(type)
        if status:
            query += " AND status=%s"; params.append(status)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        customers = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Customers", {"count": len(customers), "customers": customers})

@router.post("/customers/create")
def create_customer(data: CustomerCreate):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO customers (name, email, phone, company, type, tax_id, address, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (data.name, data.email, data.phone, data.company,
              data.type, data.tax_id, data.address, data.notes))
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Customer created", {"id": new_id, "name": data.name, "type": data.type})

@router.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM customers WHERE id=%s", (customer_id,))
        customer = cur.fetchone()
        if not customer:
            return error_response("Not found", "NOT_FOUND", "")

        # invoices
        cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as total FROM invoices WHERE partner=%s", (customer["name"],))
        inv = cur.fetchone()

        # expenses
        cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM expenses WHERE partner=%s", (customer["name"],))
        exp = cur.fetchone()

        # interactions
        cur.execute("SELECT * FROM customer_interactions WHERE customer_id=%s ORDER BY created_at DESC LIMIT 10", (customer_id,))
        interactions = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    return ok_response("Customer", {
        **dict(customer),
        "stats": {
            "invoice_count": inv["cnt"], "invoice_total": float(inv["total"]),
            "expense_count": exp["cnt"], "expense_total": float(exp["total"]),
        },
        "interactions": interactions
    })

@router.post("/customers/{customer_id}/interactions")
def add_interaction(customer_id: int, data: InteractionCreate):
    valid = ["call", "email", "meeting", "invoice", "payment", "note"]
    if data.type not in valid:
        return error_response("Invalid type", "VALIDATION_ERROR", f"Use: {valid}")
    conn = get_db()
    cur = conn.cursor()
    try:
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
def crm_summary():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT type, COUNT(*) as cnt FROM customers GROUP BY type")
        by_type = {r["type"]: r["cnt"] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) as cnt FROM customers WHERE status='active'")
        active = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM customer_interactions")
        interactions = cur.fetchone()["cnt"]
        cur.execute("""
            SELECT c.name, COUNT(i.id) as inv_count, COALESCE(SUM(i.total),0) as revenue
            FROM customers c
            LEFT JOIN invoices i ON i.partner=c.name
            WHERE c.type='client'
            GROUP BY c.name ORDER BY revenue DESC LIMIT 5
        """)
        top_clients = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("CRM summary", {
        "by_type": by_type,
        "active_customers": active,
        "total_interactions": interactions,
        "top_clients": top_clients
    })
