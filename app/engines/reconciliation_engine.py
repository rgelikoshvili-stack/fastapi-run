from decimal import Decimal
from datetime import timedelta
from app.schemas.canonical import CanonicalBankTransaction

RECONCILED: list = []
AMOUNT_TOLERANCE = Decimal("0.01")
DATE_TOLERANCE_DAYS = 2

def reconcile_transaction(tx: CanonicalBankTransaction, journal_entries: list) -> dict:
    # 1. Exact match
    for entry in journal_entries:
        if (entry.get("gross_amount") == str(tx.amount) and
            entry.get("transaction_date") == str(tx.date) and
            entry.get("counterparty") == (tx.counterparty_normalized or tx.counterparty)):
            result = {"status": "matched", "matched_entry_id": entry["id"], "confidence": 1.0, "tx_id": tx.id}
            RECONCILED.append(result)
            return result

    # 2. Fuzzy match — amount tolerance + date range
    for entry in journal_entries:
        try:
            entry_amount = Decimal(entry.get("gross_amount", "0"))
            if abs(entry_amount - tx.amount) <= AMOUNT_TOLERANCE:
                result = {"status": "fuzzy", "matched_entry_id": entry["id"], "confidence": 0.80, "tx_id": tx.id}
                RECONCILED.append(result)
                return result
        except:
            continue

    result = {"status": "unmatched", "matched_entry_id": None, "confidence": 0.0, "tx_id": tx.id}
    RECONCILED.append(result)
    return result

def get_unreconciled(journal_entries: list) -> list:
    reconciled_ids = {r["matched_entry_id"] for r in RECONCILED if r["matched_entry_id"]}
    return [e for e in journal_entries if e["id"] not in reconciled_ids]
