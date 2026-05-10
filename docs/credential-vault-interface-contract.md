# Credential Vault Interface Contract

## Purpose

This document defines the planned service interfaces and data contracts for the
Credential Vault layer. These interfaces are pseudocode specifications — they
define the future implementation target but are NOT implemented in runtime app
code in this task.

No runtime code is changed. No migrations are created. No production database is
touched. Balance.ge remains inactive.

---

## CredentialVaultService

Central orchestrator. All credential lifecycle operations flow through this
service. It never returns raw decrypted secrets to non-connector callers.

```python
class CredentialVaultService:

    async def store_secret(
        self,
        tenant_id: str,
        provider: str,           # "balance", "email", "rsge", "onec", "webhook", "totp"
        credential_type: str,    # "api_key", "password", "app_password", "secret", "totp_secret"
        raw_secret: str,         # plaintext — encrypted immediately, not stored
        actor_id: str,
    ) -> CredentialStatus:
        """
        Encrypt raw_secret via SecretCryptoProvider.
        Write encrypted_value + key_version + masked_hint to CredentialRepository.
        Log credential_stored audit event (no raw secret in log).
        Return CredentialStatus (safe fields only).
        raw_secret must not appear in any log, response, or exception.
        """

    async def get_secret_for_connector_use(
        self,
        tenant_id: str,
        provider: str,
        credential_type: str,
        purpose: str,            # e.g. "connector_execution", "connection_test"
    ) -> str:
        """
        Decrypt encrypted_value via SecretCryptoProvider.
        Log credential_used audit event (no raw secret in log).
        Return raw secret IN MEMORY ONLY.
        Caller must NOT store, log, serialize, or return this value.
        Only ConnectorCredentialProvider should call this method.
        Raises CredentialNotFoundError if not configured.
        Raises DecryptionError (with safe error code) if decryption fails.
        """

    async def get_credential_status(
        self,
        tenant_id: str,
        provider: str,
        credential_type: str,
    ) -> CredentialStatus:
        """
        Read metadata from CredentialRepository (no decryption).
        Return CredentialStatus with safe fields only.
        Never decrypts. Never returns encrypted_value or raw secret.
        """

    async def rotate_secret(
        self,
        tenant_id: str,
        provider: str,
        credential_type: str,
        new_raw_secret: str,     # plaintext — encrypted immediately
        actor_id: str,
    ) -> CredentialStatus:
        """
        Encrypt new_raw_secret via SecretCryptoProvider with new key_version.
        Update record: encrypted_value, key_version, masked_hint, rotated_at, updated_by.
        Invalidate old key version reference.
        Log credential_rotated audit event (no raw secret in log).
        Return updated CredentialStatus (safe fields only).
        """

    async def revoke_secret(
        self,
        tenant_id: str,
        provider: str,
        credential_type: str,
        actor_id: str,
    ) -> CredentialStatus:
        """
        Set is_active = FALSE, revoked_at = now(), status = "revoked".
        Log credential_revoked audit event.
        Return updated CredentialStatus.
        """

    async def test_secret(
        self,
        tenant_id: str,
        provider: str,
        credential_type: str,
        actor_id: str,
    ) -> CredentialTestResult:
        """
        Retrieve raw secret via get_secret_for_connector_use() (internal path only).
        Make a test connection to the provider (e.g. Balance.ge /health endpoint).
        Update last_tested_at, last_test_status in CredentialRepository.
        Log credential_tested audit event with result (no raw secret in log).
        Return CredentialTestResult: success, error_code, error_message (no secret).
        """
```

---

## SecretCryptoProvider

Handles all encryption, decryption, and masking. This is the only component
that holds raw secrets — and only transiently in memory.

```python
class SecretCryptoProvider:

    def encrypt(
        self,
        raw_secret: str,
        tenant_id: str,
        provider: str,
        key_version: str,
    ) -> tuple[str, str]:
        """
        Encrypt raw_secret using AES-256-GCM (Fernet) or GCP Secret Manager.
        Returns (encrypted_value, key_version).
        raw_secret must not be logged or stored by this method.
        Recommended: use GCP Secret Manager for Cloud Run deployments.
        key_version is the Secret Manager version name or a KMS key version ID.
        """

    def decrypt(
        self,
        encrypted_value: str,
        tenant_id: str,
        provider: str,
        key_version: str,
    ) -> str:
        """
        Decrypt encrypted_value using the specified key_version.
        Returns raw_secret IN MEMORY ONLY.
        Must not log the raw_secret.
        On failure: raise DecryptionError with safe error code, not partial value.
        """

    def mask(
        self,
        raw_secret: str,
    ) -> str:
        """
        Derive a safe display hint from raw_secret.
        Returns "****" + last 4 chars if len >= 8, else "****".
        This is called at write time only — never at read time.
        The masked_hint is stored in the credential record so reads never decrypt.
        """
```

---

## CredentialStatus (Response Object)

The safe public view of a credential. All public API responses and UI displays
must use this object only.

### Allowed Fields

```python
class CredentialStatus:
    provider: str             # "balance", "email", "rsge", "onec", "webhook", "totp"
    credential_type: str      # "api_key", "password", "app_password", "secret"
    status: str               # "active", "revoked", "not_configured", "rotation_pending"
    configured: bool          # True if an active credential exists
    masked_hint: str | None   # "****7a3f" — safe display hint only, null if not configured
    last_tested_at: str | None     # ISO 8601 timestamp or null
    last_test_status: str | None   # "ok", "failed", "timeout", "not_tested"
    last_used_at: str | None       # ISO 8601 timestamp or null
    rotated_at: str | None         # ISO 8601 timestamp or null
    is_active: bool
```

### Forbidden Fields in CredentialStatus

The following fields must NEVER appear in any `CredentialStatus` response or
any API response that serves status/read data:

- `api_key`
- `password`
- `app_password`
- `token`
- `secret`
- `raw_secret`
- `encrypted_value`
- `key_version`
- `totp_secret`
- `webhook_secret`
- Any decryption key or key material

This rule applies to all credential types:
- Balance.ge API key
- Email IMAP app password
- RS.ge portal password
- 1C endpoint password
- Webhook signing secret
- TOTP setup secret (after initial setup only)

---

## CredentialTestResult (Response Object)

Returned by test operations. Contains only pass/fail and safe error information.

```python
class CredentialTestResult:
    success: bool
    provider: str
    credential_type: str
    error_code: str | None     # "CONNECTION_TIMEOUT", "AUTH_FAILED", "NOT_CONFIGURED"
    error_message: str | None  # Safe human-readable message, no secret values
    tested_at: str             # ISO 8601 timestamp
```

---

## ConnectorCredentialProvider

The only internal path that exposes decrypted secrets to connectors.
Only connector constructors or execution methods may call these methods.
Route handlers must never call these methods directly.

```python
class ConnectorCredentialProvider:

    async def get_balance_credentials_for_use(
        self,
        tenant_id: str,
    ) -> dict:
        """
        Returns {"api_key": raw_key, "company_id": ..., "api_base": ...}
        IN MEMORY ONLY for connector execution.
        Calls CredentialVaultService.get_secret_for_connector_use() internally.
        Falls back to env var BALANCE_API_KEY if no DB credential (demo mode only).
        Never returns this dict to any API response.
        """

    async def get_email_credentials_for_use(
        self,
        tenant_id: str,
    ) -> dict:
        """
        Returns {"host": ..., "port": ..., "username": ..., "app_password": raw_pw}
        IN MEMORY ONLY for IMAP connection.
        app_password decrypted via CredentialVaultService (internal path).
        """

    async def get_rsge_credentials_for_use(
        self,
        tenant_id: str,
    ) -> dict:
        """
        Returns {"username": ..., "password": raw_pw, "taxpayer_inn": ...}
        IN MEMORY ONLY for RS.ge workflow execution.
        password decrypted via CredentialVaultService (internal path).
        """

    async def get_webhook_secret_for_verification(
        self,
        tenant_id: str,
        webhook_id: int,
    ) -> str:
        """
        Returns raw webhook signing secret IN MEMORY ONLY for signature computation.
        Never stored, logged, or returned to any API response.
        """
```

---

## CredentialAuditLogger

Logs all credential lifecycle events without including any secret value.

```python
class CredentialAuditLogger:

    async def log_event(
        self,
        tenant_id: str,
        actor: str,
        provider: str,
        credential_type: str,
        action: str,     # "stored", "updated", "rotated", "revoked", "tested", "used"
        result: str,     # "ok", "failed", "denied"
        safe_error_code: str | None = None,
        metadata: dict | None = None,   # safe non-secret context only
    ) -> None:
        """
        Write audit event to audit_events table or equivalent.
        metadata must never contain raw secrets, encrypted_value, or key material.
        Allowed metadata: provider, credential_type, ip_address, request_id.
        """
```

---

## API Surface Rules

### Public/Status APIs — must use CredentialStatusService only

```
GET /balance-credentials/status
    → CredentialVaultService.get_credential_status(tenant_id, "balance", "api_key")
    → Returns: CredentialStatus (safe fields only)

GET /rsge-credentials/status
    → CredentialVaultService.get_credential_status(tenant_id, "rsge", "password")
    → Returns: CredentialStatus (safe fields only)
    → Must NOT return: username, password, or any plaintext value

GET /auth/2fa/status
    → CredentialVaultService.get_credential_status(tenant_id_or_user_id, "totp", "totp_secret")
    → Returns: {"totp_enabled": true/false}
    → Must NOT return: totp_secret after setup
```

### Admin Test APIs — use CredentialVaultService.test_secret()

```
POST /balance-credentials/test
    → CredentialVaultService.test_secret(tenant_id, "balance", "api_key", actor_id)
    → Returns: CredentialTestResult (no raw key)

POST /rsge-credentials/test
    → CredentialVaultService.test_secret(tenant_id, "rsge", "password", actor_id)
    → Returns: CredentialTestResult (no raw password)
```

### Save/Update APIs — use CredentialVaultService.store_secret()

```
POST /balance-credentials/save
    → CredentialVaultService.store_secret(tenant_id, "balance", "api_key", body.api_key, actor_id)
    → Encrypts immediately. Never writes plaintext to DB.
    → Returns: CredentialStatus (safe)

POST /rsge-credentials/save
    → CredentialVaultService.store_secret(tenant_id, "rsge", "password", body.password, actor_id)
    → Encrypts immediately. Never writes plaintext to DB.
    → Returns: CredentialStatus (safe)
```

### Connector/Internal Paths — use ConnectorCredentialProvider only

```
BalanceConnector.__init__()
    → ConnectorCredentialProvider.get_balance_credentials_for_use(tenant_id)
    → self.api_key = result["api_key"]  ← in memory only, for this request only

EmailCollector.connect()
    → ConnectorCredentialProvider.get_email_credentials_for_use(tenant_id)
    → app_password used for IMAP connection only
```

---

## Invariants (Must Never Be Violated)

1. Raw secrets must never appear in API responses, HTTP bodies, or HTTP headers
   sent to clients (except in the initial TOTP setup step).
2. Raw secrets must never appear in log lines at any log level.
3. Raw secrets must never be stored in `encrypted_value`-equivalent columns
   without encryption.
4. `CredentialStatus` must never contain `api_key`, `password`, `token`,
   `secret`, `encrypted_value`, or key material.
5. Only `ConnectorCredentialProvider` may call `get_secret_for_connector_use()`.
6. Route handlers must call `get_credential_status()` for read paths, not
   `get_secret_for_connector_use()`.
7. `CredentialAuditLogger.log_event()` must be called for every credential
   lifecycle event.
8. All credential records must be scoped by `tenant_id`.
9. All future migrations must be additive-only.
10. Balance.ge live activation requires all 12 gates in
    `docs/balance-ge-activation-gate.md` to be MET.
