import pytest

from app.api import db
from app.api.middleware.rbac_middleware import rbac_middleware
from app.api.services import auth_service, worker_client


def test_worker_callback_token_requires_an_active_tenant():
    with pytest.raises(ValueError, match="tenant DB context"):
        worker_client.create_callback_token(
            tenant_id="tenant-a", doc_id=17, job_type="ocr"
        )


def test_worker_callback_token_is_server_signed_and_binds_job(monkeypatch):
    monkeypatch.setattr(auth_service, "_get_secret_key", lambda: "test-secret-key-long-enough-for-hs256")
    with db.authenticated_tenant_context("tenant-a"):
        token = worker_client.create_callback_token(
            tenant_id="tenant-a", doc_id=17, job_type="ocr", job_id="job-a"
        )

    payload = {
        "callback_token": token,
        "tenant_id": "tenant-a",
        "doc_id": 17,
        "job_type": "ocr",
    }
    claims = worker_client.authorize_callback_payload(payload)
    assert claims["tenant_id"] == "tenant-a"
    assert claims["doc_id"] == 17
    assert claims["job_id"] == "job-a"

    assert worker_client.authorize_callback_payload({**payload, "tenant_id": "tenant-b"}) is None
    assert worker_client.authorize_callback_payload({**payload, "doc_id": 18}) is None
    assert worker_client.authorize_callback_payload({"tenant_id": "tenant-b", "doc_id": 17}) is None


@pytest.mark.asyncio
async def test_only_exact_worker_callback_path_reaches_dual_auth_handler():
    request = type("Request", (), {
        "url": type("URL", (), {"path": "/worker/result"})(),
        "method": "POST",
        "state": type("State", (), {"authenticated": False})(),
    })()
    reached = False

    async def call_next(_request):
        nonlocal reached
        reached = True
        return "handler-validates-hmac-and-server-job-token"

    assert await rbac_middleware(request, call_next) == (
        "handler-validates-hmac-and-server-job-token"
    )
    assert reached

    request.url.path = "/worker/other"
    reached = False
    response = await rbac_middleware(request, call_next)
    assert not reached
    assert response.status_code == 401
