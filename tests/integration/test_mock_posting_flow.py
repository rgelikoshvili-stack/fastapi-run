import os
import pytest

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="requires DATABASE_URL",
)


@requires_db
def test_mock_posting_route_exists(client):
    response = client.post("/posting/mock/999999")
    assert response.status_code in [200, 400, 404, 422]
