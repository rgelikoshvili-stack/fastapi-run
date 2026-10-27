# Bridge Hub — Chat169 password-reset security and isolated staging gate

**Date:** 2026-10-27. **Scope:** GitHub Draft PR #154 ONLY. **Production: HOLD.**
**Last CI-verified code commit:** `80022e48a6f14c756ffb10654364af5898629756`.

## Exact verified test results

- [PostgreSQL 15 and 16 disposable CI](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40534589299): **106 passed** on PostgreSQL 15, **106 passed** on PostgreSQL 16 (each verified from the final job logs).
- [Backend + frontend workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40534589180): backend **7,967 passed, 3 skipped**; separate smoke **1 passed**; frontend PASS. Deployment job explicitly **SKIPPED**.
- [NEXT-04A synthetic RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40534589237): PASS.
- [NEXT-01 tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40534589317): PASS.
- All tests use synthetic localhost containers or unit fixtures, **not** production Cloud SQL / Cloud Run / real customer records.

## Draft-only security changes

1. **Digest storage for new reset links.** `_reset_token_storage_key()` stores `sha256:<hex>` (71 chars) instead of the 384-bit random raw code in `password_reset_tokens.token VARCHAR(128)`. No migration 017, no bulk rewrite. Existing raw-token rows remain usable until expiry.
2. **No pass-the-hash.** A database reader cannot redeem a stored digest via the legacy fallback: a presented string beginning `sha256:` is not used for plaintext-row lookup. Added both unit and actual synthetic PostgreSQL regression tests for attempted digest redemption.
3. **Single-use remains transactional.** The previously implemented `SELECT ... FOR UPDATE` and token consumption remain inside one transaction, with rollback and same-email cross-tenant tests. Synthetic forced `users` RLS with a nonowner role remains active in the PostgreSQL 15/16 test fixture.
4. **Trusted email link origin only.** `PASSWORD_RESET_BASE_URL` takes priority; otherwise `APP_BASE_URL` (already used elsewhere in this project). Must be a valid canonical HTTPS **origin**, without credentials, query, fragment or arbitrary path. For tests only, `TEST_MODE=1` allows HTTP localhost. Neither Host nor X-Forwarded-Host supplies the emailed reset link.
5. **Missing/invalid origin fails closed.** The service refuses to mint/send a reset link when neither trusted base URL is configured, while giving the same generic public response. This is an explicit **configuration gate**: an environment without `PASSWORD_RESET_BASE_URL` or `APP_BASE_URL` cannot deliver working reset links with this Draft code.
6. **Fragment-only new links.** New emails use `/static/reset_password.html#token=...&tenant_id=...` instead of a query string so new raw codes are not sent in normal HTTP GET query logs. The page reads either new fragment links or old query links, then removes the secret from the address bar using `history.replaceState`.
7. **Safer HTML and response.** Reset email `href` is HTML-escaped, public forgot-password responses suppress raw database/SMTP exceptions and disclose neither user existence nor internal error details. Reset HTML receives `Referrer-Policy: no-referrer` and `Cache-Control: no-store`.
8. **Coverage.** Added `tests/unit/test_chat169_password_reset_security.py` (bad origins, malicious Host headers, digest non-redemption, generic public error response, sanitized HTML, fragment/legacy page support). Wired it into the PostgreSQL matrix; extended existing nonowner/forced-RLS integration tests.

## READ-ONLY preparation for isolated staging

- A read-only, no-DDL/non-mutating role/schema inspection script is in [docs/sql/chat169_auth_reset_staging_readonly_preflight.sql](sql/chat169_auth_reset_staging_readonly_preflight.sql). It was **prepared, not run on Cloud SQL**.
- Obtain separate owner authorization before creating/using independent cloud staging, running migrations, granting database privileges, changing runtime flags or sending real reset emails.
- In the approved isolated database, inventory the actual schema and runtime role; verify `users.auth_version`, `password_reset_tokens`, `oauth_login_states`, their RLS policies and privileges. Review whether migration 013 is required, then explicitly apply approved 014/015/016 in the correct sequence **using a migration role**, never the public API.
- Validate the nonowner application role has only its necessary DML grants, not schema CREATE, with tenant isolation. Verify a configured HTTPS reset origin and approved SMTP settings. Test actual browser/email link fragments, legacy links, one-use/replay, duplicate email across companies, OAuth and JWT flags ON/OFF, and all rollback cases.
- No assertion is made that a staging deployment or a cloud restore was performed.

## Remaining HOLD blockers

- **No live certification** of production users/token RLS, Cloud SQL role or schema, SMTP delivery, OAuth providers, app load under production-like latency, or real financial E2E.
- Legacy raw reset records remain in storage until expired or explicitly cleaned by a separately approved retention process. Password-reset table tenant RLS is not proven in production.
- **Rollback must preserve compatibility:** reverting solely to earlier static page/API code would fail new fragment links and digest rows. After JWT version revocation is activated, turning its flag OFF may reauthorize previously revoked valid JWTs; no flag-only rollback.
- The shared SlowAPI limiter currently trusts `X-Forwarded-For` without a demonstrated trusted-proxy boundary; cross-replica Redis and proxy rate-limit behavior require independent security proof.
- User enumeration may remain measurable by response timing despite identical response bodies; SMTP and proxy/CDN redirect handling of fragment links need real E2E verification.
- Migration 016 predeploy dependency, automatic backups/PITR, isolated restore and GCS attachment recovery, PR #153/#154 stacked integration, original dirty Windows Git/index/ACL, US/EU parity and full accounting workflows remain separate release gates.

**Decision: keep PR #154 OPEN and DRAFT; no merge, Cloud Run deployment, Cloud SQL DDL or Production changes without separate approval.**
