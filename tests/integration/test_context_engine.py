import pytest


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="requires DATABASE_URL",
)
def test_context_engine():
    from app.api.services.context_engine import build_context

    result = build_context({
        "description": "office supplies",
        "partner": "ABC"
    })

    assert "context_used" in result
