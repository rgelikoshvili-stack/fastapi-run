def decide_autopilot_status(cl: dict) -> tuple[bool, str, str]:
    source = cl.get("source")
    confidence = float(cl.get("confidence") or 0)
    support_count = int(cl.get("pattern_support_count") or 0)
    failure_count = int(cl.get("pattern_failure_count") or 0)

    if source in ("pattern_active", "pattern_active_fuzzy"):
        if confidence >= 0.90 and failure_count == 0:
            return False, "auto_approved", "trusted_active_pattern"
        return False, "drafted", "active_pattern_manual_post"

    if source in ("pattern_candidate", "pattern_candidate_fuzzy"):
        return True, "pending_approval", "candidate_pattern_needs_review"

    if confidence >= 0.85:
        return False, "drafted", "high_confidence_rules"

    return True, "pending_approval", "low_confidence_rules"


def generate_draft(tx: dict, cl: dict) -> dict:
    amount = tx.get("amount")
    if amount is None:
        paid_in = tx.get("paid_in")
        paid_out = tx.get("paid_out")
        if paid_in not in (None, "", 0, 0.0):
            amount = paid_in
        elif paid_out not in (None, "", 0, 0.0):
            amount = paid_out
        else:
            amount = 0.0

    account_code = cl.get("account_code")
    review_required, status, autopilot_reason = decide_autopilot_status(cl)

    if tx.get("paid_in") not in (None, "", 0, 0.0):
        debit_account = "1210"
        credit_account = account_code
    else:
        debit_account = account_code
        credit_account = "1210"

    approved_by_mode = "pattern_autopilot" if status == "auto_approved" else None

    return {
        "date": tx.get("date"),
        "description": tx.get("description"),
        "partner": tx.get("partner"),
        "amount": amount,
        "debit_account": debit_account,
        "credit_account": credit_account,
        "account_code": account_code,
        "reason": cl.get("reason"),
        "confidence": cl.get("confidence"),
        "review_required": review_required,
        "status": status,
        "source_type": tx.get("source_type"),
        "classification_source": cl.get("source"),
        "pattern_matched_on": cl.get("pattern_matched_on"),
        "pattern_support_count": cl.get("pattern_support_count"),
        "pattern_similarity": cl.get("pattern_similarity"),
        "autopilot_decision": status,
        "autopilot_reason": autopilot_reason,
        "approved_by_mode": approved_by_mode,
    }