from app.api.services.gemini_qa_service import gemini_review


def evaluate_decision(draft: dict) -> dict:
    issues = []
    score = 1.0

    if not draft.get("account_code"):
        issues.append("missing_account_code")
        score -= 0.3

    if draft.get("confidence", 1) < 0.7:
        issues.append("low_confidence")
        score -= 0.2

    if not draft.get("partner"):
        issues.append("missing_partner")
        score -= 0.1

    gemini = gemini_review(draft)

    return {
        "ok": True,
        "score": max(score, 0),
        "issues": issues,
        "recommendation": "review" if score < 0.7 else "ok",
        "gemini_review": gemini,
    }