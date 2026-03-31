def test_version(client):
    response = client.get("/version")
    assert response.status_code == 200