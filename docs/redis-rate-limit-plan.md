# Redis / Rate-Limit Plan

## A) Purpose

Redis-backed rate limiting is required before commercial pilot. Without it, any
client can exhaust auth endpoints through brute force, abuse credential-adjacent
save/test operations, flood connector execution paths, and deplete AI, OCR, and
document processing quotas at no cost.

This plan defines:

- The target Redis-backed rate-limit architecture for Bridge Hub.
- The rate-limit key strategy for multi-dimensional throttling.
- Endpoint groups and their sensitivity classification.
- Conceptual policy matrix for initial target limits.
- Failure and fallback behavior when Redis is unavailable.
- Subscription and trial integration with rate-limit enforcement.
- Credential secret safety rules for the rate-limit layer.
- Connector execution throttling requirements.
- AI, OCR, and document processing quota rules.
- Audit and metrics requirements.
- Required error codes and API response contract.
- Future implementation scope.

**This task defines the contract only.**

No runtime behavior is changed in this task. No middleware is edited.
No app/api/security.py is edited. No Redis configuration is added in this task.
No migration is created. Production DB is untouched. Balance.ge remains inactive.

---

## B) Current State

### Completed Trust Foundation work

- `docs/trust-foundation-implementation-plan.md` — Pillar 2 defines Redis-backed
  rate limiting as a required trust foundation step before commercial pilot.
- `docs/credential-vault-design.md` + `docs/credential-vault-interface-contract.md`
  — credential vault architecture defined.
- `docs/masked-read-behavior-contract.md` — masked read behavior contract defined.
- `docs/subscription-enforcement-plan.md` — subscription enforcement contract defined.

### Runtime state (not changed in this task)

| Item | Current Behavior | Risk |
|---|---|---|
| `app/api/security.py` | `_make_limiter()` reads `REDIS_URL` env var. If set, initializes SlowAPI with Redis storage. Falls back to in-memory if not set or Redis fails. No `REDIS_URL` in production Cloud Run currently. | High |
| `main.py` | `app.state.limiter = limiter` and `SlowAPIMiddleware` added. `rate_limit_exceeded_handler` returns 429 with `RATE_LIMIT` error code. | Medium |
| Route handlers | No `@limiter.limit(...)` decorators applied to any route. All endpoints are effectively unlimited. | Critical |
| Auth endpoints | `/auth/login`, `/auth/register`, `/auth/refresh` — no brute-force protection. No rate limit on repeated login failures. | Critical |
| Password reset/TOTP | Password reset request and confirmation, TOTP verify — no rate limit. These do not exist yet as routes; planned for future. | Critical |
| Credential endpoints | `/balance-credentials/save`, `/rsge-credentials/save`, credential test endpoints — no change-rate limit. | High |
| Connector execution | `/posting/*`, `/balance-ge/*`, `/1c/*`, `/erp-connectors/*` — no execution throttle. | High |
| AI classification | `/ai-journal/*`, `/transaction-ai/*` — each call invokes Claude API. No per-tenant quota. | Critical |
| OCR processing | `/ocr/*` — GCP Vision API calls. No quota enforced per tenant. | Critical |
| Document upload | `/documents/upload` — no upload rate limit. | High |

**Runtime behavior: unchanged in this task.**
**Balance.ge activation status: inactive — Balance.ge must stay inactive.**
**Production DB status: untouched in this task.**
**No migration is created in this task.**

---

## C) Target Rate-Limit Architecture

The target rate-limiting architecture consists of seven planned components:

### 1. RateLimitService

Orchestrates rate-limit checks. Receives a request context (ip, tenant_id,
user_id, endpoint_group, provider, action) and a policy from
`RateLimitPolicyRegistry`. Returns a `RateLimitDecision`. Delegates persistence
to `RateLimitRepository`. Does not handle credentials, raw secrets, or DB queries.

### 2. RateLimitRepository

Abstracts the storage backend. Calls `RedisRateLimitBackend` when Redis is
available. Falls back to `InMemoryRateLimitBackend` when Redis is unavailable
or raises an error. Manages backend switching transparently. Emits a
`RATE_LIMIT_BACKEND_UNAVAILABLE` event and metric when fallback is active.

### 3. RedisRateLimitBackend

Redis-backed sliding-window counter. Reads `REDIS_URL` from environment. Uses
atomic increment-and-expire (Redis Lua script or pipeline) to prevent race
conditions. Stores keys with TTL matching the policy window. Never stores
credential values, raw secrets, tokens, or tenant PII beyond tenant_id and
hashed IP.

### 4. InMemoryRateLimitBackend

Single-process in-memory fallback using a sliding window dict. Safe for
development and testing. Not safe for multi-instance Cloud Run production
deployments — it cannot share state across instances. When active in production,
it must be explicit (logged, audited) and must not silently remove limits for
sensitive endpoints.

### 5. RateLimitPolicyRegistry

Registry of per-endpoint-group policies. Maps endpoint group name to a
`RateLimitPolicy` (limit, window_seconds, key_strategy, sensitive, fallback_behavior).
Loaded at startup from static config. Immutable at runtime. No DB required.

### 6. RateLimitAuditLogger

Writes rate-limit events to the audit/metrics layer when a limit is exceeded
or when a degraded fallback fires. Records: tenant_id, ip_hash (not raw IP),
endpoint_group, result, backend, timestamp, error_code. Must never log raw
credentials, passwords, api keys, tokens, or secrets.

### 7. RateLimitDecision

Immutable value object returned by `RateLimitService`:
- `allowed: bool`
- `remaining: int`
- `reset_at: datetime`
- `policy_key: str`
- `backend: str` — `"redis"` | `"memory"`
- `error_code: str | None` — set when `allowed=False`
- `audit_required: bool`

---

## D) Rate-Limit Key Strategy

Rate-limit keys are composed from safe, non-sensitive dimensions:

### Dimensions

- `ip` — client IP, hashed in audit logs (raw IP may be used in Redis keys as it is not stored)
- `tenant_id` — tenant identifier from JWT claim
- `user_id` — user identifier from JWT claim
- `endpoint_group` — classified group name (see Section E)
- `provider` — connector or credential provider name (`balance`, `rsge`, `onec`, `email`, `webhook`)
- `action` — sub-action within a group (`post`, `test`, `upload`, `classify`, `verify`)
- `idempotency_key` where applicable — prevents duplicate replay without bypassing limits

### Key formats and examples

```
rl:auth:login:ip:{ip}
rl:auth:login:user:{user_id}
rl:auth:register:ip:{ip}
rl:auth:password_reset:ip:{ip}
rl:auth:password_reset:email:{hashed_email}
rl:auth:totp:verify:ip:{ip}
rl:auth:totp:verify:user:{user_id}
rl:tenant:{tenant_id}:connector:{provider}:post
rl:tenant:{tenant_id}:connector:{provider}:test
rl:tenant:{tenant_id}:ocr:upload
rl:tenant:{tenant_id}:ai:classify
rl:credential:{tenant_id}:{provider}:save
rl:credential:{tenant_id}:{provider}:test
rl:tenant:{tenant_id}:document:upload
rl:tenant:{tenant_id}:export
```

### Forbidden in keys

The following must never appear in any rate-limit key:
- Raw api_key values
- Raw password values
- Raw tokens or access_tokens
- Raw webhook secrets
- Raw TOTP secrets or setup codes
- Raw email app passwords

Provider names (`balance`, `rsge`) are allowed. Secret values are not.

---

## E) Endpoint Groups

All Bridge Hub routes are classified into 18 rate-limit endpoint groups:

| Group | Routes / Actions | Sensitive |
|---|---|---|
| `public_health_version` | `/health`, `/version`, `/docs`, `/static/*`, `/openapi.json` | No |
| `auth_login` | `/auth/login` | Yes |
| `auth_register` | `/auth/register`, `/auth/signup` | Yes |
| `password_reset_request` | `/auth/password-reset/request` (planned) | Yes |
| `password_reset_confirm` | `/auth/password-reset/confirm` (planned) | Yes |
| `totp_verify` | `/auth/totp/verify` (planned) | Yes |
| `credential_save` | `/balance-credentials/save`, `/rsge-credentials/save`, `/email-collector/save` | Yes |
| `credential_test` | `/balance-credentials/test`, `/rsge-credentials/test`, connector test endpoints | Yes |
| `connector_status` | `/balance-credentials/status`, `/rsge-credentials/status`, `/1c/status` | No |
| `connector_execution` | `/posting/*`, `/balance-ge/*`, `/1c/post`, `/erp-connectors/execute` | Yes |
| `document_upload` | `/documents/upload`, `/bank-csv/*`, `/bank-statements/*` | Yes |
| `ocr_processing` | `/ocr/*`, `/ocr/extract/*` | Yes |
| `ai_classification` | `/ai-journal/*`, `/transaction-ai/*`, `/ai-classify/*` | Yes |
| `journal_draft_creation` | `/approval/create`, `/ai-journal/draft`, `/transaction-ai/draft` | No |
| `approval_action` | `/approval/approve`, `/approval/reject`, `/approval/queue` writes | No |
| `reporting_read` | `/reports/*`, `/financial-statements/*`, `/audit-trail/*` | No |
| `exports` | `/export/*`, `/reports/export/*`, `/payroll/slip/*` | No |
| `admin_actions` | `/tenants/*`, `/billing/*`, `/settings/*`, `/admin/*` | No |

---

## F) Suggested Policy Matrix

Conceptual target limits — not runtime-enforced in this task. Final values will
be determined during implementation tasks (10F-E5 through 10F-E7).

| Group | Limit | Window | Key Strategy | Notes |
|---|---|---|---|---|
| `public_health_version` | 1000 | 1 min | per_ip | Effectively open |
| `auth_login` | 5 | 1 min | per_ip + per_user | Strict anti-brute-force |
| `auth_register` | 5 | 1 hour | per_ip | Anti-account-farming |
| `password_reset_request` | 3 | 1 hour | per_ip + per_email_hash | Strict per email/IP |
| `password_reset_confirm` | 5 | 1 hour | per_ip + per_user | Strict |
| `totp_verify` | 5 | 5 min | per_ip + per_user | Strict anti-enumeration |
| `credential_save` | 10 | 1 hour | per_tenant + per_user | Prevent credential churn |
| `credential_test` | 5 | 1 hour | per_tenant + per_provider | Anti-enumeration |
| `connector_status` | 60 | 1 min | per_tenant | Read-heavy, moderate |
| `connector_execution` | 10 | 1 hour | per_tenant + per_provider | Strict, ERP-side limits |
| `document_upload` | 50 | 1 hour | per_tenant + per_user | Storage cost |
| `ocr_processing` | 20 | 1 hour | per_tenant + per_user | Vision API quota |
| `ai_classification` | 30 | 1 hour | per_tenant + per_user | LLM API quota |
| `journal_draft_creation` | 60 | 1 hour | per_tenant | Human-pace creation |
| `approval_action` | 60 | 1 hour | per_tenant | Human-pace approval |
| `reporting_read` | 60 | 1 min | per_tenant | Moderate |
| `exports` | 10 | 1 hour | per_tenant | Moderate/strict |
| `admin_actions` | 30 | 1 min | per_tenant | Audited, moderate |

---

## G) Failure / Fallback Policy

### Redis unavailable

When Redis is unavailable or a connection attempt fails during a request:

1. `RateLimitRepository` switches to `InMemoryRateLimitBackend` for that request.
2. A `RATE_LIMIT_BACKEND_UNAVAILABLE` event is emitted and logged at WARNING level.
3. The fallback must be logged and audited — it is never silent.
4. Rate limits are still enforced via in-memory; the fallback is not a bypass.

### Fail-open vs fail-closed per group sensitivity

- **Sensitive endpoints** (auth_login, password_reset_request, password_reset_confirm,
  totp_verify, credential_save, credential_test, connector_execution, document_upload,
  ocr_processing, ai_classification) must not silently become unlimited in production
  if Redis is unavailable. In-memory enforcement must still apply.
- **Non-sensitive endpoints** (reporting_read, connector_status, etc.) may explicitly
  allow degraded in-memory fallback if configured. Any such fallback must produce
  `audit_required=True`.
- **Production fallback must be explicit.** An environment variable controls whether
  production allows in-memory fallback for non-sensitive endpoints:
  `RATE_LIMIT_FALLBACK=strict | allow_readonly`. Default is `strict`.

### Key expiry

All rate-limit keys in Redis must have explicit TTL set. Keys must not persist
indefinitely. In-memory backend must evict expired windows on each access.

### Repeated auth failures

If Redis is unavailable during an auth rate-limit check, the in-memory backend
applies the configured per-IP limit. An alert metric must be emitted if Redis
remains unavailable for more than 30 seconds.

---

## H) Subscription Integration

Rate-limit policies must integrate with tenant subscription state defined in
`docs/subscription-enforcement-plan.md`:

- **expired and suspended tenants remain blocked by subscription enforcement before
  rate-limit quota is considered.** Rate-limit check must not run if subscription
  enforcement has already rejected the request.
- **trial tenants may have stricter quotas** — AI/OCR/document upload limits for
  trial tenants may be a fraction of active tenant limits (e.g., 50% quota).
- **rate limit must not bypass subscription blocking.** A tenant in `trial_expired`
  or `suspended` state must not gain access to mutating actions by consuming rate-
  limit quota — they are rejected before rate-limit enforcement.
- **active subscription tenants** may receive elevated quotas for AI/OCR/document
  endpoints, controlled by `RateLimitPolicyRegistry` multipliers.

Order of checks (future implementation):
1. Authentication (JWT validation)
2. Subscription state enforcement
3. Rate-limit check
4. Business logic / route handler

---

## I) Credential Safety Integration

Rate-limit components must comply with these credential safety rules:

1. `credential_save` and `credential_test` endpoints must be rate-limited — they
   interact with credential management and must not be abused for enumeration.
2. No secret values in rate-limit keys. Provider names (`balance`, `rsge`, `onec`)
   are allowed as key components. Raw api keys, passwords, and tokens are forbidden
   in rate-limit keys.
3. No raw secrets in rate-limit logs. `RateLimitAuditLogger` must log only:
   tenant_id, ip_hash, endpoint_group, provider, result, backend, error_code.
   api keys, passwords, tokens, and webhook secrets must never appear in logs.
4. Provider names are allowed in keys and logs; api keys/passwords/tokens are forbidden
   from any rate-limit key, log entry, metric label, or error response.
5. Blocked responses (429) must not include credential values. The response must
   contain only: error_code, message, retry_after_seconds (if safe).

---

## J) Connector Safety Integration

Connector execution paths require additional rate-limit safety:

1. `connector_execution` must be throttled per tenant and per provider. Connector
   abuse can cause ERP-side rate limiting or account lockout (Balance.ge, RS.ge).
2. The connector rate-limit check must fire BEFORE the connector is initialized
   and BEFORE any credential is fetched from the vault. A 429 response must not
   trigger credential retrieval.
3. Balance.ge connector execution is currently blocked by the activation gate
   (`docs/balance-ge-activation-gate.md`). All 12 gates must be MET before any
   live Balance.ge execution, regardless of rate-limit state.
4. Connector `dry_run` / sandbox calls may have a separate, more permissive policy
   (e.g., `connector_execution_dryrun`) if explicitly configured in
   `RateLimitPolicyRegistry`.
5. `connector_status` (read-only status check) is classified as non-sensitive and
   may have a more permissive limit than `connector_execution`.

---

## K) AI / OCR / Document Processing

AI classification, OCR, and document upload are quota-sensitive because they
incur external API costs per call:

### AI classification (`ai_classification` group)

- Every call to `/ai-journal/*` or `/transaction-ai/*` invokes the Claude API.
- Per-tenant + per-user hourly quota enforced: 30/hour base.
- If quota exceeded: 429 with `AI_RATE_LIMIT_EXCEEDED` error code.
- Quota state stored in Redis per tenant per rolling hour window.
- Quota must not be bypassed by retrying under different user IDs within the same
  tenant (per-tenant quota pool).

### OCR processing (`ocr_processing` group)

- Every `/ocr/*` call invokes GCP Vision API.
- Per-tenant + per-user hourly quota: 20/hour base.
- If quota exceeded: 429 with `OCR_RATE_LIMIT_EXCEEDED` error code.
- Repeated failed document parsing attempts must be throttled — failed parses
  still consume quota to prevent blind retry loops.

### Document upload (`document_upload` group)

- Per-tenant + per-user hourly quota: 50/hour base.
- Bank CSV and bank statement imports are included in this group.
- If quota exceeded: 429 with `RATE_LIMIT_EXCEEDED` error code (generic, since
  `document_upload` is the group).
- Large file processing must be subject to the same quota limit as small files.

### Repeated failures

Repeated failed OCR / document parse / AI classification attempts must count
against quota — do not exempt failed calls from rate-limit accounting.

---

## L) Audit and Metrics

### Events to audit/log

| Event | Record Type | Required |
|---|---|---|
| Rate limit exceeded | Audit log + metric | Yes |
| Fallback backend used | Metric + WARNING log | Yes |
| Redis unavailable | WARNING log + metric | Yes |
| Suspicious repeated auth failures | Audit log + alert metric | Yes |
| Credential test throttled | Audit log | Yes |
| Connector execution throttled | Audit log | Yes |
| AI/OCR quota exceeded | Audit log | Yes |
| Admin override used (if implemented) | Audit log | Yes |

### Metric names

| Metric | Type | Labels |
|---|---|---|
| `rate_limit.blocked` | Counter | endpoint_group, backend, tenant_id |
| `rate_limit.backend_unavailable` | Counter | backend |
| `rate_limit.fallback_active` | Gauge | — |
| `rate_limit.quota_remaining` | Gauge | endpoint_group, tenant_id |
| `rate_limit.auth_blocked` | Counter | endpoint_group |

Labels:
- `allowed_count` — requests allowed within limit
- `blocked_count` — requests blocked by rate limit
- `fallback_count` — requests handled by in-memory fallback
- `redis_error_count` — Redis connection errors
- `endpoint_group` — group name, always safe
- `tenant_id` — include where safe (not in public/IP-only groups)
- `provider` — connector/credential provider name, where safe

### Audit record fields

Each rate-limit audit record must include:
- `tenant_id`
- `ip_hash` (sha256 of raw IP, first 16 chars — not raw IP)
- `endpoint_group`
- `provider` (if applicable)
- `result` (`allowed` | `blocked`)
- `backend` (`redis` | `memory`)
- `limit` (configured limit)
- `remaining` (remaining quota at decision time)
- `timestamp`
- `error_code` if blocked

Each audit record must NOT include: raw IP address, passwords, api_key, tokens,
secrets, webhook secrets, encrypted_value, or any credential material.

---

## M) Error Codes / API Contract

Required error codes for the rate-limiting layer:

| Code | Condition | HTTP Status |
|---|---|---|
| `RATE_LIMIT_EXCEEDED` | Generic rate limit hit (general_api, reporting, admin, document_upload) | 429 |
| `AUTH_RATE_LIMIT_EXCEEDED` | Auth endpoint rate limit hit (auth_login, auth_register) | 429 |
| `PASSWORD_RESET_RATE_LIMIT_EXCEEDED` | Password reset request or confirm rate limit hit | 429 |
| `TOTP_RATE_LIMIT_EXCEEDED` | TOTP verify rate limit hit | 429 |
| `CREDENTIAL_RATE_LIMIT_EXCEEDED` | Credential save or test rate limit hit | 429 |
| `CONNECTOR_RATE_LIMIT_EXCEEDED` | Connector execution or test rate limit hit | 429 |
| `OCR_RATE_LIMIT_EXCEEDED` | OCR processing quota exhausted | 429 |
| `AI_RATE_LIMIT_EXCEEDED` | AI classification quota exhausted | 429 |
| `EXPORT_RATE_LIMIT_EXCEEDED` | Export rate limit hit | 429 |
| `RATE_LIMIT_BACKEND_UNAVAILABLE` | Redis unavailable, fallback active (metric only, may not be returned to client) | — |

All rate-limit blocked responses must:

- Use the standard Bridge Hub error envelope (`ok: false`, `error.code`, `error.details`).
- Include a `retry_after_seconds` field in `data` if safe (non-zero positive int).
- Include a human-readable `message`.
- Not expose raw secrets, tenant data, internal Redis key structure, or credential values.

Example:

```json
{
  "ok": false,
  "message": "Rate limit exceeded. Please wait 47 seconds.",
  "data": {"retry_after_seconds": 47},
  "error": {
    "code": "AI_RATE_LIMIT_EXCEEDED",
    "details": "AI classification quota exhausted. Limit: 30/hour per tenant."
  }
}
```

---

## N) Test Strategy

Task 10F-E tests in `tests/unit/test_redis_rate_limit_contract.py` validate this
contract using only:

- Reading doc files and asserting required content is present.
- Local test-only state definitions and pure helper functions.
- Assertions on component sets, endpoint groups, error codes, policy rules.
- No DB access, no Redis connection, no runtime imports, no SQL.

Tests must not:

- Import runtime app modules that trigger DB connections or SlowAPI initialization.
- Connect to Redis.
- Execute SQL.
- Import `app.api.security` or any `app.*` module.
- Mock or patch runtime services.
- Change any runtime behavior.

Future implementation tests (not in this task):

- `10F-E1`: Rate-limit helper and interface tests — pure function tests.
- `10F-E2`: `RateLimitService` pure logic — mocked repository.
- `10F-E3`: Fake Redis backend tests — sliding window, key expiry, race conditions.
- `10F-E4`: Middleware dry-run / log-only mode — log enforcement without blocking.
- `10F-E5`: Auth / password reset / TOTP throttling enforcement.
- `10F-E6`: Credential and connector throttling enforcement.
- `10F-E7`: AI / OCR / document quota enforcement.
- `10F-E8`: Production `REDIS_URL` verification and live checks on staging.

---

## O) Future Implementation Scope

### Task 10F-E1 — Rate-Limit Helper and Interface Tests

- Define `RateLimitDecision`, `RateLimitPolicy`, `RateLimitPolicyRegistry` interfaces.
- Pure function tests: correct policy returned per group, multipliers applied correctly.

### Task 10F-E2 — RateLimitService Pure Logic

- Implement `RateLimitService.check(context, policy) → RateLimitDecision`.
- Unit tests with mocked `RateLimitRepository`: below limit → allowed, at limit → blocked.

### Task 10F-E3 — Fake Redis Backend Tests

- Implement `RedisRateLimitBackend` with atomic sliding-window Lua script.
- Tests: concurrent increment correctness, key TTL, window boundary behavior.
- Fallback tests: Redis error → `InMemoryRateLimitBackend` fires with audit.

### Task 10F-E4 — Middleware Dry-Run / Log-Only Mode

- Add rate-limit middleware in log-only mode (record would-be blocks, do not block).
- Feature flag: `RATE_LIMIT_MODE=off | log_only | enforce`.
- Deploy to staging; validate no false positives before enabling enforcement.

### Task 10F-E5 — Auth / Password Reset / TOTP Enforcement

- Apply rate-limit decorators to `auth_login`, `auth_register`, `password_reset_request`,
  `password_reset_confirm`, `totp_verify` endpoints.
- Tests: 429 with `AUTH_RATE_LIMIT_EXCEEDED`, `PASSWORD_RESET_RATE_LIMIT_EXCEEDED`,
  `TOTP_RATE_LIMIT_EXCEEDED` after threshold.

### Task 10F-E6 — Credential and Connector Throttling

- Apply rate-limit to `credential_save`, `credential_test`, `connector_execution`.
- Tests: 429 with `CREDENTIAL_RATE_LIMIT_EXCEEDED`, `CONNECTOR_RATE_LIMIT_EXCEEDED`.
- Tests: credential check fires before connector initialized.

### Task 10F-E7 — AI / OCR / Document Quota Enforcement

- Apply per-tenant quota to `ai_classification`, `ocr_processing`, `document_upload`.
- Tests: 429 with `AI_RATE_LIMIT_EXCEEDED`, `OCR_RATE_LIMIT_EXCEEDED` after quota.
- Tests: failed parses count against quota.

### Task 10F-E8 — Production REDIS_URL Verification and Live Checks

- Require `REDIS_URL` in Cloud Run production environment.
- Startup check: warn at startup if `REDIS_URL` not set and `RATE_LIMIT_MODE=enforce`.
- Staging end-to-end: hit AI quota, verify 429, verify audit record, verify Redis key TTL.

---

## P) Explicit Non-Goals (This Task)

The following are explicitly deferred and must NOT be implemented in this task:

- No runtime behavior change.
- No middleware edit (`auth_middleware.py`, `rbac_middleware.py` not changed).
- No app/api/security.py edit — limiter wiring remains unchanged.
- No Redis configuration added (no `REDIS_URL` in production in this task).
- No migration or DDL change.
- No service implementation.
- No route decorator applied.
- No connector change.
- No auth or RBAC behavior change.
- No Balance.ge activation.
- No production DB touch.
- No production infrastructure change.
- No commercial pilot activation.

**Balance.ge activation remains blocked** until all 12 gates in
`docs/balance-ge-activation-gate.md` are MET. All gates are currently NOT MET.

**No migration is created in this task.**

**No runtime code is changed in this task.**
