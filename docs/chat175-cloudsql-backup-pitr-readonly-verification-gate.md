# Bridge Hub — Chat175 Cloud SQL backup/PITR READ-ONLY verification gate

**Prepared 2026-10-29. NOT EXECUTED against Cloud SQL. Production HOLD.**
GitHub Draft PR #154 only. No GCP project discovery, Cloud SQL connection, GCS listing, change to secrets, restore, database DDL, or deployment was performed.

## Evidence reconciliation

- Older document docs/backup-pitr-static-files-plan.md records the initial operational status as *not verified* and requires automated daily backup, PITR, retention of at least 7 days, restricted restore grants, separate GCS persistence, and a successful non-production restore drill.
- docs/migration-011-backup-pitr-confirmation-h69-pre.md contains a later **2026-05-21 operator-recorded console confirmation** of backups/PITR and a historical restore point; it explicitly says the full clone restore test was **deferred**. This is historical evidence, not a verified current October 2026 configuration.
- No current Cloud SQL configuration, recent completed backup, log retention, IAM restore permissions, cross-region copy, GCS object recovery or restore-clone proof was accessible through the GitHub repository review. Treat all of these as **PENDING**, not passed or failed.

## Read-only inventory procedure (only an owner-authorized Cloud SQL viewer)

First verify project and instance identity from owner-approved inventory, not from guessed service URLs. The following template uses non-secret placeholders and is **not executed here**. All commands are read-only; never paste raw service account credentials or DATABASE_URL.

```bash
PROJECT='<approved-project-id>'
INSTANCE='<approved-cloudsql-instance>'
gcloud sql instances describe "$INSTANCE" --project="$PROJECT" \
  --format='json(name,region,databaseVersion,settings.backupConfiguration,settings.availabilityType)'
gcloud sql backups list --instance="$INSTANCE" --project="$PROJECT" \
  --format='table(id,status,startTime,endTime,location)'
gcloud sql operations list --instance="$INSTANCE" --project="$PROJECT" \
  --limit=15 --format='table(name,operationType,status,startTime,endTime)'
```

Review and redact output **locally** before sharing: resource IDs, IPs, IAM account names and project internals may be sensitive even if no passwords appear. No restore, update, delete, export, flag change, `gcloud sql instances patch`, or traffic change is authorized.

## Required evidence before promotion

| Gate | Expected evidence | Verified in Chat175 |
| --- | --- | --- |
| Current automated backups | Backup enabled and recent successful backup within approved schedule/RPO | PENDING — no live access |
| PITR | `pointInTimeRecoveryEnabled` true and transaction log window covers agreed recovery point | PENDING |
| Retention | Effective backup/log retention documented, at least seven days per existing plan | PENDING |
| Backup region/encryption | Storage region and encryption/CMEK key availability reviewed | PENDING |
| Restore IAM | Only approved operators can initiate restores; app service accounts cannot | PENDING |
| Isolated clone restore | Owner-approved restore to NEW nonproduction clone with no production overwrite | NOT PERFORMED |
| RTO/RPO | Actual measured restore time and data-loss window compared with signed targets | PENDING |
| Database isolation | Restored user, tenant, RLS, journal, audit and auth-token state consistency | PENDING |
| Attachments | Restored DB pointers resolve to versioned/private GCS objects by tenant | PENDING |
| Production protection | Explicit confirmation no Production traffic/DB row was changed | PASS for this Draft-only review; no GCP actions |

## Separately authorized clone drill (not executed)

After independent authorization, identify a PITR timestamp within the retention window, restore to a **new** isolated instance with no production traffic routing, inspect only synthetic or properly governed sample records, validate data consistency, security policies and required GCS objects, collect measured RTO/RPO, and destroy the clone only with explicit resource-management approval. Never overwrite the live database. No Cloud Run DATABASE_URL or JWT/Redis environment changes are part of this preflight.

**Decision:** Historical backup assertions are stale; a tested clone does not exist in available evidence. Keep backup/PITR/restore gate BLOCKED_PENDING_CURRENT_EVIDENCE, and Production HOLD.
