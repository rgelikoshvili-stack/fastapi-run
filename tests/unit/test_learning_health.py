import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


def test_learning_health(client):
    response = client.get("/learning/health")
    assert response.status_code == 200
