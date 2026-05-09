# Bridge Hub AI Chief Accountant Master Plan

## Product Vision

Bridge Hub should not be positioned as just another ERP. The target product is an AI Chief Accountant and Financial Controller layer that sits above existing execution systems and keeps the human accountant in control.

Bridge Hub should connect Email, Bank, RS.ge, Balance.ge, ORIS, 1C, Documents, and Human Approval into one controlled workflow:

1. Read documents, emails, bank files, RS.ge exports, ERP data, and user chat/manual actions.
2. Convert them into canonical accounting objects.
3. Let AI classify, explain, risk-score, and propose accounting actions.
4. Require preview, edit, approve, reject, CFO approval, and audit trail before execution.
5. Execute only through approved connector, export, or manual-upload flows.

The central product invariant is approval-first execution: AI can suggest and prepare, but it must not post, submit, or synchronize live accounting outcomes without human approval.

## Current State Summary

Task 11A found that Bridge Hub already has a strong backend and accounting-control foundation:

- FastAPI backend with modular route registration.
- More than 100 routes; Task 11A statically detected 439 route handlers across 87 route files.
- 454 passing tests, 2 skipped, 0 failed in the broader Task 11A context.
- 23 primary UI pages in the product surface, with 35 static HTML pages detected overall.
- Approval-first workflow, posting preview, posting logs, and journal draft lifecycle.
- AI, OCR, document, email, bank, inventory, payroll, trade, and reporting foundations.
- Inventory, payroll, trade partner, and outgoing invoice additive migration slices.
- Destructive users migration script quarantined.
- Core schema hardening contract exists from Task 10E-B.

The main gaps are not feature breadth. They are production trust:

- ERP connector layer is incomplete.
- Balance.ge is still demo mode when `BALANCE_API_KEY` is absent.
- ORIS is a stub.
- 1C is demo/global-env based rather than tenant connector ready.
- Subscription enforcement is missing even though `trial_ends_at` exists.
- Rate limiting is in-memory when `REDIS_URL` is not set.
- Credential encryption and masked reads are not fully implemented.
- Runtime DDL shims still exist.
- 14 tables still have no migration coverage in the Task 11A context.
- Inventory costing schema exists, but full costing business logic is incomplete.
- Document/OCR pipeline works, but multi-page PDF handling is not production complete.
- Bank import exists, but automatic matching remains incomplete for production use.

Overall assessment from Task 11A: architecture 8.5/10, production readiness 4.5/10, total readiness 6.5/10.

## Target Architecture

### Input Layer

- Email inbox and email attachments.
- PDF, image, Excel, XML, and other uploaded documents.
- Bank statements and bank sync payloads.
- RS.ge exports, declarations, and manual-upload files.
- Balance.ge, ORIS, 1C, and other ERP source data.
- Chat commands and manual user actions.

### Ingestion Layer

- OCR extraction.
- File parsers.
- Email collector.
- Bank parser.
- Document classifier.
- Duplicate detector.
- Counterparty resolver.
- Evidence collector.

### Canonical Layer

Bridge Hub should normalize input into stable internal objects before AI or connector execution:

- `CanonicalDocument`
- `CanonicalInvoice`
- `CanonicalBankTransaction`
- `CanonicalContract`
- `CanonicalJournalDraft`
- `CanonicalActionPlan`

These objects should carry tenant ID, source evidence, extraction metadata, confidence, idempotency keys, and audit metadata.

### AI Reasoning Layer

- Operations AI: reads documents, bank lines, and ERP data; proposes accounting actions.
- User AI: answers finance questions and explains draft decisions.
- Teacher/QA AI: reviews AI output against accounting policy, tax rules, duplicate risk, and prior corrections.

AI output must include evidence, reasoning, confidence, risk flags, and proposed journal lines. It must not execute.

### Control Layer

- Validation engine.
- Risk engine.
- RBAC.
- Tenant isolation.
- Idempotency.
- Period lock.
- Approval state machine.
- Duplicate detection.
- Connector safety policy.

This layer decides whether a proposal is valid enough to enter human review. It should block unsafe actions before they reach connector execution.

### Human Approval Layer

- Preview.
- Edit.
- Approve.
- Reject.
- Correct.
- Assign/review.
- CFO approval.
- Batch approval with per-item result.
- Reviewer notes and evidence panel.

Human approval is the final authority before any accounting-impacting action.

### Execution Layer

- Balance.ge connector.
- ORIS connector.
- 1C connector.
- RS.ge export/manual upload flow.
- Email bridge.
- Bank connector.
- File export.

Execution must support preview, dry run, idempotency, error mapping, posting logs, and rollback/no-op strategy where possible.

### Audit / Reporting / Learning Layer

- Audit trail.
- Entity audit events.
- Posting logs.
- Reports and ledgers.
- Close cockpit.
- Pattern learning.
- Correction feedback.
- Evidence package export.

Learning should improve future suggestions, not bypass approval.

## AI Chief Accountant Capabilities

Target capabilities:

- Explainable accounting decision: every draft should show why the account, VAT treatment, counterparty, amount, and date were selected.
- Georgian Tax Guardian: VAT, payroll, withholding, CIT, dividend, RS.ge readiness, and accountant-review flags.
- Document Inbox: email/PDF/image/Excel intake, evidence extraction, duplicate detection, and draft creation.
- Bank Brain: bank line import, duplicate detection, invoice matching, classification, and reconciliation suggestions.
- Approval Cockpit: all accounting-impacting decisions in one queue with evidence, risk, and reviewer controls.
- Monthly Close Cockpit: close checklist, missing documents, bank reconciliation, VAT review, payroll review, lock readiness.
- Multi-ERP Brain: Balance.ge first, then ORIS and 1C through a standard connector adapter.
- Connector Preview/Dry-run/Execute: every connector action must be previewable and auditable before execution.
- Evidence-based accounting: files, extracted fields, source URLs, email metadata, bank line, and AI reasoning must travel with the draft.
- Human correction and pattern learning: corrections should update patterns and risk models without creating autopost authority.

## Phase Roadmap

### Phase 1 - Trust Foundation / Security Hardening

Goals:

- Enforce `trial_ends_at`.
- Configure `REDIS_URL` and production rate limiting.
- Protect metrics and sensitive diagnostics.
- Implement credential encryption and masked reads.
- Finish 10E schema contracts.
- Continue runtime DDL cutover plan.
- Create DB backup/PITR checklist.
- Define static files GCS/CDN plan.

Success criteria:

- No plaintext secret exposure in normal API responses.
- Credential tables have encryption/rotation/audit strategy.
- Runtime DDL removal is gated by migrations and tests.
- Subscription/trial enforcement blocks expired tenants.
- Protected endpoints remain protected.

### Phase 2 - AI Document + Bank Brain

Goals:

- Multi-page PDF OCR.
- Document evidence linking.
- Invoice duplicate detection.
- Supplier/customer recognition.
- Bank statement matching engine.
- Document-to-journal draft workflow.
- Risk/confidence scoring.

Success criteria:

- 90% invoice extraction accuracy on pilot set.
- 80% bank transaction classification accuracy on pilot set.
- Every AI draft has evidence and reviewer controls.

### Phase 3 - Balance.ge First Connector Pilot

Goals:

- Configure `BALANCE_API_KEY`.
- Store per-tenant credentials securely.
- Add connector health/status.
- Support dry run.
- Show payload preview.
- Require approval token or approved draft.
- Execute controlled post/export.
- Store posting logs.
- Map connector errors.
- Define rollback/no-op strategy.

Success criteria:

- Balance.ge dry run succeeds for pilot tenant.
- Live execution is impossible without approved preview.
- Posting logs contain payload, response, status, and idempotency reference.

### Phase 4 - Approval Cockpit 2.0

Goals:

- Risk badges.
- Evidence panel.
- AI explanation panel.
- Journal draft editing.
- Batch approval.
- CFO workflow.
- Audit timeline.
- Reviewer notes.

Success criteria:

- Reviewer can approve or reject from one screen with full evidence.
- Batch approval produces per-item results.
- CFO path is visible and auditable.

### Phase 5 - Monthly Close Cockpit

Goals:

- Close checklist.
- Bank reconciliation status.
- AP/AR aging review.
- VAT review.
- Payroll review.
- Missing document tracker.
- Period lock readiness.
- Close score.
- Close audit export.

Success criteria:

- Pilot tenant can run a monthly close checklist before locking a period.
- Reports use posted ledger truth where appropriate.

### Phase 6 - Multi-ERP Expansion

Goals:

- ORIS connector.
- 1C per-tenant connector.
- RS.ge automation/manual workflow.
- Bank API connectors.
- Connector adapter standard.

Success criteria:

- Each connector supports status, preview, dry run where possible, execute, error mapping, idempotency, and audit log.

### Phase 7 - Commercial SaaS

Goals:

- Subscription enforcement.
- `subscription_plans`.
- `tenant_subscriptions`.
- Billing integration.
- Plan limits.
- Onboarding wizard.
- Support/admin tools.
- Usage monitoring.

Success criteria:

- A tenant can be onboarded, limited by plan, monitored, supported, and suspended safely.

## First Pilot V1 Scope

The first sellable pilot should be narrow and trust-oriented:

- Email/PDF invoice import.
- Bank statement import.
- OCR/extraction.
- AI accounting draft.
- VAT/tax risk flags.
- Human approval.
- Balance.ge dry run and payload preview.
- Controlled posting/export only after approval.
- Audit log.
- Monthly summary.

Pilot V1 should prove that Bridge Hub can safely read evidence, propose draft accounting, and hand approved entries to Balance.ge without replacing the accountant or the ERP.

## What Not To Build Yet

- Do not replace Balance.ge, ORIS, or 1C as a full ERP yet.
- Do not allow AI direct posting without approval.
- Do not start many connectors at once.
- Do not sell before subscription enforcement and credential hardening.
- Do not remove runtime DDL before migrations and tests are complete.
- Do not start Task 10E migrations before contracts are finalized.
- Do not automate RS.ge submission without explicit preview, review, and approval.
- Do not treat VAT, payroll, or tax calculations as filing-grade before accountant validation.

## Success Metrics

- 0 unauthorized postings.
- 100% approval-before-execute.
- 95% protected endpoint coverage.
- 90% invoice extraction accuracy in pilot set.
- 80% bank transaction classification accuracy.
- 0 plaintext secret exposure.
- Balance.ge dry_run success.
- First pilot tenant onboarded.
- Monthly close checklist generated.
- 0 failed regression tests.

## Risks and Mitigations

- Connector demo mode: mitigate by piloting Balance.ge first with dry run, payload preview, and sandbox/live separation.
- Subscription enforcement missing: implement trial and plan enforcement before selling.
- Credentials plaintext risk: implement encryption-at-rest, masked reads, rotation metadata, and audit logging.
- Runtime DDL: continue additive migration slices and cutover tests before removing shims.
- Static filesystem: define GCS/CDN strategy for static files and uploaded evidence.
- Redis not set: configure Redis-backed rate limiting before public pilot.
- Multi-page OCR gap: prioritize multi-page PDF splitting, page evidence, and extracted-field traceability.
- Inventory costing incomplete: keep inventory costing under accountant review and avoid claiming full costing automation.
- RS.ge no public API uncertainty: start with export/manual-upload workflow and no direct submission.
- Accounting/tax validation risk: require Georgian accountant review for VAT, payroll, withholding, CIT, and reverse-charge rules.
