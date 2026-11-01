# Chat204 — FIN-11 attachment evidence preservation and tenant-bound read control

Date: 2026-11-01. PR #154 **OPEN / DRAFT / UNMERGED**. Production **HOLD**.

## Verified source defects (not a claim of live data damage)

1. `POST /approval/draft/{draft_id}/attach` previously fetched only an id, then allowed GCS upload + unconditional attachment-field UPDATE against posted/approved, correction or linked historical drafts. An existing attachment could be silently replaced. The storage adapter may return `None` on GCS failure, but the route still returned a false success with an absent blob path.
2. `DELETE /approval/draft/{draft_id}/attachment` physically deleted GCS evidence before clearing journal attachment metadata. The external delete cannot commit/roll back together with PostgreSQL and lacks an approved retention/immutable archival policy.
3. `GET /approval/draft/{draft_id}/attachment` did not explicitly enforce `approval:read`, and trusted the DB-stored GCS object key when generating signed URLs, even when a stored key was outside the caller's tenant prefix.

## Regression-first evidence and scoped Draft fix

**Mutation stage**
- RED test-only SHA `28ac1f1c104b4252a1bb0d39c7c06a0f8e796609`: 12 new negative regression failures; backend 8,611 other PASS / 3 SKIP. GitHub run `41241423257`.
- Fix SHA `b3fe4bbbc5616a9f25ee1c12acf38b877159972b`: tenant-specific row lock `FOR UPDATE NOWAIT`, explicit ordinary/unlinked and mutable-status allowlist, refuse replacement of any prior attachment metadata, require a tenant-prefixed non-empty GCS return, and a conditional `UPDATE ... RETURNING id` that repeats tenant/status/source/empty-attachment checks.
- The destructive DELETE handler now returns `409 FIN11_ATTACHMENT_DELETE_HOLD` **for all drafts** pending reviewed evidence retention; no GCS object deletion is performed by that endpoint.
- All 12 new tests PASS in the initial scoped code SHA. One preexisting `test_approval_routes.py` source-string assertion failed because it expected the old success response for deletion; that static contract, not the security logic, was corrected at `d924c3bba674ad3c0d2ca6b06af9dcd84bc7419b`.
- Exact compatibility-fix SHA `d924c3bba674ad3c0d2ca6b06af9dcd84bc7419b` independently passed **9/9 GitHub PR workflows**: backend **8,623 PASS / 3 SKIP**, smoke **1 PASS**, disposable PG15/PG16 **799 PASS each**. No actual frontend install/build or Cloud Run deployment.

**Read stage**
- RED test-only SHA `d7cf7e96919f40ac3c1797344521807ad05d676a`: 5 targeted negative cases failed, backend 8,623 other PASS / 3 SKIP. GitHub run `41241816220`.
- Fix SHA `8d8aa3a550d9e1eb5fd3779ad06090cce7fa2947`: `approval:read` is checked **before any DB or GCS operation**; foreign, ambiguous and noncanonical stored GCS keys are denied before signed URL or byte retrieval. Existing authorized tenant's response format is retained.
- Exact read-fix SHA verified **9/9 CI SUCCESS**: backend **8,628 PASS / 3 SKIP**, smoke **1 PASS** (run `41241843627`), disposable PostgreSQL 15/16 **799 PASS each** (run `41241843703`). All five new tests PASS. Actual frontend build/deploy jobs SKIPPED.

## Scope and mandatory remaining holds

- The 17 new targeted cases use **mocked GCS and DB/SQL contracts** and exercise no live resources. Existing 799-case disposable PostgreSQL suites pass on both versions but do not establish production-role or real storage commit atomicity. No browser E2E or real frontend build.
- A successful GCS upload and PostgreSQL commit are **not** one atomic operation: if the DB transaction fails after upload, an unreferenced remote blob can remain. Do not auto-delete; design an audited orphan/retention workflow, versioned immutable attachments and provider-consistent recovery before release.
- Existing GCS paths from legacy data may need inventory/manual validation; no source backfill, migration, overwrite or physical deletion was performed. Missing GCS configuration now fails closed.
- FIN-11 independent signed-JWT Maker/Checker, durable transactional audit, immutable ledger reversals/adjustments and financial parity remain OPEN.
- FIN-12 independently authenticated vendor receipts/status, tenant-provider identity, vendor-certified idempotency, safe fencing/UNKNOWN recovery, and local ledger/outbox/receipt atomic finalization remain **EXTERNAL-HOLD**; Chat201 interlock SQL remains UNAPPLIED.
- FIN-07/08 exact Decimal wire/UI precision and historical/indirect cashflow remain OPEN.
- No Merge, `main` change, Production deploy, real DB migration, ERP write/retry, Windows original edit, deletion of prior project history or private handoff/evidence upload.

This is a bounded Draft safety milestone. **The final documentation-only HEAD must itself pass 9/9 CI**; success on the above code SHA must not be substituted for the final HEAD.
