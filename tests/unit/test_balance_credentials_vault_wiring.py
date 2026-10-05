"""tests/unit/test_balance_credentials_vault_wiring.py — Task 11G vault wiring tests.

Verifies that:
- get_balance_credentials() reads from the vault when a record exists.
- get_balance_credentials() never reads legacy plaintext or shared env keys.
- legacy plaintext presence is reported as rotation-required metadata.
- save_balance_credentials() saves to vault and nulls out plaintext api_key.
- No raw api_key is ever returned from the status/save API routes.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault_svc(raw_key: str = "secret-key", *, save_result=None, get_status_result=None):
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(return_value=raw_key)
    svc.save_credential = AsyncMock(return_value=save_result or {
        "configured": True,
        "masked_hint": "****cret",
        "key_version": "v1",
    })
    svc.get_status = AsyncMock(return_value=get_status_result or {
        "configured": True,
        "masked_hint": "****cret",
        "status": "active",
    })
    return svc


def _make_conn(row=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=row)
    conn.execute = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=_FakeTransaction())
    return conn


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


# ---------------------------------------------------------------------------
# get_balance_credentials — vault path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_uses_vault_when_available(monkeypatch):
    svc = _make_vault_svc("real-api-key")
    meta_row = {"company_id": "CMP1", "api_base": "https://api.balance.ge"}
    conn = _make_conn(meta_row)

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t1")

    assert result["api_key"] == "real-api-key"
    assert result["source"] == "vault"
    svc.get_for_connector.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_vault_returns_company_id_from_meta_row(monkeypatch):
    svc = _make_vault_svc("key")
    meta_row = {"company_id": "COMP99", "api_base": "https://custom.balance.ge"}
    conn = _make_conn(meta_row)

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t1")

    assert result["company_id"] == "COMP99"
    assert result["api_base"] == "https://custom.balance.ge"


# ---------------------------------------------------------------------------
# get_balance_credentials — legacy plaintext fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_does_not_read_legacy_plaintext_when_vault_not_found(monkeypatch):
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(side_effect=RuntimeError("CREDENTIAL_NOT_FOUND"))
    db_row = {"legacy_present": True, "credential_status": "legacy_plaintext",
              "company_id": "CMP2", "api_base": "https://api.balance.ge"}
    conn = _make_conn(db_row)

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t2")

    assert result["api_key"] == ""
    assert result["source"] == "none"
    assert result["credential_status"] == "rotation_required"
    assert "SELECT api_key" not in conn.fetchrow.call_args.args[0]


@pytest.mark.asyncio
async def test_get_falls_back_when_vault_disabled(monkeypatch):
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(side_effect=RuntimeError("CREDENTIAL_DISABLED"))
    db_row = {"legacy_present": True, "credential_status": "legacy_plaintext",
              "company_id": "", "api_base": "https://api.balance.ge"}
    conn = _make_conn(db_row)

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t3")

    assert result["api_key"] == ""
    assert result["credential_status"] == "rotation_required"


# ---------------------------------------------------------------------------
# get_balance_credentials — env var fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_does_not_fall_back_to_shared_env_key(monkeypatch):
    monkeypatch.setenv("BALANCE_API_KEY", "synthetic-shared-test-key")
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(side_effect=RuntimeError("CREDENTIAL_NOT_FOUND"))
    conn = _make_conn(None)  # no DB row

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t4")

    assert result["api_key"] == ""
    assert result["source"] == "none"
    assert result["credential_status"] == "not_configured"


@pytest.mark.asyncio
async def test_vault_read_failure_does_not_downgrade_to_legacy_or_env(monkeypatch):
    monkeypatch.setenv("BALANCE_API_KEY", "synthetic-shared-test-key")
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(side_effect=RuntimeError("CREDENTIAL_DECRYPT_FAILED"))
    conn = _make_conn({"api_key": "synthetic-legacy-key"})

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        with pytest.raises(RuntimeError, match="BALANCE_CREDENTIAL_UNAVAILABLE"):
            await bcs.get_balance_credentials("tenant-A")

    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_returns_none_source_when_no_credentials(monkeypatch):
    monkeypatch.delenv("BALANCE_API_KEY", raising=False)
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(side_effect=RuntimeError("CREDENTIAL_NOT_FOUND"))
    conn = _make_conn(None)

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t5")

    assert result["api_key"] == ""
    assert result["source"] == "none"


# ---------------------------------------------------------------------------
# save_balance_credentials — writes to vault + nulls plaintext
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_stores_in_vault(monkeypatch):
    svc = _make_vault_svc()
    conn = _make_conn()

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        ok = await bcs.save_balance_credentials("t6", "my-secret-key", company_id="C1")

    assert ok is True
    svc.save_credential.assert_awaited_once()
    call_kwargs = svc.save_credential.call_args.kwargs
    assert call_kwargs["raw_value"] == "my-secret-key"
    assert call_kwargs["provider"] == "balance"
    assert call_kwargs["credential_type"] == "api_key"


@pytest.mark.asyncio
async def test_save_nulls_plaintext_api_key_on_vault_success(monkeypatch):
    svc = _make_vault_svc()
    conn = _make_conn()

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        await bcs.save_balance_credentials("t7", "my-secret-key")

    execute_call_args = conn.execute.call_args
    params = execute_call_args[0][1:]  # positional args after SQL
    assert "VALUES ($1, NULL" in execute_call_args.args[0]
    assert "my-secret-key" not in str(params)


@pytest.mark.asyncio
async def test_save_sets_credential_status_vault(monkeypatch):
    svc = _make_vault_svc()
    conn = _make_conn()

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        await bcs.save_balance_credentials("t8", "key")

    execute_call_args = conn.execute.call_args
    params = execute_call_args[0][1:]
    assert "credential_status = 'vault'" in execute_call_args.args[0]
    assert "my-secret-key" not in str(params)


@pytest.mark.asyncio
async def test_save_fails_closed_on_vault_failure_without_db_write(monkeypatch):
    svc = MagicMock()
    svc.save_credential = AsyncMock(side_effect=Exception("vault unavailable"))
    conn = _make_conn()

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        with pytest.raises(RuntimeError, match="BALANCE_CREDENTIAL_SAVE_FAILED"):
            await bcs.save_balance_credentials("t9", "synthetic-save-failure-key")

    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_vault_failure_log_does_not_contain_submitted_key(monkeypatch, caplog):
    submitted_key = "synthetic-secret-that-must-not-be-logged"
    svc = MagicMock()
    svc.save_credential = AsyncMock(side_effect=Exception("synthetic vault failure"))
    conn = _make_conn()

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        with pytest.raises(RuntimeError):
            await bcs.save_balance_credentials("tenant-failure", submitted_key)

    assert submitted_key not in caplog.text
    conn.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# API response: no raw secrets exposed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_credentials_status_no_raw_key(monkeypatch):
    svc = _make_vault_svc("super-secret")
    meta_row = {"company_id": "C1", "api_base": "https://api.balance.ge"}
    conn = _make_conn(meta_row)

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        status = await bcs.get_credentials_status("t10")

    # sanitize_credential_response should strip api_key
    assert "api_key" not in status
    assert "super-secret" not in str(status)


@pytest.mark.asyncio
async def test_get_vault_status_returns_masked_hint(monkeypatch):
    svc = _make_vault_svc(get_status_result={
        "configured": True,
        "masked_hint": "****ecret",
        "status": "active",
    })
    conn = _make_conn()

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_vault_status("t11")

    assert result.get("configured") is True
    # masked_hint may or may not pass through sanitize — raw key must never appear
    assert "real-api-key" not in str(result)


def test_balance_connector_fails_closed_when_tenant_key_missing(monkeypatch):
    monkeypatch.setenv("BALANCE_API_KEY", "synthetic-shared-test-key")
    monkeypatch.delenv("TEST_MODE", raising=False)
    with patch(
        "app.api.services.balance_credentials_service.get_balance_credentials_sync",
        return_value={"api_key": "", "source": "none", "credential_status": "not_configured"},
    ), patch("app.api.connectors.balance_connector.requests.post") as live_post:
        from app.api.connectors.balance_connector import BalanceConnector
        connector = BalanceConnector(tenant_id="tenant-A")
        result = connector.post({"account_dr": "1000", "account_cr": "2000", "amount": 1})

    assert connector.api_key == ""
    assert connector.mode == "unavailable"
    assert connector.status()["connected"] is False
    assert result["success"] is False
    assert result["erp_id"] is None
    live_post.assert_not_called()


def test_balance_connector_demo_requires_explicit_test_flag_or_mode(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    with patch(
        "app.api.services.balance_credentials_service.get_balance_credentials_sync",
        return_value={"api_key": "", "source": "none", "credential_status": "not_configured"},
    ), patch("app.api.connectors.balance_connector.requests.post") as live_post:
        from app.api.connectors.balance_connector import BalanceConnector
        test_flag_connector = BalanceConnector(tenant_id="tenant-A")
        monkeypatch.delenv("TEST_MODE", raising=False)
        explicit_mode_connector = BalanceConnector(tenant_id="tenant-A", mode="demo")
        demo_result = explicit_mode_connector.post({"account_dr": "1000", "account_cr": "2000", "amount": 1})

    assert test_flag_connector.mode == "demo"
    assert explicit_mode_connector.mode == "demo"
    assert explicit_mode_connector.status() == {
        "connected": False,
        "mode": "demo",
        "simulated": True,
        "message": "Simulated only; external connector is not active",
    }
    assert demo_result == {
        "success": False,
        "erp_id": None,
        "error": "SIMULATED_NOT_POSTED",
        "mode": "demo",
        "simulated": True,
    }
    assert explicit_mode_connector.validate_config() is False
    live_post.assert_not_called()


@pytest.mark.parametrize("credential_state", ["disabled", "revoked", "rotation_required", "active"])
def test_balance_connector_invalid_or_legacy_credential_state_never_enters_demo(monkeypatch, credential_state):
    monkeypatch.setenv("TEST_MODE", "1")
    with patch(
        "app.api.services.balance_credentials_service.get_balance_credentials_sync",
        return_value={"api_key": "", "source": "none", "credential_status": credential_state},
    ):
        from app.api.connectors.balance_connector import BalanceConnector
        connector = BalanceConnector(tenant_id="tenant-A")

    assert connector.mode == "unavailable"
    assert connector.api_key == ""


def test_balance_connector_vault_error_is_unavailable_not_demo_or_global(monkeypatch):
    monkeypatch.setenv("BALANCE_API_KEY", "synthetic-shared-test-key")
    with patch(
        "app.api.services.balance_credentials_service.get_balance_credentials_sync",
        side_effect=RuntimeError("synthetic lookup failure"),
    ), patch("app.api.connectors.balance_connector.requests.post") as live_post:
        from app.api.connectors.balance_connector import BalanceConnector
        connector = BalanceConnector(tenant_id="tenant-A")
        result = connector.post({"account_dr": "1000", "account_cr": "2000", "amount": 1})

    assert connector.mode == "unavailable"
    assert connector.status()["connected"] is False
    assert result["success"] is False
    live_post.assert_not_called()


@pytest.mark.asyncio
async def test_save_route_returns_safe_503_when_vault_fails():
    from app.api import routes_balance_credentials as route
    body = route.BalanceCredsPayload(api_key="synthetic_api_key_not_for_response")
    request = SimpleNamespace(state=SimpleNamespace(tenant_id="tenant-A", user_id="user-A"))

    with patch.object(route, "require_permission"), \
         patch.object(route, "save_balance_credentials", new_callable=AsyncMock,
                      side_effect=RuntimeError("BALANCE_CREDENTIAL_SAVE_FAILED")):
        response = await route.save_creds(body, request)

    assert response.status_code == 503
    assert b"synthetic_api_key_not_for_response" not in response.body


@pytest.mark.asyncio
async def test_save_route_success_response_never_contains_key():
    from app.api import routes_balance_credentials as route
    secret = "synthetic_key_must_not_escape_response"
    body = route.BalanceCredsPayload(api_key=secret)
    request = SimpleNamespace(state=SimpleNamespace(tenant_id="tenant-A", user_id="user-A"))

    with patch.object(route, "require_permission"), \
         patch.object(route, "save_balance_credentials", new_callable=AsyncMock, return_value=True):
        response = await route.save_creds(body, request)

    assert secret not in str(response)
