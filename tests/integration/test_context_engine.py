import pytest


@pytest.mark.skipif(
    not __import__("os").environ.get("DATABASE_URL")
    or __import__("os").environ.get("TEST_MODE") == "1",
    reason="requires DATABASE_URL and no TEST_MODE",
)
def test_context_engine():
    from app.api.services.context_engine import build_context

    result = build_context({
        "description": "office supplies",
        "partner": "ABC"
    })

    assert "context_used" in result
