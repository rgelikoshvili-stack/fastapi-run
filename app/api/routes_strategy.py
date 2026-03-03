from fastapi import APIRouter
from app.engines.strategy_engine import run_scenario, cost_optimize_suggestions, generate_executive_summary
from app.engines.finance_engine import compute_kpis, rolling_forecast
from app.engines.accounting_engine import JOURNAL_ENTRIES
import asyncio

router = APIRouter(prefix="/strategy", tags=["strategy"])

def get_txs():
    return [{"amount": e.get("gross_amount", 0), "direction": "OUT",
             "date": e.get("transaction_date",""), "category": e.get("reasoning","")}
            for e in JOURNAL_ENTRIES]

@router.post("/recommend")
def recommend(period: str = "2026-03"):
    txs = get_txs()
    kpis = compute_kpis(txs)
    forecast = rolling_forecast(txs, 30)
    summary = asyncio.run(generate_executive_summary(txs, period))
    return {"ok": True, "period": period, "kpis": kpis, "summary": summary}

@router.post("/scenario/run")
def scenario(revenue_change_pct: float = 0.1, expense_change_pct: float = -0.05, horizon: int = 30):
    txs = get_txs()
    base = rolling_forecast(txs, horizon)
    result = run_scenario(base, {
        "revenue_change_pct": revenue_change_pct,
        "expense_change_pct": expense_change_pct,
        "horizon_days": horizon,
    })
    return {"ok": True, "scenario": result}

@router.get("/cost-optimize")
def cost_optimize():
    txs = get_txs()
    kpis = compute_kpis(txs)
    suggestions = cost_optimize_suggestions(kpis)
    return {"ok": True, "suggestions": suggestions}
