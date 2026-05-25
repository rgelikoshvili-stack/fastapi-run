"""tests/unit/test_credential_vault_routes.py

Unit tests for /vault/credentials/* API endpoints (Task 11C).
Contract:
  - GET /status returns masked_hint only — never raw secret
  - POST (save) returns masked_hint + configured=True — never raw secret
  - POST /rotate returns new masked_hint — never raw secret
  - DELETE disables credential
  - Raw secret never appears in any response body
  - Permission map includes /vault/credentials with tenants:manage
No real DB connections — CredentialVaultService is mocked throughout.
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TEST_MODE", "1")
os.environ.setdefault("JWT_SECRET", "test-secret-for-vault-tests-32chars!")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _fake_get_conn():
    yield MagicMock()


def _mock_vault_service(
    status_return=None,
    save_return=None,
    rotate_return=None,
    disable_return=None,
):
    svc = MagicMock()
    svc.get_status = AsyncMock(return_value=status_return or {
        "configured": True,
        "status": "active",
        "masked_hint": "****5678",
        "provider": "balance",
        "credential_type": "api_key",
    })
    svc.save_credential = AsyncMock(return_value=save_return or {
        "configured": True,
        "masked_hint": "****9999",
        "key_version": "test-v1",
        "status": "active",
    })
    svc.rotate_credential = AsyncMock(return_value=rotate_return or {
        "configured": True,
        "masked_hint": "****0001",
        "key_version": "test-v1",
        "rotated": True,
    })
    svc.disable_credential = AsyncMock(return_value=disable_return or {"disabled": True})
    return svc


class _FakeState:
    tenant_id = "tenant_test"
    user_id = "admin_1"


class _FakeRequest:
    state = _FakeState()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

class TestVaultStatusEndpoint:

    def test_status_returns_masked_hint_only(self):
        """GET /status response must contain masked_hint."""
        mock_svc = _mock_vault_service()
        from app.api.routes_credential_vault import get_credential_status
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(get_credential_status("balance", "api_key", _FakeRequest()))
        assert result["ok"] is True
        assert "****" in str(result["data"].get("masked_hint", ""))

    def test_status_no_raw_secret_in_response(self):
        """Response must never contain the raw api_key value."""
        raw_secret = "VERY_SECRET_API_KEY_ABCD1234"
        mock_svc = _mock_vault_service(status_return={
            "configured": True,
            "status": "active",
            "masked_hint": "****1234",
        })
        from app.api.routes_credential_vault import get_credential_status
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(get_credential_status("balance", "api_key", _FakeRequest()))
        assert raw_secret not in json.dumps(result)

    def test_status_not_configured_returns_safe_dict(self):
        """Not-configured credential returns configured=False safely."""
        mock_svc = _mock_vault_service(status_return={
            "configured": False,
            "status": "not_configured",
            "masked_hint": None,
        })
        from app.api.routes_credential_vault import get_credential_status
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(get_credential_status("balance", "api_key", _FakeRequest()))
        assert result["ok"] is True
        assert result["data"]["configured"] is False

    def test_status_response_no_encrypted_value(self):
        """Status response must never expose encrypted_value field."""
        mock_svc = _mock_vault_service(status_return={
            "configured": True,
            "masked_hint": "****abcd",
            "status": "active",
        })
        from app.api.routes_credential_vault import get_credential_status
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(get_credential_status("balance", "api_key", _FakeRequest()))
        assert "encrypted_value" not in json.dumps(result)


# ---------------------------------------------------------------------------
# POST /save
# ---------------------------------------------------------------------------

class TestVaultSaveEndpoint:

    def test_save_returns_masked_hint_not_raw(self):
        """POST save — response contains masked_hint, never raw secret."""
        raw_secret = "SK_LIVE_SECRET_BALANCE_KEY_ABCDE"
        mock_svc = _mock_vault_service(save_return={
            "configured": True,
            "masked_hint": "****BCDE",
            "key_version": "test-v1",
            "status": "active",
        })
        from app.api.routes_credential_vault import save_credential, SaveCredentialPayload
        body = SaveCredentialPayload(raw_value=raw_secret)
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(save_credential("balance", "api_key", body, _FakeRequest()))
        assert raw_secret not in json.dumps(result)
        assert "****BCDE" in json.dumps(result)

    def test_save_empty_raw_value_returns_error(self):
        """Empty raw_value must return error response."""
        from app.api.routes_credential_vault import save_credential, SaveCredentialPayload
        body = SaveCredentialPayload(raw_value="")
        with patch("app.api.routes_credential_vault.require_permission"):
            result = _run(save_credential("balance", "api_key", body, _FakeRequest()))
        assert result["ok"] is False

    def test_save_configured_true_in_response(self):
        """Successful save returns configured=True."""
        mock_svc = _mock_vault_service()
        from app.api.routes_credential_vault import save_credential, SaveCredentialPayload
        body = SaveCredentialPayload(raw_value="sk_live_test_key_12345678")
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(save_credential("balance", "api_key", body, _FakeRequest()))
        assert result["ok"] is True
        assert result["data"]["configured"] is True

    def test_save_no_encrypted_value_in_response(self):
        """Save response must never include encrypted_value field."""
        mock_svc = _mock_vault_service()
        from app.api.routes_credential_vault import save_credential, SaveCredentialPayload
        body = SaveCredentialPayload(raw_value="secret_key_abcdefgh12345678")
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(save_credential("balance", "api_key", body, _FakeRequest()))
        assert "encrypted_value" not in json.dumps(result)


# ---------------------------------------------------------------------------
# POST /rotate
# ---------------------------------------------------------------------------

class TestVaultRotateEndpoint:

    def test_rotate_returns_new_masked_hint(self):
        """POST /rotate returns new masked_hint, never raw value."""
        new_secret = "NEW_SECRET_API_KEY_ROTATE_ABCDEFGH"
        mock_svc = _mock_vault_service(rotate_return={
            "configured": True,
            "masked_hint": "****EFGH",
            "key_version": "test-v1",
            "rotated": True,
        })
        from app.api.routes_credential_vault import rotate_credential, RotateCredentialPayload
        body = RotateCredentialPayload(new_raw_value=new_secret)
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(rotate_credential("balance", "api_key", body, _FakeRequest()))
        assert new_secret not in json.dumps(result)
        assert "****EFGH" in json.dumps(result)
        assert result["data"]["rotated"] is True

    def test_rotate_not_found_returns_error(self):
        """RuntimeError CREDENTIAL_NOT_FOUND → NOT_FOUND error response."""
        mock_svc = MagicMock()
        mock_svc.rotate_credential = AsyncMock(
            side_effect=RuntimeError("CREDENTIAL_NOT_FOUND")
        )
        from app.api.routes_credential_vault import rotate_credential, RotateCredentialPayload
        body = RotateCredentialPayload(new_raw_value="any_new_key_12345678")
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(rotate_credential("balance", "api_key", body, _FakeRequest()))
        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_rotate_empty_new_value_returns_error(self):
        """Empty new_raw_value returns error immediately."""
        from app.api.routes_credential_vault import rotate_credential, RotateCredentialPayload
        body = RotateCredentialPayload(new_raw_value="")
        with patch("app.api.routes_credential_vault.require_permission"):
            result = _run(rotate_credential("balance", "api_key", body, _FakeRequest()))
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# DELETE /disable
# ---------------------------------------------------------------------------

class TestVaultDisableEndpoint:

    def test_disable_returns_disabled_true(self):
        """DELETE disables credential and confirms disabled=True."""
        mock_svc = _mock_vault_service(disable_return={"disabled": True})
        from app.api.routes_credential_vault import disable_credential
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(disable_credential("balance", "api_key", _FakeRequest()))
        assert result["ok"] is True
        assert result["data"]["disabled"] is True


# ---------------------------------------------------------------------------
# No secrets in source / responses
# ---------------------------------------------------------------------------

class TestVaultNoSecrets:

    def test_routes_module_no_hardcoded_credentials(self):
        """routes_credential_vault.py must not contain hardcoded secrets."""
        import pathlib, re
        src = pathlib.Path("app/api/routes_credential_vault.py").read_text(encoding="utf-8")
        assert not re.search(r'password\s*=\s*["\'][^"\']+["\']', src, re.I)
        assert "postgresql://" not in src
        assert not re.search(r'api_key\s*=\s*["\'][^"\']{8,}["\']', src, re.I)

    def test_response_never_returns_encrypted_value_field(self):
        """Status response must never expose encrypted_value."""
        mock_svc = _mock_vault_service(status_return={
            "configured": True,
            "masked_hint": "****abcd",
            "status": "active",
        })
        from app.api.routes_credential_vault import get_credential_status
        with patch("app.api.routes_credential_vault.get_conn", return_value=_fake_get_conn()), \
             patch("app.api.routes_credential_vault.require_permission"), \
             patch("app.api.services.credential_vault_service.CredentialVaultService",
                   return_value=mock_svc):
            result = _run(get_credential_status("balance", "api_key", _FakeRequest()))
        assert "encrypted_value" not in json.dumps(result)

    def test_migrations_vault_module_no_hardcoded_secrets(self):
        """migrations_vault.py must not contain plaintext credentials."""
        import pathlib, re
        src = pathlib.Path("app/startup/migrations_vault.py").read_text(encoding="utf-8")
        assert not re.search(r'password\s*=\s*["\'][^"\']+["\']', src, re.I)
        assert "postgresql://" not in src


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class TestVaultPermissions:

    def test_permission_map_has_vault_credentials(self):
        """PERMISSION_MAP must include /vault/credentials with tenants:manage."""
        from app.api.policy.permission_map import PERMISSION_MAP
        vault_entries = [e for e in PERMISSION_MAP if "/vault/credentials" in str(e)]
        assert vault_entries, "No /vault/credentials entry in PERMISSION_MAP"
        for method, path, perm in vault_entries:
            assert perm == "tenants:manage", f"Expected tenants:manage, got {perm}"

    def test_vault_router_prefix(self):
        """Vault router prefix must be /vault/credentials."""
        from app.api.routes_credential_vault import router
        assert router.prefix == "/vault/credentials"

    def test_vault_routes_all_call_require_permission(self):
        """All 4 vault route handlers must call require_permission."""
        import pathlib
        src = pathlib.Path("app/api/routes_credential_vault.py").read_text(encoding="utf-8")
        count = src.count("require_permission(request,")
        assert count >= 4, f"Expected ≥4 require_permission calls, found {count}"

    def test_vault_migration_wired_in_migrations_py(self):
        """migrations.py must call run_vault_migrations."""
        import pathlib
        src = pathlib.Path("app/startup/migrations.py").read_text(encoding="utf-8")
        assert "run_vault_migrations" in src
        assert "migrations_vault" in src
