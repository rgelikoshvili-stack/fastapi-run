# Bridge Hub — Chat174 global Host guard, OAuth forced-RLS and P0 release gate

**Date:** 2026-10-29. **Scope:** Draft PR #154 only. **Production: HOLD.**
This document describes Draft code and synthetic tests, not a live deployment.

## Host policy: safe staged activation, NOT enabled

- Chat173 constrained OAuth redirect and HTTPS redirect origins but did not enforce a global Host allowlist.
- Chat174 adds app/api/trusted_host_guard.py as the outermost HTTP middleware in main.py. It executes ahead of auth, redirect, logging, limits and handler invocation when enabled.
- The policy is OFF when BRIDGE_TRUSTED_HOSTS_ENFORCE is absent or exactly 0. This preserves current, unverified ingress traffic; it does NOT prove live Host protection is enabled.
- **Only after owner-authorized isolated staging:** supply BRIDGE_TRUSTED_HOSTS_ENFORCE=1 plus a comma-separated exact BRIDGE_TRUSTED_HOSTS authority list, each host optionally including a port. Synthetic example: bridge.example.test,internal.example.test:8080.
- No wildcard, public-suffix entry, scheme, userinfo, URL path/query/fragment, percent-encoded hostname, unicode hostname, whitespace, ambiguous port or duplicate list entry. Unknown/missing/duplicate malformed Host returns generic HTTP 400 HOST_UNTRUSTED; invalid policy or mistyped enable value returns HTTP 503 HOST_POLICY_UNAVAILABLE.
- X-Forwarded-Host is never used for acceptance, and raw Host is never echoed in the response. Explicit Host validation does not replace CORS, TLS at the edge, proxy identity, or Cloud Run health and WebSocket checks. The current new middleware is **HTTP only**; WebSocket Host protection requires a separate tested ASGI-level gate before Production release.

## OAuth membership proof (synthetic only)

- Previous OAuth callback queried the users table without a transaction-local tenant context, even after consuming the provider-bound one-use OAuth state. That would fail for a non-owner runtime role under forced users RLS.
- Chat174 wraps ONLY the exact active membership lookup (email and tenant_id) in tenant_db_context after validated state/tenant and external provider identity. This is not database-owner bypass or new tenant membership creation.
- Disposable PG15/16 tests reuse a synthetic nonowner, NOSUPERUSER, NOBYPASSRLS role with forced users RLS. Migration 014 is applied to the isolated test schema before granting runtime DML. They verify identical-email identities in t_alpha and t_beta resolve their own user ID and versioned claims, consumed state rejects replay, and unknown t_gamma never receives tokens.
- Provider network calls are entirely mocked. The tests do not establish Cloud SQL permissions, production OAuth state RLS, real provider identity or real OAuth callback delivery.

## Approved independent staging: ordered stop/go plan (NOT EXECUTED)

1. **Read-only inventory:** enumerate every actual Cloud Run service, custom host, port, LB/CDN hostname, internal health probe, version/metrics endpoint, service-to-service call, WebSocket gateway, geographic region and exact immediate socket peer. Never guess Google proxy CIDR or production Host values. No secrets in the evidence.
2. **Owner approval:** approve cost/region and independent staging Cloud Run, PostgreSQL, Redis, separate OAuth test-app credentials and registered callbacks. No Production DB, Production OAuth app, customer records or live bank/SMTP.
3. **Baseline isolated test:** deploy reviewed code SHA in a separate approved environment with new Host enforcement and HTTPS in-app redirects still OFF. Capture real allowed Host and health/probe outcomes, callback origins, existing proxy chain and the correct configured APP_BASE_URL and OAUTH_REDIRECT_BASE_URL.
4. **Host policy pilot:** enable exact observed synthetic/staging Host list only. Valid Host should work through all routes and probes; unlisted/malformed/duplicate Host must not reach any handler; invalid config must return 503 rather than fail open. Verify HTTP/1.1, HTTP/2, WebSockets, API callbacks and direct connection bypass paths.
5. **OAuth E2E (only approved test identities):** provider registered callback URIs must exactly match configured HTTPS origins in each region. Test state issuance, provider binding, one-use, expiry, wrong tenant, same-email two-tenant membership, inactive user, nonowner forced RLS, OAuth error replay, access/refresh token claims and revocation. Record no token values.
6. **Stop conditions:** unknown Host accepted, health or partner integration broken, suspicious redirect, wrong-tenant token, durable state replay, per-replica limit, leaked credential, false 200 during Redis outage, or any unapproved data write. Abort promotion and keep HOLD.
7. **Independent review:** verify evidence, rollback, alarms, cost and owner sign-off. No staging pass automatically permits merging PR #153/154 or production rollout.

## Remaining P0 matrix (NOT assumed fixed by CI)

| Release gate | Current scope of evidence | Required evidence before production |
| --- | --- | --- |
| Users / financial tenant RLS | Synthetic nonowner forced-RLS and finance tests | Actual Cloud SQL owner-bypass, policy/grant audit and full cross-tenant E2E |
| Signature/Stamp and other sensitive API authorization | Previously flagged P0 | Staging endpoint-level JWT/RBAC and negative cross-tenant tests |
| JWT session revocation and US/EU parity | Disposable DB tests | Live-region JWT secret/version parity and revocation-safe rollback |
| OAuth redirects and membership | Chat173/174 Draft-only tests | Google/Microsoft staging credentials, provider callback and true tenant isolation |
| Reset links, SMTP and SQL migrations 013–016 | Draft compatibility tests | Explicit migration, runtime grants, real SMTP test and rollback |
| Redis quotas and proxy identity | Disposable multi-client Redis tests | Real two-replica Cloud Run TLS/network/outage and trusted immediate peer evidence |
| Cloud SQL backup/PITR and recovery | Not tested here | Read-only backup inventory and separately approved isolated restore drill |
| AI chat, reports, audit and account balances | Previously noted mismatch | Reconciled finance E2E and no cross-tenant annual report/audit leakage |
| Windows worktrees/index/ACL integrity | Preservation constraints | Authorized read-only inventory of originals before any mutation |
| main/Production promotion | PR #154 OPEN/DRAFT | Explicit owner approval after all P0 gates pass |

**Decision:** Draft work only; Production HOLD. No Cloud SQL DDL, live Host
configuration, OAuth provider action, Cloud Run deploy, PR merge or Windows
original-file mutation without separate explicit approval.
