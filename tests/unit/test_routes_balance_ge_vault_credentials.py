import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.routes_balance_ge import (
    JournalPostRequest,
    post_journals,
    test_connection as balance_test_connection,
)


def _request(tenant="tenant-a"):
    return SimpleNamespace(state=SimpleNamespace(tenant_id=tenant))


def test_journal_post_request_rejects_inline_api_key():
    try:
        JournalPostRequest(draft_ids=[1], api_key="must-not-be-accepted")
    except Exception as exc:
        assert "api_key" in str(exc)
    else:
        raise AssertionError("Inline credentials must be rejected")


def test_test_connection_fails_closed_when_vault_is_unavailable():
    with patch("app.api.routes_balance_ge.require_permission"), \
         patch("app.api.routes_balance_ge.get_balance_credentials", new=AsyncMock(side_effect=RuntimeError("unavailable"))), \
         patch("app.api.routes_balance_ge.httpx.AsyncClient") as client:
        response = asyncio.run(balance_test_connection(_request()))
    assert response.status_code == 503
    client.assert_not_called()


def test_test_connection_uses_tenant_vault_credential():
    response_obj = MagicMock(status_code=200)
    response_obj.json.return_value = {"connected": True}
    client_instance = MagicMock()
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)
    client_instance.get = AsyncMock(return_value=response_obj)
    with patch("app.api.routes_balance_ge.require_permission"), \
         patch("app.api.routes_balance_ge.get_balance_credentials", new=AsyncMock(return_value={
             "api_key": "SYNTHETIC-SECRET-SENTINEL", "company_id": "vault-company",
         })) as get_credentials, \
         patch("app.api.routes_balance_ge.httpx.AsyncClient", return_value=client_instance):
        response = asyncio.run(balance_test_connection(_request("tenant-a")))
    get_credentials.assert_awaited_once_with("tenant-a")
    client_instance.get.assert_awaited_once_with(
        "https://api.balance.ge/v1/company/vault-company",
        headers={"Authorization": "Bearer SYNTHETIC-SECRET-SENTINEL"},
    )
    assert "SYNTHETIC-SECRET-SENTINEL" not in str(response)


def test_test_connection_does_not_return_provider_body():
    response_obj = MagicMock(status_code=401)
    response_obj.json.return_value = {"api_key": "SYNTHETIC-SECRET-SENTINEL"}
    client_instance = MagicMock()
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)
    client_instance.get = AsyncMock(return_value=response_obj)
    with patch("app.api.routes_balance_ge.require_permission"), \
         patch("app.api.routes_balance_ge.get_balance_credentials", new=AsyncMock(return_value={
             "api_key": "SYNTHETIC-SECRET-SENTINEL", "company_id": "vault-company",
         })), \
         patch("app.api.routes_balance_ge.httpx.AsyncClient", return_value=client_instance):
        response = asyncio.run(balance_test_connection(_request("tenant-a")))
    assert "SYNTHETIC-SECRET-SENTINEL" not in str(response)
    assert "api_key" not in str(response)


def test_journal_post_fails_before_database_or_http_when_vault_missing():
    with patch("app.api.routes_balance_ge.require_permission"), \
         patch("app.api.routes_balance_ge.get_balance_credentials", new=AsyncMock(return_value={"api_key": ""})), \
         patch("app.api.routes_balance_ge.get_conn") as get_conn, \
         patch("app.api.routes_balance_ge.httpx.AsyncClient") as client:
        response = asyncio.run(post_journals(JournalPostRequest(draft_ids=[1]), _request()))
    assert response.status_code == 503
    get_conn.assert_not_called()
    client.assert_not_called()


def test_public_credential_status_returns_unavailable_on_db_context_error():
    from app.api.routes_balance_credentials import get_status

    with patch("app.api.routes_balance_credentials.require_permission"), \
         patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
        mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("synthetic-db-error-payload"))
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        response = asyncio.run(get_status(_request("tenant-a")))

    assert response["data"]["configured"] is False
    assert response["data"]["status"] == "unavailable"
    assert response["data"]["credential_status"] == "unavailable"
    assert response["data"]["mode"] == "unavailable"
    assert "synthetic-db-error-payload" not in str(response)
    assert "api_key" not in str(response)
    assert "password" not in str(response)
    assert "token" not in str(response)


def test_public_credential_status_uses_authenticated_tenant_scope():
    from app.api.routes_balance_credentials import get_status

    result = {"configured": False, "status": "not_configured", "mode": "not_configured"}
    with patch("app.api.routes_balance_credentials.require_permission"), \
         patch("app.api.routes_balance_credentials.get_vault_status", new=AsyncMock(return_value=result)) as lookup:
        response = asyncio.run(get_status(_request("tenant-a")))

    lookup.assert_awaited_once_with("tenant-a")
    assert response["data"]["status"] == "not_configured"
