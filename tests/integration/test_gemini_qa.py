def test_gemini_qa():
    from app.api.services.qa_engine import evaluate_decision

    result = evaluate_decision({
        "confidence": 0.5
    })

    assert "gemini_review" in result