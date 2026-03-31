def build_draft_preview(payload: dict) -> dict:
    return {
        "summary": {
            "description": payload.get("description"),
            "partner": payload.get("partner"),
            "amount": payload.get("amount"),
            "account_code": payload.get("account_code"),
            "confidence": payload.get("confidence"),
            "status": payload.get("status"),
        },
        "explanation": payload.get(
            "explanation",
            "Preview generated from current draft data."
        )
    }