def test_posting_logs_endpoint(client):
    response = client.get("/posting/logs")
    assert response.status_code in [200, 400, 422]

    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, dict)