from app.services.preview_service import build_draft_preview


def test_build_draft_preview():
    payload = {
        "description": "Office supplies",
        "partner": "Stationery Shop",
        "amount": 120,
        "account_code": "7180",
        "confidence": 0.91,
        "status": "drafted",
    }

    result = build_draft_preview(payload)
    assert "summary" in result
    assert result["summary"]["partner"] == "Stationery Shop"