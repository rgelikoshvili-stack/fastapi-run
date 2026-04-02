def test_confidence_adjustment():
    from app.api.services.confidence_engine import adjust_confidence

    result = adjust_confidence(
        0.5,
        {"context_used": True},
        {"score": 0.6, "issues": ["x"]}
    )

    assert result < 0.5