def test_tenant_middleware():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)

    response = client.get("/health", headers={"X-Tenant-ID": "test"})

    assert response.status_code == 200