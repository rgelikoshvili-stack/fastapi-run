# Bridge Hub — Chat172 SlowAPI shared-Redis fail-closed gate

**Date:** 2026-10-28. **Scope:** Draft PR #154 ONLY; release decision **HOLD**.
**Last code SHA verified by GitHub CI:** `d3be28f52fae236fefeed3c52f22b673a091b23c`.
No updates to `main`, Production Cloud Run/Cloud SQL/Redis, runtime flags,
production secrets, or original Windows Git/index/ACLs.

## Problem verified

Existing `app/api/security.py::_make_limiter` (SlowAPI 0.1.9) silently
selected a process-local memory backend when Redis was missing or its
configuration failed. Separate category middleware already failed closed
in strict mode, but SlowAPI's own decorated per-route quotas (including
`3/minute` and `5/minute`) lacked an explicit strict fail-closed contract.

SlowAPI 0.1.9's `SlowAPIMiddleware` routes non-`RateLimitExceeded`
storage exceptions to an incompatible default 429 handler, which can
mask a Redis failure with a secondary application error.
Upstream 0.1.9 source:
https://github.com/laurentS/slowapi/blob/v0.1.9/slowapi/middleware.py

## Changes (Draft only)

- Added `app/api/slowapi_shared_guard.py` with
  `GuardedSlowAPILimiter` and a dedicated
  `SharedRateLimitStoreUnavailable` exception.
- `app/api/security.py::_make_limiter`: in `ENVIRONMENT=production` or
  `RATE_LIMIT_REQUIRE_SHARED=1`, require `redis://` or `rediss://`
  config; never silently downgrade to a live memory quota.
  If Redis is absent/invalid or storage construction fails, the guard
  stays active but denies protected checks with a controlled 503.
- Strict mode forces the guard enabled even if inherited app config
  would disable SlowAPI. It disables process-local fallback, exception
  swallowing and post-endpoint Redis quota-header injection, so a
  backend/header failure cannot mislabel a completed operation as a 500.
- For a strict runtime Redis error, the guard raises a dedicated
  error; normal SlowAPI `RateLimitExceeded` still produces **429** under
  the original route-specific quota. No user-supplied XFF is accepted
  outside the Chat170 trusted-peer policy.
- `main.py` registers the dedicated 503 handler. Public payload is
  generic `RATE_LIMIT_BACKEND_UNAVAILABLE`, with short `Retry-After`
  and `Cache-Control: no-store`; no Redis URL/key/exception secret.
- Local/test mode retains legacy in-memory route limits.
- Added `tests/unit/test_chat172_slowapi_shared_guard.py` and
  `tests/integration/test_chat172_slowapi_redis_shared.py`; the latter
  uses **two independently instantiated SlowAPI limiters** against the
  same disposable localhost Redis 7 instance to prove the 3/minute
  decorator quota is global across both. The workflow deletes only
  namespaced synthetic test keys, never uses FLUSHDB.
- Updated both GitHub Actions matrix workflows to run the above tests.

## Verified evidence — code SHA d3be28f...

- [Disposable Redis 7 CI](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40596317055):
  **209 passed**; actual two-client shared SlowAPI quota plus category
  atomic/outage and 3/minute / 5/minute decorator contract tests.
- [Disposable PG15 / PG16 CI](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40596317021):
  **161 passed on PostgreSQL 15**, **161 passed on PostgreSQL 16**.
- [Backend and frontend CI](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40596317073):
  backend **8,022 passed, 3 skipped**, additional smoke **1 passed**,
  frontend build PASS. Actual deployment job must remain **SKIPPED**
  for Draft PR (verify before using this evidence for promotion).
- [Tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40596317134):
  PASS.
- [Fail-closed financial RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40596317250):
  PASS.

## Staging gate and release blockers

- Staging is **not deployed**. A separate approval-gated runbook exists at
  `docs/chat172-isolated-two-replica-redis-staging-runbook.md`. It calls
  for two *actual* isolated Cloud Run replicas, TLS/authenticated Redis,
  cross-replica quota evidence, a controlled Redis outage/recovery,
  ingress/proxy identity validation, and explicit stop conditions.
- Verify that real Cloud Run/Redis connection credentials, VPC route,
  proxy chains and `RATE_LIMIT_TRUSTED_PROXY_CIDRS` are correct before
  any flag or deployment. No Production REDIS_URL has been certified.
- A missing/unreachable Redis in a strict deployed environment
  intentionally causes protected endpoints to respond with 503:
  security is safer, but availability can be disrupted. Confirm
  monitoring, owner alerting and failover/rollback strategy.
- Changes do not prove real OAuth/SMTP behavior, migration 013–016
  deployment readiness, actual tenant RLS, multi-tenant finance E2E,
  Cloud SQL automated backup/PITR/restoration, attachments, US/EU
  parity, original Windows Git/ACL integrity or production readiness.
- Never merge PR #153/#154, change `main`, configure/deploy Production,
  or perform Cloud SQL DDL until the owner explicitly approves.

**Decision: Draft code PASS; real staging NOT TESTED; Production HOLD.**
