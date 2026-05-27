# Balance.ge Rollback and Manual Fallback Runbook

## Purpose

This runbook defines the emergency rollback procedure and manual fallback path
for the Balance.ge ERP connector. It must be read and understood by the
accountant and Bridge Hub admin before any live Balance.ge activation.

---

## Emergency Disable (< 30 seconds)

If a live posting must be halted immediately:

### Step 1 — Disable the connector via API

```http
POST /posting/connector/balance/disable
Authorization: Bearer <admin-token>
X-Tenant-ID: <tenant_id>
```

This sets `connector.balance_enabled = false` in `tenant_settings`.
All subsequent `/posting/balance/*` and `/posting/apply/*` calls will return:

```json
{ "ok": false, "error": { "code": "CONNECTOR_DISABLED", ... } }
```

No live ERP writes will occur after this call returns.

### Step 2 — Revoke the API key

Log into the Balance.ge console and revoke the API key for the affected tenant.
This is a belt-and-suspenders measure in case the connector is re-enabled
accidentally before the incident is resolved.

### Step 3 — Suspend autopilot (if active)

If autopilot is running for the affected tenant, suspend it:

```sql
-- Run against production DB with a qualified human present
UPDATE tenants SET status = 'suspended' WHERE id = '<tenant_id>';
```

Or via the Bridge Hub admin API:

```http
POST /admin/tenants/<tenant_id>/suspend
```

---

## Re-enable After Resolution

```http
POST /posting/connector/balance/enable
Authorization: Bearer <admin-token>
X-Tenant-ID: <tenant_id>
```

Only re-enable after:
1. The root cause is identified and documented.
2. The Balance.ge API key is rotated (if it was compromised or misfired).
3. The accountant has reviewed all posting_logs for the incident window.

---

## Manual Fallback (CSV Export)

When the Balance.ge connector is disabled and approved drafts must still be
entered into Balance.ge by hand:

### Step 1 — Export approved drafts

```http
GET /posting/export/approved-drafts/csv?limit=500&offset=0
Authorization: Bearer <accountant-token>
X-Tenant-ID: <tenant_id>
```

This returns a CSV file with one row per journal line:

| Field | Description |
|-------|-------------|
| `draft_id` | Bridge Hub journal draft ID |
| `date` | Entry date |
| `description` | Transaction description |
| `partner` | Counterparty name |
| `draft_amount` | Total amount |
| `currency` | Currency (GEL) |
| `line_no` | Line number within the draft |
| `account_code` | COA account code |
| `debit` | Debit amount |
| `credit` | Credit amount |
| `label` | Line description |

### Step 2 — Enter manually in Balance.ge

Open Balance.ge and create a manual journal entry for each draft using the
exported CSV data. Match `account_code` to Balance.ge account codes using the
COA mapping reviewed and signed off by the accountant.

### Step 3 — Mark drafts as manually posted

After manual entry in Balance.ge, update the draft status via the Bridge Hub
admin API to prevent duplicate posting when the connector is re-enabled:

```http
POST /approval/admin/mark-manually-posted/<draft_id>
Authorization: Bearer <admin-token>
X-Tenant-ID: <tenant_id>
```

If this endpoint is not yet available, do NOT re-enable the connector for the
affected drafts until the status is updated via support.

---

## Duplicate Posting Prevention

Bridge Hub uses `entry_hash` (SHA-256 of draft_id + tenant_id + amount + date +
target) and `X-Idempotent-Key` to prevent duplicate ERP entries.

If Balance.ge creates a duplicate despite idempotency protection (a Balance.ge
bug, not a Bridge Hub bug), the accountant must:

1. Identify the duplicate entry in Balance.ge by its reference number.
2. Create a reversal entry in Balance.ge to cancel the duplicate.
3. Document both the original and reversal in the `posting_logs` via a support
   ticket to Bridge Hub engineering.

---

## Posting Log Inspection

Every posting attempt (live, dry-run, or failed) is recorded in `posting_logs`.

```http
GET /posting/logs?draft_id=<id>&target_system=balance
Authorization: Bearer <admin-token>
X-Tenant-ID: <tenant_id>
```

Key fields to inspect after an incident:

| Field | Meaning |
|-------|---------|
| `status` | `posted`, `failed`, `dry_run`, `config_missing` |
| `mode` | `live` or `dry_run` |
| `actor` | User ID who triggered the posting |
| `connector` | `balance`, `onec`, `oris` |
| `idempotency_key` | X-Idempotent-Key header if provided |
| `entry_hash` | Server-computed idempotency hash |
| `error_message` | Reason for failure (no secrets stored) |
| `created_at` | Timestamp of the attempt |

---

## Post-Incident Report

Within 48 hours of any production incident, document:

1. What was posted (draft IDs, amounts, tenants).
2. What error occurred (error_code, error_message from posting_logs).
3. What was reverted (manual reversals in Balance.ge, if any).
4. Root cause analysis.
5. How future recurrence is prevented.

File the report as a GitHub issue tagged `incident` and link it from the
relevant `posting_logs` row via the Bridge Hub admin panel.

---

## Contacts

| Role | Responsibility |
|------|---------------|
| Bridge Hub engineer on-call | connector disable/enable, posting_logs investigation |
| Pilot accountant | manual CSV entry in Balance.ge, entry verification |
| Balance.ge support | API key revocation, duplicate entry reversal |

---

## Related Documents

- [Balance.ge Activation Gate Checklist](balance-ge-activation-gate.md)
- [Balance.ge Final Activation Checklist](balance-ge-activation-final-checklist.md)
- [Posting Service Ledger Write Contract](posting-service-ledger-write-contract.md)
- [Credential Vault Runtime Architecture](credential-vault-runtime-architecture.md)
