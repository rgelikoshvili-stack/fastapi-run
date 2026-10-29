# Bridge Hub — Chat179: Real Vector and Posted Writer Integrity

Date: 2026-10-29. Scope: existing Draft PR #154 only. Production HOLD.
Starting HEAD: `fdc7c8362cd84c497f564547455c593264a66546`.

## Confirmed accounting defects and Draft fixes

The actual `_write_ledger_entries` did not populate `account_type`, while
posted P&L and balance queries filter on this column. Earlier integration
fixtures populated the type manually and therefore did not exercise this
writer-to-report gap. Newly written standard-COA lines now derive the type
from the existing canonical COA; `revenue` maps to ledger `income` and
`contra_asset` to ledger `asset`. Caller-supplied type hints are ignored.
Historical rows are preserved; no backfill. Unmapped/custom COA codes still
need a reviewed classification strategy before rollout.

A direct bank/cash payment against salary expense account 7210 was omitted
from operating cashflow because its fallback classification was absent.
The existing guarded classifier now includes 7210 with the expected
`expense` type. Other unknown/ambiguous cashflow codes remain a release gate.

## Real disposable vector tests

`tests/integration/test_chat179_real_chroma.py` uses actual persistent
Chroma 1.0.20 with only synthetic text in temporary directories. Identical
embeddings across two tenants make a missing metadata filter observable.
Tests cover exact tenant filtering, absent/case-distinct tenants, legacy
and global exclusions, unchanged base/learned records, cosine thresholds,
top-k, reopening a persisted collection and empty-store behavior.

A separate test executes the application's actual DefaultEmbeddingFunction
with local ONNX all-MiniLM-L6-v2 inference, then searches a tenant-tagged
synthetic collection. Dedicated CI requires this test; no provider API keys.
This establishes backend semantics and local inference, not Georgian
semantic accuracy, provenance of historical documents or live GCS ownership.
The unused multilingual model constant in the old module is not evidence
that runtime embeddings are multilingual.

Local results before CI: six real-Chroma tests passed. Local ONNX execution
was blocked by the host's HTTP proxy/download path; it is not counted as
passed. The dedicated isolated CI job installs pinned optional vector
dependencies without changing production requirements or enabling APIs.

The first real ONNX CI run (`40909202361`) exposed a runtime defect, not a
missing test dependency: `list(numpy_array)` retains `numpy.float32`
elements, rejected by Chroma's nested-list validator. Actual inference
worked, but tenant search failed. `_plain_embedding` now converts each
coordinate to a finite native Python float at all four embedding-to-store
boundaries (file batch, global query, tenant query, learned correction).
No global retrieval or indexing HTTP permission is restored. A separate
real-Chroma NumPy regression reproduces the failure without model downloads;
invalid/empty/nonfinite embeddings are rejected before querying the store.

## Disposable PostgreSQL 15/16 verification

The Chat167 nonowner, NOSUPERUSER, NOBYPASSRLS fixture now exercises actual
writer SQL, not manually typed lines: two tenants, sequential retry,
posted P&L, balance asset totals, cashflow, trial balance, AI chat context
and AI financial-summary parity. Approved workflow amounts cannot become
posted revenue. Strict synthetic forced RLS and pooled context reset are
checked. These policies do not certify production RLS/ownership/grants.

`docs/sql/chat179_posted_ledger_tenant_constraints_DRAFT.sql` is a candidate
**not registered with startup migrations and not applied outside disposable
CI**. It checks existing lines and source links without RLS-hidden rows,
refuses mismatches without repair/deletion, and adds tenant+header composite
FKs. Tests prove the legacy schema accepts a bad parent reference, then the
candidate rejects cross-tenant INSERT and UPDATE for both child tables and
parent tenant changes with linked children. Clean repeat application and
refusal/preservation of malformed legacy rows are covered. No claim of full
ledger immutability, line-total balancing or concurrency idempotency.

## Verification status

- Original writer regression: 7 failed before the classification fix.
- Initial focused writer/nearby tests: 56 passed after the fix.
- Local full backend before the additional salary regression: 8,251 passed,
  3 skipped. Final focused checks and exact-SHA CI are recorded below when complete.
- Chat178 exact HEAD CI was independently rechecked. The frontend job was
  successful, but React setup/install/build steps were SKIPPED because the
  frontend application is absent. Older “frontend build PASS” wording must
  not be treated as proof of a compiled frontend.
- New exact implementation SHA / CI: PENDING.

## Remaining release gates

Public vector search/indexing stay disabled. Existing vectors and historical
ledger rows are untouched. The candidate FK SQL is not a production migration
approval. Keep all ledger flags unchanged in Production. Real signed HTTP/UI,
custom COA and historical NULL classification, complete ledger immutability,
header-to-line sums, concurrent source deduplication, financial exports and
tax reconciliation remain open. Production RLS/owner bypass, backup/PITR
and isolated restore, cross-region JWT parity, Redis/Cloud Run failover,
OAuth/SMTP, GCS recovery and migrations 013–016 remain separate P0 gates.

No main update, merge, deployment, live Cloud SQL access, Windows-original
modification, production vector change or real ERP/provider operation.
Private continuity and recovery details are kept out of this public report.
