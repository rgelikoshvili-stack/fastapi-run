# Bridge Hub - H30 Accountant Review Report Contract

## 1. Title

Bridge Hub - H30 Accountant Review Report Contract

Task: 11C-H30 - Accountant Review Report Contract / Snapshot Comparison Result UX Plan
Branch: `codex/accountant-review-report-contract`
Starting SHA: `15282c09d2a9b510af2591790a6840d3b359ac8e` (H29 live verified)

## 2. Purpose

H30 defines the accountant-facing review report contract for normalized snapshot comparison results. It translates H29 comparison output into a safe, auditable, human-reviewable report that an accountant or financial controller can use before any future report-path switch.

H30 is docs/tests only.
H30 does not create DB.
H30 does not connect to DB.
H30 does not execute SQL.
H30 does not run migrations.
H30 does not load fixtures into DB.
H30 does not call runtime report APIs.
H30 does not modify runtime report behavior.
H30 does not implement UI/static.
H30 does not implement app/runtime helpers.
H30 does not enable feature flags.
H30 does not activate Balance.ge.

All examples are synthetic and local. No production data, customer data, credential, or private personal data is used.

## 3. H29 Context

H29 defined comparator input/output, mismatch item shape, severity and mismatch codes, row and total comparison rules, and accountant review output at a high level.

H30 expands that accountant-facing review contract. It defines the JSON review report, human-readable markdown/table layout, pass/fail/blocking decisions, sign-off fields, audit metadata, evidence/drilldown presentation, affected entity grouping, and recommended action categories.

## 4. Accountant Review Report JSON Contract

The future review report must use this top-level schema:

```json
{
  "review_id": "review_synthetic_001",
  "comparison_name": "legacy_vs_posted_ledger_all_reports",
  "generated_at": "2026-05-16T00:00:00Z",
  "generated_by": "Bridge Hub",
  "environment": "nonproduction|staging|production-readonly",
  "tenant_id": "tenant_alpha",
  "period": {"from": "2026-01-01", "to": "2026-01-31"},
  "currency": "GEL",
  "overall_status": "passed|passed_with_rounding|blocked|failed",
  "production_switch_allowed": false,
  "summary": {},
  "report_results": [],
  "mismatch_groups": {},
  "affected_entities": {},
  "evidence_links": [],
  "recommended_actions": [],
  "sign_off": {},
  "audit": {}
}
```

Required top-level fields:
- `review_id`
- `comparison_name`
- `generated_at`
- `generated_by`
- `environment`
- `tenant_id`
- `period`
- `currency`
- `overall_status`
- `production_switch_allowed`
- `summary`
- `report_results`
- `mismatch_groups`
- `affected_entities`
- `evidence_links`
- `recommended_actions`
- `sign_off`
- `audit`

## 5. Overall Status Rules

Overall status rules:
- `passed`: zero mismatches.
- `passed_with_rounding`: only `rounding_only` mismatches exist and accountant sign-off may accept them.
- `blocked`: any critical mismatch or hard-fail rule violation exists.
- `failed`: high mismatches or unresolved material differences exist.
- `production_switch_allowed` is true only when status is `passed`, or when `passed_with_rounding` is explicitly approved and all gates pass.

Decision priority:
1. Critical mismatch or hard-fail rule -> `blocked`.
2. High mismatch -> `failed`.
3. Medium mismatch -> `failed` until reviewed.
4. Only low mismatch -> `failed` unless explicitly accepted by a later policy.
5. Only rounding-only mismatch -> `passed_with_rounding`.
6. No mismatch -> `passed`.

## 6. Summary Section

The `summary` section must include:
- `total_reports_compared`
- `reports_passed`
- `reports_failed`
- `reports_blocked`
- `total_mismatches`
- `critical_count`
- `high_count`
- `medium_count`
- `low_count`
- `rounding_only_count`
- `affected_accounts_count`
- `affected_counterparties_count`
- `affected_journal_entries_count`
- `missing_evidence_count`
- `tenant_leakage_detected`
- `status_policy_errors`
- `correction_reversal_errors`

Summary counters must be deterministic and derived from report results and mismatch items. Boolean flags must default to false and become true only when a relevant mismatch code is present.

## 7. Report Result Shape

Each item in `report_results` must include:
- `report_name`
- `status`
- `comparison_result`
- `total_mismatches`
- `severity_counts`
- `totals_summary`
- `row_count_summary`
- `key_mismatches`
- `affected_accounts`
- `affected_counterparties`
- `affected_journal_entries`
- `evidence_links`
- `recommended_actions`
- `accountant_notes`
- `sign_off_required`

Report status follows the same decision priority as overall status, scoped to the single report.

## 8. Mismatch Grouping Rules

Mismatch grouping rules:
- group by severity
- group by mismatch code
- group by report name
- group by `account_code`
- group by `counterparty_id`
- group by `journal_entry_id`
- group by `evidence_bundle_id`
- group by `source_draft_id`
- group by `posting_log_id`
- group by correction/reversal chain

Groups must preserve the original mismatch code, severity, report name, row key, field, and safe evidence identifiers. Grouping must not expose raw secrets or private data.

## 9. Affected Entities Section

The `affected_entities` section must include:
- `accounts`
- `counterparties`
- `journal_entries`
- `ledger_lines`
- `source_drafts`
- `posting_logs`
- `evidence_bundles`
- `reports`

Each item should include:
- `id`
- `count`
- `max_severity`
- `related_mismatch_codes`
- `related_reports`

The section exists so an accountant can quickly see which accounts, counterparties, journal entries, ledger lines, source drafts, posting logs, evidence bundles, and reports need review.

## 10. Evidence and Drilldown Presentation

Evidence and drilldown fields must be shown as safe identifiers only:
- `evidence_bundle_id` display
- `posting_log_id` display
- `source_draft_id` display
- `journal_entry_id` display
- `ledger_line_id` display
- `correction_of_id` display
- `reversal_of_id` display

Missing evidence is high or critical depending on report and gate context. Missing required evidence or drilldown blocks production switch until resolved.

Evidence display must not include raw secret values, connector credentials, private documents, card numbers, bank account numbers, raw tax identifiers, or private contact details.

## 11. Recommended Action Categories

Recommended action categories:
- `ACCEPT_ROUNDING_DIFFERENCE`
- `REVIEW_ACCOUNT_MAPPING`
- `REVIEW_STATUS_POLICY`
- `REVIEW_TENANT_FILTER`
- `REVIEW_CORRECTION_REVERSAL_CHAIN`
- `REVIEW_EVIDENCE_LINKS`
- `REVIEW_COUNTERPARTY_MAPPING`
- `REVIEW_CASHFLOW_CLASSIFICATION`
- `REVIEW_VAT_CLASSIFICATION`
- `REVIEW_PAYROLL_CLASSIFICATION`
- `BLOCK_PRODUCTION_SWITCH`
- `REQUEST_ENGINEERING_FIX`
- `REQUEST_ACCOUNTANT_SIGN_OFF`

Action mapping:
- Tenant leakage -> `REVIEW_TENANT_FILTER` and `BLOCK_PRODUCTION_SWITCH`.
- Status policy mismatch -> `REVIEW_STATUS_POLICY` and `BLOCK_PRODUCTION_SWITCH`.
- Correction/reversal mismatch -> `REVIEW_CORRECTION_REVERSAL_CHAIN` and `BLOCK_PRODUCTION_SWITCH`.
- Evidence or drilldown missing -> `REVIEW_EVIDENCE_LINKS` and `REQUEST_ENGINEERING_FIX`.
- Rounding-only difference -> `ACCEPT_ROUNDING_DIFFERENCE` and `REQUEST_ACCOUNTANT_SIGN_OFF`.
- Report total or row value mismatch -> `REQUEST_ENGINEERING_FIX`.

## 12. Accountant Sign-Off Contract

The `sign_off` section must include:
- required boolean fields
- `signer_name` or `signer_id` placeholder
- `signed_at`
- `sign_off_scope`
- `accepted_rounding_differences`
- `unresolved_mismatches`
- `production_switch_recommendation`
- `notes`

Required boolean fields:
- `accountant_reviewed`
- `rounding_differences_accepted`
- `critical_mismatches_absent`
- `high_mismatches_resolved`
- `evidence_reviewed`
- `production_switch_recommended`

Rules:
- Critical mismatches cannot be signed off for production switch.
- High mismatches require engineering/accounting resolution before production.
- Rounding-only differences may be accepted with accountant sign-off.
- All sign-off must be audit logged in future implementation.

## 13. Audit Metadata

The `audit` section must include:
- `review_id`
- `comparison_run_id`
- `source_snapshot_ids`
- `normalized_snapshot_ids`
- `comparator_version`
- `fixture_version`
- `git_sha`
- `environment`
- `generated_at`
- `generated_by`
- `approval_gate_state`
- `production_switch_allowed`
- `feature_flag_state`
- `rollback_plan_reference`

Audit metadata must be sufficient to prove which snapshots, comparator contract, fixture version, git SHA, environment, and gate state produced the accountant review.

## 14. Accountant-Readable Markdown/Table Layout

The human-readable layout must include:
- Executive summary
- Gate status
- Report-by-report status table
- Critical/high mismatch table
- Rounding-only section
- Affected accounts table
- Affected counterparties table
- Evidence/drilldown table
- Recommended actions
- Sign-off section
- Audit footer

The report should be readable without engineering context. It must use accountant-facing terms and stable identifiers, not raw internal stack traces or secrets.

## 15. Production Switch Gate Rules

Production switch gate rules:
- never allow production switch with critical mismatches
- never allow production switch with tenant leakage
- never allow production switch with status policy mismatch
- never allow production switch with missing required evidence/drilldown
- high mismatches block until resolved
- rounding-only may proceed only with sign-off and documented tolerance
- feature flag must remain OFF until gates G1-G10 pass

Gate checklist:
- G1: all 11 reports compared.
- G2: no critical mismatches.
- G3: no tenant leakage.
- G4: no status policy mismatch.
- G5: no missing required evidence/drilldown.
- G6: no unresolved high mismatches.
- G7: no unresolved correction/reversal mismatch.
- G8: rounding-only differences are signed off.
- G9: rollback plan reference exists.
- G10: approval gate state is approved.

## 16. Sample Review Outcomes

Clean pass:
- overall_status: `passed`
- production_switch_allowed: true
- no mismatches

Passed with rounding:
- overall_status: `passed_with_rounding`
- only `ROUNDING_ONLY_DIFFERENCE`
- production switch allowed only after accountant sign-off

Blocked by tenant leakage:
- overall_status: `blocked`
- mismatch code: `TENANT_LEAKAGE`
- recommended action: `BLOCK_PRODUCTION_SWITCH`

Failed by report total mismatch:
- overall_status: `failed`
- mismatch code: `REPORT_TOTAL_MISMATCH`
- recommended action: `REQUEST_ENGINEERING_FIX`

Blocked by missing evidence:
- overall_status: `blocked` when evidence is required by gate context
- mismatch code: `EVIDENCE_LINK_MISSING`
- recommended action: `REVIEW_EVIDENCE_LINKS`

Blocked by correction/reversal mismatch:
- overall_status: `blocked`
- mismatch code: `CORRECTION_REVERSAL_MISMATCH`
- recommended action: `REVIEW_CORRECTION_REVERSAL_CHAIN`

## 17. Future UI/UX Plan

Design only, no UI implementation:
- dashboard card summary
- filter by severity/report/account/counterparty
- click-through to evidence/drilldown
- export JSON/CSV/PDF in future
- sign-off workflow in future
- audit trail in future

Future screen behavior should make the first view an accountant review surface, not a marketing page. Filters should help accountants move from blocking mismatch to source evidence quickly.

## 18. Safety Rules

- No DB in H30.
- No runtime API calls.
- No UI/static implementation.
- No feature flag.
- No Balance.ge.
- No connector changes.
- No production data.
- No credentials.
- No infrastructure.
- No runtime code changes.
- No runtime report behavior changes.
- No approval or posting behavior changes.

## 19. H30 Results

| Check | Result |
|---|---|
| H30 targeted tests | 30 passed |
| H29 + H30 tests | 61 passed |
| Related report/fixture tests | 317 passed |
| Full unit suite | 4156 passed, 2 skipped |
| Fixture changes | none |
| Accountant review contract green | yes |

## 20. Non-Goals

H30 does not do any of the following:
- no DB
- no SQL
- no migration
- no fixture load
- no runtime API calls
- no runtime implementation
- no UI/static implementation
- no production data
- no connector
- no Balance.ge

## 21. Next Task

Only after PR merge, deploy, and live verification:

H31 - Production Switch Gate Contract / Feature Flag Approval Checklist
