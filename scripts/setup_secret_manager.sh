#!/usr/bin/env bash
# scripts/setup_secret_manager.sh
#
# Migrates Bridge Hub plaintext Cloud Run env vars to Google Secret Manager.
# Run ONCE manually with your actual secret values.
# After this script succeeds, the deploy.yml --update-secrets flags take effect
# on the next deployment.
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project YOUR_PROJECT_ID
#   Roles needed: Secret Manager Admin + Cloud Run Admin
#
# Usage:
#   export PROJECT_ID=your-gcp-project-id
#   export DATABASE_URL="postgresql://..."
#   export JWT_SECRET="..."
#   export ANTHROPIC_API_KEY="sk-ant-..."
#   export OPENROUTER_API_KEY="sk-or-..."
#   export VAULT_ENCRYPTION_KEY="..."
#   bash scripts/setup_secret_manager.sh

set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${DATABASE_URL:?Set DATABASE_URL}"
: "${JWT_SECRET:?Set JWT_SECRET}"
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY}"
: "${OPENROUTER_API_KEY:?Set OPENROUTER_API_KEY}"
: "${VAULT_ENCRYPTION_KEY:?Set VAULT_ENCRYPTION_KEY}"

SERVICE_NAME="fastapi-run"
REGION="europe-west1"

echo "=== Bridge Hub: Secret Manager Migration ==="
echo "Project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo ""

# Detect Cloud Run service account
SA_EMAIL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --format "value(spec.template.spec.serviceAccountName)" \
  --project "$PROJECT_ID" 2>/dev/null || echo "")

if [ -z "$SA_EMAIL" ]; then
  PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
  SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  echo "Using default compute SA: $SA_EMAIL"
else
  echo "Using service SA: $SA_EMAIL"
fi

echo ""

create_or_update_secret() {
  local name="$1"
  local value="$2"

  if gcloud secrets describe "$name" --project "$PROJECT_ID" &>/dev/null; then
    echo "  [UPDATE] $name — adding new version"
    echo -n "$value" | gcloud secrets versions add "$name" \
      --data-file=- --project "$PROJECT_ID"
  else
    echo "  [CREATE] $name"
    echo -n "$value" | gcloud secrets create "$name" \
      --data-file=- \
      --replication-policy automatic \
      --project "$PROJECT_ID"
  fi

  # Grant Cloud Run SA access
  gcloud secrets add-iam-policy-binding "$name" \
    --member "serviceAccount:${SA_EMAIL}" \
    --role roles/secretmanager.secretAccessor \
    --project "$PROJECT_ID" \
    --quiet
}

echo "--- Creating/updating secrets ---"
create_or_update_secret "bridge-hub-database-url"       "$DATABASE_URL"
create_or_update_secret "bridge-hub-jwt-secret"          "$JWT_SECRET"
create_or_update_secret "bridge-hub-anthropic-api-key"   "$ANTHROPIC_API_KEY"
create_or_update_secret "bridge-hub-openrouter-api-key"  "$OPENROUTER_API_KEY"
create_or_update_secret "bridge-hub-vault-encryption-key" "$VAULT_ENCRYPTION_KEY"

echo ""
echo "--- Updating Cloud Run service to reference secrets ---"
gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --update-secrets \
    "DATABASE_URL=bridge-hub-database-url:latest,\
JWT_SECRET=bridge-hub-jwt-secret:latest,\
ANTHROPIC_API_KEY=bridge-hub-anthropic-api-key:latest,\
OPENROUTER_API_KEY=bridge-hub-openrouter-api-key:latest,\
VAULT_ENCRYPTION_KEY=bridge-hub-vault-encryption-key:latest" \
  --quiet

echo ""
echo "--- Removing plaintext env vars ---"
gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --remove-env-vars \
    "DATABASE_URL,JWT_SECRET,ANTHROPIC_API_KEY,OPENROUTER_API_KEY,VAULT_ENCRYPTION_KEY" \
  --quiet

echo ""
echo "=== Done. Verifying ==="
gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "yaml(spec.template.spec.containers[0].env,spec.template.spec.containers[0].envFrom)"

echo ""
echo "Next steps:"
echo "  1. Confirm Cloud Run revision is healthy: gcloud run revisions list --service=$SERVICE_NAME --region=$REGION"
echo "  2. Hit /health to confirm app is up"
echo "  3. The deploy.yml --update-secrets flags are already in the workflow — next auto-deploy will use Secret Manager"
