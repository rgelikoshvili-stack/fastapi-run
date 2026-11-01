# Bridge Hub — Chat175 Signature/Stamp, financial Tenant isolation, recovery gate

**Date:** 2026-10-29. **Scope:** Draft PR #154 only. **Production: HOLD.**
**Last fully CI-verified code/report-preflight HEAD:** 2984bf4c09a951d300c0ed4491f50126edb84de1.
No main merge, live Cloud Run/Cloud SQL/Redis settings, Production data, secrets, Windows originals or index/ACL were modified.

## Findings and Draft-only fixes

1. Signature and Stamp GET/POST already called require_permission(settings:write) and filtered SQL by tenant_id. However, they resolved the tenant from request.state without directly proving agreement with the signed JWT and transaction-local PostgreSQL tenant context. Added central require_signed_tenant_permission() in app/api/authz.py and applied it to all four image endpoints. It fails closed on anonymous, insufficient role, unsigned/default/mismatched tenant, or missing/mismatched DB context. It keeps existing role permissions unchanged.
2. Previously any <=2MB arbitrary string could be saved as signature_b64 or stamp_b64. The new code accepts empty clear values and bounded data URLs for PNG/JPEG/WEBP only, checks base64 and raster magic, returns 422 for invalid submissions, and detects UPDATE 0 instead of declaring an unknown tenant updated. This reduces active-content risks but is not a full image parser/decompression-bomb proof; production staging must test actual PDF rendering and large files.
3. The invoice/signature HTML previously interpolated stored base64 values directly into img src attributes via innerHTML. Draft static/outgoing_form.html now creates the img without untrusted attributes and assigns src via the DOM property only after a strict passive data URL pattern check. Legacy saved values remain readable, but unsafe ones are not rendered. Image upload widgets restrict types to PNG/JPEG/WEBP and 1.5MB.
4. The annual report and pipeline audit trail already had SQL WHERE tenant_id = %s, but did not explicitly bind that value to signed JWT + DB context in the handler. Applied require_signed_tenant_permission() to /reports/annual and /reports/audit-trail. Applied it to /audit-trail/recent and entity history too, keeping SQL tenant parameters. This does not certify every other financial endpoint.
5. Added tests/unit/test_chat175_signature_stamp_security.py, updated older structural and branding-role tests to supply the verified DB context, and extended tests/integration/test_chat167_auth_forced_rls_postgres.py with real disposable PG15/16 two-tenant tables and FORCE ROW LEVEL SECURITY under a NOSUPERUSER NOBYPASSRLS nonowner runtime role. Tests verify alpha/beta signature separation, incorrect signed tenant/role denial, annual report different years and audit detail separation, and absence of residual transaction context.
6. Added catalog-only docs/sql/chat175_finance_rls_readonly_catalog_preflight.sql and docs/chat175-cloudsql-backup-pitr-readonly-verification-gate.md. Both are **prepared, not run against Cloud SQL**. The backup document reconciles historical 2026-05-21 operator-reported PITR/backup confirmation with the absence of recent evidence and the explicitly deferred full clone restore.

## Verified GitHub Actions, exact HEAD 2984bf4c...

- [Disposable PostgreSQL 15/16](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40861816526): **305 passed in PostgreSQL 15**, **305 passed in PostgreSQL 16**.
- [Full backend/frontend CI](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40861816560): **8,162 passed, 3 skipped**, additional smoke **1 passed**, frontend build successful; Cloud Run deployment job explicitly **SKIPPED**.
- [Disposable Redis 7](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40861816514): **210 passed**.
- [Tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40861816582): PASS.
- [Financial fail-closed RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40861816573): PASS.
- An earlier full CI commit reported 8 failures in legacy tests that expected unsigned request.state-only tenant access; the test fixtures were updated to pass the new signed+DB-context contract, **without weakening the guard**. Reverified final HEAD shows PASS.

## Still not verified / authorization required

- Live Production Cloud SQL owner-bypass, actual tenants/users/pipeline_runs/audit_log RLS policies, grants and any nonowner RLS on remaining financial tables.
- Real HTTP JWT/permission flow, image upload/pdf signing and legacy unsafe stored image handling in an isolated browser, plus every sensitive finance route's data consistency.
- Cloud SQL automated backup/PITR **current status**, restore permissions, 7-day retention, latest backup time, approved RPO/RTO, isolated clone restore, GCS attachments, and cross-region failover. The May 2026 confirmation is stale and full restore was deferred.
- Region-specific JWT secret/version behavior, real OAuth/SMTP, shared Redis/network/proxy in Cloud Run, host enforcement activation, finance AI chat/journal reconciliations and original Windows repository integrity.

**Decision:** Draft changes and synthetic CI PASS. Actual staging NOT TESTED. **Production HOLD**. PR #154 stays OPEN/DRAFT; do not merge/deploy or run Cloud SQL/GCP mutations without separate owner approval.
