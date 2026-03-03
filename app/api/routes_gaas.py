from fastapi import APIRouter
from pydantic import BaseModel
from decimal import Decimal
from typing import Optional
from app.engines.gaas_engine import (gaas_classify_doc_type, gaas_classify_text,
    compute_vat_split, compute_vat_return, GAAS_COA, GAAS_RULES)
from app.engines.gaas_posting_engine import gaas_classify_transaction
from app.storage.db_service import (save_journal_entry, get_journal_entries,
    save_audit_log, save_vat_return, get_db_stats)
from app.schemas.canonical import CanonicalBankTransaction
from app.workflows.state_machine import route_by_confidence

router = APIRouter(prefix="/gaas", tags=["gaas"])

class ClassifyRequest(BaseModel):
    text: str
    locale: str = "ka-GE"
    country: str = "GE"
    doc_type: Optional[str] = None
    amount: Optional[float] = None

class VATReturnRequest(BaseModel):
    tax_period: dict
    company_id: str = "CO-001"
    docs: list = []

@router.post("/classify")
def gaas_classify(req: ClassifyRequest):
    rule = None
    if req.doc_type:
        rule = gaas_classify_doc_type(req.doc_type)
    if not rule:
        rule = gaas_classify_text(req.text)
    if not rule:
        rule = {"rule_id":"F3.UNCLASSIFIED","debit":"9999","debit_name":"Unclassified",
                "credit":"1120","credit_name":"Bank accounts","vat_class":"NON_VAT",
                "confidence":0.30,"match_method":"fallback"}
    vat_info = None
    if req.amount and rule["vat_class"] != "NON_VAT":
        v = compute_vat_split(Decimal(str(req.amount)), rule["vat_class"])
        vat_info = {k: str(v) if isinstance(v, Decimal) else v for k, v in v.items()}
    result = {**rule, "queue": route_by_confidence(rule["confidence"]), "vat_split": vat_info}
    save_audit_log(rule["rule_id"], "gaas_classify", "", "classified", "gaas_engine")
    return {"ok": True, "classification": result}

@router.post("/bridge/classify")
def bridge_classify(tx: CanonicalBankTransaction, doc_type: str = ""):
    draft = gaas_classify_transaction(tx, doc_type)
    entry = {
        "id": draft.id,
        "tx_id": tx.id,
        "date": str(tx.date),
        "description": tx.description,
        "counterparty": tx.counterparty or "",
        "amount": str(tx.amount),
        "direction": tx.direction,
        "debit": draft.lines[0].account_code if draft.lines else "9999",
        "debit_name": draft.lines[0].account_name if draft.lines else "",
        "credit": draft.lines[1].account_code if len(draft.lines)>1 else "1120",
        "credit_name": draft.lines[1].account_name if len(draft.lines)>1 else "",
        "vat_class": draft.tax_hint or "NON_VAT",
        "tax_amount": str(draft.tax_amount) if draft.tax_amount else "0",
        "rule_id": draft.reasoning or "",
        "confidence": float(draft.confidence),
        "queue": route_by_confidence(float(draft.confidence)),
        "is_balanced": draft.is_balanced,
        "gaas_version": "v5.2",
    }
    save_journal_entry(entry)
    save_audit_log(tx.id, "bridge_classify", "", "classified", "gaas_v52")
    return {"ok": True, "draft": entry}

@router.post("/f4/vat-return/submit")
def vat_return_submit(req: VATReturnRequest):
    totals = compute_vat_return(req.docs)
    save_vat_return(req.company_id, req.tax_period, totals)
    return {"ok": True, "tax_period": req.tax_period,
            "company_id": req.company_id, "totals": totals,
            "schema": "VATReturnPayload_v1"}

@router.get("/coa")
def get_coa():
    return {"ok": True, "count": len(GAAS_COA), "accounts": GAAS_COA}

@router.get("/rules")
def get_rules():
    rules = [{"rule_id":r[0],"doc_types":r[1],"debit":r[2],"credit":r[3],
              "vat_class":r[4],"confidence":r[5]} for r in GAAS_RULES]
    return {"ok": True, "count": len(rules), "rules": rules}

@router.get("/journal")
def gaas_journal(limit: int = 100):
    entries = get_journal_entries(limit)
    return {"ok": True, "count": len(entries), "entries": entries}

@router.get("/db/stats")
def db_stats():
    return {"ok": True, "stats": get_db_stats()}

@router.get("/tax-constants")
def tax_constants():
    from app.policy.tax_constants import GEORGIAN_TAX_CONSTANTS
    return {"ok": True, "source": "საქართველოს საგადასახადო კოდექსი",
            "constants": GEORGIAN_TAX_CONSTANTS}
