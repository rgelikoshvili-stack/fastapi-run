# P1-SECRET-1 — Gmail/SMTP Secret Manager plan

Status: safe implementation plan; not a production change authorization.
No production secret, environment variable, database row, or deployment has been changed.

## Secret model

| Purpose | Runtime key | Secret source | Planned Secret Manager name |
|---|---|---|---|
| Outbound SMTP password | `SMTP_PASS` | Google Secret Manager via Cloud Run secret reference | `bridge-hub-smtp-password` |
| Shared/system IMAP fallback password | `IMAP_PASS` | Google Secret Manager via Cloud Run secret reference | `bridge-hub-imap-password` |
| Tenant-specific Gmail app passwords | Per-tenant vault entry `email` / `imap_app_password` | Existing encrypted credential vault; no global shared password | None; do not create a single-tenant secret for all customers |

`GMAIL_APP_PASSWORD` is not an active code lookup. If a future system-owned Gmail mailbox is introduced, use a separately approved, dedicated secret (proposed name `bridge-hub-gmail-app-password`); do not reuse a tenant password or add it to this deployment by default.

Non-secret runtime configuration may remain in environment variables: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `IMAP_HOST`, `IMAP_PORT`, `FROM_EMAIL`, `APP_BASE_URL`, `GCP_PROJECT_ID`, and `USE_SECRET_MANAGER`. Usernames/emails should still be treated as personal data and not logged unnecessarily. `DATABASE_URL`, JWT and AI credentials remain Secret Manager references under their existing names.

## Cloud Run mapping

Use additive `gcloud run deploy --update-secrets`, not `--set-secrets`, for the email additions:

```text
SMTP_PASS=bridge-hub-smtp-password:latest
IMAP_PASS=bridge-hub-imap-password:latest
```

Retain the current non-secret `--update-env-vars` deployment-metadata behavior. Keep existing database/JWT/AI/vault mappings intact. `--set-secrets` clears existing secret mappings before replacing them; `--update-secrets` avoids removing mappings not named in the update, as specified by the [official gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy).

The deployment service account must have Secret Manager Secret Accessor permission only on the required secrets. Cloud Run should consume version `latest` only after a controlled rotation/version-approval step. Do not put secret payloads into GitHub Actions variables, `--set-env-vars`, `.env.example`, logs, docs, or command output.

## Runtime behavior and compatibility

- Email send/IMAP code reads credentials through the existing `app.config.secrets.get_secret()` interface. In local `TEST_MODE=1`, external Secret Manager lookup is disabled and absent values produce a degraded/not-configured response rather than an exception or network attempt.
- Tenant email credentials continue to be tenant-scoped and decrypted through the existing credential vault. Remove legacy reads from the plaintext `app_password` DB column. An old row that is not vault-backed is reported as unconfigured; it is not silently used.
- Error/status payloads contain only `configured`/degraded state and generic error codes/messages, never password values or full credential-provider exceptions.
- No Gmail password rotation is automated. An operator must rotate the app password and save it through the approved vault flow for each affected tenant.

## Production rollout gate

Before merging/deploying this PR, an authorized operator must, in a separate controlled production operation:

1. Inventory whether any active tenant still depends on the legacy plaintext column, without selecting or printing password values.
2. Create the SMTP and shared IMAP secrets in the approved Google Cloud project and add new versions through a protected secret-entry channel (never shell history, Git, CI output, or docs).
3. Grant the Cloud Run runtime service account least-privilege access to those secrets.
4. Migrate/re-enter any legacy tenant credentials through the existing encrypted vault UI/API and verify only non-secret configured status.
5. Confirm the workflow's additive mapping is valid and that required existing Secret Manager mappings remain present.

This PR does not perform those operations or change production configuration. The repository's `main` deployment workflow runs on push to `main`; merging a future approved PR will therefore initiate its normal automated Cloud Run deployment. No manual deployment is part of this task.

## Rollback

If the new secret references or loader cause a service issue, roll back the code revision through the approved release procedure. Restore the prior workflow mapping only with an explicit operator-reviewed change; do not restore a plaintext secret value to repository configuration. Keep the previous Secret Manager version enabled until verification is complete. If a tenant is not vault-backed, mark its email connector degraded and re-enter credentials through the vault; do not re-enable a plaintext DB fallback.

## Verification

- Unit-test loader success/missing/error behavior with mocked Secret Manager only.
- Assert missing credentials return `configured=false` / degraded and no external Gmail calls occur in test mode.
- Assert no secret value appears in logs, status payloads, exceptions, docs, `.env.example`, workflow literals, or committed test fixtures.
- Check that deployment YAML uses additive secret references and retains `--update-env-vars`.
- After separate production approval, verify Cloud Run revision health and per-tenant email connector status without reading back or printing secrets; use a controlled test mailbox only if separately approved.

## Decision

`P1_EMAIL_SECRET_PLAN_READY`
