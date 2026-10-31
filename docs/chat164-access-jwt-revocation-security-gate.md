# Bridge Hub Chat164 — access JWT revocation and WebSocket security

**Date:** 2026-10-27. **Status:** Draft PR #154, release **HOLD**. Nothing applied to `main`, the user's Windows Git, Cloud SQL, Cloud Run or Production.

## Threat model

Current access JWTs expire in **24 hours**. Checking JWT signature and expiration without comparing current tenant membership permits a previously issued access token to retain its old role/tenant after a user is disabled, deleted, transferred to another tenant, or demoted. Chat161 already revalidates **refresh tokens**, which does **not** revoke already issued **access tokens**. Browser WebSocket notifications are not covered by FastAPI HTTP middleware.

## Implemented in isolated code

1. `auth_service.verify_live_access_membership(signed_payload)` queries only current active `users` row by numeric ID **and** tenant under `tenant_db_context`; compares current email, tenant and role to signed JWT. Invalid/malformed claims and revoked membership are denied. DB errors propagate, rather than falling back to stale claims.
2. `auth_middleware` performs this check **before** setting `request.state.authenticated` and before passing the request to RBAC or a protected route. Denied/changed membership receives HTTP 401; DB unavailable yields HTTP 503 (fail closed). Includes protected auth endpoints such as `/auth/me`, `/auth/company-profile`, `/auth/signature` and `/auth/stamp`.
3. Deleted the duplicate signature-only `?token=` acceptance in RBAC. Only `auth_middleware` can accept download URL tokens on its restricted download/export paths. This prevents RBAC from reauthorizing a download after the live membership check rejected it.
4. WebSocket `/notifications/ws/live` now **always** rejects missing, expired, refresh-only, invalid, default-tenant and cross-tenant JWTs before accepting any socket, even when the live membership flag is off. With live-check flag enabled it also rechecks membership at handshake and before each 30-second statistics poll, closes a revoked user's socket, and runs tenant statistics under signed tenant DB context.
5. Test coverage includes revoked/changed/deleted user, role change, tenant transfer, malformed claims, PostgreSQL failure, download query token bypass, authenticated company-profile and signature path, WebSocket handshake and socket revocation, plus real disposable PostgreSQL 15 and 16 integration.

## Operational release flag — still disabled

`ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK=1`

The default is **0 (OFF)**. Enabling in Production is a separate operational change requiring explicit authorization, an access-control/schema compatibility audit and load testing. Never claim immediate Production access-token revocation from a green Draft PR while this flag remains off.

The DB must have a compatible `users (id, email, role, tenant_id, is_active)` schema and appropriate privileges/RLS for checking active memberships. An incompatibility or DB outage when the flag is enabled returns 503 to authenticated requests, by design. Define an incident/rollback plan without accidentally restoring access to revoked sessions. Invalidating old signed tokens at release might disrupt sessions with missing/noncanonical claims; arrange a controlled client re-login and test the actual UI/SDKs.

## Residual security caveats

- **HTTP requests:** when the flag is on, revocation takes effect at the next protected HTTP request *after the disabling transaction commits*. It cannot retroactively cancel a request that already passed membership validation.
- **Existing WebSocket clients:** ongoing sockets validate on a **30-second polling interval**. A notification delivered between revocation and the next check may still be received; true immediate socket revocation requires event-driven disconnect/shared revocation signaling or per-send membership checks, separately reviewed.
- **Public endpoints:** certain intentionally public authentication/password-recovery endpoints do not use the protected HTTP middleware. Their own reset-token validation, account recovery and rate limits need dedicated security review; this change is not a complete audit of every login flow.
- **JWT query parameters:** WebSocket and historical export URLs still pass access JWTs as query strings; consider a short-lived, one-purpose socket ticket and log redaction to reduce credential leakage.
- **Performance:** access validation makes a DB read per authenticated request with the flag on. Stage realistic performance, database downtime, pooled connection reuse and multi-tenant isolation checks before enabling.
- **Other blockers:** Production automated backup/PITR, isolated restore drill, Git ACL parity, staged migration 014, OAuth provider E2E, edge rate limiting and local merge recovery remain HOLD.

## Production rollout order (NOT EXECUTED)

1. Review current PostgreSQL membership schema, user disable/role-change flows, and least-privilege DB role in isolated staging.
2. Deploy draft changes to *isolated* staging only, with migration 014 applied there by an approved independent migration step.
3. Enable `ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK=1` in staging and run disabled/changed-role/tenant, DB-outage and normal user flows, including export downloads and WebSocket; compare DB query overhead and UI behavior.
4. Approve a dedicated rollback plan and release window only after production backup protection and restore verification. Require user/owner authorization for `main` merge and any Production environment modification.
5. Verify active-session invalidation, monitoring and audit logs after staging; only then consider Production activation. Maintain separate gates for strict instantaneous WebSocket/broadcast revocation.

## Evidence

- `tests/unit/test_chat164_live_access_revocation.py`
- `tests/unit/test_chat164_websocket_revocation.py`
- `tests/integration/test_chat162_oauth_state_postgres.py`
- `.github/workflows/chat162-oauth-state-postgres.yml`
- Draft [PR #154](https://github.com/rgelikoshvili-stack/fastapi-run/pull/154)

**Decision: HOLD.** The isolated changes protect HTTP and WebSocket access when properly activated; no claim of Production deployment or unconditional instantaneous revocation.
