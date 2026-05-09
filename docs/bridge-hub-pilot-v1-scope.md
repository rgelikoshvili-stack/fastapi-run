# Bridge Hub Pilot V1 Scope

## Pilot Target User

Pilot V1 is for a Georgian small or mid-sized company, or its outsourced accounting team, that already uses Balance.ge, ORIS, 1C, or manual accounting workflows and wants Bridge Hub as an AI assistant and financial controller layer.

The pilot user should have:

- A real accountant or finance owner who remains final reviewer.
- Monthly supplier invoices and bank statements.
- A need for document-to-draft automation.
- A willingness to test Balance.ge dry-run or export flows before live posting.

## Pilot Workflow

1. User signs in to Bridge Hub.
2. User imports an invoice from email or uploads a PDF/image/Excel document.
3. Bridge Hub extracts fields, links evidence, detects duplicates, and recognizes supplier/customer.
4. AI proposes accounting treatment, VAT/tax flags, and journal draft lines.
5. User imports bank statement CSV/XLSX/XML or runs bank sync in demo/live-supported mode.
6. Bridge Hub proposes bank matching and reconciliation suggestions.
7. User reviews evidence, edits if needed, and approves or rejects the draft.
8. Bridge Hub prepares Balance.ge dry-run or payload preview.
9. User explicitly approves connector execution or uses manual export.
10. Bridge Hub stores posting logs, audit trail, and monthly summary.

## In-Scope Features

- Email/PDF invoice import.
- Manual document upload.
- OCR and structured extraction.
- Supplier/customer recognition.
- Duplicate detection.
- AI accounting draft proposal.
- VAT/tax risk flags.
- Bank statement import.
- Bank transaction classification and suggested matching.
- Approval queue.
- Draft edit, approve, reject, and correction.
- Balance.ge dry run and payload preview.
- Controlled export/posting after human approval.
- Audit log and posting logs.
- Monthly pilot summary.

## Out-of-Scope Features

- AI direct posting without approval.
- Direct RS.ge submission.
- Full ERP replacement.
- ORIS live posting.
- 1C live posting.
- Multi-connector rollout.
- Fully automated payroll filing.
- Fully automated period close.
- Inventory costing automation beyond current reviewed flows.
- Subscription billing automation unless Phase 7 is complete.

## Required Credentials

- Bridge Hub tenant admin credentials.
- Email app password or OAuth credentials if email ingestion is tested.
- Balance.ge pilot API key, company ID, and API base if dry-run/live pilot is approved.
- Bank test statement files or bank API credentials if live bank sync is tested.
- No RS.ge password should be used for direct submission in Pilot V1.

Credential handling must use masked UI display and must not expose plaintext secrets in logs, API responses, screenshots, or exports.

## Required Test Data

- 20 to 50 supplier invoices.
- 20 to 50 customer invoices if sales workflow is included.
- At least 2 monthly bank statement files.
- Known duplicate invoices.
- Known VAT and non-VAT examples.
- Known foreign-currency examples if FX is in scope.
- Expected chart-of-accounts mappings reviewed by an accountant.
- Balance.ge sandbox or test company where possible.

## Acceptance Criteria

- 0 unauthorized postings.
- 100% connector execution requires human approval.
- 90% invoice extraction accuracy on pilot set.
- 80% bank classification accuracy on pilot set.
- Duplicate invoices are flagged before approval.
- Every approved draft has evidence link, AI reason, confidence, and reviewer identity.
- Balance.ge dry-run or preview succeeds for approved pilot payload.
- Posting logs are created for connector attempts.
- Monthly summary can be generated from approved/posted data.
- No failed regression tests before pilot release.

## Go / No-Go Checklist

Go only if:

- Protected endpoint checks pass.
- Credential storage and masking are accepted for pilot risk level.
- Runtime DDL status and schema risks are documented.
- Balance.ge connector mode is explicit: demo, dry-run, or live.
- Pilot accountant validates VAT/payroll/account mapping assumptions.
- Backup and rollback plan exists.
- Manual fallback is documented.

No-go if:

- Any connector can post without approval.
- Secrets appear in logs or plain API responses.
- Trial/subscription enforcement is required for sale but not implemented.
- Balance.ge is still demo mode while the pilot promises live posting.
- Accountant review of tax rules has not happened.

## Rollback Plan

- Treat Bridge Hub as a draft/preparation layer first.
- If connector execution fails, keep draft approved but mark posting attempt failed in posting logs.
- Export payload manually for review.
- Revert to manual Balance.ge, ORIS, or 1C entry if needed.
- Never delete source evidence or approved draft history during rollback.
- Keep failed connector responses for audit and support analysis.

## Manual Fallback Workflow

1. User uploads document or bank statement.
2. Bridge Hub extracts and proposes draft.
3. Accountant reviews and approves.
4. Bridge Hub exports journal payload or readable posting preview.
5. Accountant manually enters approved journal into Balance.ge, ORIS, or 1C.
6. Accountant marks the Bridge Hub draft/posting log with manual execution reference.

Manual fallback is a valid Pilot V1 success path. The pilot goal is controlled evidence-based draft generation, not full automation.
