from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
from app.schemas.canonical import CanonicalBankTransaction, CanonicalJournalDraft, JournalLine
from app.engines.gaas_engine import gaas_classify_doc_type, gaas_classify_text, compute_vat_split, GAAS_COA
from app.workflows.state_machine import route_by_confidence
from app.storage.event_log import write as audit_write
from app.policy.tax_constants import GEORGIAN_TAX_CONSTANTS

GAAS_ENTRIES: list = []

def gaas_build_draft(tx: CanonicalBankTransaction, rule: dict) -> CanonicalJournalDraft:
    amount = tx.amount
    vat_split = compute_vat_split(amount, rule["vat_class"])
    vat_amount = vat_split["vat"]

    lines = [
        JournalLine(
            account_code=rule["debit"],
            account_name=rule["debit_name"],
            debit=amount if tx.direction == "OUT" else None,
            credit=amount if tx.direction == "IN" else None,
        ),
        JournalLine(
            account_code=rule["credit"],
            account_name=rule["credit_name"],
            credit=amount if tx.direction == "OUT" else None,
            debit=amount if tx.direction == "IN" else None,
        ),
    ]

    # Add VAT line if applicable
    if vat_amount > 0:
        if rule["vat_class"].startswith("OUT"):
            lines.append(JournalLine(
                account_code="2210",
                account_name=GAAS_COA.get("2210",{}).get("name","VAT payable"),
                credit=vat_amount,
            ))
        elif rule["vat_class"].startswith("IN") and "DED" in rule["vat_class"]:
            lines.append(JournalLine(
                account_code="1420",
                account_name=GAAS_COA.get("1420",{}).get("name","VAT receivable"),
                debit=vat_amount,
            ))

    draft = CanonicalJournalDraft(
        transaction_id=tx.id,
        lines=lines,
        tax_hint=rule["vat_class"],
        tax_amount=vat_amount if vat_amount > 0 else None,
        confidence=rule["confidence"],
        requires_approval=rule["confidence"] < 0.90,
        reasoning=f"GAAS {rule['rule_id']} | {rule.get('match_method','rule')}",
    )
    return draft

def gaas_classify_transaction(tx: CanonicalBankTransaction, doc_type: str = "") -> CanonicalJournalDraft:
    rule = None
    if doc_type:
        rule = gaas_classify_doc_type(doc_type)
    if not rule:
        rule = gaas_classify_text(tx.description, tx.counterparty or "")
    if not rule:
        rule = {
            "rule_id": "F3.UNCLASSIFIED", "debit": "9999",
            "debit_name": GAAS_COA.get("9999",{}).get("name","Unclassified"),
            "credit": "1120",
            "credit_name": GAAS_COA.get("1120",{}).get("name","Bank accounts"),
            "vat_class": "NON_VAT", "confidence": 0.30, "match_method": "fallback",
        }

    draft = gaas_build_draft(tx, rule)
    entry = {
        "rule_id":     rule["rule_id"],
        "tx_id":       tx.id,
        "date":        str(tx.date),
        "description": tx.description,
        "amount":      str(tx.amount),
        "direction":   tx.direction,
        "debit":       rule["debit"],
        "debit_name":  rule["debit_name"],
        "credit":      rule["credit"],
        "credit_name": rule["credit_name"],
        "vat_class":   rule["vat_class"],
        "tax_amount":  str(draft.tax_amount) if draft.tax_amount else "0",
        "confidence":  rule["confidence"],
        "queue":       route_by_confidence(rule["confidence"]),
        "is_balanced": draft.is_balanced,
        "gaas_version":"v5.2",
    }
    GAAS_ENTRIES.append(entry)
    audit_write(draft.id, "gaas_journal", "", "classified", "gaas_v52")
    return draft

def get_gaas_entries(): return GAAS_ENTRIES
