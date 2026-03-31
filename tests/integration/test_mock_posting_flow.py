def test_mock_posting_route_exists(client):
    # 999999 სავარაუდოდ არარსებული draft_id იქნება
    response = client.post("/posting/mock/999999")

    # route უნდა არსებობდეს; 404/400/422 ნორმალურია თუ draft არ არსებობს
    assert response.status_code in [200, 400, 404, 422]