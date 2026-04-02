def gemini_review(draft: dict) -> dict:
    issues = []

    if draft.get("confidence", 1) < 0.75:
        issues.append("low_confidence_flag")

    if not draft.get("account_code"):
        issues.append("missing_account_code")

    return {
        "ok": True,
        "ai": "gemini",
        "issues": issues,
        "suggestion": "review" if issues else "ok",
    }