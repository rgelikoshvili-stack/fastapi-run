def gemini_review(draft: dict) -> dict:
    issues = []

    confidence = float(draft.get("confidence") or 0.0)
    lines = draft.get("lines") or []

    account_code = draft.get("account_code") or ""
    if not account_code and lines and isinstance(lines, list):
        first_line = lines[0] or {}
        account_code = str(first_line.get("account_code") or "").strip()

    if confidence < 0.75:
        issues.append("low_confidence_flag")

    if not account_code and not lines:
        issues.append("missing_account_code")

    return {
        "ok": True,
        "ai": "gemini",
        "issues": issues,
        "suggestion": "review" if issues else "ok",
    }