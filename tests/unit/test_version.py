def test_health_ping(client):
    response = client.get("/health/ping")
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert "pong" in data.get("data", data)
