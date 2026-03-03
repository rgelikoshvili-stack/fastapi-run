from app.engines.finance_engine import compute_kpis, rolling_forecast

async def generate_executive_summary(transactions: list, period: str = "") -> str:
    kpis = compute_kpis(transactions)
    forecast = rolling_forecast(transactions, 30)
    try:
        from app.services.llm_service import llm_text
        import asyncio
        prompt = f"""შენ ხარ CFO Assistant. დაწერე მოკლე აღმასრულებელი ფინანსური შეჯამება ქართულად.
მაქსიმუმ 3 აბზაცი. იყავი კონკრეტული რიცხვებით.

პერიოდი: {period}
შემოსავალი:  {kpis["total_income"]:,.2f} GEL
ხარჯი:       {kpis["total_expense"]:,.2f} GEL
წმინდა:      {kpis["net_cashflow"]:,.2f} GEL
ტრანზაქციები: {kpis["tx_count"]}
30-დღიანი პროგნოზი: {forecast["projected_net"]:,.2f} GEL

მოიცავდეს: ძირითადი მაჩვენებლები, რისკები, 1-2 რეკომენდაცია."""
        return await llm_text(prompt, provider="claude")
    except:
        return f"""ფინანსური შეჯამება — {period}
შემოსავალი: {kpis["total_income"]:,.2f} GEL | ხარჯი: {kpis["total_expense"]:,.2f} GEL | წმინდა: {kpis["net_cashflow"]:,.2f} GEL
30-დღიანი პროგნოზი: {forecast["projected_net"]:,.2f} GEL (AI გარეშე — API key საჭიროა)"""

def run_scenario(base_forecast: dict, assumptions: dict) -> dict:
    rev_mult = 1 + assumptions.get("revenue_change_pct", 0)
    exp_mult = 1 + assumptions.get("expense_change_pct", 0)
    scenario_in  = base_forecast["projected_income"] * rev_mult
    scenario_out = base_forecast["projected_expense"] * exp_mult
    return {
        "base_net":      base_forecast["projected_net"],
        "scenario_net":  round(scenario_in - scenario_out, 2),
        "scenario_in":   round(scenario_in, 2),
        "scenario_out":  round(scenario_out, 2),
        "delta":         round((scenario_in - scenario_out) - base_forecast["projected_net"], 2),
        "assumptions":   assumptions,
    }

def cost_optimize_suggestions(kpis: dict) -> list:
    suggestions = []
    by_cat = kpis.get("by_category", {})
    for cat, amount in by_cat.items():
        if amount > 5000:
            suggestions.append({
                "category": cat,
                "current_spend": amount,
                "suggestion": f"გადახედე {cat} ხარჯებს — {amount:,.2f} GEL თვეში",
                "potential_saving_pct": 10,
            })
    return suggestions
