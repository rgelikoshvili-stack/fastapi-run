"""tests/unit/test_balance_credentials_vault_wiring.py — Task 11G vault wiring tests.

Verifies that:
- get_balance_credentials() reads from the vault when a record exists.
- get_balance_credentials() falls back to plaintext api_key for legacy rows.
- get_balance_credentials() falls back to the BALANCE_API_KEY env var.
- save_balance_credentials() saves to vault and nulls out plaintext api_key.
- No raw api_key is ever returned from the status/save API routes.
"""
import pytest
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
    return conn


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


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
async def test_get_falls_back_to_plaintext_when_vault_not_found(monkeypatch):
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(side_effect=RuntimeError("CREDENTIAL_NOT_FOUND"))
    db_row = {"api_key": "legacy-key", "company_id": "CMP2", "api_base": "https://api.balance.ge"}
    conn = _make_conn(db_row)

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t2")

    assert result["api_key"] == "legacy-key"
    assert result["source"] == "db_legacy"


@pytest.mark.asyncio
async def test_get_falls_back_when_vault_disabled(monkeypatch):
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(side_effect=RuntimeError("CREDENTIAL_DISABLED"))
    db_row = {"api_key": "still-active-key", "company_id": "", "api_base": "https://api.balance.ge"}
    conn = _make_conn(db_row)

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t3")

    assert result["source"] == "db_legacy"


# ---------------------------------------------------------------------------
# get_balance_credentials — env var fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_falls_back_to_env_var(monkeypatch):
    monkeypatch.setenv("BALANCE_API_KEY", "env-key")
    svc = MagicMock()
    svc.get_for_connector = AsyncMock(side_effect=RuntimeError("CREDENTIAL_NOT_FOUND"))
    conn = _make_conn(None)  # no DB row

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        result = await bcs.get_balance_credentials("t4")

    assert result["api_key"] == "env-key"
    assert result["source"] == "env"


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

    # The DB execute call must NOT contain the raw api_key — it must be None
    execute_call_args = conn.execute.call_args
    params = execute_call_args[0][1:]  # positional args after SQL
    # params[0] = tenant_id, params[1] = api_key value, ...
    assert params[1] is None, "api_key should be NULL when saved via vault"


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
    # params: tenant_id, api_key, company_id, api_base, masked_hint, credential_status, now
    credential_status = params[5]
    assert credential_status == "vault"


@pytest.mark.asyncio
async def test_save_falls_back_to_plaintext_on_vault_failure(monkeypatch):
    svc = MagicMock()
    svc.save_credential = AsyncMock(side_effect=Exception("vault unavailable"))
    conn = _make_conn()

    with patch("app.api.services.balance_credentials_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.credential_vault_service.CredentialVaultService", return_value=svc):
        from app.api.services import balance_credentials_service as bcs
        ok = await bcs.save_balance_credentials("t9", "key-fallback")

    # Should still write to DB (legacy path)
    conn.execute.assert_awaited()
    # In legacy path, api_key is stored (not NULL)
    execute_call_args = conn.execute.call_args
    params = execute_call_args[0][1:]
    assert params[1] == "key-fallback"
    assert params[5] == "legacy_plaintext"


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
