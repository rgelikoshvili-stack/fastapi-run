# Chat168 — nonowner forced-RLS auth and password-reset DDL release gate

**Date:** 2026-10-27. **Scope:** Draft PR #154 only; **release status: HOLD**.
**Verified CODE commit:** `ef2062e2aba4187a0930fa46fa28ab744363fefa`.
`main`, production Cloud Run, Cloud SQL, and on-device repositories were not changed.

## Changes made

1. Added `tests/integration/test_chat167_auth_forced_rls_postgres.py` and wired it to the dedicated synthetic PostgreSQL 15/16 Actions matrix.
2. The test creates a unique disposable schema, an actual **nonowner LOGIN database role** (`NOSUPERUSER NOBYPASSRLS`, no schema CREATE), two same-email synthetic users in separate tenants, and a strict **FORCE ROW LEVEL SECURITY users policy**. This is a synthetic staging-style policy, **not evidence that production users RLS is configured**.
3. Password login now sets a transaction-scoped tenant context for the requested credential lookup, then uses the **authenticated database user's actual tenant** for last-login update.
4. Forgot-password lookup scopes only its tenant-specific credential-recovery query; actual reset authorization remains based on the emailed one-time token. Password change uses the signed JWT tenant for its transaction-scoped user lock and update. Password reset uses the locked, verified reset-token tenant for its update.
5. Removed `CREATE TABLE IF NOT EXISTS` from the public `/auth/forgot-password` runtime path. Added the additive, repeatable, privileged migration `app/storage/migrations/016_password_reset_tokens.sql`. The route now requires the table to be created before deploying the new application code. The migration creates no service-role grants and does not delete existing tokens/rows.
6. The PostgreSQL integration fixture applies migration 016 twice, and confirms credential recovery works for a nonowner runtime role with no schema CREATE privilege.

## Independently verified CI evidence — code SHA ef2062e2...

- [Synthetic PostgreSQL 15/16 workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40530477624): **85 passed on PostgreSQL 15**, **85 passed on PostgreSQL 16**, checked from each job's output.
- [Full backend / frontend workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40530477474): backend **7,946 passed, 3 skipped**, extra integration smoke **1 passed**, frontend build PASS; **deploy SKIPPED**.
- [Fail-closed finance RLS workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40530477479): PASS.
- [Tenant-membership workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40530477448): PASS.

Intermediate CI failures were real and corrected in Draft:
- New test initially shared a SlowAPI client IP and hit the intentionally enforced 5/min rate limit; fixture uses a distinct test IP, with rate limits preserved.
- An unscoped public login/forgot lookup found zero rows under forced users RLS; code now scopes credential lookups appropriately.
- `CREATE TABLE IF NOT EXISTS` at a public password recovery endpoint failed with a nonowner/no-CREATE role even when a table already existed; the DDL moved to migration 016.

## Release-gate requirements / NOT proven

- **Do not merge or deploy** until approved staging has validated the exact migration sequence and existing schema (notably 013/014/015/**016**), least-privilege grants, tenant RLS, reset-token issuance and mail delivery, and actual authenticated UI/API + OAuth flows. Migration 016 **must precede code rollout** if the password-reset table might not exist.
- This test does **not** prove live production role permissions, live `users` RLS, production `password_reset_tokens` RLS, full provider OAuth, real SMTP delivery, or Cloud Run/Cloud SQL behavior.
- Legacy reset tokens are **stored in plaintext**. Hashing and token lifecycle should be a future separate change with safe migration/compatibility handling.
- Password-reset links are currently built from the incoming request base URL; trusted external base-URL configuration / Host-header defenses require separate security review.
- `JWT_SESSION_VERSION_ENABLED` is OFF in production by default. Activation invalidates unversioned existing JWTs; disabling after activation may accept previously signed still-valid tokens again. A rollback must preserve revocation, not merely toggle the flag off.
- Cloud SQL automated backups/PITR, proven restore, prod RLS, cross-region parity, full financial multi-tenant E2E and original dirty Git/index/ACL preservation remain separate release blockers.

**Decision:** Continue only isolated Draft work and prepare staging after explicit owner approval. Production **HOLD**.
