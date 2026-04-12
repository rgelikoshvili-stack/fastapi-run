from app.api.services.gemini_qa_service import gemini_review


def evaluate_decision(draft: dict) -> dict:
    issues = []
    score = 1.0

    confidence = float(draft.get("confidence") or 0.0)
    amount = float(draft.get("amount") or 0.0)
    lines = draft.get("lines") or []

    account_code = draft.get("account_code") or ""
    if not account_code and lines and isinstance(lines, list):
        first_line = lines[0] or {}
        account_code = str(first_line.get("account_code") or "").strip()

    if not account_code and not lines:
        issues.append("missing_account_code")
        score -= 0.3

    if confidence < 0.7:
        issues.append("low_confidence")
        score -= 0.2

    if not draft.get("partner"):
        issues.append("missing_partner")
        score -= 0.1

    try:
        safe_draft = dict(draft)
        safe_draft["confidence"] = confidence
        safe_draft["amount"] = amount
        safe_draft["account_code"] = account_code
        safe_draft["lines"] = lines
        gemini = gemini_review(safe_draft)
    except Exception as e:
        gemini = {
            "ok": False,
            "error": str(e),
            "fallback": True,
        }

    return {
        "ok": True,
        "score": max(score, 0),
        "issues": issues,
        "recommendation": "review" if score < 0.7 else "ok",
        "gemini_review": gemini,
    }