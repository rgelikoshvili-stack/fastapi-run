import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.api import db
from app.api.middleware.rbac_middleware import rbac_middleware
from app.api.services import auth_service, worker_client
from app.api.services import ocr_callback_receipts


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
        "job_id": "job-a",
    }
    claims = worker_client.authorize_callback_payload(payload)
    assert claims["tenant_id"] == "tenant-a"
    assert claims["doc_id"] == 17
    assert claims["job_id"] == "job-a"

    assert worker_client.authorize_callback_payload({**payload, "tenant_id": "tenant-b"}) is None
    assert worker_client.authorize_callback_payload({**payload, "doc_id": 18}) is None
    assert worker_client.authorize_callback_payload({**payload, "job_id": "job-b"}) is None
    assert worker_client.authorize_callback_payload({k: v for k, v in payload.items() if k != "job_id"}) is None
    assert worker_client.authorize_callback_payload({**payload, "job_type": "pdf_split"}) is None
    assert worker_client.authorize_callback_payload({"tenant_id": "tenant-b", "doc_id": 17}) is None


def test_worker_callback_token_rejects_expired_and_wrong_audience(monkeypatch):
    secret = "test-secret-key-long-enough-for-hs256"
    monkeypatch.setattr(auth_service, "_get_secret_key", lambda: secret)
    now = datetime.now(timezone.utc)
    claims = {
        "type": "worker_job",
        "purpose": "ocr_callback",
        "audience": "bridge-hub-ocr-callback",
        "job_id": "job-a",
        "tenant_id": "tenant-a",
        "doc_id": 17,
        "job_type": "ocr",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    with db.authenticated_tenant_context("tenant-a"):
        expired = jwt.encode(
            {**claims, "exp": int((now - timedelta(minutes=1)).timestamp())},
            secret,
            algorithm=auth_service.ALGORITHM,
        )
        wrong_audience = jwt.encode(
            {**claims, "audience": "other-service"},
            secret,
            algorithm=auth_service.ALGORITHM,
        )

    assert worker_client.verify_callback_token(expired) is None
    assert worker_client.verify_callback_token(wrong_audience) is None


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


@pytest.mark.asyncio
async def test_dispatch_sends_signed_callback_token_and_keeps_bridge_job_id(monkeypatch):
    monkeypatch.setattr(auth_service, "_get_secret_key", lambda: "test-secret-key-long-enough-for-hs256")
    monkeypatch.setattr(worker_client, "WORKER_URL", "https://worker.invalid")
    monkeypatch.setattr(worker_client, "WORKER_TOKEN", "test-worker-hmac-secret")
    monkeypatch.setattr(worker_client, "_WORKER_DISPATCH_ENABLED", True)
    monkeypatch.setattr(worker_client, "_OCR_CALLBACK_BASE_URL", "https://bridge.example")
    posted = {}

    async def fake_register_dispatch(*, tenant_id, doc_id, job_id):
        assert tenant_id == "tenant-a" and doc_id == 17
        return {"send": True, "job_id": job_id, "gcs_path": "gs://synthetic/document.pdf"}

    monkeypatch.setattr(ocr_callback_receipts, "register_dispatch", fake_register_dispatch)

    class Response:
        status_code = 202

        def json(self):
            # An external ID is not allowed to replace the signed Bridge Hub ID.
            return {"job_id": "worker-invented-id"}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, content, headers):
            posted.update(url=url, content=content, headers=headers)
            return Response()

    monkeypatch.setattr(worker_client.httpx, "AsyncClient", Client)
    with db.authenticated_tenant_context("tenant-a"):
        result = await worker_client.dispatch_ocr_document(17)

    payload = json.loads(posted["content"])
    claims = worker_client.verify_callback_token(payload["callback_token"])
    assert posted["url"] == "https://worker.invalid/job"
    assert worker_client.verify_worker_signature(
        posted["content"], posted["headers"]["X-Worker-Signature"]
    )
    assert claims["tenant_id"] == "tenant-a"
    assert claims["doc_id"] == 17
    assert claims["job_id"] == payload["job_id"] == result["job_id"]
    assert payload["callback_doc_id"] == 17
    assert payload["callback_url"] == "https://bridge.example/worker/result"


def test_callback_url_requires_trusted_https_outside_test_mode(monkeypatch):
    monkeypatch.delenv("TEST_MODE", raising=False)
    assert worker_client.build_callback_url("https://bridge.example/") == (
        "https://bridge.example/worker/result"
    )
    for unsafe in (
        "http://bridge.example",
        "https://user:pass@bridge.example",
        "https://bridge.example/?host=attacker",
        "https://bridge.example/attacker/path",
    ):
        with pytest.raises(ValueError):
            worker_client.build_callback_url(unsafe)


def test_callback_url_allows_only_safe_local_http_in_test_mode(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    assert worker_client.build_callback_url("http://127.0.0.1:8000") == (
        "http://127.0.0.1:8000/worker/result"
    )
    with pytest.raises(ValueError):
        worker_client.build_callback_url("http://attacker.example")
