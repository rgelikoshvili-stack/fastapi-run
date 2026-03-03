from decimal import Decimal
from app.schemas.canonical import CanonicalBankTransaction, CanonicalJournalDraft, JournalLine
from app.canonical.mappers import get_account_rules, CHART_OF_ACCOUNTS
from app.workflows.state_machine import route_by_confidence

JOURNAL_ENTRIES: list = []

def build_draft(tx, result):
    amount = tx.amount
    tax_hint = result.get("tax_hint", "EXEMPT")
    vat_rate = Decimal("0.18") if tax_hint == "VAT_18" else Decimal("0")
    vat_amount = (amount * vat_rate / (1 + vat_rate)).quantize(Decimal("0.01"))
    lines = [
        JournalLine(account_code=result["debit_account"], account_name=result["debit_account_name"],
            debit=amount if tx.direction == "OUT" else None, credit=amount if tx.direction == "IN" else None),
        JournalLine(account_code=result["credit_account"], account_name=result["credit_account_name"],
            credit=amount if tx.direction == "OUT" else None, debit=amount if tx.direction == "IN" else None),
    ]
    confidence = result.get("confidence", 0.70)
    return CanonicalJournalDraft(transaction_id=tx.id, lines=lines, tax_hint=tax_hint,
        tax_amount=vat_amount if vat_amount > 0 else None, confidence=confidence,
        requires_approval=confidence < 0.90, reasoning=result.get("reasoning", "rule-based"))

def classify_transaction(tx):
    rule = get_account_rules(tx.description, tx.counterparty_normalized or tx.counterparty or "")
    if rule and rule["confidence"] >= 0.85:
        draft = build_draft(tx, rule)
        entry = draft.model_dump()
        entry["transaction_date"] = str(tx.date)
        entry["counterparty"] = tx.counterparty_normalized or tx.counterparty
        entry["gross_amount"] = str(tx.amount)
        entry["queue"] = route_by_confidence(draft.confidence)
        for line in entry["lines"]:
            if line.get("debit"): line["debit"] = str(line["debit"])
            if line.get("credit"): line["credit"] = str(line["credit"])
        if entry.get("tax_amount"): entry["tax_amount"] = str(entry["tax_amount"])
        JOURNAL_ENTRIES.append(entry)
        return draft
    return build_draft(tx, {"debit_account": "9999", "debit_account_name": "Unclassified",
        "credit_account": "1110", "credit_account_name": CHART_OF_ACCOUNTS["1110"],
        "tax_hint": "EXEMPT", "confidence": 0.40, "reasoning": "No rule match - manual review"})

def get_journal_entries(status=""):
    if status:
        return [e for e in JOURNAL_ENTRIES if e.get("state") == status]
    return JOURNAL_ENTRIES
