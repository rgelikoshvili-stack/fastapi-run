# Bridge Hub — Post-H66 Report Endpoint Runtime Check

**Task:** 11C-H67
**Type:** Post-deployment report endpoint runtime verification.
**Date:** 2026-05-20
**Branch:** codex/h67-report-mismatch-recheck-after-schema-fix

---

## 1. Purpose

Verify the runtime behavior of production report endpoints after H66 schema fixes,
using authenticated and unauthenticated requests. Confirm no 5xx, no auth bypass,
no secret exposure, and document schema availability status.

---

## 2. /version and /health Checks

### /version
```json
{
  "ok": true,
  "message": "Version",
  "data": {
    "app": "Bridge Hub",
    "commit_sha": "7429cfecb61efac48522d933ce6dd27f6b4ba5db",
    "build_time": "2026-05-19T20:31:25Z",
    "environment": "production"
  },
  "error": null
}
```

| Field | Value |
|---|---|
| HTTP status | 200 |
| commit_sha | `7429cfecb61efac48522d933ce6dd27f6b4ba5db` (H66 SHA — confirmed) |
| environment | `production` |
| H66 deployed | Yes |

### /health
```json
{
  "ok": true,
  "message": "Health check OK",
  "data": {
    "status": "degraded",
    "env_vars": {
      "DATABASE_URL": "set",
      "JWT_SECRET": "set",
      "ANTHROPIC_API_KEY": "set",
      "BALANCE_API_KEY": "missing",
      "OPENROUTER_API_KEY": "set"
    },
    "warnings": ["BALANCE_API_KEY not configured"],
    "connectors": {
      "balance": "demo_mode",
      "anthropic": "configured",
      "openrouter": "configured"
    }
  }
}
```

| Field | Value |
|---|---|
| HTTP status | 200 |
| ok | true |
| Degraded reason | BALANCE_API_KEY missing — expected |
| Balance.ge | demo_mode — not activated |
| Startup crash | No |
| DATABASE_URL | set |
| Secrets exposed | No — only set/missing flags shown |

---

## 3. Unauthenticated Protection Checks

All tested without Authorization header.

| Endpoint | HTTP Status | Auth Required |
|---|---|---|
| `GET /reports/trial-balance` | 401 | Yes ✓ |
| `GET /reports/balance-sheet` | 401 | Yes ✓ |
| `GET /reports/profit-loss` | 401 | Yes ✓ |
| `GET /reports/vat` | 401 | Yes ✓ |
| `GET /approval/queue` | 401 | Yes ✓ |
| `GET /connectors/balance/status` | 401 | Yes ✓ |

No report data exposed without auth. RBAC intact.

---

## 4. Authenticated Endpoint Matrix

Token: derived from JWT_SECRET, role=admin, tenant=default. Token not stored in this doc.

| Endpoint | HTTP Status | ok | Response Summary |
|---|---|---|---|
| `GET /reports/trial-balance` | 200 | true | `POSTED_LEDGER_UNAVAILABLE` — `journal_entry_lines` missing |
| `GET /reports/balance-sheet` | 200 | false | `POSTED_LEDGER_UNAVAILABLE` — same error code |
| `GET /reports/profit-loss` | 404 | — | Endpoint not implemented |
| `GET /reports/vat` | 404 | — | Endpoint not implemented |
| `GET /reports/cashflow` | 200 | true | Real data returned — cash_in 91,581.27 / cash_out 77,428.96 / net 14,152.31 GEL |
| `GET /reports/ledger-summary` | 404 | — | Not implemented |
| `GET /reports/status-summary` | 404 | — | Not implemented |
| `GET /reports/source-summary` | 404 | — | Not implemented |

---

## 5. Missing-Table Finding Status

| Table | Status After H66 |
|---|---|
| `bank_transactions` | **EXISTS** — cashflow report returns live data queried from this table |
| `pipeline_runs` | **INFERRED CREATED** — startup DDL ran, no crash |
| `journal_entry_lines` | **STILL MISSING** — `relation "journal_entry_lines" does not exist` error confirmed live |
| `journal_entry_headers` | **STILL MISSING** — part of migration 011, not yet run |
| `journal_entry_sources` | **STILL MISSING** — same |

H66 resolved `bank_transactions` and `pipeline_runs`. The posted-ledger tables
(`journal_entry_headers`, `journal_entry_lines`, `journal_entry_sources`) remain absent
because migration 011 has never been executed against production.

The `ALTER TABLE journal_entry_lines ADD COLUMN IF NOT EXISTS` statements from H66
were silently skipped at startup (table does not exist — try/except swallows the error).
This is correct idempotent behavior.

---

## 6. 5xx Status

No 5xx on any endpoint during H67 verification.

| Category | Count |
|---|---|
| 5xx errors | 0 |
| Unhandled exceptions | 0 |
| Raw stack traces in response | 0 |

All schema-missing errors are handled gracefully as `POSTED_LEDGER_UNAVAILABLE` with
valid JSON envelopes and HTTP 200.

---

## 7. Schema/Runtime Limitation

| Limitation | Detail |
|---|---|
| Direct schema inspection | BLOCKED — no safe psql or schema-inspection endpoint |
| `journal_entry_lines` verification | INFERRED missing from live error response |
| `bank_transactions` verification | CONFIRMED present from cashflow live data |
| Migration 011 status | NOT executed against production |
| Startup migration scope | Only adds `bank_transactions`, `pipeline_runs` — does not create posted-ledger tables |

---

## 8. Decision

**H67 Post-H66 Runtime Check Decision: `BLOCKED_POSTED_LEDGER_SCHEMA_MISSING`**

The app is healthy. H66 bank_transactions and pipeline_runs fixes are live.
The posted-ledger schema (`journal_entry_lines` etc.) is still absent.
No 5xx. No auth bypass. No secrets. No rollback required.

---

*Bridge Hub — Task 11C-H67. Post-H66 runtime check complete.
`journal_entry_lines` still missing. No 5xx. No rollback. Balance.ge inactive.*
