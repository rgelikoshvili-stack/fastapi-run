from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List, Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from datetime import datetime

router = APIRouter(prefix="/invoices", tags=["invoices"])

class InvoiceItem(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float

class InvoiceCreate(BaseModel):
    partner: str
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    vat_rate: Optional[float] = 18.0
    currency: Optional[str] = "GEL"
    notes: Optional[str] = None
    items: List[InvoiceItem]

class InvoiceStatusUpdate(BaseModel):
    status: str  # draft, sent, paid, cancelled

@router.post("/create")
def create_invoice(data: InvoiceCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    items_with_totals = []
    subtotal = 0.0
    for item in data.items:
        total = round(item.quantity * item.unit_price, 2)
        subtotal += total
        items_with_totals.append({**item.dict(), "total": total})

    vat_amount = round(subtotal * (data.vat_rate / 100), 2)
    total = round(subtotal + vat_amount, 2)

    invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}"

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO invoices (tenant_id, invoice_number, partner, issue_date, due_date,
                subtotal, vat_amount, total, vat_rate, currency, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (tenant_id, invoice_number, data.partner, data.issue_date, data.due_date,
              subtotal, vat_amount, total, data.vat_rate, data.currency, data.notes))
        invoice_id = cur.fetchone()[0]

        for item in items_with_totals:
            cur.execute("""
                INSERT INTO invoice_items (invoice_id, description, quantity, unit_price, total)
                VALUES (%s,%s,%s,%s,%s)
            """, (invoice_id, item["description"], item["quantity"], item["unit_price"], item["total"]))

        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    return ok_response("Invoice created", {
        "id": invoice_id,
        "invoice_number": invoice_number,
        "partner": data.partner,
        "subtotal": subtotal,
        "vat_amount": vat_amount,
        "total": total,
        "status": "draft",
        "tenant_id": tenant_id,
    })

@router.get("/list")
def list_invoices(request: Request, status: Optional[str] = None):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if status:
            cur.execute(
                "SELECT * FROM invoices WHERE status=%s AND tenant_id=%s ORDER BY created_at DESC",
                (status, tenant_id),
            )
        else:
            cur.execute(
                "SELECT * FROM invoices WHERE tenant_id=%s ORDER BY created_at DESC",
                (tenant_id,),
            )
        invoices = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Invoices", {"count": len(invoices), "tenant_id": tenant_id, "invoices": invoices})

@router.get("/stats/summary")
def invoice_stats(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT status, COUNT(*) as cnt,
                   COALESCE(SUM(total),0) as total_amount
            FROM invoices WHERE tenant_id=%s GROUP BY status
        """, (tenant_id,))
        by_status = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT COALESCE(SUM(total),0) as total, COUNT(*) as cnt FROM invoices WHERE status='paid' AND tenant_id=%s",
            (tenant_id,),
        )
        paid = dict(cur.fetchone())
        cur.execute(
            "SELECT COALESCE(SUM(total),0) as total, COUNT(*) as cnt FROM invoices WHERE status='sent' AND tenant_id=%s",
            (tenant_id,),
        )
        outstanding = dict(cur.fetchone())
    finally:
        cur.close(); conn.close()
    return ok_response("Invoice stats", {
        "tenant_id": tenant_id,
        "by_status": by_status,
        "total_invoices": sum(s["cnt"] for s in by_status),
        "total_paid": float(paid["total"]),
        "total_pending": float(outstanding["total"]),
        "overdue_count": next((s["cnt"] for s in by_status if s["status"] == "overdue"), 0),
        "paid_total": float(paid["total"]),
        "outstanding_total": float(outstanding["total"]),
    })

@router.get("/{invoice_id}")
def get_invoice(invoice_id: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM invoices WHERE id=%s AND tenant_id=%s",
            (invoice_id, tenant_id),
        )
        inv = cur.fetchone()
        if not inv:
            return error_response("Not found", "NOT_FOUND", "")
        cur.execute("SELECT * FROM invoice_items WHERE invoice_id=%s", (invoice_id,))
        items = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Invoice", {**dict(inv), "items": items})

@router.post("/{invoice_id}/status")
def update_status(invoice_id: int, data: InvoiceStatusUpdate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    valid = ["draft", "sent", "paid", "cancelled", "overdue"]
    if data.status not in valid:
        return error_response("Invalid status", "VALIDATION_ERROR", f"Use: {valid}")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE invoices SET status=%s WHERE id=%s AND tenant_id=%s",
            (data.status, invoice_id, tenant_id),
        )
        if cur.rowcount == 0:
            return error_response("Not found", "NOT_FOUND", "")
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Update failed", "UPDATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Status updated", {"id": invoice_id, "status": data.status})
