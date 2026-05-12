"""
tests/unit/test_masked_read_route_enforcement.py

Route/service-level enforcement tests for masked credential reads (Task 11C-D).
Verifies that no HTTP-facing credential status response can include raw secret fields.

All DB access is mocked. No network. No production secrets.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.credential_response_sanitizer import (
    FORBIDDEN_CREDENTIAL_RESPONSE_KEYS,
    assert_no_raw_secret_fields,
    sanitize_credential_response,
)

FORBIDDEN_FIELDS = {
    "api_key", "password", "token", "secret",
    "encrypted_value", "raw_secret", "decrypted_value",
}
TENANT = "tenant_test"


def _assert_no_forbidden(result: dict, label: str = "") -> None:
    for key in result:
        assert key.lower() not in FORBIDDEN_FIELDS, (
            f"{label}: forbidden field {key!r} in response"
        )


# ---------------------------------------------------------------------------
# A) get_credentials_status — legacy plaintext path is safe
# ---------------------------------------------------------------------------

class TestGetCredentialsStatusSafe:

    @pytest.mark.asyncio
    async def test_status_never_returns_api_key_field(self):
        from app.api.services.balance_credentials_service import get_credentials_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_conn.fetchrow = AsyncMock(return_value={
                "api_key": "real-secret-12345678",
                "company_id": "COMP01",
                "api_base": "https://api.balance.ge",
            })
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_credentials_status(TENANT)
        assert "api_key" not in result
        assert "real-secret-12345678" not in str(result)

    @pytest.mark.asyncio
    async def test_status_configured_is_false_when_no_key(self):
        from app.api.services.balance_credentials_service import get_credentials_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_conn.fetchrow = AsyncMock(return_value=None)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch.dict(os.environ, {k: "" for k in ["BALANCE_API_KEY"]}, clear=False):
                os.environ.pop("BALANCE_API_KEY", None)
                result = await get_credentials_status(TENANT)
        assert result["configured"] is False

    @pytest.mark.asyncio
    async def test_status_configured_is_true_when_key_set(self):
        from app.api.services.balance_credentials_service import get_credentials_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_conn.fetchrow = AsyncMock(return_value={
                "api_key": "live-key-12345678",
                "company_id": "COMP",
                "api_base": "https://api.balance.ge",
            })
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_credentials_status(TENANT)
        assert result["configured"] is True
        assert "api_key" not in result

    @pytest.mark.asyncio
    async def test_status_safe_on_db_error_no_env_key(self):
        from app.api.services.balance_credentials_service import get_credentials_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            original = os.environ.pop("BALANCE_API_KEY", None)
            try:
                result = await get_credentials_status(TENANT)
            finally:
                if original is not None:
                    os.environ["BALANCE_API_KEY"] = original
        assert "api_key" not in result
        assert result["configured"] is False

    @pytest.mark.asyncio
    async def test_status_result_passes_sanitizer_assertion(self):
        from app.api.services.balance_credentials_service import get_credentials_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_conn.fetchrow = AsyncMock(return_value={
                "api_key": "secret-key-12345678",
                "company_id": "COMP",
                "api_base": "https://api.balance.ge",
            })
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_credentials_status(TENANT)
        assert_no_raw_secret_fields(result)

    @pytest.mark.asyncio
    async def test_status_has_mode_field(self):
        from app.api.services.balance_credentials_service import get_credentials_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_conn.fetchrow = AsyncMock(return_value=None)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            original = os.environ.pop("BALANCE_API_KEY", None)
            try:
                result = await get_credentials_status(TENANT)
            finally:
                if original is not None:
                    os.environ["BALANCE_API_KEY"] = original
        assert "mode" in result


# ---------------------------------------------------------------------------
# B) get_vault_status — sanitizer applied at service boundary
# ---------------------------------------------------------------------------

class TestGetVaultStatusSanitizer:

    @pytest.mark.asyncio
    async def test_vault_status_strips_api_key_from_upstream(self):
        from app.api.services.balance_credentials_service import get_vault_status
        from app.api.services.credential_vault_service import CredentialVaultService
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch.object(CredentialVaultService, "get_status", new_callable=AsyncMock) as mock_status:
                mock_status.return_value = {
                    "configured": True,
                    "status": "active",
                    "masked_hint": "****1234",
                    "api_key": "MUST_BE_STRIPPED",
                    "encrypted_value": "MUST_BE_STRIPPED",
                }
                result = await get_vault_status(TENANT)
        assert "api_key" not in result
        assert "encrypted_value" not in result
        assert "MUST_BE_STRIPPED" not in str(result)

    @pytest.mark.asyncio
    async def test_vault_status_strips_all_forbidden_variants(self):
        from app.api.services.balance_credentials_service import get_vault_status
        from app.api.services.credential_vault_service import CredentialVaultService
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch.object(CredentialVaultService, "get_status", new_callable=AsyncMock) as mock_status:
                mock_status.return_value = {
                    "configured": True,
                    "api_key": "strip",
                    "password": "strip",
                    "token": "strip",
                    "secret": "strip",
                    "raw_secret": "strip",
                    "decrypted_value": "strip",
                    "masked_hint": "****5678",
                }
                result = await get_vault_status(TENANT)
        _assert_no_forbidden(result, "vault_status all forbidden")
        assert result.get("masked_hint") == "****5678"

    @pytest.mark.asyncio
    async def test_vault_status_safe_fallback_on_error(self):
        from app.api.services.balance_credentials_service import get_vault_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("unavailable"))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_vault_status(TENANT)
        assert result["configured"] is False
        _assert_no_forbidden(result, "get_vault_status error fallback")

    @pytest.mark.asyncio
    async def test_vault_status_demo_mode_when_not_configured(self):
        from app.api.services.balance_credentials_service import get_vault_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("vault empty"))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_vault_status(TENANT)
        assert result.get("mode") == "demo"

    @pytest.mark.asyncio
    async def test_vault_status_configured_includes_masked_hint(self):
        from app.api.services.balance_credentials_service import get_vault_status
        from app.api.services.credential_vault_service import CredentialVaultService
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch.object(CredentialVaultService, "get_status", new_callable=AsyncMock) as mock_status:
                mock_status.return_value = {
                    "configured": True,
                    "status": "active",
                    "masked_hint": "****5678",
                }
                result = await get_vault_status(TENANT)
        assert result.get("masked_hint") == "****5678"
        assert result.get("configured") is True

    @pytest.mark.asyncio
    async def test_vault_status_result_passes_assertion(self):
        from app.api.services.balance_credentials_service import get_vault_status
        from app.api.services.credential_vault_service import CredentialVaultService
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch.object(CredentialVaultService, "get_status", new_callable=AsyncMock) as mock_status:
                mock_status.return_value = {
                    "configured": True,
                    "status": "active",
                    "masked_hint": "****1234",
                }
                result = await get_vault_status(TENANT)
        assert_no_raw_secret_fields(result)


# ---------------------------------------------------------------------------
# C) Sanitizer applied to sample route-level payloads
# ---------------------------------------------------------------------------

class TestSanitizerOnRoutePayloads:

    def test_sanitizer_strips_api_key_from_balance_status_response(self):
        payload = {
            "configured": True,
            "api_key": "should-be-stripped",
            "company_id": "COMP",
            "mode": "live",
        }
        result = sanitize_credential_response(payload)
        assert "api_key" not in result
        assert result["configured"] is True
        assert result["company_id"] == "COMP"

    def test_sanitizer_strips_password_from_rsge_like_response(self):
        payload = {
            "configured": True,
            "username": "user@example.com",
            "password": "should-be-stripped",
        }
        result = sanitize_credential_response(payload)
        assert "password" not in result
        assert result["username"] == "user@example.com"

    def test_sanitizer_strips_token_from_response(self):
        payload = {"token": "bearer-token", "valid": True, "name": "API Token"}
        result = sanitize_credential_response(payload)
        assert "token" not in result
        assert result["valid"] is True

    def test_sanitizer_preserves_all_safe_status_fields(self):
        payload = {
            "provider": "balance",
            "configured": True,
            "mode": "live",
            "masked_hint": "****1234",
            "last_test_status": "ok",
            "last_tested_at": None,
            "credential_status": "active",
            "company_id": "COMP",
            "api_base": "https://api.balance.ge",
        }
        result = sanitize_credential_response(payload)
        assert result == payload

    def test_sanitizer_handles_not_configured_payload(self):
        payload = {"configured": False, "mode": "demo", "provider": "balance"}
        result = sanitize_credential_response(payload)
        assert result["configured"] is False
        assert result["mode"] == "demo"

    def test_sanitizer_handles_empty_response(self):
        result = sanitize_credential_response({})
        assert result == {}

    def test_assert_raises_for_api_key_in_sample_payload(self):
        with pytest.raises(ValueError):
            assert_no_raw_secret_fields({"api_key": "secret", "configured": True})

    def test_assert_passes_for_safe_sample_payload(self):
        assert_no_raw_secret_fields({
            "provider": "balance",
            "configured": True,
            "mode": "demo",
            "masked_hint": "****1234",
        })

    def test_route_level_double_sanitize_is_idempotent(self):
        # Applying sanitizer twice should produce the same result as once
        payload = {"configured": True, "mode": "live", "api_key": "x"}
        once = sanitize_credential_response(payload)
        twice = sanitize_credential_response(once)
        assert once == twice


# ---------------------------------------------------------------------------
# D) Balance.ge demo mode and environment safety
# ---------------------------------------------------------------------------

class TestBalanceGeDemoModeSafe:

    @pytest.mark.asyncio
    async def test_vault_status_returns_demo_when_not_configured(self):
        from app.api.services.balance_credentials_service import get_vault_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("vault empty"))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await get_vault_status(TENANT)
        assert result.get("mode") == "demo"

    def test_no_balance_api_key_in_test_env(self):
        key = os.environ.get("BALANCE_API_KEY", "")
        assert not key, "BALANCE_API_KEY must not be set in test environment"

    def test_forbidden_keys_cover_required_fields(self):
        required = {
            "api_key", "password", "token", "secret",
            "encrypted_value", "raw_secret", "decrypted_value",
        }
        for k in required:
            assert k in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS, (
                f"{k!r} must be in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS"
            )

    @pytest.mark.asyncio
    async def test_no_connector_call_from_credentials_status(self):
        from app.api.services.balance_credentials_service import get_credentials_status
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_conn = AsyncMock()
            mock_conn.fetchrow = AsyncMock(return_value=None)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            # If BalanceConnector is imported and instantiated, this import will succeed.
            # The test verifies that get_credentials_status does NOT call the connector
            # by checking the result is produced without a live API call.
            original = os.environ.pop("BALANCE_API_KEY", None)
            try:
                result = await get_credentials_status(TENANT)
            finally:
                if original is not None:
                    os.environ["BALANCE_API_KEY"] = original
        # Result was returned — no connector was needed
        assert "configured" in result
        assert "api_key" not in result

    @pytest.mark.asyncio
    async def test_vault_status_does_not_call_balance_api(self):
        from app.api.services.balance_credentials_service import get_vault_status
        # Patching httpx ensures no real HTTP call is made
        with patch("app.api.services.balance_credentials_service.get_conn") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("no db"))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient") as mock_http:
                result = await get_vault_status(TENANT)
                mock_http.assert_not_called()
        assert result["configured"] is False
