from fastapi import APIRouter
from pydantic import BaseModel
from decimal import Decimal, ROUND_HALF_UP

router = APIRouter(prefix="/close", tags=["close"])

PROFIT_TAX_RATE = Decimal("0.15")
MONTH_CLOSE_LOG: list = []

class ProfitTaxRequest(BaseModel):
    company_id: str = "CO-001"
    tax_period: dict = {}
    revenue: float = 0.0
    expenses: float = 0.0
    taxable_profit: float = 0.0

class MonthCloseRequest(BaseModel):
    company_id: str = "CO-001"
    period: dict = {}
    gl_sums: dict = {}

@router.post("/profit-tax")
def profit_tax(req: ProfitTaxRequest):
    taxable = Decimal(str(req.taxable_profit))
    if taxable <= 0:
        taxable = max(Decimal("0"), Decimal(str(req.revenue)) - Decimal(str(req.expenses)))
    tax = (taxable * PROFIT_TAX_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "ok": True,
        "company_id": req.company_id,
        "tax_period": req.tax_period,
        "taxable_profit": float(taxable),
        "profit_tax_rate": float(PROFIT_TAX_RATE),
        "profit_tax": float(tax),
        "journal": {
            "debit": {"account": "5710", "name": "Tax Expense", "amount": float(tax)},
            "credit": {"account": "2220", "name": "Income Tax Payable", "amount": float(tax)},
        }
    }

@router.post("/month")
def month_close(req: MonthCloseRequest):
    from datetime import datetime, timezone
    from app.engines.accounting_engine import JOURNAL_ENTRIES
    from app.storage.event_log import AUDIT_LOG
    entry = {
        "company_id": req.company_id,
        "period": req.period,
        "gl_sums": req.gl_sums,
        "journal_entries_count": len(JOURNAL_ENTRIES),
        "audit_events_count": len(AUDIT_LOG),
        "status": "closed",
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }
    MONTH_CLOSE_LOG.append(entry)
    return {"ok": True, "result": entry}

@router.get("/month/log")
def month_log():
    return {"ok": True, "count": len(MONTH_CLOSE_LOG), "log": MONTH_CLOSE_LOG}
