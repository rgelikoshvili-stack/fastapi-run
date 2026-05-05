"""app/api/services/approval_patterns.py

Pattern reinforcement helpers for the approval workflow.
Extracted from approval_service.py for single-responsibility clarity.

All symbols are re-exported by approval_service.py — existing imports work unchanged.
"""

from app.api.engines.pattern_engine import mark_pattern_success, mark_pattern_failure


def _get_pattern_value_for_draft(draft: dict):
    """Return the pattern value that was used to classify this draft."""
    matched_on = draft.get("pattern_matched_on")
    if matched_on in ("description_exact", "description_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("description")
    if matched_on in ("partner_exact", "partner_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("partner")
    return None


def _mark_success_for_draft(draft: dict, tenant_id: str, weight: float = 1.0):
    """Reinforce the pattern that matched this draft after a successful approval."""
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value or not account_code:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_success(
            "description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "partner_exact":
        return mark_pattern_success(
            "partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "description_fuzzy":
        return mark_pattern_success(
            "description_fuzzy", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "partner_fuzzy":
        return mark_pattern_success(
            "partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )

    return {"updated": 0}


def _mark_failure_for_draft(draft: dict, tenant_id: str, weight: float = 1.5):
    """Penalise the pattern that matched this draft after a rejection."""
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value or not account_code:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_failure(
            "description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "partner_exact":
        return mark_pattern_failure(
            "partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "description_fuzzy":
        return mark_pattern_failure(
            "description_fuzzy", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )
    if matched_on == "partner_fuzzy":
        return mark_pattern_failure(
            "partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight
        )

    return {"updated": 0}
