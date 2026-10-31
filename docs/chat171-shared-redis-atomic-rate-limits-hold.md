# Bridge Hub — Chat171 shared Redis quota, atomicity and outage gate

**Date:** 2026-10-27. **Scope:** GitHub Draft PR #154 ONLY. **Release: HOLD.**
**Last independently CI-verified CODE SHA:** `2753ba34a52c381ea9df0474f348018846de9739`.
No changes were made to `main`, any Production Cloud Run / Cloud SQL service,
Production Redis settings, Windows originals, Git working trees or ACLs.

## 1. Confirmed problems before Chat171

- The category limiter's Redis backend incremented and set TTL in separate
  commands; concurrent requests or a crash between commands could leave a
  counter with no expiration.
- On any Redis exception, it silently used a per-process memory backend,
  allowing the effective quota to reset independently on each Cloud Run
  replica. The factory also chose memory if no Redis URL was configured.
- The documented forgot/reset/change-password endpoints were not classified
  as `AUTH` by the category limiter; some could use the default bucket.
- A subtle last-second TTL rounding case must not extend a fixed window.

## 2. Draft-only changes

1. `app/api/services/rate_limiter_service.py` now uses one atomic Redis Lua
   script (INCR + EXPIRE on first use + TTL; repair missing-TTL legacy keys).
   A TTL of **zero** for a nearly expired key is NOT refreshed; this prevents
   an attacker from indefinitely extending a fixed lockout.
2. **Fail-closed shared mode:** `ENVIRONMENT=production` or
   `RATE_LIMIT_REQUIRE_SHARED=1` requires Redis across category quotas,
   regardless of `TEST_MODE`. Missing config, init failure or a runtime
   network outage blocks limited requests without a per-instance fallback.
   Local development and ordinary tests still use isolated in-memory
   counters where shared mode is not required.
3. `app/api/middleware/rate_limit_middleware.py` reports strict shared
   storage outages as **HTTP 503**, with a generic
   `RATE_LIMIT_BACKEND_UNAVAILABLE` code and brief `Retry-After`,
   rather than pretending the user exhausted a quota (429) or letting a
   request through. No Redis URLs, keys, credentials or raw failures are
   returned to callers.
4. `app/api/services/rate_limit_policy_service.py` classifies
   `/auth/forgot-password`, `/auth/reset-password`,
   `/auth/change-password` as `AUTH`; the anonymous quota no longer
   uses arbitrary supplied tenant metadata for these routes.
5. Added synthetic unit tests and a dedicated disposable Redis 7 CI job:
   `tests/unit/test_chat171_shared_rate_limit_fail_closed.py`,
   `tests/integration/test_chat171_redis_shared_rate_limits.py`,
   `.github/workflows/chat171-disposable-redis-shared-rate-limits.yml`.
   The Redis job only accepts `redis://127.0.0.1:56379/14` with no
   credentials, uses distinct synthetic keys and never runs FLUSHDB.
6. Both independent real Redis clients contend against one quota with
   60 parallel requests; exact allowed count, remaining TTL, expiry,
   recovery, missing Redis and error behavior are tested. This simulates
   separate app clients sharing a store, **not a deployed two-replica
   Cloud Run load test**.

## 3. Independently verified CI (code SHA 2753ba34...)

- [Disposable Redis 7 job](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40546566922):
  **197 passed**, 6 warnings. Includes atomic two-client concurrent
  counters, 1-second expiry, near-expiry no-extension, recovery/failure,
  strict missing-Redis 503, route classifications and previous limit tests.
- [Disposable PostgreSQL 15/16](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40546567085):
  **150 passed in PG15**, **150 passed in PG16**.
- [Backend/frontend workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40546566996):
  **8,011 backend passed, 3 skipped**; separate integration smoke **1 passed**;
  frontend-build job successful; actual Cloud Run **deploy SKIPPED**.
- [Tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40546566974):
  PASS.
- [Finance fail-closed RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40546567466):
  PASS.
- These results come from GitHub Actions jobs; they do NOT demonstrate real
  Cloud Run ingress/egress, staging/production Redis resilience or
  customer-traffic load behavior.

## 4. Release gates / operational risks

- **Do not deploy yet.** The Production workflow sets
  `ENVIRONMENT=production`; without a correctly provisioned, secure,
  reachable shared `REDIS_URL`, this Draft code intentionally returns
  503 for limited routes. Provisioning/validating that Redis endpoint
  requires separate approval. No Redis secrets were set or read in Chat171.
- **Isolated staging (approval required):** verify VPC networking,
  TLS/authenticated Redis URL, firewall, availability/failover, memory,
  max throughput, latency, and correct unique key namespaces. Simulate
  real two-replica concurrent load and Redis outages/recovery; check
  limits stay global, 503 appears predictably and recovers appropriately.
- **SlowAPI independent limiter:** When `REDIS_URL` is configured, it
  uses Redis storage; in-memory fallback can still be chosen at
  initialization when Redis config is absent. The category guard is
  strict in production for its limited categories, but SlowAPI's
  independent failure behavior and its coverage/order need real staging
  verification before declaring the whole stack resilient.
- **Ingress:** the actual Cloud Run peer and trusted proxy allowlist
  are still unknown; with an empty `RATE_LIMIT_TRUSTED_PROXY_CIDRS`,
  many users can share one ingress IP quota. Chat170's safe IP identity
  change is necessary but not sufficient for usable production quotas.
- **Availability tradeoff:** fail-closed on dependency outage is a
  deliberate security choice with potential login/service disruption;
  confirm monitoring/alerts, on-call and an approved recovery plan.
- Existing P0 release blockers remain: migrations 013/014/015/016
  in real staging, PostgreSQL tenant RLS and role grants, OAuth/SMTP
  integration, Cloud SQL backups/PITR/restore and GCS recovery, real
  finance multi-tenant E2E, US/EU parity, and safe Windows Git/ACL
  integrity.

## 5. Next safe work — Chat172

- Audit SlowAPI Redis outage behavior, per-route decorators, and middleware
  ordering with isolated contract tests; add synthetic fail-closed coverage
  where needed, without silently changing public limits.
- Prepare an owner-approved isolated staging two-replica Redis load/failover
  runbook with explicit configuration evidence and clear stop conditions.
- Keep PR #154 OPEN/DRAFT, do not merge or deploy without separate approval.

**Decision:** Draft code and synthetic CI PASSED. **Production: HOLD.**
