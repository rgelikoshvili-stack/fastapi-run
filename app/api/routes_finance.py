from fastapi import APIRouter
from app.schemas.canonical import CanonicalBankTransaction
from app.engines.reconciliation_engine import reconcile_transaction, get_unreconciled
from app.engines.accounting_engine import JOURNAL_ENTRIES
from app.engines.finance_engine import compute_kpis, rolling_forecast, cashflow_summary
from app.storage.event_log import AUDIT_LOG

router = APIRouter(prefix="/finance", tags=["finance"])

@router.post("/reconcile")
def reconcile(tx: CanonicalBankTransaction):
    result = reconcile_transaction(tx, JOURNAL_ENTRIES)
    return {"ok": True, "result": result}

@router.get("/unreconciled")
def unreconciled():
    items = get_unreconciled(JOURNAL_ENTRIES)
    return {"ok": True, "count": len(items), "entries": items}

@router.get("/dashboard")
def dashboard():
    txs = [{"amount": e.get("gross_amount", 0), "direction": "OUT",
             "date": e.get("transaction_date",""), "category": e.get("reasoning","")}
           for e in JOURNAL_ENTRIES]
    kpis = compute_kpis(txs)
    forecast = rolling_forecast(txs, 30)
    return {"ok": True, "kpis": kpis, "forecast_30d": forecast,
            "total_journal_entries": len(JOURNAL_ENTRIES),
            "total_audit_events": len(AUDIT_LOG)}

@router.get("/forecast")
def forecast(horizon: int = 30):
    txs = [{"amount": e.get("gross_amount", 0), "direction": "OUT",
             "date": e.get("transaction_date","")} for e in JOURNAL_ENTRIES]
    return {"ok": True, "forecast": rolling_forecast(txs, horizon)}

@router.get("/cashflow")
def cashflow():
    txs = [{"amount": e.get("gross_amount", 0), "direction": "OUT",
             "date": e.get("transaction_date","")} for e in JOURNAL_ENTRIES]
    return {"ok": True, "cashflow": cashflow_summary(txs)}
