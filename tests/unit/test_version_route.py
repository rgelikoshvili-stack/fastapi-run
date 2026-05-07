from fastapi.testclient import TestClient

from main import app


def test_version_endpoint_is_public_and_reports_build_metadata(monkeypatch):
    monkeypatch.setenv("COMMIT_SHA", "abc123def456")
    monkeypatch.setenv("BUILD_TIME", "2026-05-07T12:34:56Z")
    monkeypatch.setenv("ENVIRONMENT", "production")

    client = TestClient(app)
    response = client.get("/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "Version"

    data = payload["data"]
    assert data["app"] == "Bridge Hub"
    assert data["commit_sha"] == "abc123def456"
    assert data["build_time"] == "2026-05-07T12:34:56Z"
    assert data["environment"] == "production"
