# Masked Read Behavior Contract

## A) Purpose

This document defines the behavior contract for public-facing and status credential
read APIs in Bridge Hub. It is a Trust Foundation prerequisite that must be in
place before any credential vault encryption is implemented.

The contract establishes:

- Which fields a public/status credential response may contain.
- Which fields are permanently forbidden from all public/status credential responses.
- How internal connector paths may use raw decrypted secrets.
- How masked hints must be derived and presented.
- How logs, exceptions, and audit events must handle credential values.

**This task defines the behavior contract only.**

No runtime behavior is changed in this task. No encryption is implemented. No
migration is created. No production database is touched. Balance.ge remains
inactive.

---

## B) Current State

The Credential Vault Design (`docs/credential-vault-design.md`) and Interface
Contract (`docs/credential-vault-interface-contract.md`) are complete and merged.

The following runtime state exists and is documented here for contract purposes.
These files are not changed in this task:

| File | Current Exposure | Risk |
|---|---|---|
| `app/api/services/balance_credentials_service.py` | `get_balance_credentials()` returns raw `api_key` in dict to any caller. `get_credentials_status()` does not directly return `api_key` but calls the raw path internally. | Critical |
| `app/api/routes_balance_credentials.py` | `/status` calls `get_credentials_status()` — currently safe at the route level. `/save` accepts raw `api_key` in request body. | Medium |
| `app/api/services/email_collector.py` | `get_tenant_email_credentials()` returns `{"email": ..., "app_password": raw_password}` to any caller. | Critical |
| `app/api/services/totp_service.py` | `get_user_totp()` returns `{"enabled": bool, "secret": str\|None}` — raw TOTP secret returned. | Critical |
| `app/api/services/webhook_service.py` | `secret TEXT` stored plaintext; fetched for HMAC signing in internal delivery path. | High |
| `app/api/routes_rsge_credentials.py` | `/status` returns `username` plaintext in API response. `password` not returned at route level but stored plaintext in DB. | High |
| `app/api/connectors/balance_connector.py` | `self.api_key = raw_key` held as instance attribute for request duration. | High |

Runtime behavior status: **unchanged in this task.**
Balance.ge activation status: **inactive — Balance.ge must stay inactive.**
Production DB status: **untouched in this task.**

---

## C) Public/Status Response Rule

All public-facing routes and status endpoints must comply with this rule after
future vault implementation. This is the target contract that implementation
must meet.

### Allowed Fields

A `CredentialStatus` or equivalent public/status response may contain only:

- `provider` — e.g. `"balance"`, `"email"`, `"rsge"`, `"onec"`, `"webhook"`, `"totp"`
- `credential_type` — e.g. `"api_key"`, `"password"`, `"app_password"`, `"secret"`, `"totp_secret"`
- `configured` — boolean: `true` if an active credential exists, `false` otherwise
- `status` — e.g. `"active"`, `"revoked"`, `"not_configured"`, `"rotation_pending"`
- `masked_hint` — safe display hint, e.g. `"****7a3f"` or `null` if not configured
- `last_tested_at` — ISO 8601 timestamp or `null`
- `last_test_status` — `"ok"`, `"failed"`, `"timeout"`, `"not_tested"` or `null`
- `last_used_at` — ISO 8601 timestamp or `null`
- `rotated_at` — ISO 8601 timestamp or `null`
- `revoked_at` — ISO 8601 timestamp or `null`
- `is_active` — boolean
- `message` — safe human-readable text, no secret values
- `reason` — safe reason string, no secret values
- `error_code` — safe error code string e.g. `"NOT_CONFIGURED"`, `"DECRYPTION_FAILED"`

### Forbidden Fields

The following fields must **never** appear in any `CredentialStatus` or public/status
API response, regardless of credential type:

| Forbidden Field | Reason |
|---|---|
| `api_key` | Raw Balance.ge API key — must never leave vault boundary |
| `raw_api_key` | Alias for raw key |
| `password` | Raw RS.ge or auth password — must never be returned |
| `app_password` | Raw email IMAP app password |
| `imap_password` | Alias for raw email credential |
| `rsge_password` | Alias for RS.ge raw password |
| `token` | Generic raw token |
| `access_token` | OAuth or session raw token |
| `refresh_token` | OAuth raw refresh token |
| `secret` | Generic raw secret |
| `webhook_secret` | Raw webhook HMAC signing secret |
| `totp_secret` | Raw TOTP setup secret (after initial setup only) |
| `encrypted_value` | Raw encrypted blob — not a safe field for API responses |
| `encrypted_secret` | Alias for encrypted blob |
| `decryption_key` | Encryption key material — must never leave key management |
| `private_key` | Private key material |
| `client_secret` | OAuth client secret |
| `authorization_header` | Raw bearer or basic auth header value |

This rule applies to all credential types:

- Balance.ge API key
- Email IMAP app password
- RS.ge portal password and username (username is partially identifying)
- 1C endpoint password
- Webhook HMAC signing secret
- TOTP setup secret (after initial setup step only)

---

## D) Internal Secret Use Rule

Raw decrypted secrets may exist only on the internal connector execution path,
in memory, for the duration of a single request. This is the only exception to
the no-raw-secret rule.

Rules:

1. Raw secrets must exist **in memory only** during execution — never written to a
   log, serialized to a response, or stored beyond the request lifecycle.
2. Only `ConnectorCredentialProvider` (defined in the interface contract) may call
   `CredentialVaultService.get_secret_for_connector_use()`.
3. Route handlers must never call `get_secret_for_connector_use()` directly.
4. Connectors may hold raw secrets in instance attributes (e.g. `self.api_key`)
   only for the duration of the request. The attribute must not be serialized,
   logged, or returned.
5. Raw secrets must not appear in exception messages, tracebacks, or error responses.
6. Raw secrets must not be passed to functions that log their arguments.

---

## E) Masked Hint Rule

`masked_hint` is a safe non-sensitive display hint. Rules:

1. `masked_hint` must be derived at **write time** — when the credential is saved
   or rotated. It must not require decrypting the stored value at read time.
2. Derivation: `"****" + last_4_chars` if `len(raw_secret) >= 8`, else `"****"`.
   Examples: `"****7a3f"`, `"****"`.
3. `masked_hint` must not allow reconstruction of the raw secret.
4. `masked_hint` must not expose the full key, token, or password in any form.
5. `masked_hint` may be `null` if the credential is `not_configured`.
6. `masked_hint` is the **only** partial secret representation allowed in any
   public response. No other partial representation is permitted.
7. `"configured"` and `"not_configured"` are valid status strings, not hint values.

---

## F) Logging and Error Rule

Every log line and exception in the credential lifecycle must comply with these
rules:

1. **Logs must not include raw secret fields.** No `api_key`, `password`,
   `app_password`, `totp_secret`, `webhook_secret`, `token`, or `encrypted_value`
   in any log at any log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
2. **Exceptions must be sanitized.** If decryption fails or a credential is missing,
   raise with a safe error code (`DECRYPTION_FAILED`, `NOT_CONFIGURED`) — not
   a partial secret value or stack trace containing the credential.
3. **Audit events must include action and result, not raw value.** Audit event
   metadata may include: `provider`, `credential_type`, `tenant_id`, `actor`,
   `request_id`, `ip_address`, `result`, `safe_error_code`. It must not include
   raw secrets, `encrypted_value`, or key material.
4. **Connector failure must not leak credentials.** If a connector call fails,
   the error response must contain only a safe error code and message. The raw
   API key, password, or secret must not appear in the error.

---

## G) Test Strategy

Task 10F-C tests in `tests/unit/test_masked_read_contract.py` validate this
contract using only:

- Reading doc files and asserting required content is present.
- Local test-only sample dicts (no DB, no runtime imports, no SQL).
- A recursive forbidden-field scanner implemented inside the test file.
- Assertions on allowed/forbidden field sets.

Tests must not:

- Import runtime app modules that trigger DB connections.
- Execute SQL.
- Connect to a database.
- Mock or patch runtime services.
- Change any runtime behavior.

---

## H) Future Implementation Scope

After this contract is in place, future implementation tasks must:

1. **Service layer sanitization**: `CredentialVaultService.get_credential_status()`
   must return only the allowed fields defined in Section C.
2. **Route handler updates**: All `/status` and read routes must call
   `CredentialVaultService.get_credential_status()` or `CredentialStatusService`,
   never `get_balance_credentials()`, `get_tenant_email_credentials()`, or
   `get_user_totp()` for public responses.
3. **Connector boundary**: Connectors must receive raw secrets only through
   `ConnectorCredentialProvider.get_*_for_use()`, not by calling service methods
   that return raw credential dicts.
4. **Credential type coverage**: Future tests must cover all credential types:
   - Balance.ge API key (`provider=balance`, `credential_type=api_key`)
   - Email IMAP app password (`provider=email`, `credential_type=app_password`)
   - RS.ge portal password (`provider=rsge`, `credential_type=password`)
   - 1C endpoint password (`provider=onec`, `credential_type=password`)
   - Webhook HMAC signing secret (`provider=webhook`, `credential_type=secret`)
   - TOTP setup secret (`provider=totp`, `credential_type=totp_secret`)
5. **RS.ge username**: The `username` field is partially identifying and must not
   appear in status responses after vault implementation (only `configured` bool).

---

## I) Explicit Non-Goals (This Task)

The following are explicitly deferred and must NOT be implemented in this task:

- No runtime behavior change.
- No migration or DDL change.
- No encryption implementation.
- No connector change.
- No auth or RBAC change.
- No Balance.ge activation.
- No production DB touch.
- No change to `balance_credentials_service.py`, `email_collector.py`,
  `totp_service.py`, `webhook_service.py`, any route files, or any connector.

**Balance.ge activation remains blocked** until all 12 gates in
`docs/balance-ge-activation-gate.md` are MET. All gates are currently NOT MET.

**No migration is created in this task.**

**No runtime code is changed in this task.**
