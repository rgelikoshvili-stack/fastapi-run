"""
tests/unit/test_credential_vault_service.py

Unit tests for CredentialVaultService and CredentialVaultRepository (Task 11C-C3).
All DB calls are mocked. No real DB connection. No network. No production secrets.
"""

from __future__ import annotations

import os
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.secret_crypto_provider import SecretCryptoProvider
from app.api.services.credential_vault_service import CredentialVaultService
from app.api.services.credential_vault_repository import CredentialVaultRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_SECRET = "live-api-key-for-balance-12345678"
TENANT = "tenant_test"
PROVIDER = "balance"
CTYPE = "api_key"


def _make_service():
    crypto = SecretCryptoProvider()
    repo = CredentialVaultRepository()
    svc = CredentialVaultService(repo=repo, crypto=crypto)
    return svc, repo, crypto


def _mock_conn():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    return conn


@pytest.fixture
def svc():
    service, repo, crypto = _make_service()
    return service


@pytest.fixture
def conn():
    return _mock_conn()


# ---------------------------------------------------------------------------
# A) save_credential — encryption before repository write
# ---------------------------------------------------------------------------

class TestSaveCredential:

    @pytest.mark.asyncio
    async def test_save_calls_repo_upsert_with_encrypted_value(self, svc, conn):
        repo_calls = []

        async def fake_upsert(c, *, encrypted_value, key_version, masked_hint, **kw):
            repo_calls.append({
                "encrypted_value": encrypted_value,
                "key_version": key_version,
                "masked_hint": masked_hint,
            })
            return {"status": "active", "masked_hint": masked_hint, "key_version": key_version}

        async def fake_audit(*a, **kw):
            pass

        svc._repo.upsert_credential = fake_upsert
        svc._repo.insert_audit_event = AsyncMock()

        result = await svc.save_credential(
            conn,
            tenant_id=TENANT, provider=PROVIDER,
            credential_type=CTYPE, raw_value=TEST_SECRET,
        )

        assert len(repo_calls) == 1
        call = repo_calls[0]
        # Repository must receive encrypted_value, not raw secret
        assert call["encrypted_value"] != TEST_SECRET
        assert call["encrypted_value"]
        assert call["key_version"]

    @pytest.mark.asyncio
    async def test_save_result_never_contains_raw_secret(self, svc, conn):
        svc._repo.upsert_credential = AsyncMock(return_value={"status": "active"})
        svc._repo.insert_audit_event = AsyncMock()

        result = await svc.save_credential(
            conn,
            tenant_id=TENANT, provider=PROVIDER,
            credential_type=CTYPE, raw_value=TEST_SECRET,
        )

        result_str = str(result)
        assert TEST_SECRET not in result_str

    @pytest.mark.asyncio
    async def test_save_result_contains_masked_hint(self, svc, conn):
        svc._repo.upsert_credential = AsyncMock(return_value={"status": "active"})
        svc._repo.insert_audit_event = AsyncMock()

        result = await svc.save_credential(
            conn,
            tenant_id=TENANT, provider=PROVIDER,
            credential_type=CTYPE, raw_value=TEST_SECRET,
        )

        assert "masked_hint" in result
        assert result["masked_hint"].startswith("****")
        assert result["masked_hint"] != TEST_SECRET

    @pytest.mark.asyncio
    async def test_save_empty_raw_value_raises(self, svc, conn):
        with pytest.raises(ValueError):
            await svc.save_credential(
                conn,
                tenant_id=TENANT, provider=PROVIDER,
                credential_type=CTYPE, raw_value="",
            )

    @pytest.mark.asyncio
    async def test_save_writes_audit_event(self, svc, conn):
        svc._repo.upsert_credential = AsyncMock(return_value={"status": "active"})
        audit_calls = []

        async def fake_audit(c, *, action, result, **kw):
            audit_calls.append({"action": action, "result": result})

        svc._repo.insert_audit_event = fake_audit

        await svc.save_credential(
            conn,
            tenant_id=TENANT, provider=PROVIDER,
            credential_type=CTYPE, raw_value=TEST_SECRET,
        )

        assert len(audit_calls) == 1
        assert audit_calls[0]["result"] == "success"


# ---------------------------------------------------------------------------
# B) get_status — never returns raw secret
# ---------------------------------------------------------------------------

class TestGetStatus:

    @pytest.mark.asyncio
    async def test_status_returns_configured_when_record_exists(self, svc, conn):
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

        assert result["configured"] is True
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_status_never_returns_raw_secret(self, svc, conn):
        svc._repo.get_active_credential = AsyncMock(return_value={
            "status": "active",
            "masked_hint": "****5678",
            "key_version": "test-v1",
            "company_id": None, "api_base": None,
            "last_test_status": None, "last_tested_at": None,
        })

        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        result_str = str(result)
        assert TEST_SECRET not in result_str

    @pytest.mark.asyncio
    async def test_status_never_contains_api_key_field(self, svc, conn):
        svc._repo.get_active_credential = AsyncMock(return_value={
            "status": "active",
            "masked_hint": "****5678",
            "key_version": "test-v1",
            "company_id": None, "api_base": None,
            "last_test_status": None, "last_tested_at": None,
        })

        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        assert "api_key" not in result
        assert "encrypted_value" not in result
        assert "password" not in result

    @pytest.mark.asyncio
    async def test_status_returns_not_configured_when_no_record(self, svc, conn):
        svc._repo.get_active_credential = AsyncMock(return_value=None)
        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        assert result["configured"] is False
        assert result["status"] == "not_configured"

    @pytest.mark.asyncio
    async def test_status_returns_safe_on_db_error(self, svc, conn):
        svc._repo.get_active_credential = AsyncMock(side_effect=Exception("DB down"))
        result = await svc.get_status(conn, TENANT, PROVIDER, CTYPE)
        assert result["configured"] is False
        assert TEST_SECRET not in str(result)


# ---------------------------------------------------------------------------
# C) get_for_connector — raw secret for connector only
# ---------------------------------------------------------------------------

class TestGetForConnector:

    @pytest.mark.asyncio
    async def test_returns_raw_secret_when_active(self, svc, conn):
        payload = svc._crypto.encrypt_secret(TEST_SECRET)
        svc._repo.get_encrypted_credential = AsyncMock(return_value={
            "encrypted_value": payload["encrypted_value"],
            "key_version": payload["key_version"],
            "status": "active",
            "active": True,
        })
        svc._repo.touch_last_accessed = AsyncMock()
        svc._repo.insert_audit_event = AsyncMock()

        result = await svc.get_for_connector(
            conn, tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
        )
        assert result == TEST_SECRET

    @pytest.mark.asyncio
    async def test_raises_not_found_when_no_record(self, svc, conn):
        svc._repo.get_encrypted_credential = AsyncMock(return_value=None)
        svc._repo.insert_audit_event = AsyncMock()

        with pytest.raises(RuntimeError, match="CREDENTIAL_NOT_FOUND"):
            await svc.get_for_connector(
                conn, tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
            )

    @pytest.mark.asyncio
    async def test_raises_disabled_when_active_false(self, svc, conn):
        payload = svc._crypto.encrypt_secret(TEST_SECRET)
        svc._repo.get_encrypted_credential = AsyncMock(return_value={
            "encrypted_value": payload["encrypted_value"],
            "key_version": payload["key_version"],
            "status": "active",
            "active": False,  # disabled
        })
        svc._repo.insert_audit_event = AsyncMock()

        with pytest.raises(RuntimeError, match="CREDENTIAL_DISABLED"):
            await svc.get_for_connector(
                conn, tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
            )

    @pytest.mark.asyncio
    async def test_raises_disabled_when_status_revoked(self, svc, conn):
        payload = svc._crypto.encrypt_secret(TEST_SECRET)
        svc._repo.get_encrypted_credential = AsyncMock(return_value={
            "encrypted_value": payload["encrypted_value"],
            "key_version": payload["key_version"],
            "status": "revoked",
            "active": True,
        })
        svc._repo.insert_audit_event = AsyncMock()

        with pytest.raises(RuntimeError, match="CREDENTIAL_DISABLED"):
            await svc.get_for_connector(
                conn, tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
            )

    @pytest.mark.asyncio
    async def test_raises_decrypt_failed_on_bad_ciphertext(self, svc, conn):
        svc._repo.get_encrypted_credential = AsyncMock(return_value={
            "encrypted_value": "notvalidbase64!!!!",
            "key_version": "test-v1",
            "status": "active",
            "active": True,
        })
        svc._repo.insert_audit_event = AsyncMock()

        with pytest.raises(RuntimeError, match="CREDENTIAL_DECRYPT_FAILED"):
            await svc.get_for_connector(
                conn, tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
            )

    @pytest.mark.asyncio
    async def test_connector_path_writes_audit_event(self, svc, conn):
        payload = svc._crypto.encrypt_secret(TEST_SECRET)
        svc._repo.get_encrypted_credential = AsyncMock(return_value={
            "encrypted_value": payload["encrypted_value"],
            "key_version": payload["key_version"],
            "status": "active",
            "active": True,
        })
        svc._repo.touch_last_accessed = AsyncMock()
        audit_calls = []

        async def fake_audit(c, *, action, result, **kw):
            audit_calls.append({"action": action, "result": result})

        svc._repo.insert_audit_event = fake_audit

        await svc.get_for_connector(
            conn, tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
        )

        assert any(c["result"] == "success" for c in audit_calls)


# ---------------------------------------------------------------------------
# D) rotate_credential
# ---------------------------------------------------------------------------

class TestRotateCredential:

    @pytest.mark.asyncio
    async def test_rotate_updates_key_version(self, svc, conn):
        old_payload = svc._crypto.encrypt_secret("old-secret-12345678")
        svc._repo.get_active_credential = AsyncMock(return_value={
            "key_version": old_payload["key_version"],
            "status": "active",
        })
        update_calls = []

        async def fake_update(c, *, encrypted_value, key_version, masked_hint, **kw):
            update_calls.append({
                "encrypted_value": encrypted_value,
                "key_version": key_version,
                "masked_hint": masked_hint,
            })
            return True

        svc._repo.update_rotation = fake_update
        svc._repo.insert_audit_event = AsyncMock()

        result = await svc.rotate_credential(
            conn,
            tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
            new_raw_value="new-secret-87654321",
        )

        assert len(update_calls) == 1
        assert update_calls[0]["encrypted_value"] != "new-secret-87654321"
        assert result["rotated"] is True

    @pytest.mark.asyncio
    async def test_rotate_raises_not_found_when_no_record(self, svc, conn):
        svc._repo.get_active_credential = AsyncMock(return_value=None)
        svc._repo.insert_audit_event = AsyncMock()

        with pytest.raises(RuntimeError, match="CREDENTIAL_NOT_FOUND"):
            await svc.rotate_credential(
                conn,
                tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
                new_raw_value="new-secret-87654321",
            )

    @pytest.mark.asyncio
    async def test_rotate_writes_audit_event_with_key_versions(self, svc, conn):
        old_payload = svc._crypto.encrypt_secret("old-secret-12345678")
        svc._repo.get_active_credential = AsyncMock(return_value={
            "key_version": old_payload["key_version"],
        })
        svc._repo.update_rotation = AsyncMock(return_value=True)
        audit_calls = []

        async def fake_audit(c, *, action, result, metadata=None, **kw):
            audit_calls.append({"action": action, "result": result, "metadata": metadata})

        svc._repo.insert_audit_event = fake_audit

        await svc.rotate_credential(
            conn,
            tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
            new_raw_value="new-secret-87654321",
        )

        assert any("old_key_version" in str(c.get("metadata", "")) for c in audit_calls)


# ---------------------------------------------------------------------------
# E) disable_credential
# ---------------------------------------------------------------------------

class TestDisableCredential:

    @pytest.mark.asyncio
    async def test_disable_calls_repo_disable(self, svc, conn):
        svc._repo.disable_credential = AsyncMock(return_value=True)
        svc._repo.insert_audit_event = AsyncMock()

        result = await svc.disable_credential(conn, TENANT, PROVIDER, CTYPE, actor="admin")
        svc._repo.disable_credential.assert_called_once()
        assert result["disabled"] is True

    @pytest.mark.asyncio
    async def test_disable_writes_audit_event(self, svc, conn):
        svc._repo.disable_credential = AsyncMock(return_value=True)
        audit_calls = []

        async def fake_audit(c, *, action, result, **kw):
            audit_calls.append({"action": action, "result": result})

        svc._repo.insert_audit_event = fake_audit

        await svc.disable_credential(conn, TENANT, PROVIDER, CTYPE, actor="admin")
        assert any(c["result"] == "success" for c in audit_calls)


# ---------------------------------------------------------------------------
# F) audit_access — safe metadata, no raw secret
# ---------------------------------------------------------------------------

class TestAuditAccess:

    @pytest.mark.asyncio
    async def test_audit_writes_event_without_raw_secret(self, svc, conn):
        written = []

        async def fake_insert(c, *, action, result, metadata=None, **kw):
            written.append({"action": action, "result": result, "metadata": metadata})

        svc._repo.insert_audit_event = fake_insert

        await svc.audit_access(
            conn,
            tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
            actor="system", purpose="connector_execution", result="success",
            metadata={"context": "test"},
        )

        assert len(written) == 1
        assert TEST_SECRET not in str(written[0])

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_raise(self, svc, conn):
        svc._repo.insert_audit_event = AsyncMock(side_effect=Exception("DB write failed"))

        # Should not raise — audit failures must not block primary operation
        await svc.audit_access(
            conn,
            tenant_id=TENANT, provider=PROVIDER, credential_type=CTYPE,
            actor="system", purpose="save", result="success",
        )
