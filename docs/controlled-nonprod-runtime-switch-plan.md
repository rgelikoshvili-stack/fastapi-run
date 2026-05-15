# Bridge Hub — Controlled Non-Production Runtime Switch Plan

## 1. Purpose

Task 11C-H18 defines and tests the safe process for enabling the
`POSTED_LEDGER_REPORTS_ENABLED` feature flag only in non-production or test
environments.  No production runtime switch occurs in this task.  All
verification is done with local in-memory mocks and contract tests only.

---

## 2. Safety Scope

| Constraint | Status |
|---|---|
| Production feature flag (`POSTED_LEDGER_REPORTS_ENABLED`) remains OFF | required |
| No production Cloud Run config changes | required |
| No production DB access | required |
| No Cloud Run DB access | required |
| No SQL execution | required |
| No migration execution | required |
| No Balance.ge activation | required |
| No credentials changed | required |
| No connector behavior changed | required |
| No infrastructure changed | required |
| No posting behavior changed | required |
| No approval logic changed | required |
| No UI/static files changed | required |

---

## 3. Feature Flag

**Name:** `POSTED_LEDGER_REPORTS_ENABLED`

**Default:** `False` (unset = off)

**True values:** `"1"`, `"true"`, `"True"`, `"TRUE"`, `"yes"`, `"Yes"`, `"YES"`

**Rules:**

- Production must remain `False`/off at all times.
- Non-production environments may enable only with explicit approval and a documented test plan.
- Test/local environments may use `monkeypatch` or env-var patch within test scope only.
- When enabled, the runtime must fail closed if `journal_entry_headers` or
  `journal_entry_lines` tables are unavailable — error code `POSTED_LEDGER_UNAVAILABLE`,
  never a silent fallback to `journal_drafts`.
- `tenant_id` is required; empty `tenant_id` raises `ValueError` immediately.

---

## 4. Environment Classification

| Environment | Flag allowed | Rules |
|---|---|---|
| `production` | **never** | Flag must be `False`; any attempt blocked/documented as forbidden |
| `staging` | with explicit approval | Requires test data only, non-prod DB, documented test plan |
| `test` | with explicit approval | Requires test data only, disposable/local DB |
| `local` | with explicit approval | Developer-only, no production data |
| `ci` | monkeypatch inside tests only | Never set as process env var in CI config |
| unknown | fail closed | Treat as production-safe; flag must be `False` |

---

## 5. Non-Production Enablement Checklist

Before enabling `POSTED_LEDGER_REPORTS_ENABLED` in any non-production environment:

- [ ] Explicit approval from engineering lead or designated approver
- [ ] Confirmed environment is **not** `production`
- [ ] Test data only — no production-sourced rows
- [ ] Disposable/local or non-prod DB only (if DB is involved)
- [ ] `journal_entry_headers` and `journal_entry_lines` tables present, **or** fail-closed behavior explicitly tested
- [ ] Rollback plan documented: set flag back to `""` / unset to restore legacy path
- [ ] Monitoring plan: confirm no unexpected errors in non-prod logs post-switch
- [ ] No Balance.ge calls — connector remains `demo_mode`
- [ ] No connector activation of any kind
- [ ] No credentials changed or loaded from production sources

---

## 6. Runtime Behavior When Flag is ON (Non-Production)

| Property | Behavior |
|---|---|
| Report data source | `journal_entry_headers` + `journal_entry_lines` |
| `tenant_id` | Required; `ValueError` on empty |
| Status filter | `STANDARD_NET_STATUSES` = `("posted", "correction")` |
| `reversed` entries | Excluded from net totals |
| `journal_drafts` reference | Forbidden; `_assert_no_silent_fallback` raises |
| Missing tables | Fail closed → `POSTED_LEDGER_UNAVAILABLE` error |
| Drill-down fields | `source_draft_id`, `posting_log_id`, `evidence_bundle_id` preserved |
| Response source tag | `data.source == "posted_ledger"` |

---

## 7. Production Guard

- Production environment must **never** have `POSTED_LEDGER_REPORTS_ENABLED` set to a truthy value.
- The Cloud Run production service must not receive a `--set-env-vars POSTED_LEDGER_REPORTS_ENABLED=1` argument in any deploy command from H18.
- The `/health` endpoint must not expose the flag as enabled.
- Any PR merged as part of H18 must not include changes to production env-var configuration.
- A PR that adds `POSTED_LEDGER_REPORTS_ENABLED=true` to any production deploy script is forbidden and must be rejected before merge.

---

## 8. Verification Plan

- Unit/contract tests only — no DB, no network, no Cloud Run mutation.
- Environment classification tested with mocked env-name inputs.
- Feature flag behavior tested with `monkeypatch` scoped to individual tests.
- Fail-closed behavior tested with mock DB exceptions.
- Live verification (post-deploy) confirms only that production flag remains OFF
  by inspecting `/health` read-only endpoint.

---

## 9. Non-goals

This task does **not**:

- Switch production to posted-ledger reports
- Access production DB
- Execute any DB migration
- Activate Balance.ge or any ERP connector
- Change posting service logic
- Change approval service logic
- Implement any UI/static pages
- Activate staging or deploy a new non-prod Cloud Run revision
- Start H19

---

## 10. Rollback

If the flag is accidentally enabled in non-production and must be reverted:

1. Unset `POSTED_LEDGER_REPORTS_ENABLED` (remove from env or set to `""`).
2. Restart the service — legacy `journal_drafts`-based report path resumes immediately.
3. No DB migration or schema change required — the flag controls only the query path.
4. Confirm via `/health` that the flag is absent from reported env vars.

---

## 11. Next Task

Only after PR merge, deploy to Cloud Run, and live HTTP verification:

**11C-H19 — Production Report Migration Approval Plan**
