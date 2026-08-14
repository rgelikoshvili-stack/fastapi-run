# Secret Manager Migration Runbook
**Date:** 2026-08-15  
**Priority:** CRITICAL  
**Reason:** DATABASE_URL, JWT_SECRET, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, VAULT_ENCRYPTION_KEY
are stored as plaintext Cloud Run env vars. Anyone with `run.services.get` permission can read them.

---

## Current state (INSECURE)

| Secret | Storage | Risk |
|--------|---------|------|
| `DATABASE_URL` | Plaintext Cloud Run env | DB credentials exposed |
| `JWT_SECRET` | Plaintext Cloud Run env | All tokens forgeable |
| `ANTHROPIC_API_KEY` | Plaintext Cloud Run env | API key exposed |
| `OPENROUTER_API_KEY` | Plaintext Cloud Run env | API key exposed |
| `VAULT_ENCRYPTION_KEY` | Plaintext Cloud Run env | Vault master key exposed |
| `OPENAI_API_KEY` | Secret Manager ✅ | Correctly secured |

---

## Target state (SECURE)

All 5 secrets → Google Secret Manager (`bridge-hub-*` namespace).  
Cloud Run references them via `--update-secrets` (Secret Manager mounts, not env literals).  
`deploy.yml` already updated to reference them on every deploy.

---

## Migration steps

### Step 1 — Prerequisites (5 min)

```bash
# Ensure you are authenticated and on the right project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Verify you have the right roles
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --filter "bindings.members:$(gcloud config get account)" \
  --format "table(bindings.role)"
# Need: roles/secretmanager.admin OR roles/secretmanager.secretAdmin
# Need: roles/run.admin
```

### Step 2 — Run migration script (10 min)

```bash
export PROJECT_ID="your-gcp-project-id"
export DATABASE_URL="postgresql://user:password@host/dbname"
export JWT_SECRET="your-current-jwt-secret"
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENROUTER_API_KEY="sk-or-..."
export VAULT_ENCRYPTION_KEY="your-current-vault-key"

bash scripts/setup_secret_manager.sh
```

The script will:
1. Create (or update) 5 secrets in Secret Manager
2. Grant Cloud Run SA `secretmanager.secretAccessor`
3. Update the Cloud Run service to use `--update-secrets` references
4. Remove the plaintext env vars

### Step 3 — Verify (5 min)

```bash
# Check revision is healthy
gcloud run revisions list --service=fastapi-run --region=europe-west1

# Hit health endpoint
curl https://fastapi-run-226875230147.europe-west1.run.app/health

# Confirm no plaintext secrets in env
gcloud run services describe fastapi-run --region=europe-west1 \
  --format "yaml(spec.template.spec.containers[0].env)"
# Should NOT contain DATABASE_URL, JWT_SECRET, ANTHROPIC_API_KEY, etc. as plain values
# Should show secretKeyRef entries instead
```

### Step 4 — Test login and DB (2 min)

- Log into Bridge Hub UI
- Create a test journal draft
- Confirm AI assistant responds

---

## Rollback plan

If the new revision fails health check:

```bash
# Roll back to previous revision
gcloud run services update-traffic fastapi-run \
  --region=europe-west1 \
  --to-revisions=PREVIOUS_REVISION=100

# Re-add plaintext env vars temporarily
gcloud run services update fastapi-run \
  --region=europe-west1 \
  --set-env-vars "DATABASE_URL=...,JWT_SECRET=...,..."
```

---

## VAULT_ENCRYPTION_KEY special note

The `VAULT_ENCRYPTION_KEY` is the AES-256 master key for `credential_vault_credentials`.  
**Rotating this key requires re-encrypting all vault entries.** Steps:

1. First migrate to Secret Manager WITHOUT changing the value (this runbook)
2. Schedule separate key rotation sprint:
   - Generate new key
   - Write migration script to re-encrypt vault entries with new key
   - Update Secret Manager secret version
   - Verify vault decryption works
   - Delete old secret version

---

## After migration — deploy.yml behaviour

`deploy.yml` already has `--update-secrets` flags (added in this sprint).  
On every merge to main, Cloud Run will automatically pull the latest version of each secret.  
To rotate a secret: update it in Secret Manager → redeploy (or `gcloud run services update --update-secrets`).

---

## Remaining backlog

- `email_collector.py` — `app_password TEXT NOT NULL` — migrate to vault (non-critical, future sprint)
- `SMTP_USER` — email address only, low risk, no action needed
