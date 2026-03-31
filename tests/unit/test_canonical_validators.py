from app.canonical.validators import validate_transaction_payload


def test_validate_transaction_payload_ok():
    payload = {
        "date": "2026-03-31",
        "description": "Salary payment",
        "partner": "My Company"
    }

    result = validate_transaction_payload(payload)
    assert result["ok"] is True
    assert result["missing"] == []


def test_validate_transaction_payload_missing():
    payload = {
        "date": "2026-03-31",
        "description": ""
    }

    result = validate_transaction_payload(payload)
    assert result["ok"] is False
    assert "description" in result["missing"] or "partner" in result["missing"]