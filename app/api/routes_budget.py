from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, List
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/budget", tags=["budget"])

class BudgetCreate(BaseModel):
    name: str
    year: int
    month: Optional[int] = None
    account_code: Optional[str] = None
    category: Optional[str] = None
    budgeted: float

class BudgetItem(BaseModel):
    account_code: str
    category: str
    budgeted: float

class AnnualBudgetCreate(BaseModel):
    name: str
    year: int
    items: List[BudgetItem]

@router.post("/create")
async def create_budget(data: BudgetCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        try:
            new_id = await conn.fetchval(_q("""
                INSERT INTO budgets (tenant_id, name, year, month, account_code, category, budgeted)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """), tenant_id, data.name, data.year, data.month, data.account_code, data.category, data.budgeted)
        except Exception as e:
            return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Budget created", {"id": new_id, "tenant_id": tenant_id, **data.dict()})

@router.post("/create-annual")
async def create_annual_budget(data: AnnualBudgetCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    created = []
    async with get_conn() as conn:
        try:
            async with conn.transaction():
                for item in data.items:
                    new_id = await conn.fetchval(_q("""
                        INSERT INTO budgets (tenant_id, name, year, account_code, category, budgeted)
                        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
                    """), tenant_id, data.name, data.year, item.account_code, item.category, item.budgeted)
                    created.append(new_id)
        except Exception as e:
            return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Annual budget created", {
        "name": data.name, "year": data.year, "tenant_id": tenant_id,
        "items_count": len(created), "ids": created,
    })

@router.get("/vs-actual/{year}")
async def budget_vs_actual(year: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        budgets = [dict(r) for r in await conn.fetch(_q(
            "SELECT * FROM budgets WHERE year=%s AND tenant_id = %s ORDER BY account_code"),
            year, tenant_id)]
        actuals_rows = await conn.fetch(_q("""
            SELECT account_code,
                   COALESCE(SUM(CASE WHEN debit_account=account_code THEN amount ELSE 0 END), 0) as actual_debit
            FROM journal_drafts
            WHERE tenant_id=%s AND EXTRACT(YEAR FROM date)=%s AND status IN ('approved','posted')
            GROUP BY account_code
        """), tenant_id, year)
        actuals = {r["account_code"]: float(r["actual_debit"]) for r in actuals_rows}
    result = []
    for b in budgets:
        ac = b.get("account_code", "")
        budgeted = float(b.get("budgeted", 0))
        actual = actuals.get(ac, 0.0)
        result.append({**b, "actual": actual, "variance": round(budgeted - actual, 2),
                        "utilization_pct": round(actual / budgeted * 100, 1) if budgeted else 0})
    return ok_response("Budget vs Actual", {"year": year, "tenant_id": tenant_id, "items": result})

@router.get("/list/{year}")
async def list_budgets(year: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(
            "SELECT * FROM budgets WHERE year=%s AND tenant_id = %s ORDER BY account_code, month"),
            year, tenant_id)]
    return ok_response("Budgets", {"year": year, "count": len(rows), "budgets": rows})
