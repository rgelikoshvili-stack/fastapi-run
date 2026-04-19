import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


def test_approval_queue(client):
    response = client.get("/approval/queue")
    assert response.status_code == 200
