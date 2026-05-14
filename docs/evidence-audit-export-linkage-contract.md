# Bridge Hub — Evidence / Audit Export Linkage Contract

**Task:** 11C-H10
**Type:** Contract document and tests only — no runtime code change, no SQL, no migration execution.
**Date:** 2026-05-13
**Follows:** 11C-H9 `docs/reversal-correction-contract.md`

---

## 1. Purpose

Posted accounting truth must be explainable and auditable. Every official ledger entry in `journal_entry_headers` must be traceable to its full history: the source document that triggered it, the AI reasoning and classification that shaped it, the approval decisions that validated it, the connector execution that confirmed it, the evidence bundle that packages it, and the reversal/correction chain that may follow it.

This contract defines the rules governing how `evidence_bundle_id` links to posted ledger entries, how audit export packages must be structured, and what guarantees must hold for every export. No runtime export behavior is implemented by this task. This contract is the specification that H15 will mock-test and H16 will implement once explicitly approved.

**No SQL is executed in this task. No production DB is touched. No migration is executed. No runtime evidence export, report, posting, or approval behavior is changed.**

---

## 2. Background

The H1–H9 foundation that makes this contract necessary:

| Task | Deliverable |
|---|---|
| H1 | Reports ledger integrity audit — CRITICAL: reports source from `journal_drafts` JSONB; no immutable ledger; `simulated_success` treated as truth |
| H2 | Posted journal entries schema contract — defined `journal_entry_headers` + `journal_entry_lines` with `evidence_bundle_id`, `posting_log_id`, `source_draft_id` fields |
| H3 | Safe migration plan — defined constraint requirements, rollout sequence |
| H4 | SQL migration file `011_posted_journal_entries_schema.sql` created but **not executed** |
| H5 | Posting service ledger write contract — defined when and how immutable ledger entries are written after real ERP connector posting |
| H6 | Posting service ledger write mock tests — 59 tests encoding future write rules |
| H7 | Reports posted-ledger read contract — defined how official reports must read from `journal_entry_headers` + `journal_entry_lines` |
| H8 | Report query mock tests — 89 tests for future query rules |
| H9 | Reversal / correction contract — defined append-only reversal and correction model |
| H10 (this task) | Evidence / audit export linkage contract — defines how `evidence_bundle_id` links to posted entries and how audit export packages must work |

Until H15 and H16 are implemented, no runtime evidence export occurs through this contract. H10 prepares the behavioral specification so H15 can be mock-tested safely.

---

## 3. Background — Existing Evidence Infrastructure

The following evidence-related modules exist in the codebase and are **not modified by this task**:

- `evidence_bundle_service.py` — manages evidence bundle creation and retrieval
- `evidence_bundle_repository.py` — data access layer for evidence bundles

These modules are referenced by this contract as the target of future linkage. Their interfaces, behavior, and data are not changed here.

---

## 4. Evidence Linkage Rule

The following linkage rules apply to all immutable ledger entries in `journal_entry_headers`:

1. **`evidence_bundle_id`** — must be set when an evidence bundle exists for the posted entry. Links the ledger entry to its supporting evidence package. Nullable only when the source type explicitly has no evidence (e.g., opening balance entries, internal system adjustments). When nullable, the absence must be explicit — not silent.

2. **`posting_log_id`** — must be set for every entry that resulted from a real ERP connector execution. Links the ledger entry to the connector execution log, including connector response metadata (sanitized). Never set for entries that did not go through a real connector.

3. **`source_draft_id`** — must be set for every entry that originated from a `journal_drafts` row. Links the ledger entry back to the draft that was approved and posted. Nullable only for system-generated entries with no draft precursor.

4. **Reversal/correction entries** — must preserve the `evidence_bundle_id` from the original entry where relevant, and must reference the original entry's `evidence_bundle_id` in their own evidence chain. A new evidence bundle may be created for the reversal/correction event itself.

5. **All links must be tenant-scoped** — `evidence_bundle_id`, `posting_log_id`, and `source_draft_id` must all belong to the same `tenant_id` as the ledger entry. Cross-tenant links are forbidden.

6. **Missing evidence is allowed only when source type has no evidence** — and this absence must be recorded explicitly in the export warnings/limitations section. A null `evidence_bundle_id` with no documented reason is a contract violation.

---

## 5. Audit Chain Model

Every official accounting event must be traceable through the following chain:

```
[1] Input source (document upload / bank transaction / API event / payroll run)
    │
    ▼
[2] OCR / parser extraction (if document-based)
    │  — source_hash, extraction metadata, confidence scores
    ▼
[3] AI classification
    │  — transaction category, account codes, amounts, confidence, reasoning
    ▼
[4] Journal draft creation
    │  — journal_drafts row, source_draft_id
    ▼
[5] Approval / rejection / correction
    │  — approval events, approver actor, timestamp, CFO dual-approval if applicable
    ▼
[6] ERP connector execution
    │  — posting_log row, connector response (sanitized), posting_log_id
    ▼
[7] Immutable ledger entry written
    │  — journal_entry_headers + journal_entry_lines, evidence_bundle_id set
    ▼
[8] Evidence bundle assembled
    │  — evidence_bundle_id links all prior chain elements
    ▼
[9] Report / export
    │  — query against journal_entry_headers (status='posted'), links resolved
    ▼
[10] Reversal / correction chain (if applicable)
      — new ledger entries appended; original chain preserved; audit events created
```

Every step in this chain must be reconstructable from the fields on `journal_entry_headers` combined with the linked tables. A complete audit trail means step [1] through step [10] can be traced without gaps.

---

## 6. Required Export Package Contents

A future audit export package for a posted ledger entry must include the following fields:

| Field | Required | Notes |
|---|---|---|
| `tenant_id` | yes | Must match authenticated request tenant |
| `export_id` | yes | Unique UUID for this export package |
| `export_created_at` | yes | Timestamp of export creation |
| `export_created_by` | yes | Actor (user ID / service account) who initiated export |
| `period` or `date_range` | yes | Period covered by the export |
| `report_type` or `entity_type` | yes | e.g., `trial_balance`, `pnl`, `ledger_entry`, `reversal_chain` |
| `journal_entry_header` | yes | Full `journal_entry_headers` row for the entry |
| `journal_entry_lines` | yes | All associated `journal_entry_lines` rows |
| `source_draft_id` | yes (if set) | Link to originating draft |
| `posting_log_id` | yes (if set) | Link to connector execution log |
| `evidence_bundle_id` | yes (if set) | Link to evidence bundle |
| `approval_history` | yes | Ordered list of approval/rejection/correction events |
| `audit_events` | yes | All material audit events for this entry and its chain |
| `source_document_metadata` | yes (if available) | Filename, upload timestamp, document type, source_hash |
| `ai_reasoning_metadata` | yes (if available) | AI classification output, confidence, category, explanation |
| `ocr_parser_metadata` | yes (if available) | OCR/parser extraction results, extraction confidence |
| `connector_response_summary` | yes (if applicable) | Sanitized connector response — no raw secrets |
| `reversal_correction_chain` | yes (if applicable) | Original, reversal, correction entries and their links |
| `export_manifest` | yes | Hash/checksum of export package contents |
| `warnings_and_limitations` | yes | Missing evidence, unavailable sources, data gaps |

No field may contain raw secrets, credentials, API keys, passwords, tokens, or encrypted values. `_strip_unsafe` or equivalent sanitization must be applied before any field is written to the export package.

---

## 7. Evidence Bundle Requirements

An evidence bundle (`evidence_bundle_id`) must satisfy the following requirements:

1. **Safe source metadata is required** — at minimum: source type, source reference, upload or generation timestamp, and `tenant_id`.
2. **OCR/parser outputs may be included** — extraction results, confidence scores, and field mappings from document parsing. Must not include raw credential data embedded in documents.
3. **AI explanation and confidence may be included** — classification reasoning, confidence scores, and the journal line mapping rationale the AI produced.
4. **Approval timeline may be included** — ordered list of approval events, approvers, timestamps, and approval/rejection decisions.
5. **Linked posting log summary may be included** — sanitized connector response confirming ERP write, connector name, connector mode, and `posting_log_id`. No raw API key or connector secret.
6. **Raw secrets are strictly forbidden** — `api_key`, `password`, `token`, `secret`, `encrypted_value`, and any credential field must never appear in the evidence bundle. `_strip_unsafe` from `evidence_bundle_service.py` must be applied before writing any metadata.
7. **Evidence bundle must be tenant-scoped** — `tenant_id` must match the ledger entry's `tenant_id`. Cross-tenant evidence linkage is forbidden.
8. **Evidence bundle must be immutable once linked** — once `evidence_bundle_id` is set on a `journal_entry_headers` row, the evidence bundle referenced by that ID must not be destructively modified. New versions create new bundle IDs.

---

## 8. Audit Event Requirements

Every material event in the accounting lifecycle must produce an audit event. The following events are required:

| Event | Trigger |
|---|---|
| `draft_created` | New journal draft created |
| `draft_approved` | Draft approved by authorized approver |
| `draft_rejected` | Draft rejected |
| `draft_corrected` | Draft corrected before re-approval |
| `posting_attempt_started` | ERP connector dispatch initiated |
| `posting_attempt_finished` | Connector returned success response |
| `posting_attempt_failed` | Connector returned failure response |
| `ledger_write_attempted` | `journal_entry_headers` insert initiated |
| `ledger_write_succeeded` | `journal_entry_headers` insert committed |
| `ledger_write_failed` | `journal_entry_headers` insert failed after connector success |
| `reversal_created` | Reversal entry appended to ledger |
| `correction_created` | Correction entry appended to ledger |
| `export_created` | Audit export package generated |

Each audit event must include:

- `tenant_id` — mandatory, matching the entity's tenant
- `actor` — user ID or service account that triggered the event
- `timestamp` — UTC timestamp of the event
- `entity_type` — e.g., `journal_draft`, `journal_entry_header`, `posting_log`
- `entity_id` — UUID of the affected entity
- `action` — one of the event names above
- `correlation_id` — request correlation ID if available from middleware

Audit events must **never** include raw secrets, passwords, API keys, tokens, or any credential field.

---

## 9. Export Views

The following export views must be supported by the future export implementation:

### 9.1 Single ledger entry evidence package
- One `journal_entry_headers` row and its complete audit chain.
- Includes all linked fields: `source_draft_id`, `posting_log_id`, `evidence_bundle_id`.
- Includes approval history, AI reasoning, connector summary, reversal/correction chain if present.

### 9.2 Period close audit package
- All `journal_entry_headers` rows for a given `tenant_id` and `period`.
- Full audit chain for each entry.
- Aggregate manifest with entry count, total debit, total credit, period hash.
- Excludes `status='voided'`. Excludes reversed originals from net totals (includes in history section).

### 9.3 Report support package
- Evidence backing for a specific report (trial balance, P&L, balance sheet, VAT register, etc.).
- Linked ledger entries, their source chains, and the query parameters used.
- Must be reproducible for the same snapshot parameters.

### 9.4 VAT/tax support package
- All ledger entries with `tax_code IS NOT NULL` or `vat_amount IS NOT NULL` for the period.
- Source document metadata and approval history for each entry.
- Connector confirmation summary.
- Formatted for regulatory/tax authority review.

### 9.5 Reversal/correction chain package
- Original entry, reversal entry, correction entry (where applicable), and all chain links.
- Reasons, approvers, and timestamps for each reversal/correction event.
- Net effect and history view clearly distinguished.

### 9.6 Connector posting proof package
- One or more `posting_log` entries with their associated ledger entries.
- Sanitized connector response confirming ERP write.
- Audit trail from draft to confirmed ledger entry.
- Useful for reconciliation and third-party ERP audit requests.

---

## 10. Tenant Isolation and Permissions

All audit export operations must enforce strict tenant isolation and access control:

1. **Every export must be tenant-scoped** — `tenant_id` from `request.state.tenant_id` (set by tenant middleware from JWT) must be applied to all queries and included in all export packages.
2. **No cross-tenant export** — no export may aggregate data across multiple tenants unless an explicit future consolidation feature is designed and approved.
3. **Export permission required** — the requesting actor must have the required export/audit permission (e.g., `audit:export` or `ledger:export`) before an export package can be generated.
4. **Export must record actor and timestamp** — `export_created_by` and `export_created_at` must be set on every export package.
5. **No silent fallback to default tenant** — no export may fall back to `tenant_id = 'default'` if the authenticated tenant is not set. Missing tenant must fail closed.
6. **No user input for tenant** — tenant must be derived from `request.state.tenant_id` only, never from query parameters or request body fields.

---

## 11. Integrity and Tamper Evidence

Export packages must include integrity markers:

1. **Export manifest must include hashes/checksums** — a hash of the export package contents (e.g., SHA-256 of the serialized export) must be included in every export manifest.
2. **Ledger entry line hashes where available** — `line_hash` values from `journal_entry_lines` should be included to enable tamper detection of individual lines.
3. **`source_hash` should be preserved** — the hash of the original source document or input, where available, must be included in the export to allow verification against the original source.
4. **Export package should be reproducible** — for the same `tenant_id`, `period`, and entity snapshot, re-generating the export should produce the same underlying data (though a new `export_id` and `export_created_at` will be generated).
5. **Warnings and limitations must be explicit** — any missing evidence, unavailable source data, or unresolvable chain link must be labeled in the `warnings_and_limitations` section of the export. Silent omissions are a contract violation.
6. **Export log entry must be created** — generating an export must itself create an audit event (`export_created`) recording the actor, timestamp, export scope, and export ID.

---

## 12. Reversal / Correction Linkage in Exports

Exports that include reversal or correction chains must follow these rules:

1. **Export must show full chain** — the original entry (`status='posted'`), the reversal entry (`status='reversed'`), and the correction entry (`status='correction'`) must all appear in the export chain view.
2. **Chain links must be explicit** — `reversed_by_entry_id` and `correction_of_entry_id` must be resolved and included in the export, not merely as IDs but as fully linked entry summaries.
3. **Net view and history view must be distinguishable** — the export must clearly separate the net official position (excluding reversed originals) from the complete history (full chain). Mixing the two without labels is a contract violation.
4. **No double-counting in net totals** — the report support package and period close package must not include both the reversed original and its reversal in net totals.
5. **Correction and reversal reasons must be included** — the `reversal_reason`, `correction_reason`, and `correction_policy` fields from the reversal/correction headers must appear in the export chain view.
6. **Audit events for reversals/corrections must be included** — the `reversal_created` and `correction_created` audit events, with actor, timestamp, and reason, must be present in the export chain.

---

## 13. Non-Goals for H10

This task explicitly does **not**:

- Change any runtime evidence export behavior.
- Modify `evidence_bundle_service.py`.
- Modify `evidence_bundle_repository.py`.
- Modify `posting_service.py`.
- Modify `approval_service.py`.
- Modify `ledger_service.py`.
- Modify `financial_statements_service.py`.
- Modify `routes_reports.py` or `routes_posting.py` or any route handler.
- Execute any SQL.
- Create any new SQL migration file.
- Execute any migration.
- Access any database (production or otherwise).
- Touch the production database.
- Change any connector behavior.
- Activate Balance.ge.
- Change any credentials or secrets.
- Change any production infrastructure or deployment configuration.
- Start H11, H12, H13, H14, H15, or H16 work.

This task produces two files only:
- `docs/evidence-audit-export-linkage-contract.md` (this document)
- `tests/unit/test_evidence_audit_export_linkage_contract.py`

---

## 14. Future Task Sequence

| Task | Description |
|---|---|
| **H10** (this task) | Evidence / audit export linkage contract / tests only — no runtime change |
| **H11** | Controlled local/test migration execution plan — if explicitly approved, run `011_posted_journal_entries_schema.sql` against a local or test DB only; never production without separate approval |
| **H12** | Runtime report migration plan — migrate reports to read from posted ledger tables after H11 migration is confirmed |
| **H13** | Reversal/correction implementation tests with mocks — mock-test the future `_write_reversal_entry` and `_write_correction_entry` functions |
| **H14** | Reversal/correction runtime implementation — only after H13 tests pass and explicit stakeholder approval |
| **H15** | Evidence/audit export implementation tests with mocks — mock-test the future export package builder functions |
| **H16** | Evidence/audit export runtime implementation — only after H15 tests pass and explicit stakeholder approval |

Each task follows the same protocol: branch → docs/tests → PR → merge → deploy → live verification → confirmed before starting the next task.

---

*Bridge Hub — Task 11C-H10. Contract only. No runtime changes. No SQL. No migration execution. No production DB touch. Balance.ge remains inactive.*
