# Redis / Rate-Limit Plan

## A) Purpose

Rate limiting is a required Trust Foundation prerequisite before commercial pilot.
Without it, any client can exhaust Bridge Hub's AI classification quota, flood
connector execution paths, enumerate credentials by brute force, or degrade service
for all tenants through unbounded request volume.

This plan defines:

- The current rate-limiting state and its gaps.
- The target architecture for Redis-backed rate limiting with safe in-memory fallback.
- Endpoint groups and per-group policy matrix.
- Failure and fallback policy when Redis is unavailable.
- Subscription-tier integration (trial vs active limits).
- Credential and connector safety rules for the rate-limit layer.
- AI, OCR, and document-processing quota rules.
- Audit and metrics requirements.
- Required error codes and API response contract.
- Future implementation scope split into safe sub-tasks.

**This task defines the contract only.**

No runtime behavior is changed in this task. No middleware is edited. No
Redis connection is added. No migration is created. No production database is
touched. Balance.ge remains inactive.

---

## B) Current State

### Completed Trust Foundation work

- `docs/auth-tenant-schema-contract.md` — tenant lifecycle and subscription fields.
- `docs/trust-foundation-implementation-plan.md` — Pillar 2 defines rate limiting
  as a required trust foundation step.
- `docs/credential-vault-design.md` + `docs/credential-vault-interface-contract.md`
  — credential vault architecture defined.
- `docs/masked-read-behavior-contract.md` — masked read behavior contract defined.
- `docs/subscription-enforcement-plan.md` — subscription enforcement contract defined.

### Runtime state (not changed in this task)

| Item | Current Behavior | Risk |
|---|---|---|
| `app/api/security.py` | `_make_limiter()` reads `REDIS_URL` env var. If set, initializes SlowAPI with Redis storage. If not set or Redis fails, falls back to in-memory `Limiter`. | High: single-instance only for in-memory |
| `main.py` | `app.state.limiter = limiter` and `SlowAPIMiddleware` added. `rate_limit_exceeded_handler` registered for 429. | Medium: limiter wired but no routes decorated |
| Route handlers | No `@limiter.limit(...)` decorators applied to any route. Effective rate: unlimited for all endpoints. | Critical |
| `REDIS_URL` env var | Not set in production Cloud Run configuration. In-memory fallback active. | High: limits not shared across instances |
| AI classification endpoints | `/ai-journal/*`, `/transaction-ai/*` — each call invokes Claude API (Anthropic). No per-tenant or per-IP quota enforced. | Critical |
| OCR endpoints | `/ocr/*` — vision model calls. No quota enforced. | Critical |
| Auth endpoints | `/auth/login`, `/auth/register` — no brute-force protection. | Critical |
| Connector execution | `/posting/*`, `/balance-ge/*`, `/1c/*` — no execution rate limit. | High |
| Credential save | `/balance-credentials/save`, `/rsge-credentials/save` — no change-rate limit. | High |

**Runtime behavior: unchanged in this task.**
**Balance.ge activation status: inactive — Balance.ge must stay inactive.**
**Production DB status: untouched in this task.**
**No migration is created in this task.**

---

## C) Target Architecture

The target rate-limiting architecture consists of seven components:

### 1. RateLimitService

Orchestrates rate-limit checks. Receives a request context (tenant_id, user_id,
ip_address, endpoint_group) and a policy. Returns a `RateLimitDecision`. Delegates
storage to `RateLimitRepository`. Does not touch credentials, raw secrets, or DB.

### 2. RateLimitRepository

Abstracts the storage backend. Calls `RedisRateLimitBackend` when Redis is
available, falls back to `InMemoryRateLimitBackend` when Redis is unavailable or
fails. Handles backend switching transparently. Emits a `RATE_LIMIT_BACKEND_DEGRADED`
metric when fallback is active.

### 3. RedisRateLimitBackend

Redis-backed sliding-window counter. Uses `REDIS_URL` from environment. Implements
atomic increment-and-expire via Redis Lua script or pipeline to avoid race
conditions. Stores keys with TTL matching the policy window. Safe: does not store
any credential values, secrets, tokens, or tenant PII beyond tenant_id and IP hash.

### 4. InMemoryRateLimitBackend

Single-process in-memory fallback using a sliding window dict. Safe for development
and single-instance deployments. Not safe for multi-instance Cloud Run at high
traffic — must be replaced with Redis in production. Enforces the same policy
matrix as the Redis backend when active.

### 5. RateLimitPolicyRegistry

Registry of per-endpoint-group policies. Maps endpoint group name to a
`RateLimitPolicy` (limit, window, key_strategy: per_ip | per_tenant | per_user,
subscription_multiplier). Loaded at startup. Immutable at runtime. No DB required.

### 6. RateLimitAuditLogger

Writes rate-limit events to the audit log when a limit is hit or when a degraded
fallback fires. Includes: tenant_id, ip_hash (not raw IP), endpoint_group, result
(`allowed`, `blocked`, `fallback_active`), timestamp. Must not log raw credentials,
tokens, passwords, or secrets.

### 7. RateLimitDecision

Immutable value object returned by `RateLimitService`. Fields:
- `allowed: bool`
- `remaining: int`
- `reset_at: datetime`
- `policy_key: str`
- `backend: str` — `"redis"` | `"memory"`
- `error_code: str | None` — set when `allowed=False`

---

## D) Key Strategy

### Redis-first, memory-safe fallback

Rate limiting MUST use Redis in production for shared state across Cloud Run
instances. The fallback to in-memory is acceptable only during Redis outage (not as
a permanent configuration). When fallback is active, limits are enforced per-instance
only — a `RATE_LIMIT_BACKEND_DEGRADED` metric must be emitted.

### Sliding window, not fixed window

Rate limits must use a sliding window algorithm. Fixed-window counters allow burst
doubling at window boundaries (e.g., 10 requests at 00:59 and 10 at 01:00 = 20 in
2 seconds). Sliding windows prevent this class of abuse.

### Per-tenant quota, not per-IP only

Authentication-required endpoints must apply limits per `tenant_id` AND per
`user_id` where possible, not per IP alone. IP-only limits are spoofable via
proxy. Per-tenant limits prevent noisy-tenant degradation of shared resources.

### Key strategy per group

- Auth endpoints: per_ip (pre-authentication, no tenant context yet).
- AI/OCR/document: per_tenant (expensive, shared quota pool).
- Connector execution: per_tenant.
- Credential save: per_tenant + per_ip (double enforcement).
- Reporting and read endpoints: per_tenant.
- Public/health: per_ip (low limit, globally available).

### Subscription-tier multiplier

Active-subscription tenants MAY receive a higher rate-limit quota than trial
tenants for AI/OCR/document endpoints, controlled by `subscription_multiplier` in
`RateLimitPolicy`. This is additive: `effective_limit = base_limit * multiplier`.
Multiplier defaults to 1.0. Must not bypass limits entirely.

---

## E) Endpoint Groups

All Bridge Hub routes are classified into 18 rate-limit groups:

| Group | Routes | Key Strategy |
|---|---|---|
| `public_health` | `/health`, `/version`, `/docs`, `/static/*`, `/openapi.json` | per_ip |
| `auth_login` | `/auth/login` | per_ip |
| `auth_register` | `/auth/register`, `/auth/signup` | per_ip |
| `auth_refresh` | `/auth/refresh`, `/auth/logout` | per_ip |
| `ai_classification` | `/ai-journal/*`, `/transaction-ai/*`, `/ai-classify/*` | per_tenant |
| `ocr_processing` | `/ocr/*`, `/ocr/extract/*` | per_tenant |
| `document_upload` | `/documents/upload`, `/documents/process/*` | per_tenant |
| `bank_csv_import` | `/bank-csv/*`, `/bank-statements/*` | per_tenant |
| `email_collector` | `/email-collector/*` (non-save) | per_tenant |
| `approval_write` | `/approval/approve`, `/approval/reject`, `/approval/create` | per_tenant |
| `posting_erp` | `/posting/*`, `/balance-ge/*`, `/1c/*`, `/erp-connectors/*` | per_tenant |
| `credential_save` | `/balance-credentials/save`, `/rsge-credentials/save`, `/email-collector/save` | per_tenant + per_ip |
| `credential_status` | `/balance-credentials/status`, `/rsge-credentials/status`, `/balance-credentials/test` | per_tenant |
| `connector_test` | `/rsge-credentials/test`, `/1c/test`, `/erp-connectors/test` | per_tenant |
| `reporting` | `/reports/*`, `/financial-statements/*`, `/audit-trail/*` | per_tenant |
| `export` | `/export/*`, `/reports/export/*`, `/payroll/slip/*` | per_tenant |
| `tenant_admin` | `/tenants/*`, `/billing/*`, `/settings/*` | per_tenant |
| `general_api` | All other authenticated endpoints not in above groups | per_tenant |

---

## F) Policy Matrix

Rate limits applied per group. `trial_multiplier` applies to trial tenants.
`active_multiplier` applies to active (paid) tenants. Default window unit: minute
unless specified.

| Group | Base Limit | Window | Trial Multiplier | Active Multiplier | Notes |
|---|---|---|---|---|---|
| `public_health` | 300 | 1 min | 1.0 | 1.0 | Effectively open |
| `auth_login` | 10 | 1 min | 1.0 | 1.0 | Anti-brute-force, no tier benefit |
| `auth_register` | 5 | 1 hour | 1.0 | 1.0 | Anti-farming |
| `auth_refresh` | 60 | 1 min | 1.0 | 1.0 | Normal session use |
| `ai_classification` | 30 | 1 hour | 0.5 | 2.0 | Expensive; trial gets 15/hour |
| `ocr_processing` | 20 | 1 hour | 0.5 | 2.0 | Expensive; trial gets 10/hour |
| `document_upload` | 50 | 1 hour | 0.5 | 2.0 | Storage cost |
| `bank_csv_import` | 10 | 1 hour | 1.0 | 2.0 | Moderate use |
| `email_collector` | 5 | 1 min | 1.0 | 1.0 | Prevents email abuse |
| `approval_write` | 60 | 1 hour | 1.0 | 1.0 | Human-pace approval |
| `posting_erp` | 20 | 1 hour | 0.0 | 1.0 | 0 = blocked for trial |
| `credential_save` | 10 | 1 hour | 1.0 | 1.0 | Prevent credential churn |
| `credential_status` | 120 | 1 min | 1.0 | 1.0 | Read-heavy but monitored |
| `connector_test` | 5 | 1 hour | 0.5 | 1.0 | Prevent connector enumeration |
| `reporting` | 30 | 1 min | 1.0 | 2.0 | Normal reporting |
| `export` | 10 | 1 hour | 0.5 | 2.0 | Expensive export |
| `tenant_admin` | 30 | 1 min | 1.0 | 1.0 | Admin operations |
| `general_api` | 120 | 1 min | 1.0 | 1.0 | Default catch-all |

Notes:
- `posting_erp` multiplier of `0.0` for trial means connector execution is blocked
  by rate-limit policy in addition to subscription enforcement (defense in depth).
- Trial multiplier less than 1.0 reduces effective limit (e.g., `30 * 0.5 = 15`).
- Active multiplier greater than 1.0 increases effective limit for paid tenants.

---

## G) Failure and Fallback Policy

### Redis unavailable

When Redis is unavailable or connection fails during a request:

1. `RateLimitRepository` switches to `InMemoryRateLimitBackend` for that request.
2. `RateLimitDecision.backend` is set to `"memory"`.
3. A `RATE_LIMIT_BACKEND_DEGRADED` metric is emitted (not a blocking error).
4. Rate limits are still enforced — degraded mode is not a bypass.
5. `RateLimitAuditLogger` records the fallback event.
6. The response does NOT include a `RATE_LIMIT_BACKEND_DEGRADED` error code to the
   client — the client sees normal allowed/blocked decisions.

### Fail-open vs fail-closed

Rate limiting must be **fail-open** for normal requests (allow on Redis failure)
to avoid service outage during Redis blips. Exception: auth endpoints (`auth_login`,
`auth_register`) must be **fail-closed** — if the rate-limit backend is unavailable
for auth endpoints, apply the in-memory limit rather than allowing unlimited attempts.

### Key expiry

Rate-limit keys in Redis must have explicit TTL set to the policy window plus a
buffer (window * 2). Keys must not persist indefinitely. In-memory backend must
evict expired windows on each access.

### Circuit breaker

If Redis fails more than 3 times in a 30-second window, the circuit breaker opens
and all requests use in-memory until the circuit resets. Circuit state must be
logged at WARNING level. No credentials or secrets are logged.

---

## H) Subscription Integration

Rate-limit policies must integrate with tenant subscription state defined in
`docs/subscription-enforcement-plan.md`:

| Tenant State | Rate-Limit Behavior |
|---|---|
| `active` | Apply base limit × active_multiplier |
| `trial` | Apply base limit × trial_multiplier |
| `trial_expired` | Apply trial limits; mutating endpoints blocked by subscription enforcement |
| `suspended` | Apply trial limits; most actions already blocked by subscription enforcement |
| `expired` | Apply trial limits; mutating endpoints blocked by subscription enforcement |
| `inactive` | Requests blocked before rate limit is checked (subscription enforcement first) |

Rules:

1. Rate-limit check happens AFTER authentication and subscription state check. If
   subscription enforcement blocks the request, rate-limit is not checked.
2. Rate-limit check happens BEFORE business logic. A blocked request (429) must not
   invoke AI, OCR, or connector calls.
3. Subscription multipliers must be read from `RateLimitPolicyRegistry`, not from
   the DB on every request. The registry is loaded at startup.
4. Trial multiplier of `0.0` for `posting_erp` is defense-in-depth — subscription
   enforcement is the primary block.

---

## I) Credential Safety

Rate-limit components must comply with these credential safety rules:

1. `RateLimitService`, `RateLimitRepository`, `RedisRateLimitBackend`, and
   `InMemoryRateLimitBackend` must never receive, store, or log raw credentials.
   They receive only: `tenant_id`, `user_id`, `ip_hash` (hashed, not raw), and
   `endpoint_group`.
2. Redis rate-limit keys must not encode credential values, secrets, API keys, or
   passwords. Keys are of the form: `rl:{group}:{tenant_id}:{window_start}` or
   `rl:{group}:{ip_hash}:{window_start}`.
3. `RateLimitAuditLogger` must never log raw IP addresses — use `sha256(ip)[:16]`
   as `ip_hash`. Rationale: raw IPs may be PII under GDPR.
4. Blocked responses (429) must not include tenant credential data. The response
   must contain only: `error_code`, `message`, `retry_after`.
5. Rate-limit middleware must not call any credential service. The credential service
   and rate-limit service are independent layers.

---

## J) Connector Safety

Connector execution paths (`posting_erp`, `connector_test`) require additional rate-
limit safety:

1. Connector rate-limit check must fire BEFORE the connector is initialized or
   any credential is fetched from the vault. A 429 response must not trigger
   credential retrieval.
2. `posting_erp` group must enforce per-tenant limits strictly — connector abuse can
   cause ERP-side rate limiting or account lockout (Balance.ge, RS.ge).
3. `connector_test` group must enforce strict limits (5/hour per tenant) — repeated
   test calls can exhaust connector test quota on the ERP side.
4. Balance.ge connector execution is currently blocked by the activation gate
   (`docs/balance-ge-activation-gate.md`). Rate limits for `posting_erp` apply
   to any connector, but Balance.ge requires all 12 gates MET before live execution
   regardless of rate-limit state.
5. Dry-run / sandbox connector calls may have a separate, more permissive policy
   defined in `RateLimitPolicyRegistry` as `posting_erp_dryrun` if needed.

---

## K) AI, OCR, and Document Quotas

AI classification, OCR, and document upload are quota-sensitive because they incur
external API costs (Anthropic, GCP Vision) per call:

### AI Classification (`ai_classification` group)

- Every call to `/ai-journal/*` or `/transaction-ai/*` invokes the Claude API.
- Per-tenant hourly quota enforced: 30/hour base, 15/hour for trial, 60/hour for active.
- If quota exceeded: 429 with `AI_QUOTA_EXCEEDED` error code.
- Quota state stored in Redis (not DB) per tenant per hour window.
- Quota must not be bypassed by retrying under different user IDs within the same tenant.

### OCR Processing (`ocr_processing` group)

- Every `/ocr/*` call invokes GCP Vision API.
- Per-tenant hourly quota: 20/hour base, 10/hour for trial, 40/hour for active.
- If quota exceeded: 429 with `AI_QUOTA_EXCEEDED` error code (same code as AI — both
  are external AI/vision API calls).
- GCS upload is rate-limited separately via `document_upload` group.

### Document Upload (`document_upload` group)

- Per-tenant hourly quota: 50/hour base, 25/hour for trial, 100/hour for active.
- If quota exceeded: 429 with `DOCUMENT_QUOTA_EXCEEDED` error code.
- Bank CSV import (`bank_csv_import` group): 10/hour base, enforced separately.

### Shared Tenant Quota Pool

Future implementation may define a shared quota pool across AI + OCR + document
endpoints so trial tenants cannot max AI quota AND OCR quota simultaneously.
The current plan defines independent per-group limits as a safe starting point.

---

## L) Audit and Metrics

### Audit events

The following events must create audit or metric records when rate limiting is active:

| Event | Record Type | Required |
|---|---|---|
| Rate limit hit (request blocked) | Audit log | Yes |
| Redis backend degraded (fallback active) | Metric + warning log | Yes |
| Circuit breaker opened | Warning log | Yes |
| AI quota hit (tenant level) | Audit log | Yes |
| OCR quota hit (tenant level) | Audit log | Yes |
| Document quota hit (tenant level) | Audit log | Yes |
| Connector rate limit hit | Audit log | Yes |
| Auth rate limit hit (potential brute force) | Audit log + alert metric | Yes |
| Rate-limit key eviction (TTL) | No record required | — |

### Metric names

| Metric | Type | Labels |
|---|---|---|
| `rate_limit.blocked` | Counter | group, backend, tenant_id |
| `rate_limit.backend_degraded` | Counter | backend |
| `rate_limit.circuit_breaker_open` | Gauge | — |
| `rate_limit.quota_remaining` | Gauge | group, tenant_id |
| `rate_limit.auth_blocked` | Counter | group |

### Audit record fields

Each rate-limit audit record must include:
- `tenant_id`
- `ip_hash` (sha256 of raw IP, first 16 chars)
- `endpoint_group`
- `result` (`allowed` | `blocked`)
- `backend` (`redis` | `memory`)
- `limit` (configured limit)
- `remaining` (remaining quota at decision time)
- `timestamp`
- `error_code` if blocked

Each audit record must NOT include: raw IP address, user passwords, tokens, API keys,
or any credential values.

---

## M) Error Codes

Required error codes for the rate-limiting layer:

| Code | Condition | HTTP Status |
|---|---|---|
| `RATE_LIMIT_EXCEEDED` | Generic rate limit hit — applies to `general_api`, `reporting`, `tenant_admin`, `auth_refresh` | 429 |
| `AUTH_RATE_LIMIT_EXCEEDED` | Auth endpoint rate limit hit (`auth_login`, `auth_register`) | 429 |
| `AI_QUOTA_EXCEEDED` | Per-tenant AI or OCR hourly quota exhausted | 429 |
| `DOCUMENT_QUOTA_EXCEEDED` | Per-tenant document upload hourly quota exhausted | 429 |
| `CONNECTOR_RATE_LIMIT_EXCEEDED` | Connector execution rate limit hit (`posting_erp`, `connector_test`) | 429 |
| `CREDENTIAL_RATE_LIMIT_EXCEEDED` | Credential save rate limit hit (`credential_save`) | 429 |
| `TENANT_QUOTA_EXCEEDED` | Tenant-level aggregate quota exhausted (future shared pool) | 429 |
| `RATE_LIMIT_BACKEND_DEGRADED` | Redis unavailable, in-memory fallback active (metric only, not returned to client) | — |
| `RATE_LIMIT_POLICY_NOT_FOUND` | No policy configured for endpoint group — internal error | 500 |
| `EXPORT_RATE_LIMIT_EXCEEDED` | Export endpoint rate limit hit (`export` group) | 429 |

All rate-limit blocked responses must:

- Use the standard Bridge Hub error envelope (`ok: false`, `error.code`, `error.details`).
- Include a `Retry-After` header with the number of seconds until the window resets.
- Include a human-readable `message` such as "Rate limit exceeded. Please wait N seconds."
- Not expose raw tenant data, credential values, or Redis key structure.

```json
{
  "ok": false,
  "message": "Rate limit exceeded. Please wait 47 seconds.",
  "data": null,
  "error": {
    "code": "AI_QUOTA_EXCEEDED",
    "details": "AI classification quota exhausted for this tenant. Limit: 30/hour."
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
- No DB access, no runtime imports, no Redis connection, no SQL.

Tests must not:

- Import runtime app modules that trigger DB connections.
- Connect to Redis.
- Execute SQL.
- Import `app.api.security` (this would trigger SlowAPI initialization).
- Mock or patch runtime services.
- Change any runtime behavior.

Future implementation tests (not in this task):

- `10F-E1`: Repository tests — unit tests for `RateLimitRepository` with mocked Redis.
- `10F-E2`: Policy registry tests — pure function tests for policy lookup by group.
- `10F-E3`: Backend tests — unit tests for sliding-window algorithm, key expiry.
- `10F-E4`: Middleware integration — tests for limiter decorator on route handlers.
- `10F-E5`: Subscription multiplier — tests that trial/active multipliers apply correctly.
- `10F-E6`: Fallback tests — Redis unavailable → in-memory fallback fires.
- `10F-E7`: Audit tests — rate-limit events create correct audit records.
- `10F-E8`: Staging verification — end-to-end rate limit hit with real Redis.

---

## O) Future Implementation Scope

### Task 10F-E1 — RateLimitRepository and Backend Tests

- Create `app/api/services/rate_limit_repository.py`.
- Implement `RateLimitRepository` with Redis and in-memory backends.
- Unit tests with mocked Redis: hit limit → blocked, below limit → allowed.
- Unit tests for circuit breaker: 3 Redis failures → circuit opens.

### Task 10F-E2 — RateLimitPolicyRegistry

- Create `app/api/services/rate_limit_policy.py`.
- Implement `RateLimitPolicyRegistry` with all 18 endpoint groups and policy matrix.
- Pure function tests: correct limit returned for each group and tenant state.
- Tests for subscription multiplier: trial × 0.5, active × 2.0.

### Task 10F-E3 — Sliding Window Backend

- Implement Redis Lua script for atomic sliding-window increment.
- Implement in-memory sliding-window with correct eviction.
- Tests: concurrent increment correctness, window boundary behavior.

### Task 10F-E4 — Route Decorator Application

- Apply `@limiter.limit(...)` decorators to all route handlers grouped by category.
- Unit + integration tests: 429 returned after limit, 200 returned below limit.
- Tests for `Retry-After` header presence.

### Task 10F-E5 — Subscription Multiplier Integration

- Read tenant subscription state from `tenant_state_service` (implemented in 10F-D2).
- Apply multiplier at `RateLimitService` level.
- Tests: trial tenant gets reduced AI quota, active tenant gets elevated quota.

### Task 10F-E6 — Fallback and Circuit Breaker

- Implement circuit breaker in `RateLimitRepository`.
- Tests: Redis fail → fallback active → limits still enforced → circuit resets.
- Metric emission tests: `rate_limit.backend_degraded` counter incremented.

### Task 10F-E7 — Audit Logger

- Implement `RateLimitAuditLogger` writing to audit_log table.
- Tests: blocked request → audit record created with correct fields.
- Tests: raw IP not logged, ip_hash present.

### Task 10F-E8 — Staging Verification

- Deploy with `REDIS_URL` set to staging Redis instance.
- End-to-end: hit AI quota, verify 429 with `AI_QUOTA_EXCEEDED`, verify audit record.
- Verify fallback: Redis down → in-memory limits still fire.

---

## P) Explicit Non-Goals (This Task)

The following are explicitly deferred and must NOT be implemented in this task:

- No runtime behavior change.
- No edit to `app/api/security.py` (limiter wiring not changed).
- No middleware edit (`auth_middleware.py`, `rbac_middleware.py`, `slowapi` middleware
  not changed).
- No migration or DDL change.
- No service implementation (`rate_limit_repository.py` not created).
- No Redis connection added.
- No route decorator applied.
- No connector change.
- No auth or RBAC change.
- No Balance.ge activation.
- No production DB touch.
- No commercial pilot activation.

**Balance.ge activation remains blocked** until all 12 gates in
`docs/balance-ge-activation-gate.md` are MET. All gates are currently NOT MET.

**No migration is created in this task.**

**No runtime code is changed in this task.**
