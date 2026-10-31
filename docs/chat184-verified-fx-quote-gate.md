# Chat184 — FIN-05 approved as-of FX quote gate (Draft only)

**Date:** 2026-10-30. **PR #154:** OPEN/DRAFT/unmerged. **Production:** HOLD.
**Exact tested code SHA:** `55ebd684e7d98bf229dd795e5eb95afe47a685b9`.
The PR includes all inherited Chat180–183 work. No reset/rebase/main merge.

## Defect and safe bounded repair
FIN-05 previously accepted a mutable `exchange_rates` latest-snapshot rate for
official posting merely because a number existed. In a separate revaluation path,
`fx_service._get_rate_conn` ignored its as-of date and selected latest updated
rate; missing one currency silently skipped that open monetary position, yielding
a plausible-looking partial result.

New `verified_fx_quote_service.py` requires synthetically testable, independently
reviewed NBG-source quote evidence with source revision/payload SHA-256, published
and effective dates, retrieval/approval metadata, exact Decimal raw rate / unit
quantity / GEL rate agreement, unique latest effective date, and bounded 7-calendar-
day as-of age. Ambiguous, stale, future, manual, missing, malformed or unapproved
source rows fail CLOSED; there is no hardcoded fallback, today's rate substitution,
or live provider call on the financial path. The legacy `exchange_rates` cache and
its standalone estimates remain unchanged for nonofficial preview use.

Strict `currency_service.get_rate_async(..., allow_fallback=False)` now reads
reviewed quotes, while the public preview helper retains existing behavior.
Official FX revaluation shares the validated source and refuses incomplete
results; its route errors redact internal exceptions. A standalone unregistered
`docs/sql/chat184_verified_fx_quotes_DRAFT.sql` candidate adds append-only
evidence storage with DB triggers and no public write permissions. It was
executed ONLY in disposable PostgreSQL 15/16 synthetic tests, never live.

## Before/after evidence
- Test-only SHA `70bc7d54e75f1ff4fd8a0ea7d22c5b58c4508abf`:
  15 expected FAIL / 552 PASS in BOTH PG15/PG16 runs 41055680965;
  genuine legacy-rate acceptance and ignored revaluation date observed.
- Implementation `55ebd684e7d98bf229dd795e5eb95afe47a685b9`:
  exact nine GitHub Actions workflows completed SUCCESS:
  - backend 8,389 PASS / 3 SKIP + one smoke; run 41056047193;
  - disposable PG15/16 567 PASS EACH; run 41056046957;
  - Chroma/ONNX run 41056046997; Redis 41056047282;
  - tenant membership 41056047031; vault 41056047179;
  - RLS 41056047368; PR127 270 PASS + smoke 1 (41056047152);
  - PR84 82 + 219 PASS + smoke 1 (41056047188).
  The actual Cloud Run deploy job SKIPPED. Node install/frontend build SKIPPED.
  The code's synthetic tests are not real NBG approval or Production proof.

## Limitations and next work
A reviewed quote row is an **attestation contract**, not proof that a real NBG
publication/revision/raw-payload hash was verified externally. The provider
calendar, ingestion, role grants, schema rollout, historical legacy inventory,
posting-transaction durable quote/receipt linkage and production acceptance
remain EXTERNAL-HOLD. The seven-calendar-day bound is a conservative fail-closed
interim policy; provider-specific holiday exceptions need explicit review.
FIN-06/FIN-12 require direct SQL uniqueness/immutability and durable external
receipt/outbox/unknown-response handling. No historical entries were backfilled.

No Production data/config/cloud resource/Windows original was changed, and no
private handoff, credentials or recovery manifests were uploaded to GitHub.
