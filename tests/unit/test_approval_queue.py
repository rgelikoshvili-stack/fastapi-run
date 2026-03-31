def test_approval_queue(client):
    response = client.get("/approval/queue")
    assert response.status_code == 200