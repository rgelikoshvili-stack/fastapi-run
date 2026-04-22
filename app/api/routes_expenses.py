from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, List
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from datetime import datetime

router = APIRouter(prefix="/expenses", tags=["expenses"])

class ExpenseCreate(BaseModel):
    date: Optional[str] = None
    description: str
    category: str
    amount: float
    currency: Optional[str] = "GEL"
    partner: Optional[str] = None
    receipt_ref: Optional[str] = None
    submitted_by: Optional[str] = None

class ExpenseStatusUpdate(BaseModel):
    status: str  # pending, approved, rejected, reimbursed

@router.get("/categories")
def list_categories():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM expense_categories WHERE active=TRUE ORDER BY code")
        cats = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Expense categories", {"count": len(cats), "categories": cats})

@router.post("/create")
def create_expense(data: ExpenseCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT account_code FROM expense_categories WHERE code=%s", (data.category,))
        row = cur.fetchone()
        account_code = row["account_code"] if row else "7190"

        expense_date = data.date or datetime.now().strftime("%Y-%m-%d")
        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO expenses (tenant_id, date, description, category, account_code, amount,
                currency, partner, receipt_ref, submitted_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (tenant_id, expense_date, data.description, data.category, account_code,
              data.amount, data.currency, data.partner, data.receipt_ref, data.submitted_by))
        new_id = cur2.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    return ok_response("Expense created", {
        "id": new_id,
        "description": data.description,
        "category": data.category,
        "account_code": account_code,
        "amount": data.amount,
        "status": "pending",
        "tenant_id": tenant_id,
    })

@router.get("/list")
def list_expenses(request: Request, status: Optional[str] = None, category: Optional[str] = None):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM expenses WHERE tenant_id = %s"
        params = [tenant_id]
        if status:
            query += " AND status=%s"; params.append(status)
        if category:
            query += " AND category=%s"; params.append(category)
        query += " ORDER BY created_at DESC LIMIT 50"
        cur.execute(query, params)
        expenses = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Expenses", {"count": len(expenses), "tenant_id": tenant_id, "expenses": expenses})

@router.post("/{expense_id}/status")
def update_status(expense_id: int, data: ExpenseStatusUpdate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    valid = ["pending", "approved", "rejected", "reimbursed"]
    if data.status not in valid:
        return error_response("Invalid status", "VALIDATION_ERROR", f"Use: {valid}")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE expenses SET status=%s WHERE id=%s AND tenant_id=%s",
            (data.status, expense_id, tenant_id),
        )
        if cur.rowcount == 0:
            return error_response("Not found", "NOT_FOUND", "")
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Update failed", "UPDATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Status updated", {"id": expense_id, "status": data.status})

@router.get("/summary")
def expense_summary(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT e.category, ec.name,
                   COUNT(*) as tx_count,
                   COALESCE(SUM(e.amount),0) as total_spent
            FROM expenses e
            LEFT JOIN expense_categories ec ON ec.code=e.category
            WHERE e.tenant_id = %s
            GROUP BY e.category, ec.name
            ORDER BY total_spent DESC
        """, (tenant_id,))
        by_category = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE status!='rejected' AND tenant_id = %s",
            (tenant_id,),
        )
        total = float(cur.fetchone()["coalesce"])

        cur.execute(
            "SELECT status, COUNT(*) as cnt FROM expenses WHERE tenant_id = %s GROUP BY status",
            (tenant_id,),
        )
        by_status = {r["status"]: r["cnt"] for r in cur.fetchall()}
    finally:
        cur.close(); conn.close()

    summary = []
    for r in by_category:
        spent = float(r["total_spent"])
        limit = 0.0
        summary.append({
            "category": r["category"],
            "name": r["name"],
            "tx_count": r["tx_count"],
            "total_spent": round(spent, 2),
            "budget_limit": limit,
            "usage_pct": round(spent / limit * 100, 1) if limit else 0,
            "over_budget": spent > limit if limit else False,
        })

    return ok_response("Expense summary", {
        "tenant_id": tenant_id,
        "total_expenses": round(total, 2),
        "by_status": by_status,
        "by_category": summary,
    })

@router.get("/monthly/{year}")
def monthly_expenses(year: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT SUBSTRING(date,1,7) as month,
                   category,
                   COALESCE(SUM(amount),0) as total
            FROM expenses
            WHERE date LIKE %s AND tenant_id = %s
            GROUP BY month, category
            ORDER BY month, total DESC
        """, (f"{year}%", tenant_id))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    monthly = {}
    for r in rows:
        m = r["month"]
        if m not in monthly:
            monthly[m] = {"month": m, "total": 0, "categories": {}}
        monthly[m]["categories"][r["category"]] = float(r["total"])
        monthly[m]["total"] += float(r["total"])

    return ok_response("Monthly expenses", {
        "year": year,
        "tenant_id": tenant_id,
        "months": list(monthly.values()),
    })
