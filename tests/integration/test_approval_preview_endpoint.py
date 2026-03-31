def test_approval_preview_endpoint(client):
    payload = {
        "description": "Office supplies",
        "partner": "Stationery Shop",
        "amount": 120,
        "account_code": "7180",
        "confidence": 0.91,
        "status": "drafted",
    }

    response = client.post("/approval/preview", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["ok"] is True
    assert "summary" in data["data"]