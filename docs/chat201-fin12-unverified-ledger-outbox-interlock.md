# Chat201 FIN-12 — unverified local ledger/outbox write interlock (Draft)

2026-10-31. PR #154 stays OPEN/DRAFT/UNMERGED. Started from current
`a22c6724d4f9fd69eef37e8769b037ba7260d2ad`: 7/9 CI SUCCESS;
two CI failures belonged to concurrent cashflow/decimal precision tests,
not to the previously accepted Chat200 diagnostic. Preserve both workstreams,
all existing commits, and all historical ledgers. Production HOLD.

## P0 gap and bounded fix

Chat200 added a read-only diagnostic proving an *already existing* posted
ledger `journal_draft` source cannot establish real ERP acceptance when the
same source has an unverified outbox intent. But cooperating and direct-SQL
writers could still create those incompatible **new** local records in
separate transactions. A missing vendor receipt must not be treated as
permission to post, retry, recreate or backfill.

- **RED first**: `tests/integration/test_chat167_auth_forced_rls_postgres.py`
  adds PG15/PG16 real-DB regressions for outbox-first and ledger-first
  inserts, historical preflight without destruction, tenant isolation and
  concurrent writers. Red commit `19f382c6780614acee3e8455b331bd876612462f`.
- **UNAPPLIED Draft SQL**:
  `docs/sql/chat201_fin12_local_ledger_outbox_interlock_DRAFT.sql`.
  Requires migration 011, Chat179 tenant constraints, Chat185 immutable
  ledger source uniqueness, and Chat186 outbox schema, all in a *disposable*
  database. It is deliberately NOT a startup migration or live change.
- A prerequisite and full-history cross-table preflight fails if historical
  `journal_draft` pairs already exist (preserve, escalate, **never auto-fix**).
  Non-owner RLS-filtered preflights fail closed.
- Paired BEFORE INSERT triggers reject either new posted-ledger source
  against an existing unverified outbox or new outbox against an already
  posted-ledger source. The same tenant+source advisory transaction lock
  serializes concurrent cooperating and direct SQL insertions. Transaction
  isolation other than READ COMMITTED fails closed rather than using a
  stale snapshot. The lock is **local**, not a provider fencing token.
- No UPDATE/DELETE/backfill, no posting status transitions, no vendor
  callback or manual approval bypass. This deliberately blocks an eventual
  provider-confirmed finalizer UNTIL a separately reviewed authenticated
  vendor receipt and locally atomic settlement protocol is designed.
- Existing terminal receipt guards and UNKNOWN crash/manual HOLD continue.
  Chat201 includes only a DB candidate and isolated tests, not activation.

## External dependencies and acceptance

Real-world provider idempotency, signed/status-readback receipts, tenant-ERP
account binding, maker/checker JWT proof, safe lease/fencing, provider
crash-after-send outcome, FIN-11 corrections, local finalizer protocol,
Production privileged-role review, historical preflight and authorized
migration remain **OPEN / EXTERNAL-HOLD**.

CI acceptance must be based on the exact final PR commit, not an earlier
code or documentation SHA. 9/9 green disposable CI cannot certify external
ERP exactly-once or Production readiness. Deploy job must be SKIPPED.
Never alter `main`, Merge, deploy, run a real DB migration, write ERP,
change original Windows files, or upload private Handoff/Evidence to GitHub.
