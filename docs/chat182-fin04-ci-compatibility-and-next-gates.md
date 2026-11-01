# Bridge Hub — Chat182 / FIN-04 regression compatibility and CI gate

**Date:** 2026-10-30. **Release:** Production HOLD. **Scope:** existing Draft PR #154 only.

## Continuity / origin of this check

The active Draft branch was already at Chat181, not Chat177, when Chat182 started.
Chat178–181 implementation and their evidence were inspected and preserved.
No rebase, reset, force push, replacement PR, or edits to original Windows files.
No production cloud, financial data, provider credentials, migration or feature flag was touched.

## Finding and correction

At code SHA `4d1119f1985a519b949543b6c2537cb4e7f938b3`, full backend CI failed:
**8 failed, 8,352 passed, 3 skipped** (run
https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41029904247).
All failures were the older `tests/unit/test_h70a_g8b_posting_log_source.py`
traceability fixture. It created a mock journal using COA code `3100`, which
is absent from the repository's canonical chart. The new, intended FIN-04
writer guard correctly raises `LEDGER_ACCOUNT_UNCLASSIFIED` before INSERT.

**Draft correction:** changed that fixture's balancing credit account from
unregistered `3100` to canonical `3110` (liability), preserving the
same journal amount and source-link assertions. **No posting/account
classification/FX/RLS application code was weakened or changed.** Existing
negative tests still reject genuinely unregistered accounts.

## Independently verified exact implementation SHA

Commit: `15d4781eb06f19c8f3440b3957e0fd9afc61c363`.
All nine GitHub CI workflows on that exact commit completed **SUCCESS**:

| Evidence | Result | Run |
| --- | --- | --- |
| Backend tests | 8,360 PASS, 3 SKIP; extra smoke 1 PASS | [41046927194](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927194) |
| PostgreSQL 15/16 | 537 PASS each | [41046927200](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927200) |
| Real Chroma/ONNX | 43 PASS | [41046927406](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927406) |
| Disposable Redis 7 | 210 PASS | [41046927266](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927266) |
| PR127 PostgreSQL reporting | 270 PASS + 1 smoke | [41046927220](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927220) |
| PR84 snapshot | 82 PASS + 219 PASS + 1 smoke | [41046927168](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927168) |
| Tenant membership | PASS | [41046927082](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927082) |
| Vault | PASS | [41046927125](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927125) |
| Financial RLS | PASS | [41046927105](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/41046927105) |

The deploy workflow's *test* job passed; the actual Cloud Run deployment
job was **SKIPPED**, and React build setup was SKIPPED because the React
source is absent in this backend-only tree. Do not describe those as
live deployment/frontend compilation.

## Next gates (not certified by the above)

1. **FIN-04:** identify and formally map tenant-specific/custom COA codes
   before any Bridge-authority posting. Do not invent a type or accept
   client-supplied account_type to fix unknown codes.
2. **FIN-05:** approved posting-date/source/quote provenance and freshness
   policy, plus real provider evidence (current fixed stored-rate guard is
   NOT proof of official published rate correctness).
3. **FIN-06 / FIN-12:** database-enforced uniqueness and immutability
   (separate from cooperative application lock), source receipt/outbox,
   unknown ERP post outcome, correction and idempotent replay.
4. **AI Vector:** preserve disabled HTTP global search/indexing; real Chroma
   43-PASS validates synthetic tenant learned query, not historical file
   provenance or permission to expose all records.
5. Current Cloud SQL backup/PITR + isolated restore, RLS owner/role audit,
   migrations 013–016, Cloud Run/Redis multi-replica failover, OAuth/SMTP,
   real ERP and finance E2E, JWT regional parity and Windows preservation
   remain separate Production HOLD gates.

**Decision:** Draft-only compatibility regression repaired and all exact-SHA
CI green. No main merge. No Production deploy, DB migrations or live restore.
