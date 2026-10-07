import pytest

from app.api import db
from app.api import routes_worker


class FakeRequest:
    def __init__(self, body, signature="synthetic-signature"):
        self._body = body
        self.headers = {"X-Worker-Signature": signature}

    async def body(self):
        return self._body


@pytest.mark.asyncio
async def test_invalid_hmac_is_rejected_before_token_or_db_access(monkeypatch):
    monkeypatch.setattr(routes_worker, "verify_worker_signature", lambda *_: False)

    def should_not_authorize(_payload):
        raise AssertionError("token authorization must follow HMAC verification")

    monkeypatch.setattr(routes_worker, "authorize_callback_payload", should_not_authorize)
    monkeypatch.setattr(
        routes_worker,
        "accept_callback_result",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("DB receipt access is forbidden")),
    )
    response = await routes_worker.worker_result(FakeRequest(b"{}"))
    assert response["error"]["code"] == "UNAUTHORIZED"
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
async def test_valid_hmac_with_invalid_token_is_rejected_before_db_access(monkeypatch):
    monkeypatch.setattr(routes_worker, "verify_worker_signature", lambda *_: True)
    monkeypatch.setattr(routes_worker, "authorize_callback_payload", lambda _payload: None)
    monkeypatch.setattr(
        routes_worker,
        "accept_callback_result",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("DB receipt access is forbidden")),
    )
    response = await routes_worker.worker_result(FakeRequest(b'{"callback_token":"invalid"}'))
    assert response["error"]["code"] == "UNAUTHORIZED"
    assert db._current_tenant_id.get() is None
