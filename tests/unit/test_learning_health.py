def test_learning_health(client):
    response = client.get("/learning/health")
    assert response.status_code == 200