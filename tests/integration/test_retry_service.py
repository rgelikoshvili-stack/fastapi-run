def test_retry_service_success_after_retry():
    from app.api.services.retry_service import run_with_retry

    state = {"count": 0}

    def flaky():
        state["count"] += 1
        if state["count"] < 2:
            return {"ok": False, "error": "NETWORK_ERROR"}
        return {"ok": True, "data": "done"}

    result = run_with_retry(flaky, max_attempts=3, delay_seconds=0)

    assert result["ok"] is True
    assert result["retry_applied"] is True
    assert result["attempts_used"] == 2


def test_retry_service_no_retry_on_validation_error():
    from app.api.services.retry_service import run_with_retry

    def bad_request():
        return {"ok": False, "error": "VALIDATION_ERROR"}

    result = run_with_retry(bad_request, max_attempts=3, delay_seconds=0)

    assert result["ok"] is False
    assert result["attempts_used"] == 1