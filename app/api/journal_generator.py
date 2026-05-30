from __future__ import annotations


def decide_autopilot_status(cl: dict) -> tuple[bool, str, str]:
    source = (cl.get("source") or "").strip().lower()
    confidence = float(cl.get("confidence") or 0.0)

    support_count = int(cl.get("pattern_support_count") or 0)
    success_count = int(cl.get("pattern_success_count") or 0)
    failure_count = int(cl.get("pattern_failure_count") or 0)
    pattern_days_since_seen = cl.get("pattern_days_since_seen")

    if pattern_days_since_seen is None:
        pattern_days_since_seen = 999999
    else:
        try:
            pattern_days_since_seen = int(pattern_days_since_seen)
        except (ValueError, TypeError):
            pattern_days_since_seen = 999999

    if source == "expense_article":
        return False, "auto_approved", "expense_article_rule"

    if source == "memory":
        usage_count = int(cl.get("memory_usage_count") or 0)
        memory_days_since_seen = cl.get("memory_days_since_seen")

        if memory_days_since_seen is None:
            memory_days_since_seen = 999999
        else:
            try:
                memory_days_since_seen = int(memory_days_since_seen)
            except (ValueError, TypeError):
                memory_days_since_seen = 999999

        if confidence >= 0.90 and usage_count >= 3 and memory_days_since_seen <= 45:
            return False, "auto_approved", "memory_match"

        if memory_days_since_seen > 45:
            return True, "pending_approval", "memory_stale"

        return True, "pending_approval", "memory_needs_review"

    if source == "erp_history":
        erp_evidence_count = int(cl.get("erp_evidence_count") or 0)
        erp_days_since_seen = cl.get("erp_days_since_seen")

        if erp_days_since_seen is None:
            erp_days_since_seen = 999999
        else:
            try:
                erp_days_since_seen = int(erp_days_since_seen)
            except (ValueError, TypeError):
                erp_days_since_seen = 999999

        if confidence >= 0.93 and erp_evidence_count >= 2 and erp_days_since_seen <= 60:
            return False, "auto_approved", "erp_history_rule"

        if erp_days_since_seen > 60:
            return True, "pending_approval", "erp_history_stale"

        return True, "pending_approval", "erp_history_needs_review"

    if source in ("pattern_active", "pattern_active_fuzzy"):
        if (
            confidence >= 0.90
            and failure_count == 0
            and support_count >= 5
            and success_count >= 3
            and pattern_days_since_seen <= 45
        ):
            return False, "auto_approved", "trusted_active_pattern"

        if pattern_days_since_seen > 45:
            return True, "pending_approval", "pattern_stale"
        if failure_count > 0:
            return True, "pending_approval", "has_failures"
        if support_count < 5:
            return True, "pending_approval", "support_below_threshold"
        if success_count < 3:
            return True, "pending_approval", "success_below_threshold"
        if confidence < 0.90:
            return True, "pending_approval", "confidence_below_autopilot_threshold"

        return True, "pending_approval", "active_pattern_needs_review"

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

    amount = float(amount or 0.0)

    review_required, status, autopilot_reason = decide_autopilot_status(cl)

    raw_account_code = str(cl.get("account_code") or "").strip()
    reason = str(cl.get("reason") or "").strip()
    confidence = float(cl.get("confidence") or 0.0)

    description = str(tx.get("description") or "").strip() or "Transaction"
    partner = str(tx.get("partner") or "").strip() or "Unknown"
    currency = str(tx.get("currency") or "GEL").strip() or "GEL"
    tx_date = tx.get("date")
    source_type = tx.get("source_type")

    is_income = tx.get("paid_in") not in (None, "", 0, 0.0)

    if is_income:
        main_account_code = raw_account_code or "6110"
        debit_account = "1210"
        credit_account = main_account_code
        lines = [
            {
                "account_code": debit_account,
                "label": "Bank/Cash",
                "debit": amount,
                "credit": 0.0,
            },
            {
                "account_code": credit_account,
                "label": reason or "Income",
                "debit": 0.0,
                "credit": amount,
            },
        ]
    else:
        main_account_code = raw_account_code or "7190"
        debit_account = main_account_code
        credit_account = "1210"
        lines = [
            {
                "account_code": debit_account,
                "label": reason or "Expense",
                "debit": amount,
                "credit": 0.0,
            },
            {
                "account_code": credit_account,
                "label": "Bank/Cash",
                "debit": 0.0,
                "credit": amount,
            },
        ]

    approved_by_mode = "autopilot" if status == "auto_approved" else "manual_review"

    return {
        "date": tx_date,
        "description": description,
        "partner": partner,
        "amount": amount,
        "currency": currency,
        "debit_account": debit_account,
        "credit_account": credit_account,
        "account_code": main_account_code,
        "lines": lines,
        "reason": reason,
        "confidence": confidence,
        "review_required": review_required,
        "status": status,
        "source_type": source_type,
        "classification_source": cl.get("source"),
        "pattern_matched_on": cl.get("pattern_matched_on"),
        "pattern_support_count": cl.get("pattern_support_count"),
        "pattern_success_count": cl.get("pattern_success_count"),
        "pattern_failure_count": cl.get("pattern_failure_count"),
        "pattern_similarity": cl.get("pattern_similarity"),
        "pattern_value_used": cl.get("pattern_value_used"),
        "pattern_days_since_seen": cl.get("pattern_days_since_seen"),
        "pattern_recency_penalty": cl.get("pattern_recency_penalty"),
        "memory_usage_count": cl.get("memory_usage_count"),
        "memory_match_type": cl.get("memory_match_type"),
        "memory_days_since_seen": cl.get("memory_days_since_seen"),
        "erp_evidence_count": cl.get("erp_evidence_count"),
        "erp_match_type": cl.get("erp_match_type"),
        "erp_days_since_seen": cl.get("erp_days_since_seen"),
        "autopilot_decision": status,
        "autopilot_reason": autopilot_reason,
        "approved_by_mode": approved_by_mode,
    }