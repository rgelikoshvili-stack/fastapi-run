import os


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def _is_true(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def balance_config_status():
    base_url = _clean(os.getenv("BALANCE_BASE_URL"))
    api_key = _clean(os.getenv("BALANCE_API_KEY"))
    company_id = _clean(os.getenv("BALANCE_COMPANY_ID"))
    dry_run = _is_true(os.getenv("BALANCE_DRY_RUN", "false"))

    return {
        "base_url": base_url,
        "api_key_configured": bool(api_key),
        "company_id": company_id,
        "dry_run": dry_run,
        "ready": bool(base_url and api_key and company_id),
    }


def balance_ping():
    config = balance_config_status()

    if not config["ready"]:
        return {
            "ok": False,
            "status": "config_missing",
            "error": "Balance config is incomplete",
            "details": {
                "base_url_present": bool(config["base_url"]),
                "api_key_present": config["api_key_configured"],
                "company_id_present": bool(config["company_id"]),
                "dry_run": config["dry_run"],
            },
        }

    if config["dry_run"]:
        return {
            "ok": True,
            "status": "dry_run_only",
            "error": None,
            "message": "Balance config is present and dry-run mode is enabled.",
            "details": {
                "base_url": config["base_url"],
                "company_id": config["company_id"],
                "dry_run": True,
            },
        }

    return {
        "ok": True,
        "status": "ready_for_live_ping",
        "error": None,
        "message": "Balance config is present. Live API call can be enabled.",
        "details": {
            "base_url": config["base_url"],
            "company_id": config["company_id"],
            "dry_run": False,
        },
    }


def build_balance_payload(draft: dict):
    return {
        "company_id": _clean(os.getenv("BALANCE_COMPANY_ID")),
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


def post_to_balance(payload: dict):
    config = balance_config_status()

    if not config["ready"]:
        return {
            "ok": False,
            "status": "config_missing",
            "error": "Balance config is incomplete",
            "details": {
                "base_url_present": bool(config["base_url"]),
                "api_key_present": config["api_key_configured"],
                "company_id_present": bool(config["company_id"]),
                "dry_run": config["dry_run"],
            },
        }

    if config["dry_run"]:
        return {
            "ok": True,
            "status": "dry_run_only",
            "error": None,
            "message": "Balance dry-run completed successfully. No live API request was sent.",
            "payload": payload,
            "target": {
                "base_url": config["base_url"],
                "company_id": config["company_id"],
                "dry_run": True,
            },
        }

    # Live HTTP request placeholder
    return {
        "ok": True,
        "status": "simulated_success",
        "error": None,
        "message": "Balance connector is ready. Replace this placeholder with a live API request when Balance access is available.",
        "payload": payload,
        "target": {
            "base_url": config["base_url"],
            "company_id": config["company_id"],
            "dry_run": False,
        },
    }