# P1-SECRET-1 — Email credential audit

Audit date: 2026-09-29
Scope: read-only source/configuration review before implementation. No production environment, Secret Manager, database, or external email service was accessed or changed. Resolution status below reflects this PR's safe local implementation.

## Findings

### Credential sources

- `app/api/services/email_collector.py` reads each tenant's email address and app password from `tenant_email_credentials`. Rows with `credential_status='active'` are decrypted through `CredentialVaultService` using the `email` / `imap_app_password` vault entry. The save path writes through that vault and stores only a marker in the legacy column.
- At audit time the collector had a `legacy_plaintext` fallback returning `tenant_email_credentials.app_password` to the IMAP client. This PR removes that fallback; legacy rows now fail closed and require controlled vault migration.
- At audit time `app/api/services/email_invoice_service.py` had a second IMAP path with a legacy `app_password` fallback and environment fallback. This PR removes the DB plaintext fallback and routes shared IMAP password access through the email secret loader; tenant credentials remain vault-backed.
- At audit time `app/api/email_service.py` read `SMTP_PASS` directly from process environment. This PR routes it through the shared email-secret loader; Cloud Run receives the value through a Secret Manager-backed mapping.
- No `GMAIL_APP_PASSWORD` runtime lookup was found in the inspected code. Gmail tenant credentials are the per-tenant vault values described above; a single global Gmail password would not represent the multi-tenant model.
- `app/config/secrets.py` supports environment-first reads and Google Secret Manager lookup when configured with `GCP_PROJECT_ID` and `USE_SECRET_MANAGER`. Its warm-up currently checks only `DATABASE_URL` and `JWT_SECRET`; the email call sites bypass this loader.

### Cloud Run workflow

- `.github/workflows/deploy.yml` currently uses `--set-secrets` for the five existing mappings: `DATABASE_URL`, `JWT_SECRET`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, and `VAULT_ENCRYPTION_KEY`.
- The workflow uses `--update-env-vars` for deployment metadata (`COMMIT_SHA`, `BUILD_TIME`, `ENVIRONMENT`); it does not set `SMTP_PASS` or Gmail passwords as plain environment values.
- `--set-secrets` is replacement-style and removes other existing secret mappings. The plan changes this to `--update-secrets`, preserving the existing mappings while adding email secret references. The official [gcloud run deploy reference](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy) documents both behaviors.

### Logging and API surface

- The collector did not intentionally log password values, but credential lookup and IMAP failures included exception text in some logs/results. This PR replaces those outward errors with generic, value-free messages.
- `/email-collector/status` returns a configured boolean and email address only; it does not return the app password. Credential save/test endpoints accept the password in the request body but their successful responses do not include it.
- `/email-invoice/status` returns configured state, server address/port, and a masked username; it does not return the password. Some email operations return provider exception text/tracebacks; these should not contain or echo the password and will be covered by response-redaction tests.

### Files and fixtures

- `.env.example` contains blank sensitive settings and no Gmail/SMTP password values.
- Existing email unit tests use local fakes/mocks and do not make live Gmail calls. Test inputs are synthetic placeholders; no production secret values were inspected or printed.
- No evidence of a real secret was found in the scoped source/config/test review. Broad secret-keyword searches also match docs, variable names, and synthetic test cases; these are not themselves secret values.

## Decision

`P1_EMAIL_SECRET_AUDIT_READY` (audit complete; findings addressed locally as noted)

The baseline runtime had plaintext compatibility/configuration risks: a legacy per-tenant DB fallback and direct SMTP/IMAP environment reads. The local implementation removes the legacy DB fallback, uses the shared loader, adds Cloud Run secret references, and sanitizes errors. Production setup and password rotation remain out of scope for this code change.
