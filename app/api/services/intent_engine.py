def detect_intent(message: str) -> dict:
    msg = (message or "").lower()

    if any(k in msg for k in ["ინვოისი", "invoice", "pdf"]):
        return {"intent": "parse_invoice"}

    if any(k in msg for k in ["გადახდა", "post", "დაპოსტვა"]):
        return {"intent": "post_transaction"}

    if any(k in msg for k in ["მაჩვენე", "show", "ნახვა"]):
        return {"intent": "show_data"}

    return {"intent": "unknown"}