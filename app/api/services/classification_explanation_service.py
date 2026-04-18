"""
app/api/services/classification_explanation_service.py
Bridge Hub — Deterministic explanation layer for classification results.

build_explanation(result) → adds explanation, source_label,
matched_rule, matched_keyword, matched_pattern to the result dict.
Never invents — only reflects what the classifier already decided.
"""

_SOURCE_LABELS = {
    "learned":                  "learned",
    "rules":                    "rule",
    "coa":                      "coa",
    "fallback":                 "fallback",
    "pattern_active":           "pattern",
    "pattern_active_fuzzy":     "pattern",
    "pattern_candidate":        "pattern_candidate",
    "pattern_candidate_fuzzy":  "pattern_candidate",
    "partner_memory":           "memory",
    "transaction_memory":       "memory",
    "erp_history":              "erp",
    "expense_article":          "expense_article",
    "llm":                      "ai",
}


def _human_explanation(result: dict) -> str:
    source = (result.get("source") or "").strip().lower()
    confidence = result.get("confidence", 0)
    account = result.get("account") or result.get("account_code") or ""
    account_name = result.get("account_name") or ""
    pattern_value = result.get("pattern_value_used") or result.get("pattern_value") or ""
    support_count = result.get("pattern_support_count")
    success_count = result.get("pattern_success_count")
    similarity = result.get("pattern_similarity")
    matched_on = result.get("matched_on") or result.get("pattern_matched_on") or ""

    acc_label = f"{account} ({account_name})" if account_name else account

    if source == "expense_article":
        return f"ხარჯის სტატიის წესი: '{pattern_value}' → {acc_label}"

    if source == "partner_memory":
        return f"პარტნიორის მეხსიერება: '{pattern_value}' — ამ პარტნიორს ყოველთვის {acc_label}"

    if source == "transaction_memory":
        return f"ტრანზაქციის ისტორია: ადრე იდენტური ტრანზაქცია {acc_label}-ზე გავიდა"

    if source == "erp_history":
        return f"ERP ისტორია: Balance.ge-ში {acc_label}-ზე გატარდა"

    if source in ("pattern_active", "pattern_active_fuzzy"):
        parts = [f"ნასწავლი pattern (აქტიური): '{pattern_value}' → {acc_label}"]
        if support_count:
            parts.append(f"{support_count}-ჯერ გამოყენებული")
        if success_count and support_count:
            parts.append(f"{success_count}/{support_count} სწორი")
        if similarity:
            parts.append(f"მსგავსება {int(similarity * 100)}%")
        if "fuzzy" in source:
            parts.append("fuzzy match")
        return ", ".join(parts)

    if source in ("pattern_candidate", "pattern_candidate_fuzzy"):
        parts = [f"სწავლის პროცესში pattern: '{pattern_value}' → {acc_label}"]
        if support_count:
            parts.append(f"{support_count}-ჯერ დაფიქსირებული")
        return ", ".join(parts)

    if source == "rules":
        kw = pattern_value or matched_on
        if kw:
            return f"საკვანძო სიტყვის წესი: '{kw}' → {acc_label} (confidence {int(confidence * 100)}%)"
        return f"საკვანძო სიტყვის წესი → {acc_label} (confidence {int(confidence * 100)}%)"

    if source == "learned":
        return f"ხელით ნასწავლი წესი: '{pattern_value}' → {acc_label}"

    if source == "coa":
        return f"ანგარიშთა გეგმის კლასიფიკაცია → {acc_label}"

    if source == "llm":
        return f"AI კლასიფიკაცია → {acc_label} (confidence {int(confidence * 100)}%)"

    if source == "fallback":
        return f"Default fallback → {acc_label} (კლასიფიკაცია ვერ მოხდა)"

    return f"კლასიფიკაცია: {source} → {acc_label}"


def build_explanation(result: dict) -> dict:
    """
    Returns enriched dict: adds explanation, source_label,
    matched_rule, matched_keyword, matched_pattern.
    Does not modify the original dict.
    """
    source = (result.get("source") or "").strip().lower()
    pattern_value = result.get("pattern_value_used") or result.get("pattern_value") or ""
    matched_on = result.get("matched_on") or result.get("pattern_matched_on") or ""

    matched_rule = pattern_value if source == "rules" else None
    matched_keyword = pattern_value if source == "rules" else None
    matched_pattern = pattern_value if source.startswith("pattern") or source in ("learned", "expense_article", "partner_memory") else None

    return {
        **result,
        "explanation": _human_explanation(result),
        "source_label": _SOURCE_LABELS.get(source, source),
        "matched_rule": matched_rule,
        "matched_keyword": matched_keyword,
        "matched_pattern": matched_pattern,
    }
