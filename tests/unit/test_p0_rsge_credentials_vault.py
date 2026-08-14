"""tests/unit/test_p0_rsge_credentials_vault.py
P0-2: RS.ge credential saves must use the credential vault.
Plain-text password must never be written to tenant_rsge_credentials.password.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def run_sync(coro):
    return asyncio.run(coro)


def _make_body(password="s3cr3t!"):
    from app.api.routes_rsge_credentials import RsgeCredsPayload
    return RsgeCredsPayload(username="user@rs.ge", password=password, taxpayer_inn="123456789")


def _make_request(tenant_id="tenant1", user_id="accountant1"):
    req = MagicMock()
    req.state = MagicMock()
    req.state.tenant_id = tenant_id
    req.state.user_id = user_id
    return req


def _make_mock_conn():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)
    tr = AsyncMock()
    conn.transaction = MagicMock(return_value=tr)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, conn


# ── save_creds must use vault ─────────────────────────────────────────────────

def test_save_creds_calls_vault_service():
    ctx, conn = _make_mock_conn()
    vault_mock = AsyncMock()
    vault_mock.save_credential = AsyncMock(return_value={"id": "vault-uuid-1"})

    with patch("app.api.routes_rsge_credentials.get_conn", return_value=ctx), \
         patch("app.api.routes_rsge_credentials.resolve_tenant_id", return_value="tenant1"), \
         patch("app.api.routes_rsge_credentials.require_permission"), \
         patch("app.api.routes_rsge_credentials.CredentialVaultService",
               return_value=vault_mock):
        from app.api.routes_rsge_credentials import save_creds
        result = run_sync(save_creds(_make_body(), _make_request()))

    vault_mock.save_credential.assert_called_once()
    call_kwargs = vault_mock.save_credential.call_args.kwargs
    assert call_kwargs["provider"] == "rsge"
    assert call_kwargs["credential_type"] == "portal_password"
    assert call_kwargs["raw_value"] == "s3cr3t!"


def test_save_creds_does_not_write_plaintext_to_db():
    ctx, conn = _make_mock_conn()
    vault_mock = AsyncMock()
    vault_mock.save_credential = AsyncMock(return_value={"id": "vault-uuid-2"})

    with patch("app.api.routes_rsge_credentials.get_conn", return_value=ctx), \
         patch("app.api.routes_rsge_credentials.resolve_tenant_id", return_value="tenant1"), \
         patch("app.api.routes_rsge_credentials.require_permission"), \
         patch("app.api.routes_rsge_credentials.CredentialVaultService",
               return_value=vault_mock):
        from app.api.routes_rsge_credentials import save_creds
        run_sync(save_creds(_make_body("my_plaintext_pass"), _make_request()))

    # Check that none of the DB execute calls contain the raw password
    for call in conn.execute.call_args_list:
        sql_and_args = str(call)
        assert "my_plaintext_pass" not in sql_and_args, (
            f"Plaintext password found in DB call: {call}"
        )


def test_save_creds_writes_stored_in_vault_marker():
    ctx, conn = _make_mock_conn()
    vault_mock = AsyncMock()
    vault_mock.save_credential = AsyncMock(return_value={"id": "vault-uuid-3"})

    with patch("app.api.routes_rsge_credentials.get_conn", return_value=ctx), \
         patch("app.api.routes_rsge_credentials.resolve_tenant_id", return_value="tenant1"), \
         patch("app.api.routes_rsge_credentials.require_permission"), \
         patch("app.api.routes_rsge_credentials.CredentialVaultService",
               return_value=vault_mock):
        from app.api.routes_rsge_credentials import save_creds
        run_sync(save_creds(_make_body(), _make_request()))

    # Find the INSERT call and verify it uses '[stored-in-vault]' marker
    insert_calls = [c for c in conn.execute.call_args_list
                    if "INSERT INTO tenant_rsge_credentials" in str(c)
                    or "ON CONFLICT" in str(c)]
    assert insert_calls, "Expected an INSERT/UPSERT into tenant_rsge_credentials"
    insert_str = str(insert_calls[0])
    assert "[stored-in-vault]" in insert_str


def test_save_creds_returns_ok_response():
    ctx, conn = _make_mock_conn()
    vault_mock = AsyncMock()
    vault_mock.save_credential = AsyncMock(return_value={"id": "vault-uuid-4"})

    with patch("app.api.routes_rsge_credentials.get_conn", return_value=ctx), \
         patch("app.api.routes_rsge_credentials.resolve_tenant_id", return_value="tenant1"), \
         patch("app.api.routes_rsge_credentials.require_permission"), \
         patch("app.api.routes_rsge_credentials.CredentialVaultService",
               return_value=vault_mock):
        from app.api.routes_rsge_credentials import save_creds
        result = run_sync(save_creds(_make_body(), _make_request()))

    assert result.get("ok") is True
    data = result.get("data", {})
    assert data.get("credential_status") == "active"
    assert "password" not in data


def test_save_creds_vault_failure_returns_error():
    ctx, conn = _make_mock_conn()
    vault_mock = AsyncMock()
    vault_mock.save_credential = AsyncMock(side_effect=Exception("vault not configured"))

    with patch("app.api.routes_rsge_credentials.get_conn", return_value=ctx), \
         patch("app.api.routes_rsge_credentials.resolve_tenant_id", return_value="tenant1"), \
         patch("app.api.routes_rsge_credentials.require_permission"), \
         patch("app.api.routes_rsge_credentials.CredentialVaultService",
               return_value=vault_mock):
        from app.api.routes_rsge_credentials import save_creds
        result = run_sync(save_creds(_make_body(), _make_request()))

    # Must NOT silently fall back to plaintext — must return an error
    assert result.get("ok") is False
    assert result.get("error", {}).get("code") == "CREDENTIAL_VAULT_ERROR"

    # Verify plaintext password was not written to DB
    for call in conn.execute.call_args_list:
        assert "s3cr3t!" not in str(call)


# ── get_status does not return password ──────────────────────────────────────

def test_get_status_does_not_return_password():
    ctx, conn = _make_mock_conn()

    class _FakeRow:
        def __getitem__(self, k):
            return {"username": "user@rs.ge", "taxpayer_inn": "123",
                    "credential_status": "active"}[k]

    conn.fetchrow = AsyncMock(return_value=_FakeRow())

    with patch("app.api.routes_rsge_credentials.get_conn", return_value=ctx), \
         patch("app.api.routes_rsge_credentials.resolve_tenant_id", return_value="tenant1"), \
         patch("app.api.routes_rsge_credentials.require_permission"), \
         patch("app.api.routes_rsge_credentials._ensure_schema", new=AsyncMock()):
        from app.api.routes_rsge_credentials import get_status
        result = run_sync(get_status(_make_request()))

    assert result.get("ok") is True
    data = result.get("data", {})
    assert "password" not in data
    assert data.get("username") == "user@rs.ge"
    assert data.get("credential_status") == "active"


# ── Legacy rotation_required ──────────────────────────────────────────────────

def test_test_connection_returns_rotation_required_for_legacy():
    ctx, conn = _make_mock_conn()

    class _FakeRow:
        def __getitem__(self, k):
            return {"username": "old@rs.ge", "taxpayer_inn": "111",
                    "credential_status": "rotation_required"}[k]

    conn.fetchrow = AsyncMock(return_value=_FakeRow())

    with patch("app.api.routes_rsge_credentials.get_conn", return_value=ctx), \
         patch("app.api.routes_rsge_credentials.resolve_tenant_id", return_value="tenant1"), \
         patch("app.api.routes_rsge_credentials.require_permission"):
        from app.api.routes_rsge_credentials import test_connection
        result = run_sync(test_connection(_make_request()))

    data = result.get("data", {})
    assert data.get("credential_status") == "rotation_required"
    assert "action_required" in data
