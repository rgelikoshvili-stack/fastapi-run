import os


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def onec_config_status():
    base_url = _clean(os.getenv("ONEC_BASE_URL"))
    api_key = _clean(os.getenv("ONEC_API_KEY"))
    company_id = _clean(os.getenv("ONEC_COMPANY_ID"))

    return {
        "base_url": base_url,
        "api_key_configured": bool(api_key),
        "company_id": company_id,
        "ready": bool(base_url and api_key and company_id),
    }


def onec_ping():
    config = onec_config_status()

    if not config["ready"]:
        return {
            "ok": False,
            "status": "config_missing",
            "details": {
                "base_url_present": bool(config["base_url"]),
                "api_key_present": config["api_key_configured"],
                "company_id_present": bool(config["company_id"]),
            },
        }

    return {
        "ok": True,
        "status": "ready_for_live_ping",
        "details": {
            "message": "1C config is present. Live API call not enabled yet.",
            "base_url": config["base_url"],
            "company_id": config["company_id"],
        },
    }


def build_onec_payload(draft: dict):
    return {
        "company_id": _clean(os.getenv("ONEC_COMPANY_ID")),
        "draft_id": draft.get("id"),
        "transaction_date": str(draft.get("date")) if draft.get("date") is not None else None,
        "description": draft.get("description"),
        "partner": draft.get("partner"),
        "amount": float(draft.get("amount")) if draft.get("amount") is not None else 0.0,
        "debit_account": draft.get("debit_account"),
        "credit_account": draft.get("credit_account"),
        "account_code": draft.get("account_code"),
        "reason": draft.get("reason"),
        "source_type": draft.get("source_type"),
        "bank_file_id": draft.get("bank_file_id"),
        "metadata": {
            "confidence": float(draft.get("confidence")) if draft.get("confidence") is not None else None,
            "review_required": draft.get("review_required"),
            "created_at": str(draft.get("created_at")) if draft.get("created_at") is not None else None,
        },
    }


def post_to_onec(payload: dict):
    config = onec_config_status()

    if not config["ready"]:
        return {
            "ok": False,
            "status": "config_missing",
            "error": "1C config is incomplete",
            "details": {
                "base_url_present": bool(config["base_url"]),
                "api_key_present": config["api_key_configured"],
                "company_id_present": bool(config["company_id"]),
            },
        }

    return {
        "ok": True,
        "status": "simulated_onec_post",
        "message": "1C connector skeleton is ready. Replace this stub with live API request later.",
        "payload": payload,
        "target": {
            "base_url": config["base_url"],
            "company_id": config["company_id"],
        },
    }
