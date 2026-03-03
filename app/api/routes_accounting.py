from fastapi import APIRouter
from app.schemas.canonical import CanonicalBankTransaction
from app.engines.accounting_engine import classify_transaction, get_journal_entries, JOURNAL_ENTRIES
from app.storage.event_log import write as audit_write

router = APIRouter(prefix="/accounting", tags=["accounting"])

@router.post("/classify")
def classify(tx: CanonicalBankTransaction):
    draft = classify_transaction(tx)
    audit_write(draft.id, "journal_draft", "", "draft", "system", "classified")
    entry = draft.model_dump()
    entry["is_balanced"] = draft.is_balanced
    for line in entry["lines"]:
        if line.get("debit"): line["debit"] = str(line["debit"])
        if line.get("credit"): line["credit"] = str(line["credit"])
    if entry.get("tax_amount"): entry["tax_amount"] = str(entry["tax_amount"])
    return {"ok": True, "draft": entry}

@router.get("/journal/list")
def journal_list(status: str = ""):
    return {"ok": True, "count": len(get_journal_entries(status)), "entries": get_journal_entries(status)}

@router.post("/approve/{entry_id}")
def approve(entry_id: str, approved_by: str = "user"):
    for entry in JOURNAL_ENTRIES:
        if entry["id"] == entry_id:
            entry["state"] = "approved"
            entry["approved_by"] = approved_by
            audit_write(entry_id, "journal_draft", "draft", "approved", approved_by)
            return {"ok": True, "entry_id": entry_id, "state": "approved"}
    return {"ok": False, "error": "not found"}

@router.get("/accounts")
def get_accounts():
    from app.canonical.mappers import CHART_OF_ACCOUNTS
    return {"ok": True, "accounts": CHART_OF_ACCOUNTS}
