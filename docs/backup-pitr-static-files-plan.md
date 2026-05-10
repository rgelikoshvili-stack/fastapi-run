# Backup / PITR / Static Files GCS-CDN Plan

## A) Purpose

Database backup, point-in-time recovery (PITR), and durable static file storage
are required before commercial pilot. Without them:

- A Cloud SQL failure or data corruption has no tested recovery path.
- Cloud Run local filesystem is ephemeral — uploaded documents, OCR source
  files, attachments, and evidence bundles stored only in the container are
  lost on every deploy or instance restart.
- Backup status and restore capability are not auditable, violating the trust
  foundation commitments required before pilot.

This plan defines:

- Database backup configuration requirements.
- PITR / point-in-time recovery requirements and restore drill protocol.
- Backup evidence and audit requirements.
- Durable object storage requirements for uploads and documents.
- GCS / CDN target architecture.
- Static file migration strategy.
- Security and tenant isolation requirements for object storage.
- Failure and rollback policy.
- Evidence bundle storage integration.
- Commercial pilot go/no-go gates.
- Future implementation scope.

**This task defines the contract only.**

No production infrastructure change is made in this task.
No Cloud SQL configuration is changed in this task.
No GCS/CDN resources are created in this task.
No runtime code is changed in this task.
No workflow files are edited in this task.
No migration is created in this task.
No SQL execution in this task.
No DB touch in this task.
No Balance.ge activation in this task.

---

## B) Current State

### Completed Trust Foundation work

- `docs/trust-foundation-implementation-plan.md` — 9-pillar trust foundation
  plan; backup/PITR/durable storage listed as required pillar.
- `docs/runtime-ddl-cutover-plan.md` — DDL cutover contract completed.
- `docs/subscription-enforcement-plan.md` — subscription enforcement contract.
- `docs/redis-rate-limit-plan.md` — rate-limit contract.
- `docs/masked-read-behavior-contract.md` — masked read contract.
- `docs/credential-vault-design.md` + `docs/credential-vault-interface-contract.md`
  — credential vault architecture.

### Runtime state (not changed in this task)

| Item | Current Behavior | Risk |
|---|---|---|
| Cloud SQL backup | Status not verified/documented | Critical |
| Cloud SQL PITR | Status not verified/documented | Critical |
| Restore drill | Never performed or documented | Critical |
| Cloud Run `static/` directory | Mounted from local container filesystem — ephemeral | High |
| `app/api/services/storage_service.py` | GCS upload/download with DB fallback when `GCS_BUCKET_NAME` not set | Medium |
| GCS bucket | `GCS_BUCKET_NAME` env var — must be set in production; status not verified | High |
| CDN | Not configured | Medium |
| Backup evidence | Not collected or audited | High |

**Production DB status: untouched in this task.**
**Balance.ge activation status: inactive — Balance.ge must stay inactive.**
**All 12 Balance.ge activation gates remain NOT MET.**

---

## C) Database Backup Requirements

Before commercial pilot, the production Cloud SQL instance must satisfy all of
the following:

| Requirement | Rule |
|---|---|
| `automated_backups_enabled` | Cloud SQL automated backups must be enabled; backup schedule must be daily or more frequent |
| `pitr_enabled` | Point-in-time recovery (PITR) must be enabled on the production instance |
| `retention_policy_documented` | Backup retention window must be at least 7 days; policy must be documented in ops checklist |
| `backup_region_documented` | Backup storage region/location must be documented; must not be the sole-region matching the application region without cross-region copy policy |
| `encryption_documented` | Backup encryption method (Google-managed or CMEK) must be documented |
| `restricted_restore_permissions` | Restore operation must require explicit IAM permission; must not be grantable to application service accounts |
| `backup_status_visible` | Latest successful backup timestamp must be visible in ops monitoring checklist |

All requirements must be verified before the commercial pilot go/no-go gate.

---

## D) PITR / Restore Drill Requirements

Point-in-time recovery capability must be tested before commercial pilot. The
restore drill protocol is:

| Requirement | Rule |
|---|---|
| `non_production_clone` | Restore drill must be performed against a non-production clone; never against the production instance |
| `no_production_overwrite` | Restore operation must never overwrite production data; drill must produce a clone, not replace the live instance |
| `schema_validation` | After restore, schema must match expected state: all tables, columns, constraints, and indexes present |
| `tenant_data_validation` | After restore, tenant records must be present and correct; tenant isolation must hold |
| `audit_event_validation` | After restore, audit_log records must be present and consistent |
| `journal_data_validation` | After restore, journal_drafts and journal_entries must be present and consistent |
| `user_data_validation` | After restore, user records and hashed passwords must be present; raw passwords must never appear |
| `credential_metadata_validation` | After restore, credential metadata (without raw secrets) must be present and intact |
| `document_metadata_validation` | After restore, processed_documents metadata must be present; GCS paths must reference existing objects |
| `restore_evidence_report` | Restore drill must produce a written evidence report: timestamps, actor, result, findings |
| `rpo_rto_documented` | RPO (recovery point objective) and RTO (recovery time objective) targets must be documented before pilot |

RPO/RTO targets must be agreed before the restore drill is run, so the drill
can verify the targets are met.

---

## E) Backup Evidence / Audit Requirements

Backup evidence must be collected and retained before commercial pilot.
Each evidence record must include:

| Field | Description |
|---|---|
| `backup_configuration_snapshot` | Screenshot or export of Cloud SQL backup configuration |
| `backup_schedule` | Documented schedule (e.g. daily at 02:00 UTC) |
| `pitr_enabled_status` | Confirmed enabled/disabled at time of evidence collection |
| `latest_successful_backup_timestamp` | UTC timestamp of most recent verified backup |
| `restore_drill_timestamp` | UTC timestamp of most recent successful restore drill |
| `restore_drill_result` | Pass/fail and summary of validation checks |
| `actor` | Identity of person performing evidence collection and drill |
| `environment` | Must be `production` for backup evidence; `staging` or `clone` for restore drill |
| `db_instance_identifier` | Cloud SQL instance name |
| `no_production_overwrite_confirmation` | Explicit written confirmation that restore drill did not touch production |
| `rollback_notes` | Any issues encountered and how they were resolved |

Evidence records must NOT include:
- Raw database passwords or connection strings.
- JWT secrets or API keys.
- Credential values from the credential vault.
- Raw session tokens.

---

## F) Static Files / Upload Storage Requirements

Cloud Run local filesystem must be treated as ephemeral. It is not safe for
storing user documents, attachments, OCR source files, exports, or evidence
bundles. The following object types must be stored in durable object storage:

| Object Type | Current Path | Risk |
|---|---|---|
| `uploaded_documents` | `gcs_path` or DB `file_content` BYTEA fallback | Medium — DB fallback is not scalable |
| `attachments` | `gcs_path` or DB fallback in `journal_drafts` | Medium |
| `ocr_source_files` | Passed in-memory; not durably stored separately | High |
| `evidence_bundles` | Not yet implemented as durable objects | High |
| `exports` | Generated in-memory, returned as HTTP response | High — no durable copy |
| `generated_pdfs` | Generated in-memory | High — no durable copy |

### Object Storage Requirements

All durable object storage must satisfy:

- GCS bucket per environment (`production`, `staging`, `dev`) or clearly
  scoped key prefixes (e.g. `{env}/{tenant_id}/...`).
- `tenant_id` included in every object key to enforce isolation.
- Object ownership metadata must be stored (tenant_id, uploader_user_id,
  created_at, mime_type, original_filename).
- Immutable original file must be retained where required (accounting evidence,
  audit trail, tax documents).
- Signed URL / controlled access: private documents must never be publicly
  accessible without a time-limited signed URL.
- Lifecycle policy: define retention, archival, and deletion rules per object
  type.
- Antivirus/malware scanning hook: architecture must include a hook point for
  future scanning integration.
- No public bucket by default: no bucket holding private documents may be
  configured as public.

---

## G) GCS / CDN Target Architecture

### Planned Storage Components

| Component | Responsibility |
|---|---|
| `ObjectStorageService` | Interface/abstract base defining `upload`, `download`, `delete`, `generate_signed_url` |
| `GCSObjectStorageBackend` | Production GCS implementation of `ObjectStorageService` |
| `LocalObjectStorageBackend` | Local/dev-only implementation using local filesystem; must be forbidden in production |
| `StaticAssetPublisher` | Manages deployment of public immutable frontend assets to CDN-backed bucket |
| `EvidenceBundleStorage` | Specialized wrapper for storing and referencing accounting evidence bundles |
| `SignedUrlService` | Generates short-lived signed URLs for private document access |
| `StorageAuditLogger` | Logs all private file access events to audit trail |

### Static Asset Split

Public and private storage must be separated:

| Asset Class | Storage Policy | CDN | Signed URL |
|---|---|---|---|
| Frontend HTML/JS/CSS (`static/`) | CDN-backed public bucket; immutable versioned paths | Yes | No |
| User-uploaded documents | Private bucket; per-tenant scope | No | Yes (15–60 min) |
| Evidence bundles | Private bucket; per-tenant scope; immutable | No | Yes |
| Exports | Private bucket or ephemeral signed URL; short TTL | No | Yes |
| Generated PDFs | Private bucket or ephemeral; short TTL | No | Yes |
| OCR source files | Private bucket; linked to processed_documents record | No | Yes |

---

## H) Static File Migration Strategy

Migration from ephemeral local filesystem and DB BYTEA storage to durable
object storage must proceed in safe, audited phases:

| Phase | Name | Description |
|---|---|---|
| Phase 0 | `docs_tests_only` | This task: contract, docs, read-only tests |
| Phase 1 | `storage_path_inventory` | Inventory all upload/document/static paths in source; record which are ephemeral vs GCS-backed |
| Phase 2 | `storage_abstraction_interface_tests` | Define `ObjectStorageService` interface; write pure function tests |
| Phase 3 | `local_backend_parity` | Implement `LocalObjectStorageBackend`; verify parity with production contract |
| Phase 4 | `fake_gcs_backend_tests` | Implement fake/stub GCS backend for tests; verify all object operations |
| Phase 5 | `write_new_to_gcs_read_old_fallback` | New uploads go to GCS; reads fall back to DB if no `gcs_path` |
| Phase 6 | `backfill_existing_objects` | Migrate existing DB `file_content` BYTEA to GCS; backfill `gcs_path` column |
| Phase 7 | `signed_url_access_control` | Remove any direct BYTEA serving; enforce signed URL for all private documents |
| Phase 8 | `cdn_public_static_assets_only` | Deploy public frontend assets to CDN-backed bucket; keep private docs in private bucket |
| Phase 9 | `production_cutover_live_verification` | Full production verification: signed URL round-trip, CDN cache, upload durability |

No phase may be executed without the preceding phase verified and committed.
Phase 5 onward requires production readiness review.

---

## I) Security and Tenant Isolation

The following security requirements apply to all object storage:

| Requirement | Rule |
|---|---|
| `no_cross_tenant_access` | Object keys must be scoped to `tenant_id`; no query or signed URL may return objects across tenant boundary |
| `short_lived_signed_urls` | Signed URLs must expire in ≤ 60 minutes; default is 15 minutes |
| `audit_private_file_access` | Every private file access (download, signed URL generation) must produce an audit log record |
| `no_secrets_in_object_names` | Object keys must not contain credential values, tokens, passwords, or JWT claims |
| `no_public_bucket_for_private_documents` | Private document bucket must never be set to public access |
| `separate_public_assets_and_private_documents` | Frontend static assets and user private documents must be in separate buckets or clearly separated prefixes with separate ACLs |

Additional rules:

- Deleted/suspended tenant access policy must follow subscription enforcement
  rules defined in `docs/subscription-enforcement-plan.md`.
- File metadata stored in DB must not include raw credential values.
- Object lifecycle rules for deleted tenants must be defined before commercial
  pilot.

---

## J) Failure / Rollback Policy

| Scenario | Required Behavior |
|---|---|
| GCS unavailable during upload (sensitive document) | Upload must fail safely with error; must not silently store nothing and return success |
| GCS unavailable during upload (non-sensitive) | Local fallback may be allowed in temporary mode only; must be logged and alerted |
| Local fallback in production | Must be explicitly forbidden for accounting evidence and private documents |
| Write silently disappears | Forbidden — every upload must return a durable path or an explicit error |
| Failed upload creates approved evidence | Forbidden — a failed upload must prevent downstream approval/posting |
| Rollback | Must restore previous read path while preserving any new writes already committed to GCS |
| Migration / backfill | Must be idempotent — re-running backfill must not create duplicate objects or corrupt existing records |

---

## K) Integration With Evidence Bundle

Evidence bundles (audit packages for accounting entries, ERP postings, and
document intelligence results) must satisfy:

- Evidence bundle must reference durable GCS object IDs, not ephemeral file
  paths or in-memory bytes.
- Original document hash (SHA-256 or equivalent) must be stored at upload time
  and verified at evidence bundle creation.
- OCR output and AI classification reasoning must be linked to the source
  object's GCS path.
- Audit package must be reproducible: given the same GCS object IDs and DB
  records, the bundle can be reconstructed.
- Deletion policy for evidence objects: accounting/audit evidence objects must
  be retained for the minimum legal period even if the parent document or draft
  is deleted or the tenant is suspended/expired.
- `EvidenceBundleStorage` must enforce immutability for completed evidence
  objects (no overwrite allowed).

---

## L) Commercial Pilot Go/No-Go Gates

Before commercial pilot, all of the following must be confirmed:

| Gate | Required State |
|---|---|
| Automated backups verified | Cloud SQL automated backups confirmed enabled and tested |
| PITR enabled and verified | PITR confirmed enabled; restore point tested |
| Restore drill completed | Full restore drill on non-production clone with written evidence report |
| Backup evidence report exists | Evidence doc with all fields in section E present and signed off |
| Durable object storage plan approved | ObjectStorageService architecture reviewed and approved |
| Private upload access model approved | Signed URL model and bucket ACL reviewed and approved |
| No public bucket for private documents | Verified: no private document bucket is publicly accessible |
| Static asset caching policy approved | CDN/cache headers for public static assets defined and approved |
| Rollback plan approved | Section J rollback policy reviewed and approved by engineering lead |
| Live /health and /version verification playbook exists | Runbook for post-deploy health check exists |

All gates must be documented as MET or NOT MET in the pre-pilot ops checklist.
Any NOT MET gate blocks pilot launch.

---

## M) Explicit Non-Goals (This Task)

The following are explicitly deferred and must NOT be implemented in this task:

- No production infrastructure change.
- No Cloud SQL configuration change.
- No GCS/CDN resource creation.
- No runtime code change.
- No workflow file edit.
- No migration creation.
- No SQL execution.
- No DB touch.
- No Balance.ge activation.
- No Task 11C implementation.

**Balance.ge activation remains blocked** until all 12 gates in
`docs/balance-ge-activation-gate.md` are MET. All gates are currently NOT MET.

**No migration is created in this task.**

**No runtime code is changed in this task.**

---

## N) Test Strategy

Task 10F-G tests in `tests/unit/test_backup_pitr_static_files_contract.py`
validate this contract using only:

- Reading doc files and asserting required content.
- Local test-only set definitions (no runtime imports).
- Assertions on requirement sets, component sets, phase sets.
- Source text scanning (read-only, no imports) of runtime files.
- No DB access, no network calls, no GCP calls, no SQL.

---

## O) Future Implementation Scope

Future work must be split into small, independently reviewable tasks:

| Task | Scope |
|---|---|
| `10F-G1` | Backup/PITR ops checklist — document Cloud SQL backup config, schedule, PITR status |
| `10F-G2` | Restore drill runbook — step-by-step protocol for non-production restore drill |
| `10F-G3` | Storage path inventory — audit all upload/document/static paths in source |
| `10F-G4` | `ObjectStorageService` interface tests — pure function tests for upload/download/signed_url contract |
| `10F-G5` | Local backend implementation — `LocalObjectStorageBackend` with parity tests |
| `10F-G6` | Fake/stub GCS backend tests — verify all object operations without real GCP |
| `10F-G7` | Signed URL / access control contract — per-tenant URL generation, expiry enforcement |
| `10F-G8` | Evidence bundle storage integration — link OCR/AI output to durable GCS objects |
| `10F-G9` | CDN / static asset plan — public frontend asset deployment to CDN-backed bucket |
| `10F-G10` | Production verification playbook — post-cutover health, backup, and access verification |

No future task may skip to a later phase without completing the prior phase.
Tasks 10F-G5 onward require explicit engineering lead approval before
production scope begins.
