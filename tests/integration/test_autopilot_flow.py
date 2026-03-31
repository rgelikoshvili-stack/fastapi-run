def test_autopilot_endpoint_available(client):
    response = client.post("/approval/autopilot")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)
    assert "ok" in data