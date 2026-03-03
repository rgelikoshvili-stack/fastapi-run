from decimal import Decimal
from datetime import date, timedelta

TRANSACTIONS_STORE: list = []

def compute_kpis(transactions: list) -> dict:
    posted = [t for t in transactions if t.get("state") == "posted"]
    total_in  = sum(Decimal(str(t.get("amount", 0))) for t in transactions if t.get("direction") == "IN")
    total_out = sum(Decimal(str(t.get("amount", 0))) for t in transactions if t.get("direction") == "OUT")
    net = total_in - total_out
    by_category = {}
    for t in transactions:
        cat = t.get("category", "unclassified")
        by_category[cat] = by_category.get(cat, Decimal("0")) + Decimal(str(t.get("amount", 0)))
    return {
        "total_income":   float(total_in),
        "total_expense":  float(total_out),
        "net_cashflow":   float(net),
        "tx_count":       len(transactions),
        "by_category":    {k: float(v) for k, v in by_category.items()},
    }

def rolling_forecast(transactions: list, horizon_days: int = 30) -> dict:
    if not transactions:
        return {"horizon_days": horizon_days, "projected_income": 0,
                "projected_expense": 0, "projected_net": 0, "method": "rolling_avg", "confidence": 0.5}
    kpis = compute_kpis(transactions)
    days = max(1, len(set(t.get("date","") for t in transactions)))
    daily_in  = kpis["total_income"]  / days
    daily_out = kpis["total_expense"] / days
    proj_in   = round(daily_in  * horizon_days, 2)
    proj_out  = round(daily_out * horizon_days, 2)
    return {
        "horizon_days":      horizon_days,
        "projected_income":  proj_in,
        "projected_expense": proj_out,
        "projected_net":     round(proj_in - proj_out, 2),
        "method":            "rolling_avg",
        "confidence":        0.70,
    }

def cashflow_summary(transactions: list) -> dict:
    by_date = {}
    for t in transactions:
        d = str(t.get("date", "unknown"))
        if d not in by_date:
            by_date[d] = {"in": 0.0, "out": 0.0}
        amt = float(t.get("amount", 0))
        if t.get("direction") == "IN":
            by_date[d]["in"] += amt
        else:
            by_date[d]["out"] += amt
    return {"daily": by_date}
