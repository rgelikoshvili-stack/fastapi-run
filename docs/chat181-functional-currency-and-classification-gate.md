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
