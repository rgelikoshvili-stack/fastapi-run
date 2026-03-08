from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
import psycopg2.extras
from app.api.db import get_db
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
def create_budget(data: BudgetCreate):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO budgets (name, year, month, account_code, category, budgeted)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (data.name, data.year, data.month, data.account_code, data.category, data.budgeted))
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Budget created", {"id": new_id, **data.dict()})

@router.post("/create-annual")
def create_annual_budget(data: AnnualBudgetCreate):
    conn = get_db()
    cur = conn.cursor()
    created = []
    try:
        for item in data.items:
            cur.execute("""
                INSERT INTO budgets (name, year, account_code, category, budgeted)
                VALUES (%s,%s,%s,%s,%s) RETURNING id
            """, (data.name, data.year, item.account_code, item.category, item.budgeted))
            created.append(cur.fetchone()[0])
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Annual budget created", {
        "name": data.name, "year": data.year,
        "items_count": len(created), "ids": created
    })

@router.get("/vs-actual/{year}")
def budget_vs_actual(year: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM budgets WHERE year=%s ORDER BY account_code", (year,))
        budgets = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT account_code, reason as category,
                   COALESCE(SUM(amount),0) as actual
            FROM journal_drafts
            WHERE date LIKE %s
            GROUP BY account_code, reason
        """, (f"{year}%",))
        actuals = {(r["account_code"], r["category"]): float(r["actual"]) for r in cur.fetchall()}
    finally:
        cur.close(); conn.close()

    comparison = []
    total_budgeted = 0
    total_actual = 0
    for b in budgets:
        actual = actuals.get((b["account_code"], b["category"]), 0.0)
        budgeted = float(b["budgeted"])
        variance = round(actual - budgeted, 2)
        pct = round((actual / budgeted * 100) if budgeted else 0, 1)
        total_budgeted += budgeted
        total_actual += actual
        comparison.append({
            "account_code": b["account_code"],
            "category": b["category"],
            "budgeted": budgeted,
            "actual": actual,
            "variance": variance,
            "usage_pct": pct,
            "status": "over" if variance > 0 else "under" if variance < 0 else "on_target"
        })

    return ok_response("Budget vs Actual", {
        "year": year,
        "total_budgeted": round(total_budgeted, 2),
        "total_actual": round(total_actual, 2),
        "total_variance": round(total_actual - total_budgeted, 2),
        "items": comparison
    })

@router.get("/forecast/{year}")
def forecast(year: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # ბოლო 3 თვის საშუალო
        cur.execute("""
            SELECT account_code, reason as category,
                   COALESCE(AVG(monthly_total),0) as avg_monthly
            FROM (
                SELECT account_code, reason,
                       DATE_TRUNC('month', created_at) as month,
                       SUM(amount) as monthly_total
                FROM journal_drafts
                WHERE created_at >= NOW() - INTERVAL '3 months'
                GROUP BY account_code, reason, DATE_TRUNC('month', created_at)
            ) sub
            GROUP BY account_code, reason
        """)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    forecast_items = []
    for r in rows:
        avg = float(r["avg_monthly"])
        forecast_items.append({
            "account_code": r["account_code"],
            "category": r["category"],
            "avg_monthly": round(avg, 2),
            "forecast_annual": round(avg * 12, 2),
            "forecast_q1": round(avg * 3, 2),
        })

    total_forecast = sum(f["forecast_annual"] for f in forecast_items)
    return ok_response("Forecast", {
        "year": year,
        "based_on": "last 3 months average",
        "total_annual_forecast": round(total_forecast, 2),
        "items": forecast_items
    })

@router.get("/list/{year}")
def list_budgets(year: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM budgets WHERE year=%s ORDER BY account_code", (year,))
        budgets = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Budgets", {"year": year, "count": len(budgets), "budgets": budgets})
