from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.authz import require_permission
from datetime import datetime
from app.api.tenant_context import resolve_tenant_id

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
    status: str

@router.get("/categories")
async def list_categories():
    async with get_conn() as conn:
        cats = [dict(r) for r in await conn.fetch("SELECT * FROM expense_categories WHERE active=TRUE ORDER BY code")]
    return ok_response("Expense categories", {"count": len(cats), "categories": cats})

@router.post("/create")
async def create_expense(data: ExpenseCreate, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        try:
            row = await conn.fetchrow(_q("SELECT account_code FROM expense_categories WHERE code=%s"), data.category)
            account_code = row["account_code"] if row else "7910"
            expense_date = data.date or datetime.now().strftime("%Y-%m-%d")
            new_id = await conn.fetchval(_q("""
                INSERT INTO expenses (tenant_id, date, description, category, account_code, amount,
                    currency, partner, receipt_ref, submitted_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """), tenant_id, expense_date, data.description, data.category, account_code,
                data.amount, data.currency, data.partner, data.receipt_ref, data.submitted_by)
        except Exception as e:
            return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Expense created", {
        "id": new_id, "description": data.description, "category": data.category,
        "account_code": account_code, "amount": data.amount, "status": "pending", "tenant_id": tenant_id,
    })

@router.get("/list")
async def list_expenses(request: Request, status: Optional[str] = None, category: Optional[str] = None):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    sql = "SELECT * FROM expenses WHERE tenant_id = $1"
    params: list = [tenant_id]
    if status:
        params.append(status); sql += f" AND status=${len(params)}"
    if category:
        params.append(category); sql += f" AND category=${len(params)}"
    sql += " ORDER BY created_at DESC LIMIT 50"
    async with get_conn() as conn:
        expenses = [dict(r) for r in await conn.fetch(sql, *params)]
    return ok_response("Expenses", {"count": len(expenses), "tenant_id": tenant_id, "expenses": expenses})

@router.post("/{expense_id}/status")
async def update_status(expense_id: int, data: ExpenseStatusUpdate, request: Request):
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    valid = ["pending", "approved", "rejected", "reimbursed"]
    if data.status not in valid:
        return error_response("Invalid status", "VALIDATION_ERROR", f"Use: {valid}")
    async with get_conn() as conn:
        try:
            status = await conn.execute(_q("UPDATE expenses SET status=%s WHERE id=%s AND tenant_id=%s"),
                                        data.status, expense_id, tenant_id)
            if int(status.split()[-1]) == 0:
                return error_response("Not found", "NOT_FOUND", "")
        except Exception as e:
            return error_response("Update failed", "UPDATE_ERROR", str(e))
    return ok_response("Status updated", {"id": expense_id, "status": data.status})

@router.get("/summary")
async def expense_summary(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        by_category = [dict(r) for r in await conn.fetch(_q("""
            SELECT e.category, ec.name,
                   COUNT(*) as tx_count,
                   COALESCE(SUM(e.amount),0) as total_spent
            FROM expenses e
            LEFT JOIN expense_categories ec ON ec.code=e.category
            WHERE e.tenant_id = %s
            GROUP BY e.category, ec.name
            ORDER BY total_spent DESC
        """), tenant_id)]
        total_row = await conn.fetchrow(_q(
            "SELECT COALESCE(SUM(amount),0) as total FROM expenses WHERE status!='rejected' AND tenant_id = %s"),
            tenant_id)
        total = float(total_row["total"] if total_row else 0)
        by_status_rows = await conn.fetch(_q(
            "SELECT status, COUNT(*) as cnt FROM expenses WHERE tenant_id = %s GROUP BY status"), tenant_id)
        by_status = {r["status"]: r["cnt"] for r in by_status_rows}
    summary = []
    for r in by_category:
        spent = float(r["total_spent"])
        summary.append({"category": r["category"], "name": r["name"],
                        "tx_count": r["tx_count"], "total_spent": round(spent, 2),
                        "budget_limit": 0.0, "usage_pct": 0, "over_budget": False})
    return ok_response("Expense summary", {"tenant_id": tenant_id, "total_expenses": round(total, 2),
                                           "by_status": by_status, "by_category": summary})

@router.get("/monthly/{year}")
async def monthly_expenses(year: int, request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q("""
            SELECT SUBSTRING(date::text,1,7) as month, category, COALESCE(SUM(amount),0) as total
            FROM expenses
            WHERE date::text LIKE %s AND tenant_id = %s
            GROUP BY month, category
            ORDER BY month, total DESC
        """), f"{year}%", tenant_id)]
    monthly = {}
    for r in rows:
        m = r["month"]
        if m not in monthly:
            monthly[m] = {"month": m, "total": 0, "categories": {}}
        monthly[m]["categories"][r["category"]] = float(r["total"])
        monthly[m]["total"] += float(r["total"])
    return ok_response("Monthly expenses", {"year": year, "tenant_id": tenant_id, "months": list(monthly.values())})
