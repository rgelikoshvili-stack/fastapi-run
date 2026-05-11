# Credential Vault Runtime Architecture and Migration Plan

## A) Purpose

Task 11C-B defines the authoritative credential vault runtime architecture and
migration plan before any vault runtime implementation begins.

This document is the implementation specification for Task 11C-C. It defines:
- Exact future schema changes required for the credential vault.
- Staged migration strategy.
- Runtime service component responsibilities and boundaries.
- Masked read enforcement rules.
- Connector credential access boundary.
- Key management, audit, and rotation requirements.
- Error model.
- Allowed and forbidden files for 11C-C.
- Test strategy and rollback strategy for 11C-C.
- Stop conditions.

**This task is documentation and tests only.**
**This task does NOT implement runtime code.**
**This task does NOT create migrations.**
**This task does NOT touch the production database.**
**This task does NOT run SQL.**
**This task does NOT change credentials.**
**This task does NOT activate Balance.ge.**
**This task does NOT start 11C-C implementation.**

Cross-references:
- `docs/credential-vault-design.md` — high-level vault design
- `docs/credential-vault-interface-contract.md` — pseudocode service interface
- `docs/masked-read-behavior-contract.md` — masked read behavior contract
- `docs/balance-ge-activation-final-checklist.md` — Balance.ge gate checklist
- `docs/trust-foundation-runtime-implementation-sequence.md` — 11C task order

---

## B) Current Baseline

As of main HEAD `f185c0ab137850a8eadfb48938cf79db4553ce58` (Task 11C-A live):

| Item | Current State |
|---|---|
| Balance.ge status | **DEMO** — `BALANCE_API_KEY` absent from production environment |
| Live /health `BALANCE_API_KEY` | `missing` |
| `tenant_balance_credentials.api_key` | **Plaintext TEXT column** — no encryption |
| `tenant_balance_credentials.encrypted_value` | **Does not exist** |
| `tenant_balance_credentials.key_version` | **Does not exist** |
| `tenant_balance_credentials.masked_hint` | **Does not exist** |
| `tenant_balance_credentials.rotated_at` | **Does not exist** |
| `tenant_balance_credentials.last_accessed_at` | **Does not exist** |
| `get_balance_credentials()` return value | Returns raw `api_key` in dict — **security gap** |
| `get_credentials_status()` return value | Omits raw `api_key` but leaks `source` |
| `CredentialVaultService` | **Does not exist** |
| `SecretCryptoProvider` | **Does not exist** |
| Masked read runtime enforcement | **NOT implemented** |
| Credential vault design | Defined in `docs/credential-vault-design.md` only |
| 10F-H GATE-01 | **NOT MET** — vault not implemented |
| 10F-H GATE-02 | **NOT MET** — credentials stored as plaintext |
| 10F-H GATE-03 | **NOT MET** — masked reads not enforced at runtime |
| 11C-C implementation | **NOT started** |

---

## C) Target Architecture — Components

### CredentialVaultService

**Responsibility:** Central orchestrator for all credential lifecycle operations.
All other services that need credentials must call this service — no direct DB
queries for credential values.

**Allowed callers:** `balance_connector.py` (via `ConnectorCredentialProvider`),
admin credential management routes, credential rotation jobs.

**Forbidden behavior:** Must never return raw decrypted secret to any API caller.
Must never log raw secret. Must never store raw secret after encrypting.

**Inputs:** `tenant_id`, `provider`, `credential_type`, `raw_secret` (for write),
`actor`, `purpose`.

**Outputs:** `CredentialStatus` (for reads/writes), decrypted secret only to
`ConnectorCredentialProvider` internal path, masked hint for status path.

**Audit behavior:** Every call is logged via `CredentialAuditLogger` without
raw secret.

---

### SecretCryptoProvider

**Responsibility:** Encrypts and decrypts secret values. Uses AES-256-GCM or
equivalent authenticated encryption. Never stores the key — receives it from
`KeyProvider` on each operation.

**Allowed callers:** `CredentialVaultService` only.

**Forbidden behavior:** Must not cache decrypted values. Must not log plaintext.

**Inputs:** `raw_secret` (encrypt) or `encrypted_value` + `key_version` (decrypt).

**Outputs:** `encrypted_value` + `key_version` (encrypt), `raw_secret` in memory
only (decrypt).

**TEST_MODE:** In `TEST_MODE=1`, uses a deterministic test key
(`b"test-key-32bytes-for-unit-tests!"`) so unit tests can exercise roundtrip
without production key material. Production key path must not use this key.

---

### KeyProvider

**Responsibility:** Provides the encryption key for a given `key_version`. In
production, reads from GCP Secret Manager or an approved secret store. In
`TEST_MODE`, returns the deterministic test key. Never returns a key to any
caller other than `SecretCryptoProvider`.

**Allowed callers:** `SecretCryptoProvider` only.

**Forbidden behavior:** Must not expose key material in logs, responses, or errors.

**Inputs:** `key_version` (string).

**Outputs:** Raw key bytes, in memory only.

**Audit behavior:** Key access is logged (version only, not key value).

---

### CredentialRepository

**Responsibility:** Reads and writes credential records to the database.
Never returns `encrypted_value` directly to callers outside the vault service.
Returns raw encrypted bytes only to `SecretCryptoProvider` for decryption.

**Allowed callers:** `CredentialVaultService` only.

**Forbidden behavior:** Must not expose `encrypted_value` outside the vault
service boundary. Must not perform encryption or decryption.

**Inputs:** `tenant_id`, `provider`, `credential_type` (read); full credential
record (write).

**Outputs:** Credential record metadata (status, masked_hint, timestamps) for
non-connector callers; encrypted bytes to `SecretCryptoProvider` for connector
path.

---

### CredentialStatusProvider

**Responsibility:** Returns public-safe credential status for API/status
endpoints. Returns only: `configured`, `not_configured`, `demo`, `masked_hint`,
`last_test_status`, `last_tested_at`, `status`.

**Allowed callers:** Status API routes, health check routes, settings UI routes.

**Forbidden behavior:** Must never return `api_key`, `encrypted_value`,
`password`, `token`, or any secret field. Must never call `SecretCryptoProvider`.

**Inputs:** `tenant_id`, `provider`, `credential_type`.

**Outputs:** `CredentialStatusResponse` with only safe fields.

---

### ConnectorCredentialProvider

**Responsibility:** Provides the raw decrypted secret to connector runtime code
(e.g., `BalanceConnector`) for the duration of a single connector execution.
Secret is held in memory only — never returned to callers outside the connector.

**Allowed callers:** `BalanceConnector`, `OnecConnector`, and other ERP
connectors that require live credentials.

**Forbidden behavior:** Must not return raw secret to any API route or response
object. Must not cache decrypted secret across requests.

**Inputs:** `tenant_id`, `provider`, `credential_type`, `actor`, `purpose`.

**Outputs:** Raw decrypted secret, in memory only for connector use.

**Audit behavior:** Access logged via `CredentialAuditLogger` (no secret value).

---

### CredentialAuditLogger

**Responsibility:** Logs every credential lifecycle event to the audit log or
a dedicated credential audit table. Never includes secret values.

**Allowed callers:** All vault service components.

**Forbidden behavior:** Must never include `api_key`, `encrypted_value`,
`password`, `token`, or any secret in the log record.

**Required fields per log entry:**
- `tenant_id`
- `provider`
- `credential_type`
- `actor`
- `purpose` (e.g., `connector_execution`, `status_check`, `rotation`, `save`)
- `result` (`success`, `failure`, `not_found`, `disabled`)
- `timestamp`
- `key_version` (for decrypt/encrypt operations)
- `request_id` (if available from request context)

---

### MaskedCredentialFormatter

**Responsibility:** Derives the `masked_hint` from a raw secret value at save
time. Format: `****` + last 4 characters of the secret (e.g., `****xYz9`).
If secret is shorter than 8 characters, returns `****` only.

**Allowed callers:** `CredentialVaultService` (at save time only, before
discarding raw secret).

**Forbidden behavior:** Must not be called with raw secret at read time. The
`masked_hint` is computed once at save and stored — never recomputed from the
encrypted value at read time.

**Inputs:** `raw_secret` (string).

**Outputs:** `masked_hint` (string, e.g. `****xYz9`).

---

### CredentialRotationService

**Responsibility:** Manages credential rotation. Decrypts the old value using
the old `key_version`, re-encrypts with the current key, updates `key_version`,
`rotated_at`, and `masked_hint`. Optionally accepts a new raw secret to replace
the old one.

**Allowed callers:** Admin rotation endpoint, automated rotation job.

**Forbidden behavior:** Must not expose old or new raw secret in any response or
log. Must not leave the credential in an inconsistent state (all-or-nothing
transaction).

**Inputs:** `tenant_id`, `provider`, `credential_type`, `new_raw_secret`
(optional — if absent, re-encrypt only), `actor`.

**Outputs:** Updated `CredentialStatus` with new `key_version` and `rotated_at`.

**Audit behavior:** Rotation event logged with old `key_version`, new
`key_version`, `actor`, and `timestamp` — no secret values.

---

## D) Future Schema Plan

The following describes the target schema for the credential vault table.
This replaces or extends `tenant_balance_credentials`.
**No migration is created in this task (11C-B). Migration is authorized for 11C-C.**

### Target table: `credential_vault`

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL PRIMARY KEY` | Auto-increment row ID |
| `tenant_id` | `TEXT NOT NULL` | Tenant identifier |
| `provider` | `TEXT NOT NULL` | e.g. `balance`, `email`, `rsge`, `onec` |
| `credential_type` | `TEXT NOT NULL` | e.g. `api_key`, `password`, `app_password` |
| `encrypted_value` | `TEXT` | AES-256-GCM ciphertext, base64-encoded; NULL until migration |
| `key_version` | `TEXT` | Key version used to encrypt `encrypted_value` |
| `masked_hint` | `TEXT` | e.g. `****xYz9`; derived at save time only |
| `status` | `TEXT` | `active`, `disabled`, `pending_rotation` |
| `active` | `BOOLEAN DEFAULT TRUE` | Quick disable flag |
| `company_id` | `TEXT` | Balance.ge company identifier |
| `api_base` | `TEXT DEFAULT 'https://api.balance.ge'` | Connector endpoint |
| `last_test_status` | `TEXT` | `ok`, `failed`, `untested` |
| `last_tested_at` | `TIMESTAMPTZ` | Timestamp of last connectivity test |
| `last_accessed_at` | `TIMESTAMPTZ` | Timestamp of last connector use |
| `rotated_at` | `TIMESTAMPTZ` | Timestamp of last rotation |
| `created_at` | `TIMESTAMPTZ DEFAULT NOW()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ DEFAULT NOW()` | Record update timestamp |
| `created_by` | `TEXT` | Actor who created the credential |
| `updated_by` | `TEXT` | Actor who last updated the credential |

**Unique constraint:** `(tenant_id, provider, credential_type)`

### Plaintext api_key transition plan

The existing `tenant_balance_credentials.api_key` (plaintext TEXT) must be
handled as follows:

1. **Do not read `api_key` in any public/status API response after vault is live.**
2. **Explicit migration task:** Copy `api_key` → encrypt → store in `encrypted_value`
   only through the vault migration task (within 11C-C, explicitly authorized).
3. **After encrypted migration verified:** Null the plaintext `api_key` column.
4. **After null verified on production:** Remove column in a follow-up migration.
5. **No raw `api_key` value in tests, docs, PR bodies, or logs at any step.**

---

## E) Migration Strategy for 11C-C

The credential vault migration must follow this staged approach:

| Phase | Label | Scope |
|---|---|---|
| Phase 0 | `docs_tests_only` | 11C-B — this document and tests only |
| Phase 1 | `additive_encrypted_fields` | Add `encrypted_value`, `key_version`, `masked_hint`, `status`, `rotated_at`, `last_accessed_at`, `created_by`, `updated_by` to existing table or create new `credential_vault` table — additive only, no column removal |
| Phase 2 | `crypto_provider_test_mode` | Implement `SecretCryptoProvider` with `TEST_MODE` deterministic key; unit tests only, no production key |
| Phase 3 | `write_through_encrypted_service` | New `save_credential()` calls write to `encrypted_value` immediately; old `api_key` also written for backward compatibility during transition |
| Phase 4 | `connector_internal_decrypt_path` | `ConnectorCredentialProvider` reads `encrypted_value`, decrypts in memory; connector no longer reads `api_key` directly |
| Phase 5 | `masked_status_path` | `CredentialStatusProvider` returns `configured`/`demo`/`masked_hint` — raw `api_key` never returned by any public endpoint |
| Phase 6 | `migrate_plaintext_to_encrypted_value` | Explicit controlled migration of existing plaintext `api_key` rows to `encrypted_value` |
| Phase 7 | `null_plaintext_api_key` | After evidence and backup verified: null `api_key` column for all migrated rows |
| Phase 8 | `remove_plaintext_dependency` | After live verification and backup: remove `api_key` column in explicit migration |

**Rules for every migration step:**
- No production SQL manual execution.
- No live credential values in tests or test fixtures.
- No Balance.ge activation at any migration phase.
- Every phase is additive before destructive — no column removal before backup.
- Every phase requires targeted tests passing before deployment.
- `11C-C may create Phase 1 migration only if explicitly authorized in the task.`
- Phases 2–8 require separate explicit authorization per phase.

---

## F) Runtime Service Interface

These are pseudocode specifications — they define the future implementation
target and are not runtime code in this document.

### `save_credential(tenant_id, provider, credential_type, raw_value, metadata, actor)`

- **Classification:** Internal admin only — must not be callable from public API
  without authentication and authorization check.
- **Raw secret returned:** Never — raw value is encrypted immediately and
  discarded from memory after encryption.
- **Audit:** Required — log `tenant_id`, `provider`, `credential_type`, `actor`,
  `result` without logging `raw_value`.
- **Error codes:** `CREDENTIAL_ROTATION_FAILED` on encrypt failure;
  `CREDENTIAL_ACCESS_DENIED` if caller not authorized.

### `get_for_connector(tenant_id, provider, credential_type, actor, purpose)`

- **Classification:** Internal connector path only — not exposed as an API endpoint.
- **Raw secret returned:** Yes — decrypted secret returned to connector in memory
  only for the duration of connector execution.
- **Audit:** Required — log access event without secret value.
- **Error codes:** `CREDENTIAL_NOT_FOUND`, `CREDENTIAL_DISABLED`,
  `CREDENTIAL_DECRYPT_FAILED`, `CREDENTIAL_PROVIDER_NOT_CONFIGURED`.

### `get_status(tenant_id, provider, credential_type)`

- **Classification:** Public — safe for API/settings/status endpoints.
- **Raw secret returned:** Never — returns `configured`/`not_configured`/`demo`,
  `masked_hint`, `last_test_status`, `last_tested_at` only.
- **Audit:** Optional (status check frequency may make full auditing impractical;
  at minimum log on first access per session).
- **Error codes:** `CREDENTIAL_STATUS_UNAVAILABLE` on DB error.

### `rotate_credential(tenant_id, provider, credential_type, new_raw_value, actor)`

- **Classification:** Internal admin/rotation job only.
- **Raw secret returned:** Never — new value encrypted immediately, old value
  decrypted only in memory during rotation.
- **Audit:** Required — log old `key_version`, new `key_version`, `actor`,
  `timestamp`. No secret values.
- **Error codes:** `CREDENTIAL_NOT_FOUND`, `CREDENTIAL_ROTATION_FAILED`.

### `disable_credential(tenant_id, provider, credential_type, actor)`

- **Classification:** Internal admin only.
- **Raw secret returned:** Never.
- **Audit:** Required.
- **Error codes:** `CREDENTIAL_NOT_FOUND`, `CREDENTIAL_ACCESS_DENIED`.
- **Effect:** Sets `active = FALSE` and `status = disabled`. Connector will
  receive `CREDENTIAL_DISABLED` error on next execution attempt.

### `audit_access(tenant_id, provider, credential_type, actor, purpose, result)`

- **Classification:** Internal — called by all vault service components.
- **Raw secret returned:** Never.
- **Audit:** This IS the audit call — writes the audit record.
- **Error codes:** None — audit failures must not block the primary operation.

---

## G) Masked Read Rules

These rules apply at runtime once the vault is implemented:

1. **API and status endpoints MUST NEVER return raw `api_key`, `password`,
   `token`, `secret`, or `encrypted_value` fields in any JSON response.**

2. **Public/status credential response MAY contain:**
   - `configured` (boolean)
   - `status` (`active`, `disabled`, `demo`, `not_configured`)
   - `masked_hint` (e.g. `****xYz9`)
   - `last_test_status`
   - `last_tested_at`
   - `provider`
   - `company_id` (non-secret metadata)
   - `api_base` (non-secret metadata)

3. **Connector internal path MAY receive** the raw decrypted secret, but only:
   - Through `ConnectorCredentialProvider` only.
   - In memory only — never persisted or returned.
   - For the duration of a single request only.

4. **Logs and exceptions MUST NEVER include raw secrets.** Exception messages
   must be sanitized before logging. If a raw secret appears in a log, it is a
   P0 security incident.

5. **Tests MUST scan status API responses** and assert that no response body
   contains the strings `api_key`, `password`, `token`, `secret`, or any value
   matching the test credential pattern.

6. **Masked hint is computed once at save time** and stored. It is never
   recomputed from the encrypted value at read time.

---

## H) Connector Boundary

Once the credential vault is implemented (11C-C onwards):

1. **`balance_connector.py` MUST NOT read `os.environ["BALANCE_API_KEY"]` for
   production credentials.** The environment variable fallback may be retained
   for demo/test detection only (empty string = demo mode).

2. **`balance_connector.py` MUST receive credentials only through
   `ConnectorCredentialProvider`.** It must not call `get_balance_credentials()`
   directly — that service will be replaced by vault calls.

3. **Dry-run and payload preview** remain separate future tasks (11C-K). The
   credential vault implementation (11C-C) does not add dry-run support.

4. **No live Balance.ge API call in 11C-B or 11C-C.** The connector must remain
   in `demo_mode` throughout vault implementation.

5. **Balance.ge live activation remains blocked until 11C-L** and all 14 gates
   in `docs/balance-ge-activation-final-checklist.md` are MET.

6. **After vault implementation**, if `ConnectorCredentialProvider` returns
   `CREDENTIAL_DISABLED` or `CREDENTIAL_NOT_FOUND`, the connector must:
   - Return `demo_mode` response, not a hard crash.
   - Log the event via `CredentialAuditLogger`.
   - NOT proceed with a live API call.

---

## I) Key Management

1. **TEST_MODE key:** In `TEST_MODE=1`, `KeyProvider` uses a deterministic
   32-byte test key (`b"test-key-32bytes-for-unit-tests!"`) to enable
   encryption roundtrip testing without production key material.
   This key MUST be hardcoded only for test use and MUST NOT be used in
   production or staging environments.

2. **Production key source:** Must come from GCP Secret Manager or an
   equivalent approved secret store. The key must never be stored in:
   - Environment variables as plaintext.
   - `.env` files in the repository.
   - Application source code outside `KeyProvider.TEST_MODE` branch.
   - Cloud Run environment variable console as plaintext.

3. **No hardcoded production key.** Any production key found in source code,
   commits, or PR bodies is a P0 security incident requiring immediate rotation.

4. **`key_version` storage:** Every encrypted credential stores the `key_version`
   used to encrypt it. This enables key rotation without re-encrypting all rows
   at once.

5. **Rotation support:** `CredentialRotationService` must:
   - Decrypt old value using `key_version` from the credential record.
   - Encrypt new value using the current active key.
   - Update `key_version`, `rotated_at`, and `masked_hint` atomically.
   - Log the rotation event (old version, new version, actor, timestamp).

6. **Key access auditing:** Every call to `KeyProvider.get_key(key_version)` is
   logged with the `key_version` only — not the key value.

---

## J) Audit Requirements

Every credential lifecycle event must be logged with the following fields.
Raw secret values must never appear in any audit record.

| Field | Required | Notes |
|---|---|---|
| `tenant_id` | Yes | Tenant that owns the credential |
| `provider` | Yes | e.g. `balance`, `email` |
| `credential_type` | Yes | e.g. `api_key`, `password` |
| `actor` | Yes | User ID or service name performing the action |
| `purpose` | Yes | e.g. `connector_execution`, `rotation`, `save`, `disable`, `status_check` |
| `result` | Yes | `success`, `failure`, `not_found`, `disabled` |
| `timestamp` | Yes | UTC timestamp |
| `key_version` | Yes (for encrypt/decrypt) | Key version used — not the key itself |
| `request_id` | If available | Correlation ID from request context |
| `raw_secret` | **NEVER** | Must not appear in any log record |
| `encrypted_value` | **NEVER** | Must not appear in any log record |

Audit events must be written as structured JSON log entries. They must not
block the primary operation if writing fails.

---

## K) Error Model

| Error Code | Meaning | HTTP Equivalent |
|---|---|---|
| `CREDENTIAL_NOT_FOUND` | No credential record exists for this tenant/provider/type | 404 |
| `CREDENTIAL_DISABLED` | Credential exists but `active = FALSE` | 403 |
| `CREDENTIAL_DECRYPT_FAILED` | Encrypted value could not be decrypted (key mismatch, corruption) | 500 |
| `CREDENTIAL_PROVIDER_NOT_CONFIGURED` | Vault service or key provider not initialized | 503 |
| `CREDENTIAL_ACCESS_DENIED` | Caller does not have permission to access this credential | 403 |
| `CREDENTIAL_ROTATION_FAILED` | Rotation could not complete atomically | 500 |
| `CREDENTIAL_STATUS_UNAVAILABLE` | DB or vault service temporarily unavailable for status query | 503 |

All errors must:
- Use the standard Bridge Hub error envelope `{"ok":false,"error":{"code":"...","details":"..."}}`.
- Include `details` field with context but NO secret values.
- Be logged via `CredentialAuditLogger`.

---

## L) Allowed / Forbidden Files for 11C-C

### Allowed (future 11C-C, requires explicit task authorization):

| File | Purpose |
|---|---|
| `app/api/services/credential_vault_service.py` (new) | `CredentialVaultService` implementation |
| `app/api/services/secret_crypto_provider.py` (new) | `SecretCryptoProvider` + `KeyProvider` |
| `app/api/services/balance_credentials_service.py` | Update read/write path to use vault |
| `app/api/connectors/balance_connector.py` | Redirect credential access to `ConnectorCredentialProvider` only (no live activation) |
| `app/storage/migrations/<vault_migration>.sql` | Phase 1 additive migration only (if explicitly authorized) |
| `tests/unit/test_credential_vault_runtime.py` (new) | Encryption roundtrip, masked status, audit tests |
| `tests/unit/test_masked_read_runtime.py` (new) | Status endpoint scan for raw secrets |

### Forbidden for 11C-C unless explicitly re-authorized:

| File | Reason |
|---|---|
| `app/api/services/posting_service.py` | Must not change posting behavior |
| `app/api/services/approval_service.py` | Must not change approval behavior |
| `app/api/services/financial_statements_service.py` | Must not change report behavior |
| `app/api/middleware/` | Rate-limit and subscription enforcement are separate tasks |
| `main.py` (beyond middleware registration) | No structural app changes |
| `.env` files | No credential changes |
| `.github/workflows/*` | No CI/CD changes |
| Production DB direct SQL | No manual SQL |
| Cloud Run environment variables | No credential injection via console |

---

## M) Test Strategy for 11C-C

Required unit tests for the future 11C-C implementation:

| Test | Purpose |
|---|---|
| Encryption roundtrip | `SecretCryptoProvider.encrypt(secret)` → `decrypt()` returns original secret using TEST_MODE key |
| Masked status never returns raw secret | `get_status()` response scan: no `api_key`, `password`, `token`, `secret` fields present |
| Connector internal path receives decrypted secret | `ConnectorCredentialProvider.get_for_connector()` returns raw secret to connector; not returned to API caller |
| Disabled credential blocks connector | `active=FALSE` credential → `CREDENTIAL_DISABLED` error, connector stays in demo/not_configured |
| Missing credential returns safe default | No record → `CREDENTIAL_NOT_FOUND` or `not_configured` status, no crash |
| Audit event written without raw secret | `CredentialAuditLogger` output contains no secret field values |
| Rotation updates key_version and rotated_at | After rotation: new `key_version`, `rotated_at` updated, old value not readable by new key |
| Plaintext api_key not returned by any service | `get_status()` and any public endpoint return no raw `api_key` |
| No logs contain raw secret | Log capture test: no secret appears in captured log output |
| No real Balance.ge call | `BalanceConnector` with vault credentials makes no HTTP request when `TEST_MODE=1` |

All tests must use `TEST_MODE=1` key. No real credentials in test files.

---

## N) Rollback Strategy

Every migration and code change in 11C-C must support rollback:

1. **Additive migration first.** Phase 1 adds new columns only — no column
   removal, no data destruction. Rollback = revert app code; old columns unused
   but harmless.

2. **Keep old plaintext column until encrypted read path verified.** The `api_key`
   column must NOT be nulled until:
   - `encrypted_value` is populated for all active tenants.
   - `ConnectorCredentialProvider` read path is verified in production.
   - Backup of credentials is confirmed before any null operation.

3. **Feature flag for vault read path.** An environment variable (e.g.,
   `CREDENTIAL_VAULT_ENABLED=1`) allows the vault read path to be toggled off
   without a code deploy, falling back to `demo_mode` or `not_configured` — not
   to raw plaintext exposure.

4. **Rollback path after column null:** If `encrypted_value` decrypt fails after
   `api_key` nulling, connector must return `not_configured`/`demo_mode` —
   NEVER attempt a live API call with an unknown credential state.

5. **No data loss on migration rollback.** All migrations must be `IF NOT EXISTS`
   / `IF EXISTS` guarded. Down migrations must be documented.

6. **Idempotent migration strategy.** Every migration must be safe to run
   multiple times without error.

---

## O) Live Verification Standard for 11C-C

After future 11C-C merge and deploy, the following must be verified:

1. Local `main` HEAD matches live `/version` SHA.
2. `GET /health` returns HTTP 200.
3. Static pages return HTTP 200.
4. Protected endpoints return HTTP 401 without auth token.
5. Balance.ge connector status is `demo_mode` — **unchanged from current state.**
6. Credential status endpoint (if tested) returns no raw `api_key` field.
7. No raw secret visible in any `/health` or `/version` response.
8. No live Balance.ge API posting occurred.
9. Targeted vault tests pass on the deployed version.
10. `CredentialAuditLogger` writes are visible in production logs (no secret values).

---

## P) Stop Conditions

Task 11C-C (and subsequent 11C tasks) must stop and report to the user if:

| Stop Condition | Action |
|---|---|
| Production credential is requested or needed | Stop. Report. Do not retrieve or modify production credentials. |
| Migration is needed but not authorized by task spec | Stop. Report. Do not create migration file. |
| Runtime code outside the allowed file list requires changes | Stop. Report which files and why. Do not proceed. |
| DB access is required beyond what migrations provide | Stop. Report. Do not run manual SQL. |
| Live Balance.ge API call is required | Stop. Report. Do not call Balance.ge. |
| Tests fail | Stop. Fix tests before committing. Do not commit failing tests. |
| Plaintext secret appears in any test fixture, doc, or log output | Stop. Remove immediately. Do not commit. This is a P0 security incident. |
| Working tree has unexpected tracked changes | Stop. Report the unexpected files. Do not commit. |

---

## Q) Final Status

- Task 11C-B completes the credential vault runtime architecture and migration
  plan only.
- No runtime implementation has been started.
- No migrations have been created.
- No production database has been touched.
- No SQL has been executed.
- No credentials have been changed.
- Balance.ge has not been activated.
- Task 11C-C has not been started.

**Next safe task after 11C-B live verification:**
**11C-C — Credential Vault Migration and Storage Service**

11C-C is the first true vault implementation task. It may create Phase 1
additive migration only if explicitly authorized in the task specification.
It implements `CredentialVaultService`, `SecretCryptoProvider`, and updates
`balance_credentials_service.py` to route through the vault. It must not
activate Balance.ge.
