# Credential Vault Design

## A) Purpose

The Credential Vault is the security boundary between stored secrets and the
rest of Bridge Hub. It enforces a strict separation:

- **Internal connector use**: raw decrypted secrets are available only inside
  the connector execution path, in memory, for the duration of a single request.
- **Public/API responses**: only masked values, boolean status, or safe metadata
  are returned to any API caller.
- **Connector health checks**: status endpoints report `configured`,
  `not_configured`, `demo`, `last_test_status`, and `last_tested_at` — never
  raw credentials.
- **Audit-safe credential handling**: every credential lifecycle event is logged
  without including any secret value.

**This task does NOT implement encryption or change runtime credential behavior.**
This document defines the design target for future implementation.

No migration is created. No runtime code is changed. No production database is
touched. Balance.ge remains inactive.

---

## B) Current State

### Credential-Related Files Inspected

| File | Finding | Risk |
|---|---|---|
| `app/api/services/balance_credentials_service.py` | `api_key` stored and returned as plaintext TEXT. `get_balance_credentials()` returns raw `api_key` in dict. `get_credentials_status()` calls `get_balance_credentials()` internally but the underlying key is plaintext in the DB row. No vault boundary exists. | Critical |
| `app/api/routes_balance_credentials.py` | `/balance-credentials/status` calls `get_credentials_status()` which does not directly return `api_key`, but it calls the raw DB read path. `/balance-credentials/save` accepts raw `api_key` in request body and writes it to DB. `/balance-credentials/test` creates `BalanceConnector` which binds raw key to `self.api_key`. | High |
| `app/api/connectors/balance_connector.py` | Constructor calls `get_balance_credentials()` and assigns `self.api_key = creds.get("api_key", "")`. Raw API key is an instance attribute accessible throughout the request lifecycle. `_safe_headers_log()` does mask `Authorization` in debug logs — partial mitigation. | High |
| `app/api/connectors/onec_connector.py` | `self.password = os.environ.get("ONEC_PASSWORD", "")`. Global env var, not per-tenant. Raw password stored as instance attribute. No vault boundary. | Medium |
| `app/api/routes_rsge_credentials.py` | `password` stored plaintext to `tenant_rsge_credentials` table. `/rsge-credentials/status` returns `username` plaintext in API response — partial exposure. Table DDL is inline in the route file (runtime DDL). | Critical |
| `app/api/routes_2fa.py` | TOTP `secret` stored plaintext to `users.totp_secret` column via `UPDATE users SET totp_secret = %s`. Returned to client during setup step (correct for setup) but no encrypted-at-rest protection for the stored value. | High |
| `app/api/services/balance_credentials_service.py:ensure_table()` | `tenant_balance_credentials` table created with `api_key TEXT NOT NULL` — no encrypted column exists. | Critical |

### Known Risks Summary

1. **Plaintext `api_key` in DB**: `tenant_balance_credentials.api_key` stores the
   Balance.ge API key as plaintext TEXT. Any DB read, backup, or log of this table
   exposes the credential.

2. **Raw secret returned to callers**: `get_balance_credentials()` returns
   `{"api_key": raw_key, ...}`. Callers receive the raw key without going through
   any vault boundary.

3. **Connector reads credentials directly**: `BalanceConnector.__init__()` calls
   `get_balance_credentials()` and stores the raw key in `self.api_key`. There is
   no `ConnectorCredentialProvider` boundary.

4. **RS.ge `username` in status API response**: `routes_rsge_credentials.py`
   `/status` endpoint returns `{"username": row["username"]}` — the username is
   partially identifying data. The `password` is not returned but is stored
   plaintext in DB.

5. **1C credentials from global env**: `OneCConnector` reads `ONEC_PASSWORD`
   directly from environment variables. All tenants share the same 1C credential.
   No per-tenant isolation.

6. **TOTP secret plaintext at rest**: `users.totp_secret` stores the TOTP secret
   as a plaintext TEXT column. If the DB is compromised, all TOTP secrets are
   exposed.

7. **No `CredentialVaultService` boundary**: any function can call
   `get_balance_credentials()` and receive the raw key. There is no enforced
   separation between internal use and public reads.

8. **No `CredentialStatusService`**: each credential type has its own ad-hoc
   status response shape. Some expose more than they should.

9. **Missing rotation metadata**: `tenant_balance_credentials` has no
   `rotated_at`, `last_used_at`, `last_tested_at`, or `key_version` columns.

**Balance.ge remains inactive** (no `BALANCE_API_KEY` in production environment).
**Production DB untouched** by this task.

---

## C) Target Credential Vault Architecture

The Credential Vault is composed of six components with strict dependency rules:

```
┌─────────────────────────────────────────────────────────────┐
│                   PUBLIC API LAYER                           │
│  Routes → CredentialStatusService → CredentialStatus (safe) │
└──────────────────────────┬──────────────────────────────────┘
                           │ (status only, no raw secret)
┌──────────────────────────▼──────────────────────────────────┐
│              CredentialVaultService                          │
│  store_secret / rotate_secret / revoke_secret / test_secret │
└──────┬───────────────────────────────────────────────┬──────┘
       │ (encrypted blob only)                         │ (audit events)
┌──────▼──────────┐                         ┌──────────▼──────────┐
│ CredentialRepo  │                         │ CredentialAuditLogger│
│ (DB read/write) │                         │ (no raw secrets)    │
└──────┬──────────┘                         └─────────────────────┘
       │ (encrypted_value)
┌──────▼────────────────┐
│  SecretCryptoProvider │
│  encrypt / decrypt    │
│  mask                 │
└──────┬────────────────┘
       │ (raw secret in memory only)
┌──────▼──────────────────────────┐
│  ConnectorCredentialProvider    │
│  get_*_for_use() → connector    │
│  (raw secret never stored)      │
└─────────────────────────────────┘
```

### Component Descriptions

**CredentialVaultService**
The central orchestrator. Callers request operations through this service.
It never returns raw secrets to non-connector callers. It delegates storage to
`CredentialRepository`, encryption to `SecretCryptoProvider`, and audit events
to `CredentialAuditLogger`.

**SecretCryptoProvider**
Handles all encryption and decryption. Responsible for:
- `encrypt(raw_secret, tenant_id, provider, key_version)` → `encrypted_value`
- `decrypt(encrypted_value, tenant_id, provider, key_version)` → `raw_secret`
- `mask(raw_secret_or_metadata)` → `"****xxxx"` hint

Raw secrets must not leave this component except to the connector execution path.

**CredentialRepository**
Handles all DB reads and writes for credential records. Only stores and retrieves
`encrypted_value`, `key_version`, and metadata. Never stores or returns the
decrypted secret directly.

**CredentialStatusService**
Provides the public-safe status view of a credential. Returns only:
`configured`, `not_configured`, `status`, `masked_hint`, `last_tested_at`,
`last_test_status`, `last_used_at`, `rotated_at`, `is_active`. Never includes
any raw secret, `encrypted_value`, or decryption key.

**ConnectorCredentialProvider**
The only internal path that receives a decrypted secret. Called by connector
constructors or execution methods. The decrypted secret is held in memory only
for the duration of the connection/request and must not be stored, logged, or
returned.

**CredentialAuditLogger**
Logs all credential lifecycle events without including any secret value. Events
include: store, update, rotate, revoke, test (pass/fail), use, and failed access.
Each event includes: actor, tenant_id, provider, credential_type, action, result,
and timestamp.

---

## D) Secret Storage Model

Future `tenant_secrets` or per-provider credential tables must contain:

| Column | Type | Purpose |
|---|---|---|
| `id` | SERIAL PRIMARY KEY | Record identity |
| `tenant_id` | TEXT NOT NULL | Tenant ownership — every credential is tenant-scoped |
| `provider` | TEXT NOT NULL | `balance`, `email`, `rsge`, `onec`, `webhook`, `totp` |
| `credential_type` | TEXT NOT NULL | `api_key`, `password`, `app_password`, `secret`, `totp_secret` |
| `encrypted_value` | TEXT | Encrypted credential value (GCP Secret Manager reference or AES-256-GCM ciphertext) |
| `key_version` | TEXT | Encryption key version identifier for rotation |
| `masked_hint` | TEXT | Safe display hint only — e.g. `"****7a3f"` — derived at write time |
| `status` | TEXT | `active`, `revoked`, `rotation_pending`, `test_failed` |
| `is_active` | BOOLEAN DEFAULT TRUE | Quick filter for active credentials |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | Creation timestamp |
| `updated_at` | TIMESTAMPTZ DEFAULT NOW() | Last update timestamp |
| `rotated_at` | TIMESTAMPTZ | Last rotation timestamp |
| `last_used_at` | TIMESTAMPTZ | Last time credential was decrypted for use |
| `revoked_at` | TIMESTAMPTZ | Revocation timestamp if revoked |
| `created_by` | TEXT | Actor who created this credential |
| `updated_by` | TEXT | Actor who last updated this credential |
| `last_tested_at` | TIMESTAMPTZ | Last time credential was tested |
| `last_test_status` | TEXT | `ok`, `failed`, `timeout`, `not_tested` |

**What must NOT be stored:**
- Raw/plaintext secret values
- Decryption keys in the same table as encrypted values
- Logs of decrypted secrets

---

## E) Separation of Use Cases

Five distinct paths exist, each with different access rights and response shapes:

### 1. Internal Connector Use: `get_secret_for_connector_use()`

- Caller: `ConnectorCredentialProvider` → connector constructor or execution
- Returns: raw decrypted secret, in memory only
- Restrictions: must never be called from route handlers directly; must never
  return the secret to any API response; must log a `use` audit event
- Audit event includes: tenant_id, provider, credential_type, purpose, actor,
  timestamp — but NOT the secret value

### 2. Public Status Read: `get_credential_status()`

- Caller: route handlers, settings UI
- Returns: `CredentialStatus` (safe fields only — see Section C)
- Restrictions: never returns `encrypted_value`, raw secret, or decryption key
- Response shape:
  ```json
  {
    "provider": "balance",
    "credential_type": "api_key",
    "status": "active",
    "configured": true,
    "masked_hint": "****7a3f",
    "last_tested_at": "2026-05-10T09:00:00Z",
    "last_test_status": "ok",
    "last_used_at": "2026-05-10T08:30:00Z",
    "rotated_at": null,
    "is_active": true
  }
  ```
  If not configured:
  ```json
  {
    "provider": "balance",
    "credential_type": "api_key",
    "status": "not_configured",
    "configured": false,
    "masked_hint": null,
    "last_tested_at": null,
    "last_test_status": "not_tested",
    "last_used_at": null,
    "rotated_at": null,
    "is_active": false
  }
  ```

### 3. Admin Test: `test_credential_connection()`

- Caller: admin route handler
- Action: decrypts credential in memory, makes test request to provider, returns
  pass/fail and safe error code only
- Returns: `{"success": true/false, "error_code": "...", "error_message": "..."}`
- Never returns the credential value in response
- Logs a `test` audit event with result

### 4. Rotation: `rotate_credential()`

- Caller: admin route handler with actor_id
- Action: encrypts new secret, writes new record, updates `rotated_at`,
  invalidates old key version
- Returns: updated `CredentialStatus` (safe)
- Logs `rotate` audit event without secrets

### 5. Revocation: `revoke_credential()`

- Caller: admin route handler with actor_id
- Action: sets `is_active = FALSE`, sets `revoked_at`, sets `status = revoked`
- Returns: confirmation without secrets
- Logs `revoke` audit event

---

## F) Masking Rules

The following rules apply throughout the vault layer:

- **Never return a raw secret** in any API response, log line, exception message,
  or debug output after the initial setup step.
- **Return `configured: true` or `configured: false`** as the primary status signal.
- **Return `masked_hint`** only if it was derived and stored at write time from the
  last 4 characters of the raw secret. Do not derive the hint by decrypting at
  read time.
- **No full API key, password, token, or secret** in any log at any level (DEBUG,
  INFO, WARNING, ERROR). Log only the tenant, provider, and safe error codes.
- **No raw secret in exceptions**: if decryption fails, raise an internal error with
  a safe code (`DECRYPTION_FAILED`), not the partial secret value.
- **TOTP setup exception**: during the initial TOTP setup step, the secret may be
  returned once in the setup response. After setup is confirmed, the status endpoint
  must return only `{"totp_enabled": true}`. The setup secret must never appear again.

---

## G) Audit Rules

Every credential lifecycle event must create an audit record:

| Event | When |
|---|---|
| `credential_stored` | New credential saved |
| `credential_updated` | Credential value replaced |
| `credential_rotated` | Key rotated, new version active |
| `credential_revoked` | Credential deactivated |
| `credential_tested` | Connection test performed |
| `credential_used` | Secret decrypted for connector use |
| `credential_test_failed` | Connection test returned failure |
| `credential_access_denied` | Unauthorized access attempt |

Each audit record must include:
- `actor` (user_id or system identifier)
- `tenant_id`
- `provider` (`balance`, `email`, `rsge`, `onec`, `webhook`, `totp`)
- `credential_type` (`api_key`, `password`, `secret`)
- `action` (event name above)
- `result` (`ok`, `failed`, `denied`)
- `timestamp`
- `safe_error_code` if applicable

Each audit record must NOT include:
- Raw secret value
- Encrypted value
- Decryption key
- Password hash
- TOTP secret

---

## H) Connector Rules

After vault implementation:

- Connectors must receive secrets **only** through `ConnectorCredentialProvider`.
- Connectors must **not** read raw DB credential fields directly.
- `BalanceConnector.__init__()` must call `ConnectorCredentialProvider.get_balance_credentials_for_use()` instead of `get_balance_credentials()`.
- Status endpoints must call `CredentialStatusService.get_credential_status()`.
- The connector may hold the raw secret in `self.api_key` **only** for the
  duration of a request. It must not serialize, log, or return this value.
- **Balance.ge must stay inactive** until all 12 activation gates pass
  (see `docs/balance-ge-activation-gate.md`). No connector change in this task.

---

## I) Migration / Implementation Deferral

This task is design and documentation only. The following are explicitly deferred:

- **No migration**: no `encrypted_value` or `key_version` column is added in
  this task. The existing `tenant_balance_credentials.api_key` column remains
  as-is.
- **No encryption implementation**: the `SecretCryptoProvider` interface is
  defined here but not implemented.
- **No runtime behavior change**: `balance_credentials_service.py`,
  `routes_balance_credentials.py`, `routes_rsge_credentials.py`,
  `routes_2fa.py`, `balance_connector.py`, and `onec_connector.py` are not
  changed in this task.
- **Future migration must be additive-only**: add `encrypted_value` and
  `key_version` as nullable columns first; backfill encrypted values; switch
  read path; null out plaintext columns in a separate step; never use DROP in
  the same migration as the data migration.

---

## J) Rollout Plan

1. **10F-B** (this task): design document + interface contract + tests.
2. **10F-C**: masked read behavior tests — unit tests proving each credential
   type's API never returns raw secrets.
3. **11C-A**: encryption implementation — add `encrypted_value` columns, integrate
   `SecretCryptoProvider`, update `CredentialRepository`, switch service layer.
4. Shadow read: deploy with both plaintext and encrypted columns; read from
   encrypted, write to both; verify in staging.
5. Masked read implementation: update route handlers to call
   `CredentialStatusService` instead of raw service functions.
6. Connector refactor: replace direct credential reads with
   `ConnectorCredentialProvider`.
7. Audit event wiring: connect `CredentialAuditLogger` to all lifecycle events.
8. Staging verification: full vault round-trip test on staging tenant.
9. Live gate verification: all 12 gates in `docs/balance-ge-activation-gate.md`
   must be verified before Balance.ge activation.

---

## K) Rollback / No-Op Strategy

**In this task (10F-B):** no runtime change — nothing to roll back.

**In future implementation tasks:**
- Encryption columns are additive (nullable). If implementation fails, the old
  plaintext path still works. Rollback = deploy previous version.
- If `SecretCryptoProvider` fails at runtime: return `DECRYPTION_FAILED` error
  code. Do not fall back to plaintext. Do not crash.
- If connector tests fail after connector refactor: revert connector to use
  previous credential read path (plaintext). Deploy as hotfix. Re-attempt vault
  integration after root cause is identified.
- **Balance.ge activation remains blocked** until all 12 gates pass and rollback
  strategy is documented per gate.
