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
8347 PASS /3SKIP on Python3.12. Exact implementation CI pending.

A separate confirmed issue remains in rate acquisition: currency_service's
preview lookup can return a static fallback and accepts rates without a proved
posting-date/source contract. Stored arithmetic validation does not establish
that provenance. The next independent safe step must block that fallback on
the financial posting boundary while preserving separately labelled previews.
Historical backfill, default-rate replacement, unknown COA, report numeric-output
precision, complete equity, live schema/provider/UI/recovery gates remain open.
