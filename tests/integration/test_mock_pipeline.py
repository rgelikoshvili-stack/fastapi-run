import os
import pytest

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="requires DATABASE_URL",
)


@requires_db
def test_mock_pipeline_core_endpoints(client):
    health = client.get("/health")
    approval = client.get("/approval/queue")
    learning = client.get("/learning/health")
    version = client.get("/version")

    assert health.status_code == 200
    assert approval.status_code == 200
    assert learning.status_code == 200
    assert version.status_code == 200
