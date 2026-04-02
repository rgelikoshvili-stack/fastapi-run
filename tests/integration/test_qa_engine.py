def test_qa_engine():
    from app.api.services.qa_engine import evaluate_decision

    result = evaluate_decision({
        "account_code": "7100",
        "confidence": 0.5
    })

    assert "score" in result