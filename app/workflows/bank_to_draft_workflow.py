from app.canonical.validators import validate_transaction_payload


def run_bank_to_draft_workflow(payload: dict) -> dict:
    validation = validate_transaction_payload(payload)
    if not validation["ok"]:
        return {
            "ok": False,
            "error": "VALIDATION_ERROR",
            "missing": validation["missing"],
        }

    return {
        "ok": True,
        "stage": "validated",
        "payload": payload,
    }