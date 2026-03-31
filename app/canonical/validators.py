def require_keys(data: dict, keys: list[str]) -> list[str]:
    missing = []
    for key in keys:
        if key not in data or data.get(key) in (None, ""):
            missing.append(key)
    return missing


def validate_transaction_payload(data: dict) -> dict:
    required = ["date", "description", "partner"]
    missing = require_keys(data, required)

    return {
        "ok": len(missing) == 0,
        "missing": missing,
    }