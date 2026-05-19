# Bridge Hub — H65 Auth Token Handling Safety

## 1. Purpose

This document defines the auth token handling policy for H65 authenticated report endpoint verification. It ensures that any auth token used for read-only production checks is handled safely and never committed, logged, or exposed.

---

## 2. Token Source

**Acceptable source:** Environment variable `H65_AUTH_TOKEN` only.

```
H65_AUTH_TOKEN="<token>"  # set in shell only — never committed
```

No other token source is permitted for H65.

---

## 3. Redaction Rules

| Rule | Requirement |
|---|---|
| R1 | Never print or echo `H65_AUTH_TOKEN` value |
| R2 | Never include raw token in curl output captured to docs |
| R3 | Redact `Authorization: Bearer <token>` in all logged output |
| R4 | Replace token in any example with `<REDACTED>` |
| R5 | Never store token value in any file |
| R6 | Use only in-memory environment variable |

Example of safe usage:
```bash
curl -s -H "Authorization: Bearer ${H65_AUTH_TOKEN}" <url>
# token expanded by shell only — never echoed
```

---

## 4. Forbidden Token Storage

| Storage location | Permitted? |
|---|---|
| .env file | NO |
| .env.* file | NO |
| Committed file | NO |
| docs/* | NO |
| tests/* | NO |
| logs | NO |
| GitHub Actions secrets (as raw value) | only if GH Actions secret vault |
| Shell environment variable (session only) | YES |

---

## 5. Forbidden Endpoint Calls

Even with a valid auth token, the following calls are forbidden during H65:

| Endpoint type | Forbidden |
|---|---|
| POST /approval/* | YES |
| POST /posting/* | YES |
| POST /connectors/balance/apply | YES |
| POST /connectors/balance/post | YES |
| DELETE /* | YES |
| PUT /* | YES |
| PATCH /* | YES |
| Any endpoint that writes to DB | YES |
| Any endpoint that posts to ERP | YES |
| Any endpoint that activates Balance.ge | YES |

---

## 6. Read-Only Scope

Permitted calls with auth token during H65:

| Endpoint | Method | Permitted |
|---|---|---|
| /reports/trial-balance | GET | YES |
| /reports/balance-sheet | GET | YES |
| /reports/profit-loss | GET | YES |
| /reports/vat | GET | YES |
| /reports/ledger-summary | GET | YES |
| /reports/status-summary | GET | YES |
| /reports/source-summary | GET | YES |
| /version | GET | YES |
| /health | GET | YES |

---

## 7. H65 Token Status

**H65_AUTH_TOKEN: NOT AVAILABLE at time of execution**

Authenticated checks blocked. Unauthenticated baseline completed. Deep checks deferred.

---

## 8. Safety Decision

**H65 Auth Token Handling Decision: `TOKEN_HANDLING_SAFE_NO_TOKEN_AVAILABLE`**

No token was available. No token was committed, logged, or exposed. Token handling policy was defined and applied. Authenticated checks are deferred pending token provision.
