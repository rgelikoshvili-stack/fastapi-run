# Bridge Hub — Chat173: Host, HTTPS upgrade and OAuth callback origin

**Date:** 2026-10-29. **Scope:** Draft PR #154 ONLY. **Release:** HOLD.
**Last independently CI-verified CODE SHA:** `ee67facecf8c1f3a1ad6c3eefb4fca2c4f97e4de`.

No merge to `main`; no Production Cloud Run / Cloud SQL / Redis setting changes,
real OAuth provider calls, credential changes, staging deployment, or original
Windows Git/ACL mutation.

## 1. Confirmed vulnerabilities (pre-Chat173)

- `main.py::https_redirect` accepted `X-Forwarded-Proto: http` from any
  request and built a new `Location` by rewriting `str(request.url)`, whose
  authority comes from untrusted `Host`. This permitted host poisoning of
  redirect destinations and potential redirect loops behind TLS termination.
- `app/api/routes_oauth.py::_redirect_uri` fell back to
  `str(request.base_url)` when `APP_BASE_URL` was absent. That could feed
  an attacker-supplied request authority into the provider's OAuth redirect
  URI on login and token exchange. The state creation/consumption order did not
  prevent this origin misconfiguration.
- `app/api/routes_auth.py::auth_login` logged the raw, untrusted
  `X-Forwarded-For` header and therefore recorded attacker-selectable
  IP strings and raw client IP addresses.

## 2. Draft-only changes

1. **Central origin validator:**
   `app/api/trusted_request_origin.py` parses only explicitly configured
   origin strings. Requires canonical HTTPS, forbids authority userinfo,
   arbitrary paths, query, fragment, encoded hostname, Unicode authority,
   control characters, whitespace, backslash and invalid ports. During
   synthetic local tests only, an explicit `TEST_MODE=1` permits HTTP
   localhost, but **never** when `ENVIRONMENT=production`.
2. **OAuth callback URI:** Uses `OAUTH_REDIRECT_BASE_URL`, or falls back to
   the configured `APP_BASE_URL`; it **never** uses request `Host`,
   `request.base_url` or `X-Forwarded-*`. Invalid/missing origin returns
   generic `503 OAUTH_ORIGIN_UNTRUSTED` **before issuing** a durable OAuth
   state and **before consuming** a callback state. Login and token exchange
   use the same validated URI.
3. **Optional HTTPS upgrade:** App-level redirects are **OFF by default**.
   `HTTPS_REDIRECT_ENABLED=1` is not enough by itself: an explicitly
   configured, validated `HTTPS_REDIRECT_TRUSTED_PROXY_CIDRS` must match
   the **immediate socket peer**, and exactly one
   `X-Forwarded-Proto: http` and one `Host` matching the approved
   canonical `APP_BASE_URL` authority are required. Request URL authority
   is never reflected. Raw ASGI path/query are validated before forming
   `Location`; unsafe/malformed inputs do not trigger a redirect. A
   trusted redirect uses **307**, preserving the HTTP method and avoiding
   an implicitly permanent redirect.
4. **Login logs:** Hashes the same trusted IP identity used by Chat170's
   rate limiters and logs only a short non-reversible fingerprint; no raw IP
   or client-supplied XFF is copied into login audit logs.
5. Synthetic unit tests:
   `tests/unit/test_chat173_https_oauth_host_proxy.py` covers
   configured origins, HTTPS-only production, OAuth Host spoofing,
   no state issuance/consumption on bad origin, untrusted XFP, duplicate
   headers, missing/broad proxy ranges, malformed raw path/query, and
   valid opt-in redirect. Existing OAuth membership/state test fixtures
   now explicitly configure synthetic HTTPS callback origins.
6. PG15/16 workflow now includes the Chat173 tests and source paths.
   No actual proxy IP allowlist, environment flag or OAuth credential was set.

## 3. Verified synthetic CI evidence

- [Disposable Redis 7](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40855537429):
  **210 passed**.
- [Disposable PostgreSQL 15/16](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40855537354):
  **210 passed on PG15**, **210 passed on PG16**.
- [Backend/frontend workflow](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40855537201):
  **8,071 backend passed, 3 skipped**, additional integration smoke
  **1 passed**, frontend build SUCCESS, actual Cloud Run
  **deploy SKIPPED**.
- [Tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40855537400):
  PASS.
- [Fail-closed finance RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40855537434):
  PASS.
- Tests are synthetic/isolated. **No real Cloud Run HTTPS/proxy setup,
  provider OAuth callback, real user login or Production availability was
  verified.**

## 4. Critical staging preflight / release gates

- Verify the actual external HTTPS edge and **immediate ASGI socket peer**,
  Cloud Run runtime scheme and TLS termination; the installed Uvicorn
  `--no-proxy-headers` behavior is not a substitute for live testing.
  **Do not guess** Google/Cloud Run proxy CIDRs or turn on app redirects.
  The ingress should enforce HTTPS without relying on client-supplied
  forwarded headers.
- Confirm exact canonical public `APP_BASE_URL`, optionally dedicated
  `OAUTH_REDIRECT_BASE_URL`, and OAuth provider-registered callback URLs
  for each approved region/provider. Misconfigured/missing origins now
  **intentionally block** OAuth. Real Google/Microsoft OAuth exchange and
  callback are NOT tested.
- Validate that ingress **overwrites/sanitizes** `X-Forwarded-Proto`,
  `X-Forwarded-Host` and XFF. Only after explicit owner approval and
  proof may staging set `HTTPS_REDIRECT_ENABLED=1` and the narrow,
  observed `HTTPS_REDIRECT_TRUSTED_PROXY_CIDRS`.
- The new protection covers known URL-generation sinks and in-app redirect.
  A **global TrustedHost allowlist is NOT configured**; enumerate all
  authorized Cloud Run/custom domains and internal probes first, or a
  global Host filter can cause an outage. Verify URL generation, CDN
  routing and error/redirect behavior with malicious Host headers
  in isolated staging before deciding on global enforcement.
- Verify GET/POST redirect semantics, legacy password reset links,
  no OAuth state loss, no HTTP redirect loops, no leaking auth code/state
  in logs or cross-domain redirects, and canonical host behavior.
- Require separate approval for staging deployment and SQL/Redis changes.
  Legacy release gates remain: shared Redis with verified multi-replica
  network/failover and availability; RLS/role grants; migrations 013–016;
  Cloud SQL backup/PITR and recovery drill; real SMTP/OAuth, US/EU parity,
  complete financial tenant isolation E2E; original Windows repo integrity.

**Decision:** Draft code and CI PASS; live staging NOT VERIFIED;
Production **HOLD**, PR #154 OPEN/DRAFT.
