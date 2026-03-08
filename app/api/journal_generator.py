BANK_ACCOUNT = "1210"

POSTING_RULES = {
    "income":    {"dr": BANK_ACCOUNT, "cr": "6100"},
    "salary":    {"dr": "7120", "cr": BANK_ACCOUNT},
    "rent":      {"dr": "7110", "cr": BANK_ACCOUNT},
    "utility":   {"dr": "7130", "cr": BANK_ACCOUNT},
    "software":  {"dr": "7140", "cr": BANK_ACCOUNT},
    "bank_fee":  {"dr": "7150", "cr": BANK_ACCOUNT},
    "transport": {"dr": "7160", "cr": BANK_ACCOUNT},
    "marketing": {"dr": "7170", "cr": BANK_ACCOUNT},
    "office":    {"dr": "7180", "cr": BANK_ACCOUNT},
    "delivery":  {"dr": "7185", "cr": BANK_ACCOUNT},
    "tax":       {"dr": "3100", "cr": BANK_ACCOUNT},
    "transfer":  {"dr": BANK_ACCOUNT, "cr": BANK_ACCOUNT},
    "default expense": {"dr": "7190", "cr": BANK_ACCOUNT},
}

def generate_draft(transaction: dict, classification: dict) -> dict:
    reason = classification.get("reason", "default expense")
    account_code = classification.get("account_code", "7190")
    confidence = classification.get("confidence", 0.4)
    review_required = classification.get("review_required", confidence < 0.6)

    paid_in = transaction.get("paid_in")
    paid_out = transaction.get("paid_out")
    amount = float(paid_out or paid_in or 0)

    rules = POSTING_RULES.get(reason, {"dr": account_code, "cr": BANK_ACCOUNT})

    if paid_in and not paid_out:
        dr = BANK_ACCOUNT
        cr = account_code
    else:
        dr = rules["dr"]
        cr = rules["cr"]

    return {
        "date": transaction.get("date"),
        "description": transaction.get("description"),
        "partner": transaction.get("partner"),
        "amount": amount,
        "debit_account": dr,
        "credit_account": cr,
        "account_code": account_code,
        "reason": reason,
        "confidence": confidence,
        "review_required": review_required,
        "status": "pending_approval" if review_required else "drafted",
        "source_type": transaction.get("source_type", "manual"),
    }
