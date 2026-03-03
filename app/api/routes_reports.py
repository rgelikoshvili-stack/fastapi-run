from fastapi import APIRouter
from app.engines.finance_engine import compute_kpis, rolling_forecast, cashflow_summary
from app.engines.accounting_engine import JOURNAL_ENTRIES
from app.engines.audit_engine import get_issues
from app.storage.event_log import AUDIT_LOG

router = APIRouter(prefix="/reports", tags=["reports"])

def get_txs():
    return [{"amount": e.get("gross_amount", 0), "direction": "OUT",
             "date": e.get("transaction_date",""), "category": e.get("reasoning","")}
            for e in JOURNAL_ENTRIES]

@router.get("/executive-brief")
def executive_brief(period: str = "2026-03"):
    txs = get_txs()
    kpis = compute_kpis(txs)
    forecast = rolling_forecast(txs, 30)
    critical = [i for i in get_issues() if i["severity"] in ["CRITICAL","HIGH"]]
    return {
        "ok": True,
        "period": period,
        "kpis": kpis,
        "forecast_30d": forecast,
        "open_critical_issues": len(critical),
        "total_journal_entries": len(JOURNAL_ENTRIES),
        "total_audit_events": len(AUDIT_LOG),
    }

@router.get("/audit-summary")
def audit_summary():
    issues = get_issues()
    by_severity = {}
    for i in issues:
        s = i["severity"]
        by_severity[s] = by_severity.get(s, 0) + 1
    return {
        "ok": True,
        "total_issues": len(issues),
        "by_severity": by_severity,
        "open": len([i for i in issues if i["status"] == "open"]),
        "resolved": len([i for i in issues if i["status"] == "resolved"]),
    }
