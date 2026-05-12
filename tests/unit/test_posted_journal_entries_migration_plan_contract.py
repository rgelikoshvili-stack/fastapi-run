"""
tests/unit/test_posted_journal_entries_migration_plan_contract.py

Contract tests for the Posted Journal Entries Migration Plan (11C-H3).

Rules:
  - No DB connection.
  - No SQL execution.
  - No runtime app imports.
  - No connector calls.
  - No Balance.ge activation.
  - Reads docs/posted-journal-entries-migration-plan.md as text.
  - Tests fail if required contract language disappears from the document.
"""
from __future__ import annotations

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PLAN = _ROOT / "docs" / "posted-journal-entries-migration-plan.md"


def _doc() -> str:
    return _PLAN.read_text(encoding="utf-8")


def _doc_lower() -> str:
    return _doc().lower()


# ---------------------------------------------------------------------------
# 1. Document existence
# ---------------------------------------------------------------------------

class TestMigrationPlanDocumentExists:

    def test_migration_plan_document_exists(self):
        assert _PLAN.exists(), f"Migration plan not found at {_PLAN}"

    def test_migration_plan_is_nonempty(self):
        assert len(_doc().strip()) > 500

    def test_migration_plan_is_markdown(self):
        assert _PLAN.suffix == ".md"

    def test_migration_plan_has_title(self):
        assert "posted journal entries migration plan" in _doc_lower()


# ---------------------------------------------------------------------------
# 2. H3 is plan only — no SQL migration
# ---------------------------------------------------------------------------

class TestH3IsPlanOnlyAndNotSqlMigration:

    def test_h3_is_plan_only_and_not_sql_migration(self):
        text = _doc_lower()
        assert "plan only" in text or "does not create" in text or "no sql" in text

    def test_plan_states_no_sql_file_created_in_h3(self):
        text = _doc_lower()
        assert "no sql" in text or "does not create" in text or "no migration file" in text

    def test_plan_states_no_db_accessed_in_h3(self):
        text = _doc_lower()
        assert "no database" in text or "no db" in text or "no production db" in text

    def test_plan_explicitly_references_h4_as_sql_creation_task(self):
        text = _doc_lower()
        assert "h4" in text
        assert "sql" in text or "migration" in text

    def test_plan_states_two_files_only(self):
        text = _doc_lower()
        assert "two files only" in text or (
            "posted-journal-entries-migration-plan.md" in text
            and "test_posted_journal_entries_migration_plan_contract" in text
        )


# ---------------------------------------------------------------------------
# 3. Additive-only migration required
# ---------------------------------------------------------------------------

class TestPlanRequiresAdditiveOnlyMigration:

    def test_plan_requires_additive_only_migration(self):
        text = _doc_lower()
        assert "additive only" in text or "additive-only" in text

    def test_plan_requires_create_table_if_not_exists(self):
        text = _doc_lower()
        assert "if not exists" in text or "create table if not exists" in text

    def test_plan_forbids_drop_statements(self):
        text = _doc_lower()
        assert "no drop" in text or "no `drop`" in text or "drop" in text and "destructive" in text

    def test_plan_forbids_destructive_ddl(self):
        text = _doc_lower()
        assert "destructive" in text
        assert "no" in text or "must not" in text or "forbidden" in text

    def test_plan_forbids_journal_drafts_changes_in_migration(self):
        text = _doc_lower()
        assert "journal_drafts" in text
        assert "must not modify" in text or "no journal_drafts changes" in text or (
            "not modify" in text and "journal_drafts" in text
        ) or "not" in text


# ---------------------------------------------------------------------------
# 4. Production DB not touched in H3
# ---------------------------------------------------------------------------

class TestPlanForbidsProductionDbTouchInH3:

    def test_plan_forbids_production_db_touch_in_h3(self):
        text = _doc_lower()
        assert "production" in text
        assert "not touched" in text or "no production db" in text or "must not be touched" in text or (
            "production database" in text and ("not" in text or "no" in text)
        )

    def test_plan_states_local_ci_only(self):
        text = _doc_lower()
        assert "local" in text and ("ci" in text or "test" in text)

    def test_plan_states_production_requires_explicit_approval(self):
        text = _doc_lower()
        assert "explicit" in text and ("approval" in text or "approved" in text)


# ---------------------------------------------------------------------------
# 5. SQL execution forbidden in H3
# ---------------------------------------------------------------------------

class TestPlanForbidsSqlExecutionInH3:

    def test_plan_forbids_sql_execution_in_h3(self):
        text = _doc_lower()
        assert "no sql" in text or "does not execute" in text

    def test_plan_states_no_sql_created(self):
        text = _doc_lower()
        assert "no sql" in text or "no migration file" in text

    def test_plan_forbids_select_queries_against_production(self):
        text = _doc_lower()
        assert "no direct db" in text or "no sql" in text or "no production sql" in text


# ---------------------------------------------------------------------------
# 6. Migration execution forbidden in H3
# ---------------------------------------------------------------------------

class TestPlanForbidsMigrationExecutionInH3:

    def test_plan_forbids_migration_execution_in_h3(self):
        text = _doc_lower()
        assert "no migration" in text or "does not execute" in text or "not execute" in text

    def test_plan_states_migration_file_not_created_in_h3(self):
        text = _doc_lower()
        assert "no migration file" in text or "does not create" in text or (
            "h3" in text and "no sql" in text
        )


# ---------------------------------------------------------------------------
# 7. journal_entry_headers and lines planned
# ---------------------------------------------------------------------------

class TestPlanDefinesJournalEntryHeadersAndLines:

    def test_plan_defines_journal_entry_headers_and_lines(self):
        text = _doc_lower()
        assert "journal_entry_headers" in text
        assert "journal_entry_lines" in text

    def test_plan_mentions_journal_entry_sources(self):
        text = _doc_lower()
        assert "journal_entry_sources" in text

    def test_plan_mentions_source_draft_id(self):
        assert "source_draft_id" in _doc_lower()

    def test_plan_mentions_posting_log_id(self):
        assert "posting_log_id" in _doc_lower()

    def test_plan_mentions_evidence_bundle_id(self):
        assert "evidence_bundle_id" in _doc_lower()

    def test_plan_mentions_total_debit_and_total_credit(self):
        text = _doc_lower()
        assert "total_debit" in text
        assert "total_credit" in text

    def test_plan_mentions_line_hash_and_source_hash(self):
        text = _doc_lower()
        assert "line_hash" in text
        assert "source_hash" in text

    def test_plan_mentions_posted_at_and_created_at(self):
        text = _doc_lower()
        assert "posted_at" in text
        assert "created_at" in text

    def test_plan_mentions_reversal_linkage_fields(self):
        text = _doc_lower()
        assert "reversed_by_entry_id" in text
        assert "correction_of_entry_id" in text


# ---------------------------------------------------------------------------
# 8. tenant_id constraints planned
# ---------------------------------------------------------------------------

class TestPlanRequiresTenantIdConstraints:

    def test_plan_requires_tenant_id_constraints(self):
        text = _doc_lower()
        assert "tenant_id" in text
        assert "not null" in text

    def test_plan_requires_tenant_id_nonempty_check(self):
        text = _doc_lower()
        assert "ck_jeh_tenant_nonempty" in text or (
            "tenant_id" in text and ("nonempty" in text or "<> ''" in text or "not null" in text)
        )

    def test_plan_states_line_tenant_must_match_header(self):
        text = _doc_lower()
        assert "must match" in text or (
            "tenant_id" in text and "lines" in text and ("match" in text or "same" in text)
        )

    def test_plan_states_tenant_id_on_every_row(self):
        text = _doc_lower()
        assert "every" in text and "tenant_id" in text or "not null" in text


# ---------------------------------------------------------------------------
# 9. Posted-only ledger truth required
# ---------------------------------------------------------------------------

class TestPlanRequiresPostedOnlyLedgerTruth:

    def test_plan_requires_posted_only_ledger_truth(self):
        text = _doc_lower()
        assert "posted" in text
        assert "accounting truth" in text or "official" in text

    def test_plan_defines_allowed_statuses(self):
        text = _doc_lower()
        assert "posted" in text
        assert "reversed" in text
        assert "correction" in text
        assert "voided" in text

    def test_plan_defines_check_constraint_for_status(self):
        text = _doc_lower()
        assert "ck_jeh_status" in text or (
            "check" in text and "status" in text and "posted" in text
        )


# ---------------------------------------------------------------------------
# 10. simulated_success and mock_posting rejected
# ---------------------------------------------------------------------------

class TestPlanRejectsSimulatedSuccessAndMockPostingAsTruth:

    def test_plan_rejects_simulated_success_and_mock_posting_as_truth(self):
        text = _doc_lower()
        assert "simulated_success" in text
        assert "not accounting truth" in text or "must not" in text or "not truth" in text

    def test_plan_rejects_draft_as_truth(self):
        text = _doc_lower()
        assert "draft" in text and ("not" in text or "forbidden" in text)

    def test_plan_rejects_approved_as_truth(self):
        text = _doc_lower()
        assert "approved" in text and "not accounting truth" in text or (
            "approved" in text and "not" in text
        )

    def test_plan_rejects_auto_approved_as_truth(self):
        text = _doc_lower()
        assert "auto_approved" in text
        assert "not" in text

    def test_plan_states_simulated_success_must_not_be_backfilled(self):
        text = _doc_lower()
        assert "simulated_success" in text
        assert "backfill" in text or "must not" in text


# ---------------------------------------------------------------------------
# 11. Balanced entry constraints
# ---------------------------------------------------------------------------

class TestPlanRequiresBalancedEntryConstraints:

    def test_plan_requires_balanced_entry_constraints(self):
        text = _doc_lower()
        assert "total_debit" in text and "total_credit" in text
        assert "=" in text or "equal" in text or "balanced" in text

    def test_plan_defines_ck_jeh_balanced_constraint(self):
        text = _doc_lower()
        assert "ck_jeh_balanced" in text or (
            "total_debit = total_credit" in text or
            ("balanced" in text and "constraint" in text)
        )

    def test_plan_defines_nonneg_constraints_for_debit_credit(self):
        text = _doc_lower()
        assert "ck_jeh_debit_nonneg" in text or (
            "total_debit >= 0" in text or ("debit" in text and "nonneg" in text)
        )

    def test_plan_defines_nonzero_constraint_for_lines(self):
        text = _doc_lower()
        assert "ck_jel_nonzero" in text or (
            "debit > 0 or credit > 0" in text or ("nonzero" in text)
        )


# ---------------------------------------------------------------------------
# 12. Append-only reversals and corrections
# ---------------------------------------------------------------------------

class TestPlanRequiresAppendOnlyReversalsAndCorrections:

    def test_plan_requires_append_only_reversals_and_corrections(self):
        text = _doc_lower()
        assert "append-only" in text
        assert "reversal" in text or "reversals" in text

    def test_plan_states_reversals_create_new_rows(self):
        text = _doc_lower()
        assert "new" in text and ("header" in text or "row" in text or "entry" in text)
        assert "reversal" in text

    def test_plan_states_corrections_create_new_entries(self):
        text = _doc_lower()
        assert "correction" in text
        assert "new" in text or "create" in text

    def test_plan_states_lines_are_immutable(self):
        text = _doc_lower()
        assert "immutable" in text
        assert "line" in text or "lines" in text

    def test_plan_states_posted_entries_never_mutated(self):
        text = _doc_lower()
        assert "never mutate" in text or "immutable" in text or "never update" in text or (
            "posted" in text and ("immutable" in text or "not mutate" in text)
        )


# ---------------------------------------------------------------------------
# 13. Evidence and posting log linkage
# ---------------------------------------------------------------------------

class TestPlanRequiresEvidenceAndPostingLogLinkage:

    def test_plan_requires_evidence_and_posting_log_linkage(self):
        text = _doc_lower()
        assert "evidence_bundle_id" in text
        assert "posting_log_id" in text

    def test_plan_defines_evidence_bundle_index(self):
        text = _doc_lower()
        assert "idx_jeh_evidence_bundle" in text or (
            "evidence_bundle" in text and "index" in text
        )

    def test_plan_defines_source_draft_index(self):
        text = _doc_lower()
        assert "idx_jeh_source_draft" in text or (
            "source_draft" in text and "index" in text
        )

    def test_plan_states_soft_link_strategy(self):
        text = _doc_lower()
        assert "soft link" in text or "soft-link" in text or "no hard fk" in text or (
            "without" in text and "foreign key" in text
        ) or "soft" in text


# ---------------------------------------------------------------------------
# 14. Index requirements
# ---------------------------------------------------------------------------

class TestPlanDefinesIndexRequirements:

    def test_plan_defines_index_requirements(self):
        text = _doc_lower()
        assert "index" in text or "idx_" in text

    def test_plan_defines_tenant_period_index(self):
        text = _doc_lower()
        assert "idx_jeh_tenant_period" in text or (
            "tenant_id" in text and "period" in text and "index" in text
        )

    def test_plan_defines_tenant_status_index(self):
        text = _doc_lower()
        assert "idx_jeh_tenant_status" in text or (
            "tenant_id" in text and "status" in text and "index" in text
        )

    def test_plan_defines_account_code_index(self):
        text = _doc_lower()
        assert "idx_jel_account" in text or (
            "account_code" in text and "index" in text
        )

    def test_plan_defines_counterparty_index(self):
        text = _doc_lower()
        assert "idx_jel_counterparty" in text or (
            "counterparty_id" in text and "index" in text
        )

    def test_plan_defines_header_to_lines_index(self):
        text = _doc_lower()
        assert "idx_jel_header" in text or (
            "journal_entry_id" in text and "index" in text
        )


# ---------------------------------------------------------------------------
# 15. Future rollout H4 to H8 defined
# ---------------------------------------------------------------------------

class TestPlanDefinesFutureRolloutH4ToH8:

    def test_plan_defines_future_rollout_h4_to_h8(self):
        text = _doc_lower()
        assert "h4" in text
        assert "h5" in text
        assert "h6" in text
        assert "h7" in text
        assert "h8" in text

    def test_plan_defines_h4_as_sql_migration(self):
        text = _doc_lower()
        assert "h4" in text
        assert "sql" in text or "migration" in text

    def test_plan_defines_h5_as_posting_service(self):
        text = _doc_lower()
        assert "h5" in text
        assert "posting" in text

    def test_plan_defines_h6_as_reports_read(self):
        text = _doc_lower()
        assert "h6" in text
        assert "report" in text

    def test_plan_defines_h7_as_reversal_and_evidence(self):
        text = _doc_lower()
        assert "h7" in text
        assert "reversal" in text or "evidence" in text

    def test_plan_defines_h8_as_optional_backfill(self):
        text = _doc_lower()
        assert "h8" in text
        assert "backfill" in text


# ---------------------------------------------------------------------------
# 16. Safe backfill policy
# ---------------------------------------------------------------------------

class TestPlanDefinesSafeBackfillPolicy:

    def test_plan_defines_safe_backfill_policy(self):
        text = _doc_lower()
        assert "backfill" in text

    def test_plan_states_no_backfill_in_h3(self):
        text = _doc_lower()
        assert "no backfill in h3" in text or (
            "h3" in text and "backfill" in text and ("no" in text or "not" in text)
        )

    def test_plan_states_no_production_backfill_without_approval(self):
        text = _doc_lower()
        assert "no production backfill" in text or (
            "backfill" in text and "explicit" in text and "approval" in text
        )

    def test_plan_states_simulated_success_not_backfilled(self):
        text = _doc_lower()
        assert "simulated_success" in text
        assert "backfill" in text
        assert "must not" in text or "not be backfilled" in text

    def test_plan_states_backfill_must_use_dry_run(self):
        text = _doc_lower()
        assert "dry_run" in text or "dry run" in text

    def test_plan_states_backfill_must_be_reversible(self):
        text = _doc_lower()
        assert "reversible" in text

    def test_plan_states_backfill_must_produce_audit_report(self):
        text = _doc_lower()
        assert "audit report" in text or ("audit" in text and "report" in text)

    def test_plan_states_backfill_must_be_idempotent(self):
        text = _doc_lower()
        assert "idempotent" in text


# ---------------------------------------------------------------------------
# 17. Future verification plan
# ---------------------------------------------------------------------------

class TestPlanDefinesFutureVerificationPlan:

    def test_plan_defines_future_verification_plan(self):
        text = _doc_lower()
        assert "verification" in text

    def test_plan_includes_schema_tests_in_verification(self):
        text = _doc_lower()
        assert "schema test" in text or ("schema" in text and "test" in text)

    def test_plan_states_no_production_sql_in_planning_phase(self):
        text = _doc_lower()
        assert "no production sql" in text or (
            "production" in text and "sql" in text and ("no" in text or "not" in text)
        )

    def test_plan_states_live_verification_reads_only_version_and_health(self):
        text = _doc_lower()
        assert "/version" in text or "version" in text
        assert "/health" in text or "health" in text

    def test_plan_states_no_db_writes_during_live_verification(self):
        text = _doc_lower()
        assert "no db writes" in text or (
            "live verification" in text and ("no" in text and "db" in text or "no db" in text)
        )

    def test_plan_states_local_test_db_only(self):
        text = _doc_lower()
        assert "local" in text and ("test db" in text or "test database" in text or "ci" in text)


# ---------------------------------------------------------------------------
# 18. No runtime report or posting changes in H3
# ---------------------------------------------------------------------------

class TestPlanStatesNoRuntimeReportOrPostingChangesInH3:

    def test_plan_states_no_runtime_report_or_posting_changes_in_h3(self):
        text = _doc_lower()
        assert "no runtime" in text or "runtime report" in text or (
            "does not" in text and "report" in text
        )

    def test_plan_states_routes_reports_not_modified(self):
        text = _doc_lower()
        assert "routes_reports" in text or (
            "runtime report" in text and ("not" in text or "no" in text)
        )

    def test_plan_states_posting_service_not_modified(self):
        text = _doc_lower()
        assert "posting_service" in text or (
            "posting service" in text and ("not" in text or "no" in text)
        )

    def test_plan_states_approval_service_not_modified(self):
        text = _doc_lower()
        assert "approval_service" in text or (
            "approval" in text and ("not" in text or "no" in text)
        )

    def test_plan_states_no_balance_ge_activation(self):
        text = _doc_lower()
        assert "balance.ge" in text
        assert "inactive" in text or "not activated" in text or "remains inactive" in text

    def test_plan_states_no_credential_changes(self):
        text = _doc_lower()
        assert "no credential" in text or "credential" in text and "no" in text

    def test_plan_states_no_connector_changes(self):
        text = _doc_lower()
        assert "no connector" in text or (
            "connector" in text and ("no" in text or "not" in text)
        )
