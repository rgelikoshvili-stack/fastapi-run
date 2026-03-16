import os

def balance_config_status():
    return {
        "base_url": os.environ.get("BALANCE_BASE_URL"),
        "api_key_configured": bool(os.environ.get("BALANCE_API_KEY")),
        "company_id": os.environ.get("BALANCE_COMPANY_ID"),
        "ready": False
    }

def balance_ping():
    return {"ok": False, "status": "config_missing", "details": {"base_url_present": False, "api_key_present": False, "company_id_present": False}}

def build_balance_payload(draft: dict) -> dict:
    return {"company_id": None, "draft_id": draft.get("id"), "transaction_date": str(draft.get("date")) if draft.get("date") else None, "description": draft.get("description"), "partner": draft.get("partner"), "amount": float(draft.get("amount") or 0), "debit_account": draft.get("debit_account"), "credit_account": draft.get("credit_account"), "account_code": draft.get("account_code"), "reason": draft.get("reason"), "source_type": draft.get("source_type"), "bank_file_id": draft.get("bank_file_id"), "metadata": {"confidence": float(draft.get("confidence") or 0), "review_required": draft.get("review_required"), "created_at": str(draft.get("created_at")) if draft.get("created_at") else None}}

def post_to_balance(payload: dict) -> dict:
    return {"ok": False, "status": "config_missing", "error": "Balance config is incomplete", "details": {"base_url_present": False, "api_key_present": False, "company_id_present": False}}
