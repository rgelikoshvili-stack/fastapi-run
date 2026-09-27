# Cloud Run environment preservation hotfix

## Problem

The Cloud Run deployment workflow used `gcloud run deploy --set-env-vars` to
write the dynamic deployment metadata `COMMIT_SHA`, `BUILD_TIME`, and
`ENVIRONMENT`. For Cloud Run, `--set-env-vars` replaces the service's existing
environment-variable set. As a result, a deployment that supplied only those
three metadata values could remove variables configured outside the workflow.

The 2026-09-26 production audit identified affected classes of configuration:

- posted-ledger write and report feature flags;
- document storage configuration, including the GCS bucket name;
- RS.ge feature and safety flags;
- database pool sizing and migration-startup controls; and
- an AI provider credential that had previously been configured as an
  environment variable.

Secrets and production configuration values are intentionally not recorded in
this document or added to the repository.

## Hotfix

The workflow now uses `gcloud run deploy --update-env-vars` for only
`COMMIT_SHA`, `BUILD_TIME`, and `ENVIRONMENT`. This updates those metadata keys
while preserving other environment variables already configured on the Cloud
Run service. The existing `--set-secrets` configuration is unchanged.

## Scope and follow-up

This hotfix prevents future deployments from wiping unrelated Cloud Run
environment variables. It does not restore variables that were already lost,
change the current production environment, deploy a revision, or modify any
production data.

The next required P0 task is a controlled production environment restoration:
inventory the intended configuration, review it for correctness and secret
handling, apply it through an approved operational procedure, and verify the
result independently. That restoration must remain separate from this code
change.
