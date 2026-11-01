# Bridge Hub — Chat172 isolated two-replica quota and Redis failover runbook

**Prepared only — not executed.** Draft PR #154; no Production authorization.
No `main` merge, Cloud Run deploy, Redis provisioning, Cloud SQL mutation, Secret
Manager access, or Windows Git/ACL changes authorized by this runbook.

## 1. Gate zero: approval, scope and credentials

Before performing these steps, obtain explicit owner approval for a **new,
independent staging environment**, including resource budgets/region, provisioned
Redis, TLS credentials, synthetic client source addresses and a rollback operator.
Do not attach staging to Production Cloud SQL, Production Redis, OAuth provider
credentials, SMTP mailing lists, real bank connectors or actual finance tenants.
Use fixed synthetic traffic only. Never copy Production Redis keyspaces or secrets.

Ensure an isolated build from the approved exact Draft SHA (after code review);
do **not** use the existing Production deployment GitHub Actions workflow. Use
a separately approved staging-only workflow or an isolated test launcher.
Record image digest, git SHA, region, revision IDs, instance count and traffic
routing, excluding all secrets.

## 2. Read-only configuration and ingress preflight

- Verify the actual proxy connection peer as observed by ASGI, independent of
  client-controllable `X-Forwarded-For`. Keep `--no-proxy-headers`; do not
  guess any `RATE_LIMIT_TRUSTED_PROXY_CIDRS` addresses. Inspect known trusted
  ingress topology and whether each hop sanitizes/appends forwarded headers.
- Verify canonical HTTPS reset URL, OAuth callback URL and the untrusted
  `X-Forwarded-Proto` handling in `main.py` separately; ensure no redirect
  loop or attacker-controlled redirect. Stop if a request-derived host can
  appear in a password reset or OAuth redirect.
- Confirm explicit staging `ENVIRONMENT=staging`,
  `RATE_LIMIT_REQUIRE_SHARED=1` and secure `REDIS_URL` (Secret Manager
  reference, not plaintext in logs or workflow). Do not set `TEST_MODE=1`
  on deployed services.
- Verify Redis TLS certificate/authentication, VPC firewall, network ACL,
  namespace, timeouts, connection limits, memory, eviction policy, backups and
  alerting. Deny release if Redis can be accessed without the expected auth.
- Check SlowAPI initialization does not choose memory or become disabled
  through an inherited `RATELIMIT_*` configuration. Confirm its 3/minute and
  5/minute route decorators remain active. Confirm category limiter and
  SlowAPI use the same shared Redis endpoint but intentionally distinct
  quota keys.

## 3. Controlled two-replica quota exercise

Run **two separately identifiable replicas**, with synthetic traffic routed
to both. Record instance routing (no customer IPs), the exact allowed/denied
counts, quota keys' remaining TTL and aggregate request counts.

| Scenario | Expected result / stop condition |
| --- | --- |
| Shared category AUTH quota of 10/min across both | Exactly 10 accepted before 429, not 10 per replica; safe response and Retry-After |
| SlowAPI existing decorated login 5/min or forgot 3/min, per route | Existing route-specific cap preserved across both replicas; 429 after aggregate cap |
| Mixed endpoint load over categories | No cross-tenant privilege escalation; no ability to cycle client-supplied XFF to reset limit |
| Near-expiry requests | Fixed window expires based on first request; no extension or lockout reset by late traffic |
| Service restart with Redis counter live | Shared counter and TTL persist, no reset to zero |
| Proxy trust not configured | Rate limits fail safely by socket peer, but shared ingress IPs may cause false 429: record as operational blocker |
| Malformed or duplicate XFF and attacker-supplied leftmost hop | Identity cannot be chosen by an untrusted header |

Use exact synthetic IDs and rates sufficiently below service-scale thresholds
to avoid incidental costs. Do not generate unbounded load.

## 4. Controlled Redis outage and recovery (explicit approval required)

Only in isolated staging, with an approved operator, simulate a Redis
connection failure and then restore it. Check both limiter layers, and
confirm no write/financial operation proceeds unthrottled. Expected HTTP is
`503`, error `RATE_LIMIT_BACKEND_UNAVAILABLE`, short `Retry-After`, no
database/Redis secrets, no local-memory fallback. Test existing 429 separately
so backend outages are not confused with an exhausted quota.

Restore Redis and confirm pre-existing counters resume (or expire according
to their original TTL), no secrets enter logs, alerts fire and recover, and
failure behavior is consistent across replicas. Stop immediately on unexpected
200, 500 with Redis error details, 429 mislabeled as an outage, counter reset
on one replica, invalid TLS, unauthorized access, or 503 that persists despite
healthy Redis without an approved recovery step.

## 5. Evidence and release decision

Capture staging-only configuration metadata (no secrets), a signed/tested SHA,
network/topology proof, route-level results, distributed Redis counter evidence,
Redis outage/restore and auth user experience, alerts, costs and rollback plan.
Independent reviewer must confirm both correctness **and availability**.
Failure of any criterion leaves **HOLD**. Passing staging is a gate toward,
not automatic permission for, `main` merge or Production deployment.

Other P0 gates remain: SQL migrations 013–016, tenant RLS/runtime grants,
JWT rollback, real OAuth/SMTP E2E, Cloud SQL automated backups/PITR and restore,
GCS attachment restore, US/EU parity, finance E2E, and local Git/ACL integrity.
