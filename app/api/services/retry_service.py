import time
from typing import Callable, Any


RETRYABLE_ERROR_TYPES = {
    "NETWORK_ERROR",
    "TIMEOUT_ERROR",
    "TEMPORARY_UNAVAILABLE",
    "RATE_LIMIT",
}


def is_retryable_error(error_code: str | None) -> bool:
    return (error_code or "").strip().upper() in RETRYABLE_ERROR_TYPES


def run_with_retry(
    operation: Callable[[], dict],
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
) -> dict:
    attempt = 0
    current_delay = delay_seconds
    last_result: dict[str, Any] | None = None

    while attempt < max_attempts:
        attempt += 1

        try:
            result = operation()
        except Exception as e:
            result = {
                "ok": False,
                "error": "NETWORK_ERROR",
                "details": str(e),
            }

        last_result = result

        if result.get("ok"):
            result["attempts_used"] = attempt
            result["retry_applied"] = attempt > 1
            return result

        error_code = result.get("error")
        if attempt >= max_attempts or not is_retryable_error(error_code):
            result["attempts_used"] = attempt
            result["retry_applied"] = attempt > 1
            return result

        time.sleep(current_delay)
        current_delay *= backoff_multiplier

    return {
        "ok": False,
        "error": "RETRY_EXHAUSTED",
        "details": last_result,
        "attempts_used": attempt,
        "retry_applied": attempt > 1,
    }