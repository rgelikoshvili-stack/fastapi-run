# Chat186 — FIN-12 durable outbox/receipt *foundation* (Draft only)

**2026-10-30.** Existing PR #154 remains OPEN/DRAFT and unmerged.
**Final verified source SHA:** `7d7682703b50bbc5657b74bcd3a8137d7424cc4a`.
No main write, rebase, force-push, Production deploy, cloud mutation,
real ERP call, credential acquisition, Windows-original write or data deletion.

## Defect boundary and design

The current `apply_posting_service` performs an external ERP mutation and
commits the corresponding local draft/log/ledger in separate steps. A timeout
may mean the ERP posted successfully while the local transaction did not
persist; a blind retry can duplicate money. The previous cooperative
`journal_draft` ledger lock and Chat185 unique source SQL do not provide
external exactly-once delivery.

This stage adds an **INERT, non-registered** outbox foundation:
`app/api/services/posting_outbox_intent_service.py` prepares a deterministic
per-tenant/source/target intent and canonical payload SHA-256 inside the
caller's existing transaction. Repeated identical requests return the same
durable row; conflicting changed amounts are rejected. Without a verified
tenant context, canonical source, supported target or active transaction,
prepare refuses before DB write. No connector dispatch is implemented.

`docs/sql/chat186_posting_outbox_DRAFT.sql` is a standalone candidate with
nonowner FORCE-RLS tenant isolation, per-tenant/source and idempotency-key
uniqueness, immutable identities/payloads, append-only receipt evidence with
tenant+outbox composite FK, and no public table permissions. UNKNOWN result
cannot transition into automatic in-flight retry. Receipt "accepted" requires
an evidence digest, provider receipt ID and verifier; the schema alone does
not certify vendor authenticity.

All tests were synthetic on disposable PostgreSQL only. No runtime migration,
job, queue, provider ID or database rollout was activated. A narrow follow-up
`7d768270` kept ordinary runtime producers SELECT/INSERT-only (no UPDATE
grant needed for duplicate lookup), handled bad payloads safely and fixed a
test import.

## Exact implementation CI

All **nine** workflows SUCCESS at `7d7682703b50bbc5657b74bcd3a8137d7424cc4a`:
- Backend 8,397 PASS / 3 SKIP + smoke 1 — run 41057934116.
- PostgreSQL 15 **579 PASS** and PostgreSQL 16 **579 PASS** — 41057933825.
- Redis — 41057933873; Chroma/ONNX — 41057934106;
  membership — 41057933992; vault — 41057934070;
  finance RLS — 41057934140;
  PR127 reporting — 41057934025; PR84 snapshots — 41057933890.

Actual Cloud Run deploy **SKIPPED** and React build steps **SKIPPED**.
Suites overlap; counts must not be summed across workflows.

## Still OPEN / EXTERNAL-HOLD

No actual ERP call is routed through this outbox yet. No provider-certified
idempotency key, signed/validated receipt, timeout/unknown reconciliation,
worker lease, crash recovery, legacy draft/ERP synchronization or atomic
posted-ledger receipt linkage has been accepted. Thus FIN-12 is a tested
**foundation**, NOT a complete durable execution flow or V1 acceptance.
The pending live provider contract, system roles/grants, schema migration,
RLS/backup/PITR/restore, financial maker/checker and release operations
remain HOLD. The next safe independent work is the FIN-11 close-vs-post /
reversal controls or further isolated FIN-12 fault-injection design.
