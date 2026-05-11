"""
tests/unit/test_masked_read_runtime.py

Runtime safety tests for masked credential status behavior (Task 11C-C4).
Verifies that no secret fields are returned from status/vault paths.
All DB access is mocked. No network. No production secrets.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.credential_vault_service import CredentialVaultService
from app.api.services.secret_crypto_provider import SecretCryptoProvider

TENANT = "tenant_test"
PROVIDER = "balance"
CTYPE = "api_key"
FORBIDDEN_FIELDS = {"api_key", "password", "token", "secret", "encrypted_value", "raw_secret"}


def _assert_no_secret_in(result: dict, label: str = ""):
    for key in result:
        assert key.lower() not in FORBIDDEN_FIELDS, f"{label}: forbidden field {key!r} in response"
    for val in result.values():
        if isinstance(val, str):
            assert "test-secret" not in val.lower()
            assert "raw_secret" not in val.lower()


# ---------------------------------------------------------------------------
# A) get_status — safe output
# ---------------------------------------------------------------------------

class TestGetStatusSafeOutput:

    @pytest.mark.asyncio
    async def test_status_with_vault_record_has_no_forbidden_fields(self):
        crypto = SecretCryptoProvider()
        svc = CredentialVaultService(crypto=crypto)
        conn = MagicMock()
        svc._repo.get_active_credential = AsyncMock(return_value={
            "status": "active",
            "masked_hint": "****5678",
            "key_version": "test-v1",
            "company_id": "COMP01",
            "api_base": "https://api.balance.ge",
            "last_test_status": "ok",
            "last_tested_at": None,
        })

        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        _assert_no_secret_in(result, "get_status with record")

    @pytest.mark.asyncio
    async def test_status_without_vault_record_has_no_forbidden_fields(self):
        svc = CredentialVaultService()
        conn = MagicMock()
        svc._repo.get_active_credential = AsyncMock(return_value=None)

        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        _assert_no_secret_in(result, "get_status no record")
        assert result["configured"] is False

    @pytest.mark.asyncio
    async def test_status_on_db_error_has_no_forbidden_fields(self):
        svc = CredentialVaultService()
        conn = MagicMock()
        svc._repo.get_active_credential = AsyncMock(side_effect=Exception("DB error"))

        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        _assert_no_secret_in(result, "get_status DB error")
        assert result["configured"] is False

    @pytest.mark.asyncio
    async def test_status_configured_field_present(self):
        svc = CredentialVaultService()
        conn = MagicMock()
        svc._repo.get_active_credential = AsyncMock(return_value={
            "status": "active", "masked_hint": "****abcd",
            "key_version": "test-v1", "company_id": None,
            "api_base": None, "last_test_status": None, "last_tested_at": None,
        })

        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        assert "configured" in result

    @pytest.mark.asyncio
    async def test_status_masked_hint_does_not_equal_raw_secret(self):
        crypto = SecretCryptoProvider()
        raw = "super-secret-key-1234"
        payload = crypto.encrypt_secret(raw)
        svc = CredentialVaultService(crypto=crypto)
        conn = MagicMock()
        svc._repo.get_active_credential = AsyncMock(return_value={
            "status": "active",
            "masked_hint": payload["masked_hint"],
            "key_version": payload["key_version"],
            "company_id": None, "api_base": None,
            "last_test_status": None, "last_tested_at": None,
        })

        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        assert result.get("masked_hint") != raw
        assert raw not in str(result)


# ---------------------------------------------------------------------------
# B) get_vault_status — safe fallback in balance_credentials_service
# ---------------------------------------------------------------------------

class TestGetVaultStatusSafe:

    @pytest.mark.asyncio
    async def test_vault_status_no_forbidden_fields_when_configured(self):
        mock_status = {
            "configured": True,
            "status": "active",
            "masked_hint": "****1234",
            "provider": "balance",
            "credential_type": "api_key",
            "last_test_status": "ok",
            "last_tested_at": None,
            "company_id": "COMP",
            "api_base": "https://api.balance.ge",
        }

        with patch("app.api.services.balance_credentials_service.get_conn") as mock_conn_ctx:
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(CredentialVaultService, "get_status", new_callable=AsyncMock) as mock_get_status:
                mock_get_status.return_value = mock_status

                from app.api.services.balance_credentials_service import get_vault_status
                result = await get_vault_status(TENANT)

        _assert_no_secret_in(result, "get_vault_status configured")
        assert result["configured"] is True

    @pytest.mark.asyncio
    async def test_vault_status_no_forbidden_fields_when_not_configured(self):
        mock_status = {
            "configured": False,
            "status": "not_configured",
            "provider": "balance",
            "credential_type": "api_key",
            "masked_hint": None,
            "last_test_status": None,
            "last_tested_at": None,
        }

        with patch("app.api.services.balance_credentials_service.get_conn") as mock_conn_ctx:
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(CredentialVaultService, "get_status", new_callable=AsyncMock) as mock_get_status:
                mock_get_status.return_value = mock_status

                from app.api.services.balance_credentials_service import get_vault_status
                result = await get_vault_status(TENANT)

        _assert_no_secret_in(result, "get_vault_status not_configured")
        assert result["configured"] is False

    @pytest.mark.asyncio
    async def test_vault_status_safe_on_vault_error(self):
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_conn_ctx:
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("Vault unavailable"))
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.api.services.balance_credentials_service import get_vault_status
            result = await get_vault_status(TENANT)

        _assert_no_secret_in(result, "get_vault_status error fallback")
        assert result["configured"] is False

    @pytest.mark.asyncio
    async def test_vault_status_filters_forbidden_fields_from_upstream(self):
        # Even if vault service somehow returned a forbidden field, the
        # safety filter in get_vault_status must strip it.
        mock_status = {
            "configured": True,
            "status": "active",
            "masked_hint": "****1234",
            "api_key": "SHOULD_BE_FILTERED",  # forbidden — must be stripped
            "encrypted_value": "SHOULD_BE_FILTERED",
        }

        with patch("app.api.services.balance_credentials_service.get_conn") as mock_conn_ctx:
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(CredentialVaultService, "get_status", new_callable=AsyncMock) as mock_get_status:
                mock_get_status.return_value = mock_status

                from app.api.services.balance_credentials_service import get_vault_status
                result = await get_vault_status(TENANT)

        assert "api_key" not in result
        assert "encrypted_value" not in result
        assert "SHOULD_BE_FILTERED" not in str(result)

    @pytest.mark.asyncio
    async def test_vault_status_mode_is_demo_when_not_configured(self):
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_conn_ctx:
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("unavailable"))
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.api.services.balance_credentials_service import get_vault_status
            result = await get_vault_status(TENANT)

        assert result.get("mode") == "demo"


# ---------------------------------------------------------------------------
# C) Connector safety — Balance.ge remains demo
# ---------------------------------------------------------------------------

class TestBalanceGeDemoSafety:

    @pytest.mark.asyncio
    async def test_get_for_connector_not_found_raises_not_found(self):
        svc = CredentialVaultService()
        conn = MagicMock()
        svc._repo.get_encrypted_credential = AsyncMock(return_value=None)
        svc._repo.insert_audit_event = AsyncMock()

        with pytest.raises(RuntimeError, match="CREDENTIAL_NOT_FOUND"):
            await svc.get_for_connector(conn, tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE)

    @pytest.mark.asyncio
    async def test_get_for_connector_disabled_raises_not_calls_balance(self):
        crypto = SecretCryptoProvider()
        payload = crypto.encrypt_secret("secret-12345678")
        svc = CredentialVaultService(crypto=crypto)
        conn = MagicMock()
        svc._repo.get_encrypted_credential = AsyncMock(return_value={
            "encrypted_value": payload["encrypted_value"],
            "key_version": payload["key_version"],
            "status": "disabled",
            "active": False,
        })
        svc._repo.insert_audit_event = AsyncMock()

        with pytest.raises(RuntimeError, match="CREDENTIAL_DISABLED"):
            await svc.get_for_connector(conn, tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE)

    def test_no_balance_api_key_in_env(self):
        balance_key = os.environ.get("BALANCE_API_KEY", "")
        assert not balance_key, "BALANCE_API_KEY must not be set in test environment"
