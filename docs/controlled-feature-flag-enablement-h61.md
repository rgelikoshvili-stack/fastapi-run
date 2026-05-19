# Bridge Hub — H61 Controlled Feature Flag Enablement

## 1. Purpose

This document records the controlled enablement of `POSTED_LEDGER_REPORTS_ENABLED` in production. H61 was executed after H59 FINAL_SIGNOFF_APPROVED and H60 CONTROLLED_SWITCH_EXECUTION_READY, with all pre-switch checks passing.

---

## 2. Pre-Switch Verification (executed immediately before enablement)

| Check | Expected | Result |
|---|---|---|
| /version HTTP 200 | yes | ✅ HTTP 200 |
| live SHA matches main HEAD | `21665ffb37bcabd4f926956e314c0bd2c5cd064f` | ✅ exact match |
| /health HTTP 200 | yes | ✅ HTTP 200 |
| `POSTED_LEDGER_REPORTS_ENABLED` absent/OFF | yes | ✅ absent |
| Balance.ge demo_mode | yes | ✅ demo_mode |
| Protected endpoints HTTP 401 | yes | ✅ 401 |
| No active incident | yes | ✅ confirmed |

All pre-switch checks PASS. Enablement authorized.

---

## 3. Enablement Execution

| Property | Value |
|---|---|
| Command | `gcloud run services update fastapi-run --region europe-west1 --update-env-vars POSTED_LEDGER_REPORTS_ENABLED=true` |
| Operator | ROLANDI GELIKOSHVILI |
| Timestamp | 2026-05-19T00:52:00Z (approx) |
| Service | `fastapi-run` |
| Region | `europe-west1` |
| Env var changed | `POSTED_LEDGER_REPORTS_ENABLED=true` |
| Other env vars changed | **none** — `--update-env-vars` modifies only the specified var |
| Revision before | `fastapi-run-00324-9hp` |
| Revision after | `fastapi-run-00325-67n` |
| Traffic | 100% to new revision |
| Outcome | Deploying → Creating Revision → Routing traffic → Done ✅ |

---

## 4. Post-Enablement State (gcloud confirmation)

```
POSTED_LEDGER_REPORTS_ENABLED present in: fastapi-run / europe-west1 env vars
```

Confirmed via: `gcloud run services describe fastapi-run --region europe-west1 --format="value(spec.template.spec.containers[0].env[].name)"`

Output includes `POSTED_LEDGER_REPORTS_ENABLED` ✅

---

## 5. H61 Decision Options

| Decision | Condition |
|---|---|
| `FEATURE_FLAG_ENABLED_CONTROLLED` | All gates pass, gcloud succeeds, revision active |
| `BLOCKED_H59_H60_NOT_READY` | H59 or H60 not approved before H61 |
| `BLOCKED_CLOUD_RUN_TARGET_UNCERTAIN` | Region/project not determinable safely |
| `BLOCKED_PRE_SWITCH_VERIFICATION_FAILED` | Any pre-switch check FAIL |
| `BLOCKED_ENABLEMENT_COMMAND_FAILED` | gcloud command error |
| `ROLLBACK_TRIGGERED_DURING_ENABLEMENT` | H62 rollback trigger fired immediately |

---

## 6. H61 Final Decision

**H61 Decision: `FEATURE_FLAG_ENABLED_CONTROLLED`**

`POSTED_LEDGER_REPORTS_ENABLED=true` set on `fastapi-run` / `europe-west1`. New revision `fastapi-run-00325-67n` serving 100% traffic. No other env var changed. Proceed to H62 post-switch live verification.
