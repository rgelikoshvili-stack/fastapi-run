# Bridge Hub Target Architecture

## Text Architecture Diagram

```text
Inputs
  Email | Documents | Bank | RS.ge | ERP data | Chat/manual action
    |
Ingestion
  OCR | parsers | email collector | bank parser | classifier | duplicate detection
    |
Canonical Objects
  CanonicalDocument
  CanonicalInvoice
  CanonicalBankTransaction
  CanonicalContract
  CanonicalJournalDraft
  CanonicalActionPlan
    |
AI Reasoning
  Operations AI | User AI | Teacher/QA AI
    |
Control
  validation | risk | RBAC | tenant isolation | idempotency | period lock
    |
Human Approval
  preview | edit | approve | reject | CFO approval | reviewer notes
    |
Execution
  Balance.ge | ORIS | 1C | RS.ge export/manual upload | Email bridge | Bank connector
    |
Audit, Reporting, Learning
  audit trail | posting logs | reports | close cockpit | pattern learning
```

## Main Modules

- Auth and tenant management.
- Credential and secret vault.
- Document inbox.
- Email collector.
- OCR and extraction.
- Bank import and reconciliation.
- Accounting draft engine.
- Approval cockpit.
- Posting and connector execution.
- ERP modules: inventory, payroll, trade.
- Reporting workbench and monthly close cockpit.
- AI chat, decision engine, QA, and learning.
- Admin, billing, subscription, usage, and support tools.

## Canonical Object Flow

Canonical objects are the contract between inputs, AI reasoning, approval, and execution.

1. Raw input is stored with tenant, source, and evidence metadata.
2. Ingestion extracts fields and normalizes them.
3. AI proposes a canonical action plan.
4. Control layer validates the action plan.
5. A canonical journal draft is created for human review.
6. Approval creates an approved accounting instruction.
7. Connector adapters receive only approved payloads.
8. Posting logs and audit records store outcomes.

Required object fields:

- `tenant_id`
- source reference
- evidence references
- normalized counterparty
- amounts and currency
- tax/VAT metadata
- proposed journal lines
- confidence score
- risk flags
- idempotency key
- audit metadata

## AI Role Flow

Operations AI:

- Extracts and classifies documents.
- Matches bank lines.
- Suggests journal entries.
- Flags tax and duplicate risks.

User AI:

- Answers finance questions.
- Explains drafts and reports.
- Helps users navigate workflows.

Teacher/QA AI:

- Reviews AI decisions.
- Compares against policies and history.
- Learns from corrections.
- Raises review-required flags.

AI must not directly post, submit, or synchronize accounting outcomes. AI output is a proposal with evidence.

## Approval-First Flow

```text
AI proposal
  -> validation and risk checks
  -> journal draft
  -> preview and evidence review
  -> edit or correction
  -> approve/reject
  -> optional CFO approval
  -> connector payload preview
  -> explicit execute/export
  -> posting log and audit trail
```

Invariant rules:

- No direct posting from AI.
- No RS.ge submission without approval.
- No Balance.ge, ORIS, or 1C execution without preview and approval.
- No posting in locked periods.
- Idempotency must protect repeated execution.
- Every execution attempt must be auditable.

## Connector Adapter Standard

Every connector should implement:

- `status`
- `health`
- `validate_credentials`
- `preview_payload`
- `dry_run`
- `execute`
- `get_result`
- `map_error`
- `idempotency_key`
- `audit_payload`

Connector modes:

- `demo`
- `sandbox`
- `dry_run`
- `live`

Connector execution requirements:

- Tenant-scoped credentials.
- Encrypted secrets.
- Masked reads.
- No plaintext logging.
- Explicit approval token or approved draft reference.
- Posting log for every attempt.
- Retry policy with idempotency.

## Audit / Logging Standard

Every accounting-impacting object should have:

- who created it
- when it was created
- source evidence
- AI reasoning
- reviewer decision
- status transitions
- connector payload preview
- connector result
- correction history
- tenant ID

Audit records should support accountant review, management review, and external audit evidence packages.

## Security Boundaries

- Tenant data boundary: every tenant-owned table and query must be tenant-scoped.
- Credential boundary: secrets must be encrypted at rest and masked on read.
- Approval boundary: AI and connectors cannot bypass approval.
- Posting boundary: only approved drafts can execute.
- Period boundary: locked periods block posting.
- Admin boundary: billing, tenant, credential, and security settings require elevated permissions.
- Public boundary: unauthenticated endpoints must be limited to health/version/login/reset/OAuth callbacks and explicitly intended inbound hooks.

## Production Readiness Gates

Before real customer accounting:

- Credential vault implemented.
- Subscription enforcement active.
- Runtime DDL cutover proven by migrations/tests.
- Balance.ge pilot connector tested in dry-run and approved live mode.
- Accountant validates Georgian VAT, payroll, and tax rules.
- Evidence package exists for every AI draft.
- Rate limiting and metrics protection are production configured.
- Backup/PITR and rollback plan are verified.
