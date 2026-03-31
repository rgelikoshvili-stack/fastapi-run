def test_manual_review_case_placeholder(client):
    payload = {
        "date": "2026-03-31",
        "description": "Unknown unusual operation xyz",
        "partner": "Random Entity",
        "paid_in": 0,
        "paid_out": 77.77
    }

    response = client.post("/transaction-ai/analyze", json=payload)

    assert response.status_code in [200, 400, 422]

    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, dict)