# Bridge Hub — Posting Ledger Source Traceability Plan

**Task:** 11C-H70-PRE
**Type:** Design document — source traceability for immutable ledger entries.
**Date:** 2026-05-21
**Depends on:** 11C-H69 (Migration 011 production execution success)

---

## 1. Purpose

This document defines how each `journal_entry_headers` row is linked back to its
originating objects: the journal draft, the posting log, and optionally the source
document or bank file. Traceability is critical for audit, period-close review, and
accounting reconciliation.

**Decision: `H70_PRE_DESIGN_READY_WAITING_FOR_H69`**

H70 implementation is blocked until H69 produces tables in production.
If H69 has not run: `BLOCKED_H69_MIGRATION_NOT_EXECUTED`
If schema is unavailable: `BLOCKED_LEDGER_SCHEMA_UNAVAILABLE`

---

## 2. Traceability Architecture

Migration 011 provides two mechanisms for source linkage:

| Mechanism | Location | Type | Notes |
|---|---|---|---|
| `source_draft_id` | `journal_entry_headers` | UUID NULL | Reserved for when `journal_drafts` migrates to UUID PKs |
| `posting_log_id` | `journal_entry_headers` | UUID NULL | Reserved for when `posting_logs` migrates to UUID PKs |
| `source_type` + `source_id` | `journal_entry_sources` | TEXT + TEXT | Soft link — used in H70 for all integer-PK sources |

In H70, the UUID columns (`source_draft_id`, `posting_log_id`) are left NULL because
`journal_drafts.id` and `posting_logs.id` are `SERIAL` (INTEGER), not UUID.
All traceability uses `journal_entry_sources` rows with TEXT `source_id`.

---

## 3. journal_entry_sources Rows Written Per Posting

For every successful posting in H70, at minimum two source rows are written:

### 3.1 Draft source (always written)

```
source_type : 'journal_draft'
source_id   : str(draft_id)          # e.g., "42"
tenant_id   : draft["tenant_id"]
journal_entry_id : header_id
```

This is the primary traceability link. Any audit query can resolve:
`SELECT * FROM journal_entry_sources WHERE source_type='journal_draft' AND source_id='42'`
to find all posted ledger entries that originated from draft 42.

### 3.2 Posting log source (always written when log_id is not None)

```
source_type : 'posting_log'
source_id   : str(log_id)            # e.g., "17"
tenant_id   : draft["tenant_id"]
journal_entry_id : header_id
```

Links the immutable ledger entry back to the `posting_logs` row which contains
the full ERP connector payload and response. Provides the bridge between the
posted ledger and the connector evidence.

### 3.3 Source document (written if source_document_id is set on draft)

```
source_type : 'document'
source_id   : str(draft["source_document_id"])
tenant_id   : draft["tenant_id"]
journal_entry_id : header_id
```

`journal_drafts.source_document_id` is populated when a draft was auto-generated
from an uploaded document (invoice, bank statement, etc.). If set, the traceability
chain extends from: document → draft → posted ledger entry.

### 3.4 Bank transaction source (future — not in H70)

When `bank_transaction_id` is available on draft lines, a future task may add:
```
source_type : 'bank_transaction'
source_id   : str(bank_transaction_id)
```

Not implemented in H70.

---

## 4. Tenant Isolation

Every `journal_entry_sources` row must carry the same `tenant_id` as the parent
`journal_entry_headers` row. The service must set `tenant_id` explicitly on each
sources row — the DB does not enforce cross-table tenant consistency.

The application layer invariant:
- `journal_entry_headers.tenant_id == draft["tenant_id"]`
- All `journal_entry_lines.tenant_id == draft["tenant_id"]`
- All `journal_entry_sources.tenant_id == draft["tenant_id"]`

This mirrors how `posting_logs` carries `tenant_id` on every row and is always
queried with `WHERE tenant_id = $tenant_id`.

---

## 5. Draft ID Traceability Query Pattern

To find all posted ledger entries for a given draft:

```sql
SELECT jeh.*
FROM journal_entry_headers jeh
INNER JOIN journal_entry_sources jes
    ON jes.journal_entry_id = jeh.id
   AND jes.tenant_id = jeh.tenant_id
WHERE jes.source_type = 'journal_draft'
  AND jes.source_id   = $str_draft_id
  AND jes.tenant_id   = $tenant_id
```

To find the posting log from a posted ledger entry:

```sql
SELECT posting_logs.*
FROM posting_logs
INNER JOIN journal_entry_sources jes
    ON jes.source_type = 'posting_log'
   AND jes.source_id   = posting_logs.id::TEXT
WHERE jes.journal_entry_id = $header_id
  AND jes.tenant_id        = $tenant_id
```

---

## 6. Source Hash on journal_entry_headers

`journal_entry_headers.source_hash` is set to:

```python
source_hash = SHA-256(f"{draft_id}:{tenant_id}:{amount}:{date}:{target}")
```

This is the full (non-truncated) version of the 16-char `entry_hash` used on
`posting_logs`. It provides an additional tamper-detection layer at the header level:
if the source inputs change, the hash changes.

The source_hash is stored for audit purposes. It is not used as a unique constraint
in H70 (the existing `POSTING_DUPLICATE_BLOCKED` + `entry_hash` on `posting_logs`
is sufficient for uniqueness).

---

## 7. Evidence Bundle Integration (future)

`journal_entry_headers.evidence_bundle_id` (UUID NULL) is reserved for a future
task where an evidence bundle is created per posting (linking approvals, signatures,
supporting documents). Not populated in H70.

---

## 8. Audit Trail Completeness

For any posted ledger entry, H70 provides the following complete audit trail:

```
journal_entry_headers
  └── journal_entry_lines (via journal_entry_id FK)
  └── journal_entry_sources
        ├── source_type='journal_draft', source_id=str(draft_id)
        │     └── journal_drafts (via id=source_id::int)
        │           └── journal_drafts.lines_json  (original line data)
        │           └── journal_drafts.status = 'posted'
        └── source_type='posting_log', source_id=str(log_id)
              └── posting_logs (via id=source_id::int)
                    └── posting_logs.payload_json  (ERP payload sent)
                    └── posting_logs.response_json (ERP response received)
```

This chain preserves the full origin, content, and evidence for each immutable
posted ledger row.

---

*Bridge Hub — Task 11C-H70-PRE. Source traceability plan only.
No runtime code changed. No SQL executed. No production DB connection.
Decision: H70_PRE_DESIGN_READY_WAITING_FOR_H69.*
