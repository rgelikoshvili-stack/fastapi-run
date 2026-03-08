from fastapi import APIRouter
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
def create_expense(data: ExpenseCreate):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # account_code კატეგორიიდან
        cur.execute("SELECT account_code FROM expense_categories WHERE code=%s", (data.category,))
        row = cur.fetchone()
        account_code = row["account_code"] if row else "7190"

        expense_date = data.date or datetime.now().strftime("%Y-%m-%d")
        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO expenses (date, description, category, account_code, amount,
                currency, partner, receipt_ref, submitted_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (expense_date, data.description, data.category, account_code,
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
        "status": "pending"
    })

@router.get("/list")
def list_expenses(status: Optional[str] = None, category: Optional[str] = None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM expenses WHERE 1=1"
        params = []
        if status:
            query += " AND status=%s"; params.append(status)
        if category:
            query += " AND category=%s"; params.append(category)
        query += " ORDER BY created_at DESC LIMIT 50"
        cur.execute(query, params)
        expenses = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Expenses", {"count": len(expenses), "expenses": expenses})

@router.post("/{expense_id}/status")
def update_status(expense_id: int, data: ExpenseStatusUpdate):
    valid = ["pending", "approved", "rejected", "reimbursed"]
    if data.status not in valid:
        return error_response("Invalid status", "VALIDATION_ERROR", f"Use: {valid}")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE expenses SET status=%s WHERE id=%s", (data.status, expense_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Update failed", "UPDATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Status updated", {"id": expense_id, "status": data.status})

@router.get("/summary")
def expense_summary():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT e.category, ec.name, ec.budget_limit,
                   COUNT(*) as tx_count,
                   COALESCE(SUM(e.amount),0) as total_spent
            FROM expenses e
            LEFT JOIN expense_categories ec ON ec.code=e.category
            GROUP BY e.category, ec.name, ec.budget_limit
            ORDER BY total_spent DESC
        """)
        by_category = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE status!='rejected'")
        total = float(cur.fetchone()["coalesce"])

        cur.execute("SELECT status, COUNT(*) as cnt FROM expenses GROUP BY status")
        by_status = {r["status"]: r["cnt"] for r in cur.fetchall()}
    finally:
        cur.close(); conn.close()

    summary = []
    for r in by_category:
        spent = float(r["total_spent"])
        limit = float(r["budget_limit"] or 0)
        summary.append({
            "category": r["category"],
            "name": r["name"],
            "tx_count": r["tx_count"],
            "total_spent": round(spent, 2),
            "budget_limit": limit,
            "usage_pct": round(spent / limit * 100, 1) if limit else 0,
            "over_budget": spent > limit if limit else False
        })

    return ok_response("Expense summary", {
        "total_expenses": round(total, 2),
        "by_status": by_status,
        "by_category": summary
    })

@router.get("/monthly/{year}")
def monthly_expenses(year: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT SUBSTRING(date,1,7) as month,
                   category,
                   COALESCE(SUM(amount),0) as total
            FROM expenses
            WHERE date LIKE %s
            GROUP BY month, category
            ORDER BY month, total DESC
        """, (f"{year}%",))
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
        "months": list(monthly.values())
    })
