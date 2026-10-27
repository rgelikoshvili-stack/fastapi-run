# Bridge Hub — Chat166: JWT session revocation on password change/reset

**Date:** 2026-10-27. **Scope:** Draft [PR #154](https://github.com/rgelikoshvili-stack/fastapi-run/pull/154). **Status:** tests PASS, **release HOLD**. **Production and main are unchanged.**

## Completed in isolated Draft branch

1. Added additive, idempotent PostgreSQL 15+ migration `app/storage/migrations/015_user_auth_version.sql`: `users.auth_version BIGINT NOT NULL DEFAULT 1` and positive constraint. Migration has been executed **only** against synthetic disposable PostgreSQL 15/16 in GitHub Actions; **not** on Cloud SQL.
2. Added gated `JWT_SESSION_VERSION_ENABLED=1` in `auth_service.py`. Default is **OFF**. When enabled, all freshly issued access **and** refresh JWTs must contain `auth_version` sourced from the actual user DB row; a missing/malformed session version is refused. The setting also enables the existing live membership check via `access_membership_check_enabled()`, requiring a DB read on every protected HTTP request.
3. Login, SaaS signup, OAuth callback and refresh-token exchange now include the current DB version when this flag is enabled.
4. `verify_live_access_membership()` rejects an access token whose signed `auth_version` differs from the current active user's version. `refresh_token()` rejects refresh tokens with a missing/mismatched version; newly issued tokens contain the current version.
5. Password change: inside one DB transaction, locks the exact user membership row, verifies the existing password and signed JWT version, updates password hash and increments auth_version. Old tokens are then rejected for that account on next request/refresh. The same email in a **different tenant** is not affected.
6. Password reset: locks one reset-token row with `FOR UPDATE`; checks unused/not-expired; atomically updates active user's password, increments auth_version when enabled and consumes the reset token. Parallel replay allows only one successful reset; an error updating the reset token rolls back password and version changes.

## Verified CI evidence

Last fully verified commit after wiring the Chat166 test into CI and correcting test Request fixtures:
`165110c9faea180f4949857955838ec3425edbfb`.

- [PostgreSQL 15+16 disposable CI](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40524133171): **80 passed** on PostgreSQL 15, **80 passed** on PostgreSQL 16 (test results verified from logs, action URL should be independently checked in PR checks).
- [Full backend test CI](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40524133332): **7,946 passed, 3 skipped**, and one extra integration smoke pass (action URL should be independently checked in PR checks).
- Frontend Build, RLS fail-closed disposable PostgreSQL and tenant-membership disposable PostgreSQL: all **PASS**.
- Deploy: **SKIPPED**, no Production deployment.
- Earlier CI initially failed because Chat166 test code passed `SimpleNamespace` to a SlowAPI-decorated route, which requires a real Starlette `Request`. Corrected in isolated test code; final PostgreSQL 15/16 matrix and full tests passed.
- New test: `tests/integration/test_chat166_session_version_postgres.py` exercises real application schema, migration idempotence, legacy token re-login behavior, change password, reset token one-use/replay, concurrency, other-tenant isolation and rollback on synthetic database error.
- `.github/workflows/chat162-oauth-state-postgres.yml` now includes both migration 015 and Chat166 tests in the matrix.

## Important remaining blockers and security caveats

**Do not activate the flag on Production without a coordinated migration and release plan.**

1. **Migration 015 unapplied to live Production**. The `users.auth_version` column must exist, and the runtime role must have appropriate permissions/RLS context, **before** enabling the flag. Staging must verify real PostgreSQL schema, tenant RLS behavior, existing users, and signup/Google/Microsoft provider flows.
2. **Flag OFF by default**. The new per-user token family revocation is not active in Production and is not a secure rollout until `JWT_SESSION_VERSION_ENABLED=1` is consistently enabled across every serving instance/region. Enabling intentionally forces users with pre-migration JWTs lacking `auth_version` to log in again.
3. **Disabling the flag after rollout is NOT a safe security rollback**: while OFF, previously issued signed JWTs can be accepted under legacy membership rules. Design an incident rollback that preserves revocation, rather than silently turning off the check.
4. **Reset under tenant RLS**: the public reset handler starts without a signed tenant context, then looks up token and updates the corresponding user. This passes synthetic PostgreSQL tests without Production RLS. Real production-role RLS, privilege and tenant-scoped reset behavior still need controlled isolated staging validation before release.
5. **Account/email scope**: password reset tokens are stored un-hashed in the legacy reset table, and first issued by the existing forgot-password route; consider hashed reset codes and stronger transactional/expiry handling as a separate security refinement.
6. **Existing open WebSocket**: membership checks occur at handshake and before each ~30s stats poll, not immediately on every broadcast. Financial events may require event-driven revocation/short-lived dedicated ticket.
7. **Other release gates**: migration 014, a separate truly isolated staging service and production-like DB, automated Cloud SQL backup/PITR, an isolated restore drill, Git ACL parity/dirty merge preservation, rate-limiting behind a trusted proxy, and actual Cloud Run latency validation all remain open.

## Safe remaining work (Chat167)

- Add synthetic **Production-role + forced RLS** staging tests for login, refresh, password-reset and the auth_version migration, without accessing production user data. Verify SQL identity context and non-owner DB role.
- Review legacy password-reset token storage, expiry and email/tenant mapping for robust tenant separation.
- Prepare a two-stage migration/release plan that cannot bypass active token revocation during rollback.
- Maintain PR #154 in Draft; never merge #153 and #154 separately without coordinated integration/CI.
- Do not modify local original Git, restored snapshots, main, Cloud SQL or Production without explicit approval.

**Gate: HOLD.** This report certifies disposable CI correctness, NOT an end-to-end Production security release.