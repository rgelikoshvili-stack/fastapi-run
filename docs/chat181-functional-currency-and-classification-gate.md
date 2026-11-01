# Chat181 — functional currency and financial completeness

2026-10-29. Continuation from exact Chat180 head
`81d2150e0efc5e15b35db9358d1c35459d18b616`; PR154 Draft only.
Main/Production/live migrations/Windows originals remain untouched.

## FIN-05 reproduction

Existing posted P&L, balance, cashflow and both trial readers aggregate raw
line debit/credit, although official outputs say GEL. The writer stores
functional `amount_gel` and original posting exchange rate, but does not check
that independently rounded functional lines remain balanced. A GEL line can
also receive a non-unit exchange rate.

New regressions require mixed USD/EUR/GEL results from the actual writer under
nonowner FORCE-RLS PostgreSQL15/16, both AI readers, CFO, date bounds and another
tenant. Invalid/missing legacy functional amounts/rates, NaN, currency mismatch
and functional rounding imbalance must make official reports unavailable,
without guessing a rate or rewriting historical rows. All data is synthetic.

This first commit intentionally records failing regression tests against the
unchanged implementation. The next isolated Draft commit will implement the
repair and rerun the same tests. No production/provider activity is involved.


## Stage 1: stored functional basis and legacy foreign-currency guard

Regression source `28794b0e63dfc3cb548efe93c4a7dde6e41134fe` failed as intended:
PG15/16 each 14 FAIL / 492 PASS (40927067665), including actual 120 vs expected
310 GEL. Seven new local unit cases failed before. Six additional legacy-path
cases failed locally before their guard was added.

A shared CTE scopes tenant/status/date and complete journals before account
filters. It uses stored functional amounts for foreign lines, validates finite
bounded rates/amounts, header/line currency and rate consistency, exact per-line
rounding and functional journal balance. Both trial readers, P&L, balance and
cashflow use this same basis. Invalid evidence returns a stable unavailable
response before float conversion; CFO also marks failed P&L metrics null.
Legacy GEL rows with migration011's default amount_gel=0 retain their raw GEL
values only when rate1/header currency agree. No foreign FX is inferred.

The writer now rejects non-unit GEL rates and rounded functional imbalance
before INSERT, preserving the journal instead of inventing a balancing line.
Foreign legacy posted-draft aggregates have no durable verified posting FX;
P&L/BS/trial/account/counterparty/payroll therefore fail closed for those rows.
GEL-only legacy behavior remains. Raw journal browsing retains original amounts
and exposes currency/source. This does not activate the posted-report flag.

The minimal PR127 synthetic schema now includes migration011 currency/rate/
amount_gel columns; no production schema or startup registration changed.
Local focused suite:250 PASS. Local full suite before the six legacy additions:
8347 PASS /3SKIP on Python3.12. Exact implementation plus follow-up `547ba514cd1a60a48453df58d06b7ba4545f3673`: all nine workflows PASS. Backend8344/3SKIP+smoke1 (40929065402), PG15/16 514EACH (40929065506), Chroma43 (40929065466), Redis210 (40929065550), membership45 (40929065529), vault104 (40929065488), RLS18 (40929065399), PR127254+1 (40929065536), PR8482/203+1 (40929065404). Actual deploy and frontend build SKIPPED.

A separate confirmed issue remains in rate acquisition: currency_service's
preview lookup can return a static fallback and accepts rates without a proved
posting-date/source contract. Stored arithmetic validation does not establish
that provenance. The next independent safe step must block that fallback on
the financial posting boundary while preserving separately labelled previews.
Historical backfill, default-rate replacement, unknown COA, report numeric-output
precision, complete equity, live schema/provider/UI/recovery gates remain open.


### Actual CI follow-up

Initial implementation `f42dcfa` passed the mixed-currency/report/AI/CFO and
invalid-FX PostgreSQL cases. Two new legacy cases exposed an older trial SQL
bug: SELECT and GROUP BY used different bind positions for the same CASE.
Grouping now uses the selected bucket, DATE inputs are normalized, and null
opposite-side accounts are excluded instead of doubling legacy turnover.
Real tests also cover opening-only foreign rejection and GEL-only period/
opening balances. The separate H84 snapshot fixture, like PR127, needed the
migration011 currency fields; its synthetic schema is now updated. No test
assertion or FX validation was weakened. Full isolated CI is rerun below.


## Stage 2 — stored-rate-only financial posting (2026-10-30)

A further regression reproduced static USD fallback on missing DB rows,
database outage and invalid stored rate:3 FAIL before the repair. Posting now
passes `allow_fallback=false`; async conversion propagates this policy through
both legs of cross conversions. Missing/invalid rates fail before a connector
call. Native DATE binding fixes valid ISO-date lookups rather than accidentally
falling back after an asyncpg type error. A strict lookup requires a valid date.

Posting preserves an exact eight-decimal rate beside the connector numeric
field, and ledger bindings prefer that exact value. Functional amounts use the
same quantized rate; no connector float can change stored booked FX. Existing
standalone estimate helpers remain separate and are not used for posting.
New real PG coverage verifies date cutoff, missing/cross rates, invalid rate,
exact payload→writer persistence and unchanged standalone estimate behavior.
Exact stage2 `5ef73cddcc1e3bea85d522dd7de76113d6ea01eb`: all9 workflows PASS. Backend8351/3SKIP+1 (41028220880), PG15/16 522EACH (41028220726), Chroma43 (41028220683), Redis210 (41028220621), membership45 (41028220626), vault104 (41028220633), RLS18 (41028220624), PR127261+1 (41028220671), PR8482/210+1 (41028220682). Actual deploy/frontend build SKIPPED. Final focused local78PASS.

This is not a complete NBG publication/effective-date or stale-quote policy.
The existing stored on-or-before lookup is retained; trusted ingestion,
immutability/history, effective date/source attestation, freshness limits and
explicit estimate labels on every preview consumer remain acceptance gates.
No live fetch, schema/config change or migration was performed.


## Stage 3 — classification-completeness reproduction

FIN-04 regression tests now cover historical NULL canonical types and revenue
aliases, typed custom history, unmapped NULL, unknown and contradictory types,
and unregistered new ledger accounts. Seven local unit cases fail before the
repair. The following test-only Draft commit intentionally records the real
PostgreSQL before state. No historical financial row is repaired automatically.


### Classification repair

Test-only `12eac81133761adf27c036c1528a89a2756fc334` reproduced real zero
revenue from historical NULL/alias types and acceptance of contradictory types.
PG15/16 each12FAIL/523PASS (41029251830). Seven unit cases and two additional
legacy statement cases failed before their repairs.

A repository-owned canonical COA supplies missing types for known account codes
at read time, with revenue/contra-asset aliases normalized. No historical row
is updated. Valid explicitly typed custom historical accounts remain readable;
unmapped NULL, unknown type or contradiction with the canonical COA makes the
whole scoped official basis unavailable. A global scoped flag is retained even
when ordinary P&L/BS account filters would otherwise remove the bad line.
Both AI readers/CFO inherit the same unavailable result. Legacy P&L/BS also
refuse unknown account codes instead of silently skipping their balances.

New Bridge-ledger writes require a registered canonical classification before
INSERT, and the Bridge-authority payload preflight checks it before connector
dispatch. Caller account_type hints cannot supply authority. Stable review
errors cover normal, preview and dry-run paths. ERP-authority custom account
posting is not newly restricted when ledger writes are disabled. Full tenant
COA import/validation and registering new custom ledger accounts remain FINISH.

The old custom-unmapped writer case now asserts no INSERT rather than NULL
persistence. PR127's unknown-cashflow fixture uses a valid typed custom account;
contradictory canonical metadata has its own new real-PG negative test. This
keeps incomplete IAS7 classification separate from a corrupt account type.
Local focused262PASS. Exact classification implementation CI pending.
