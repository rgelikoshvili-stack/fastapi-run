"""tests/unit/test_sprint1_email_vault.py

Sprint 1: email app_password → Credential Vault.
Verifies that:
 - save_tenant_email_credentials stores '[stored-in-vault]' + credential_status='active'
 - get_tenant_email_credentials decrypts from vault when credential_status='active'
 - get_tenant_email_credentials falls back to plaintext for legacy rows
 - _get_tenant_imap_creds in email_invoice_service decrypts vault rows
"""
import asyncio
import inspect
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run_sync(coro):
    return asyncio.run(coro)


# ─── Vault-save path ──────────────────────────────────────────────────────────

def test_save_email_creds_calls_vault_save():
    """save_tenant_email_credentials must call vault.save_credential."""
    from app.api.services.email_collector import save_tenant_email_credentials

    mock_vault = AsyncMock()
    mock_vault.save_credential = AsyncMock(return_value={"configured": True})

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    @asynccontextmanager
    async def _fake_get_conn():
        yield mock_conn

    with patch("app.api.services.email_collector.CredentialVaultService",
               return_value=mock_vault), \
         patch("app.api.services.email_collector.get_conn", _fake_get_conn):
        result = run_sync(save_tenant_email_credentials("tenant1", "test@gmail.com", "secret123"))

    assert result is True
    mock_vault.save_credential.assert_awaited_once()
    call_kwargs = mock_vault.save_credential.call_args.kwargs
    assert call_kwargs["provider"] == "email"
    assert call_kwargs["credential_type"] == "imap_app_password"
    assert call_kwargs["raw_value"] == "secret123"
    assert call_kwargs["tenant_id"] == "tenant1"


def test_save_email_creds_stores_marker_not_plaintext():
    """app_password column must be '[stored-in-vault]', not the raw password."""
    from app.api.services.email_collector import save_tenant_email_credentials

    mock_vault = AsyncMock()
    mock_vault.save_credential = AsyncMock(return_value={"configured": True})

    executed_sqls = []
    mock_conn = AsyncMock()

    async def _capture_execute(q, *args, **kwargs):
        executed_sqls.append((str(q), args))

    mock_conn.execute = _capture_execute

    @asynccontextmanager
    async def _fake_get_conn():
        yield mock_conn

    with patch("app.api.services.email_collector.CredentialVaultService",
               return_value=mock_vault), \
         patch("app.api.services.email_collector.get_conn", _fake_get_conn):
        run_sync(save_tenant_email_credentials("tenant1", "test@gmail.com", "secret123"))

    assert executed_sqls, "no SQL executed"
    sql, args = executed_sqls[0]
    assert "[stored-in-vault]" in args or "[stored-in-vault]" in sql
    assert "secret123" not in sql
    assert not any("secret123" in str(a) for a in args)


def test_save_email_creds_sets_status_active():
    """credential_status must be set to 'active' on save."""
    from app.api.services.email_collector import save_tenant_email_credentials

    mock_vault = AsyncMock()
    mock_vault.save_credential = AsyncMock(return_value={"configured": True})

    executed_sqls = []
    mock_conn = AsyncMock()

    async def _capture_execute(q, *args, **kwargs):
        executed_sqls.append((str(q), args))

    mock_conn.execute = _capture_execute

    @asynccontextmanager
    async def _fake_get_conn():
        yield mock_conn

    with patch("app.api.services.email_collector.CredentialVaultService",
               return_value=mock_vault), \
         patch("app.api.services.email_collector.get_conn", _fake_get_conn):
        run_sync(save_tenant_email_credentials("tenant1", "test@gmail.com", "secret123"))

    assert executed_sqls
    sql, args = executed_sqls[0]
    combined = sql + " ".join(str(a) for a in args)
    assert "active" in combined


# ─── Vault-read path ─────────────────────────────────────────────────────────

class _FakeRecord(dict):
    pass


def test_get_email_creds_decrypts_vault_row():
    """get_tenant_email_credentials must call vault.get_for_connector for active rows."""
    from app.api.services.email_collector import get_tenant_email_credentials

    db_row = _FakeRecord({
        "email": "test@gmail.com",
        "app_password": "[stored-in-vault]",
        "credential_status": "active",
    })

    mock_vault = AsyncMock()
    mock_vault.get_for_connector = AsyncMock(return_value="decrypted_password")

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=db_row)

    @asynccontextmanager
    async def _fake_get_conn():
        yield mock_conn

    with patch("app.api.services.email_collector.CredentialVaultService",
               return_value=mock_vault), \
         patch("app.api.services.email_collector.get_conn", _fake_get_conn):
        result = run_sync(get_tenant_email_credentials("tenant1"))

    assert result is not None
    assert result["app_password"] == "decrypted_password"
    assert result["email"] == "test@gmail.com"
    mock_vault.get_for_connector.assert_awaited_once()
    call_kwargs = mock_vault.get_for_connector.call_args.kwargs
    assert call_kwargs["provider"] == "email"
    assert call_kwargs["credential_type"] == "imap_app_password"


def test_get_email_creds_legacy_plaintext_fallback():
    """Legacy rows (credential_status='legacy_plaintext') must return app_password directly."""
    from app.api.services.email_collector import get_tenant_email_credentials

    db_row = _FakeRecord({
        "email": "legacy@gmail.com",
        "app_password": "old_plaintext_pass",
        "credential_status": "legacy_plaintext",
    })

    mock_vault = AsyncMock()
    mock_vault.get_for_connector = AsyncMock()

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=db_row)

    @asynccontextmanager
    async def _fake_get_conn():
        yield mock_conn

    with patch("app.api.services.email_collector.CredentialVaultService",
               return_value=mock_vault), \
         patch("app.api.services.email_collector.get_conn", _fake_get_conn):
        result = run_sync(get_tenant_email_credentials("tenant1"))

    assert result is not None
    assert result["app_password"] == "old_plaintext_pass"
    mock_vault.get_for_connector.assert_not_awaited()


def test_get_email_creds_returns_none_when_not_configured():
    """Returns None when no credential row exists."""
    from app.api.services.email_collector import get_tenant_email_credentials

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _fake_get_conn():
        yield mock_conn

    with patch("app.api.services.email_collector.get_conn", _fake_get_conn):
        result = run_sync(get_tenant_email_credentials("tenant1"))

    assert result is None


# ─── email_collector.py source inspection ────────────────────────────────────

def test_email_collector_imports_vault_at_module_level():
    """CredentialVaultService must be imported at module level (not lazily inside fn body)."""
    import app.api.services.email_collector as ec
    assert hasattr(ec, "CredentialVaultService"), (
        "CredentialVaultService must be importable from email_collector module scope"
    )


def test_save_email_creds_never_stores_raw_password_in_db():
    """Ensure the function body never passes raw app_password to conn.execute."""
    from app.api.services.email_collector import save_tenant_email_credentials
    src = inspect.getsource(save_tenant_email_credentials)
    # The only place app_password appears after vault save must be the marker
    lines_with_pw = [l for l in src.splitlines()
                     if "app_password" in l and "conn.execute" in l]
    assert not lines_with_pw, (
        "conn.execute must not reference app_password directly in save_tenant_email_credentials"
    )


# ─── email_invoice_service sync path ─────────────────────────────────────────

def test_email_invoice_service_decrypts_vault_row_via_crypto_provider():
    """_get_tenant_imap_creds must decrypt vault rows using SecretCryptoProvider."""
    from app.api.services.email_invoice_service import _get_tenant_imap_creds

    fake_row = ("invoice@gmail.com", "[stored-in-vault]", "active", "enc_blob", "v1")

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone = MagicMock(return_value=fake_row)

    mock_pconn = MagicMock()
    mock_pconn.cursor = MagicMock(return_value=mock_cursor)
    mock_pconn.close = MagicMock()

    mock_crypto = MagicMock()
    mock_crypto.decrypt_secret = MagicMock(return_value="decrypted_imap_pass")

    with patch("psycopg2.connect", return_value=mock_pconn), \
         patch("os.environ.get", return_value="postgresql://fake"), \
         patch("app.api.services.secret_crypto_provider.SecretCryptoProvider",
               return_value=mock_crypto):
        email, pw = _get_tenant_imap_creds("tenant1")

    assert email == "invoice@gmail.com"
    assert pw == "decrypted_imap_pass"
    mock_crypto.decrypt_secret.assert_called_once_with("enc_blob", "v1")


def test_email_invoice_service_legacy_plaintext_still_works():
    """Legacy rows (app_password not stored-in-vault) are returned as-is."""
    from app.api.services.email_invoice_service import _get_tenant_imap_creds

    fake_row = ("legacy@gmail.com", "plainpass", "legacy_plaintext", None, None)

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone = MagicMock(return_value=fake_row)

    mock_pconn = MagicMock()
    mock_pconn.cursor = MagicMock(return_value=mock_cursor)
    mock_pconn.close = MagicMock()

    with patch("psycopg2.connect", return_value=mock_pconn), \
         patch("os.environ.get", return_value="postgresql://fake"):
        email, pw = _get_tenant_imap_creds("tenant1")

    assert email == "legacy@gmail.com"
    assert pw == "plainpass"
