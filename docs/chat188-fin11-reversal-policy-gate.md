# Chat188 — FIN-11 reversal and adjustment safety gate

**Date:** 2026-10-30. **Repository:** rgelikoshvili-stack/fastapi-run.
**PR #154:** OPEN / DRAFT / UNMERGED. `main` untouched. Production HOLD.
**Exact implementation SHA:** `8dde6735847f30ab53855039f87224b761abfb87`.

## Confirmed source defects
1. Both reversal and adjustment HTTP routes accepted a raw
   `allow_closed_period` body flag. The service bypassed the period lock for
   any caller with basic `approval:write`. No independent CFO/admin
   maker-checker authority or reopen-evidence existed.
2. The reversal service treated `simulated_success` as financially posted.
3. The adjustment service accepted non-posted source drafts.
4. Reversal and adjustment date parsing silently truncated arbitrary input
   to ten characters; a timestamp suffix could be accepted.
5. Correction-draft period validation previously had no FIN-11 advisory
   serialization against concurrent month/year close.

## Changes (Draft branch only)
- Reject any non-False `allow_closed_period` at the route and direct service
  boundary with `CLOSED_PERIOD_OVERRIDE_DISABLED`. A real authorized
  reopening policy is **not** implemented or implied.
- Reversal of only `posted` originals; adjustments of only `posted` originals.
  No simulation or unposted record can impersonate a posted transaction.
- Accept exact YYYY-MM-DD dates, reject suffixes, malformed dates and None
  before opening the DB.
- Share the FIN-11 year/month transaction lock when creating reversal or
  adjustment drafts, then check period_locks before INSERT.
- Preserve ordinary pending_approval draft approval flow, original row,
  other clients' tenancies and old historical documentation.
- Supersede (do not delete) old BIZ-3 override guide with a dated addendum.

## Regression proof
Red-only `2dae703ec3fc9d9a1087b259b3ddabb9c32ad646`:
10 FIN-11 policy test failures in each disposable PG15 and PG16 run;
other unrelated workflows passed. These reproduce code defects, not live
financial data corruption.

Repair `8dde6735847f30ab53855039f87224b761abfb87`:
all nine GitHub Actions workflow families SUCCESS at exact code SHA.
Backend **8,416 PASS / 3 SKIP**, plus smoke 1, run 41062444249.
Disposable PG15 and PG16 **601 PASS EACH**, run 41062444166.
All other workflows (RLS, Redis, Vault, Membership, PR127, PR84, Chroma)
SUCCESS. Real Cloud Run deploy job SKIPPED; frontend source build SKIPPED.
Distinct workflow suites overlap, so their counts must not be added.

## Deliberate limitations / next safe work
This stage only changes the **correction DRAFT creation guard**. It does not
create a new posted ledger reversal row or prove a durable independent audit
log, maker/checker separation, source-specific concurrent reversal uniqueness,
a separately approved unlock workflow or real ERP receipt. No real Cloud SQL
DDL, RLS/roles, real vendor operation, backup/PITR modification or local
Windows original was touched. Next independent FIN-11 target:
per-tenant source-level reversal uniqueness under concurrency and approval
state consistency, followed by full append-only posted-ledger reversal design.

No private Master Handoff, evidence ZIP, Windows recovery path/manifest or
credential was published to GitHub.
