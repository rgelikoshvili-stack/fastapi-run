# Bridge Hub Chat163 — OAuth throttling, state cleanup and JWT revocation audit

**Date:** 2026-10-27. **Branch:** `fix/chat161-auth-refresh-oauth-durable-20261027` (draft PR #154). **Main, Production, Cloud SQL and local unresolved Git are unchanged.**

## Implemented in the draft branch
1. OAuth GET login, callback and provider paths are classified as `RateLimitCategory.AUTH` (10 requests per 60 seconds), instead of the `DEFAULT` category (120 per 60 seconds).
2. AUTH limits use a shared anonymous bucket per direct network peer; neither unverified `X-Tenant-ID`, user ID nor client-supplied `X-Forwarded-For` can reset the rate-limit bucket. The counter key stores only a hash of the peer address.
3. New OAuth issuance performs a **bounded opportunistic** PostgreSQL cleanup: at most 128 expired hashed state rows per issuance, using `expires_at` index and `FOR UPDATE SKIP LOCKED` to avoid waiting on concurrent transactions. New state still requires migration `014`, which remains unapplied outside disposable CI.
4. Unit and disposable PostgreSQL 15/16 tests cover: strict OAuth classification and 429 response; spoofed tenant/XFF attempts to evade quota; cleanup batch size and index criteria; expired row removal; keeping live states; non-blocking cleanup when a stale row is locked.
5. This adds **no** Cloud Scheduler job, external OAuth provider requests, production Redis changes, database migrations, or deployment.

## Important limits — still HOLD
- **P0 / Access token revocation not fixed**: `app/api/services/auth_service.py` currently issues access JWTs with **24-hour expiry**, and `verify_token()` checks signature, expiry and token type but does not query current account membership. `auth_middleware.py` uses JWT role/tenant claims for most protected routes. A revoked/deactivated member's **previously issued access token may remain usable for up to 24 hours**, even though the newly hardened refresh path rejects their refresh attempts. Password changes are also not guaranteed to invalidate old access JWTs. Do not claim immediate JWT/session revocation.
- **Cross-replica quota not certified**: `app/api/services/rate_limiter_service.py` falls back to process-local memory when Redis is absent/down. Redis is necessary for a consistent application-wide quota under multiple Cloud Run instances. Its failure fallback means rate limiting is *best effort*, not a security boundary.
- **Proxy behavior needs staging proof**: direct `request.client.host` is deliberately non-spoofable, but behind Cloud Run ingress it may be a shared proxy address, causing false positive 429s for different clients. Before activation test realistic proxy topology and availability; use an appropriately configured, trusted edge policy (for example Google Cloud Armor) and restrict direct `run.app` ingress bypass. See official docs: https://docs.cloud.google.com/armor/docs/rate-limiting-overview and https://docs.cloud.google.com/armor/docs/integrating-cloud-armor.
- **Expired-row collection is traffic-triggered only**: when no new OAuth login occurs, cleanup does not run. Operational completion requires a separately approved periodic Cloud Scheduler/Cloud Run job or equivalent least-privilege cleanup mechanism; do not run a production cron until approved. Existing migration's `expires_at` index supports this.
- **Auth migration rollout order**: migration `014_durable_oauth_login_states.sql` must be applied and tested under correct privileges on isolated staging **before** enabling any version of this OAuth code; otherwise new OAuth login fails closed with HTTP 503.
- **One more security review**: verify all authentication bypass/public route prefixes and query-string token paths under the actual middleware order, including `rbac_middleware` and `auth_middleware`, before release.
- **No user-approved Git merge or Production deploy**: draft PR only; do not separately merge PR #153 and #154.

## Next gate (Chat164) — short-lived access tokens and revocation architecture
1. Define whether disabling a user must revoke issued access tokens immediately (finance/payment operations strongly favor yes).
2. Prepare versioned identity/session revocation or an authoritative active-membership check on every protected API request; validate tenant scope and current role in PostgreSQL, with fail-closed handling and bounded DB performance. Select a plan for legacy JWTs without silently trusting missing revocation claims.
3. Add disposable PostgreSQL tests for disabled user, tenant transfer, role changes, forced logout and previously issued **access** JWTs (not only refresh); include direct file download and privileged financial endpoints.
4. Decide access JWT TTL (today 24h) together with frontend refresh behavior; a shorter TTL alone is **not immediate revocation**.
5. Only after owner approval, staging tests and recovery evidence, schedule production changes. Git ACL and backup/PITR/restore gates remain open.

## Evidence to inspect
- CI: `test`, `frontend-build`, `tenant-membership-postgres`, `OAuth migration and JWT refresh (Postgres 15/16)`
- `tests/unit/test_chat163_oauth_rate_limit.py`
- `tests/unit/test_chat161_oauth_state.py`
- `tests/integration/test_chat162_oauth_state_postgres.py`

**Release gate: HOLD until the P0 JWT access revocation and infrastructure items are validated.**
