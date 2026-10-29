# Bridge Hub — Chat178: Tenant-scoped Vector groundwork and Posted Ledger line integrity

**Date:** 2026-10-29. **Scope:** GitHub Draft PR #154 only. **Production HOLD.**
**Fully verified implementation SHA:** `978771d636e2f3dcad49fa2d6e53eb76d668c6a5`.

No changes to main/Production, Cloud Run deployment, Cloud SQL, Redis/GCS,
OAuth/SMTP, bank data, stored production vectors, source indexes, or
Windows originals/worktrees/index/ACL. No actual provider connections.

## 1. Confirmed issues and safe Draft fixes

### A. Legacy Chroma vector collection risk

The historical `bridge_hub_vector_db.py::semantic_search` queries the
global document collection and merges self-learned results from the learned
collection without a Tenant filter. `index_files` places documents in the
global base collection with no verified tenant/source privacy metadata.
Existing learned corrections include a tenant_id metadata key, but legacy
read paths did not restrict it. Global Chroma APIs and user-selected file
indexing therefore remain **DISABLED** at the HTTP boundary from Chat177.

New `bridge_hub_vector_db.py::tenant_learned_search` is a **nonactivated
internal-only building block**. It:
- Requires an explicit bounded canonical tenant ID; rejects missing,
  global, default, public, malformed, oversized and non-ASCII authority.
- Rejects invalid/oversized query, search count and similarity threshold
  BEFORE any vector client or embedding I/O.
- Reads **only the learned collection**, NEVER the older unclassified
  document collection. Queries Chroma with `where={"tenant_id": tenant_id}`.
- Independently checks every returned item's `tenant_id` after query,
  excluding other-tenant and unlabelled historical entries if the store
  unexpectedly returns them. Does not return raw metadata or file paths.
- Fails closed on malformed metadata/response or backend error; it does not
  retry without a filter or silently expose global data.
- Does not delete/reindex any existing Chroma file, collection or record.

Tests use a synthetic optional-Chroma module stub in disposable CI because
the default backend requirements do not install `chromadb`. These prove
the Python guard and exact query arguments, **NOT** actual Chroma database
isolation or production embedding behavior. Do not claim vector search has
been enabled or a live Chroma instance tested. A separate authorized,
pinned-dependency, real Chroma staging test is required before any feature
flag, HTTP route or writing/indexing is enabled.

### B. Posted Ledger header/line Tenant mismatch

The migration 011 ledger schema records `journal_entry_lines.tenant_id`
but its FK only references the header's ID; the migration explicitly
delegates header/line Tenant consistency to application code. The
`financial_statements_service` four canonical posted-ledger query
builders formerly scoped `jeh.tenant_id` but joined lines by header ID
alone. An incorrectly linked line tagged with a different Tenant could
then pollute the original Tenant's P&L/cashflow/balance/trial balance if
line RLS were permissive.

The query builders now require BOTH `jeh.tenant_id = $1` and
`jel.tenant_id = jeh.tenant_id` when joining:
- `_build_pnl_posted_ledger_query`
- `_build_balance_sheet_posted_ledger_query`
- `_build_cashflow_posted_ledger_query`
- `_build_posted_trial_balance_as_of_query`

New real PostgreSQL 15/16 integration coverage extends the isolated
Chat167 nonowner NOSUPERUSER/NOBYPASSRLS fixture. It executes the **actual
Migration 011 in a disposable schema only**, twice for idempotency,
creates synthetic posted/reversed entries for two tenants and an
intentionally inconsistent cross-Tenant line, and checks P&L, AI
context and trial balance against expected numbers. It first tests with a
deliberately broad line-RLS policy (simulated misconfiguration), then
with strict forced line RLS. A pooled no-tenant connection sees zero
headers/lines after strict RLS is restored.

**This is a query-level defense only.** The production database still
needs an independently reviewed composite tenant/ID foreign-key
constraint or equivalent line-write invariant, real RLS/grant and owner
bypass audit, direct table access testing and a controlled migration plan.
No Production migration or feature flag was changed.

## 2. Exact implementation-SHA CI evidence (synthetic only)

- [Disposable PostgreSQL 15/16](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40873510637):
  **395 PASS on PG15, 395 PASS on PG16**, including the nonowner Migration
  011 / wrong-tenant-line test.
- [Full backend/frontend](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40873510605):
  **8,244 backend PASS / 3 SKIP**, smoke **1 PASS**, frontend build PASS,
  **Cloud Run deployment SKIPPED**.
- [Redis 7 shared quota](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40873510609):
  **210 PASS**.
- [PR127 disposable PostgreSQL reporting](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40873510627):
  **229 PASS**, additional integration **1 PASS**.
- [PR84 disposable report snapshots](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40873510619):
  **82 PASS**, **178 PASS** and extra smoke **1 PASS**.
- [NEXT-01 Tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40873510596):
  PASS.
- [NEXT-04A financial RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40873510653):
  PASS.

The first new CI revision failed 26 Vector unit cases because
`chromadb` is an optional dependency absent from GitHub's ordinary
requirements. The test fixture was isolated with synthetic import stubs
instead of installing Chroma or enabling the unsafe feature. Both unit
and integration suites were rerun successfully on the SHA above.
A real Chroma instance/metadata migration has **NOT** been verified.

## 3. Next safe stages / remaining blockers

1. Inspect a real, separately authorized disposable Chroma instance;
   supply synthetic tenant-labelled learned records and a verified
   per-tenant isolated or strict-metadata collection policy. Test filters
   against actual Chroma query semantics, no historical global reads,
   file provenance and deletion/reindex permissions before HTTP exposure.
2. Design an **additive, reversible** DB invariant enforcing line Tenant =
   header Tenant, including detection/handling of existing bad lines,
   sequence/idempotency, owner permissions, foreign keys and indexes.
   Do not apply it to Production without explicit approval and backup.
3. Keep `POSTED_LEDGER_REPORTS_ENABLED` unchanged in Production.
   Independently check migration 011 grants/owner bypass and regional
   immutable-posted-ledger P&L, cashflow, trial balance, AI chat parity,
   account reports and audit/evidence traceability.
4. All prior P0 release gates stay OPEN: Cloud SQL current backup/PITR
   and isolated restore, real Cloud Run Host/proxy/Redis failover,
   JWT US/EU parity and revocation, OAuth/SMTP, migrations 013-016,
   finance cross-Tenant E2E and Windows preservation integrity.

**Decision:** Draft code and synthetic CI PASS; actual Chroma staging,
Production Cloud SQL, and signed owner-approved Deployment NOT DONE.
PR #154 remains OPEN + DRAFT; Production **HOLD**.
