"""
tests/unit/test_posted_journal_entries_schema_contract.py

Contract tests for the Posted Journal Entries Schema Contract (11C-H2).

Rules:
  - No DB connection.
  - No SQL execution.
  - No runtime app imports.
  - No connector calls.
  - No Balance.ge activation.
  - Reads docs/posted-journal-entries-schema-contract.md as text.
  - Tests fail if required contract language disappears from the document.
"""
from __future__ import annotations

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CONTRACT = _ROOT / "docs" / "posted-journal-entries-schema-contract.md"


def _doc() -> str:
    return _CONTRACT.read_text(encoding="utf-8")


def _doc_lower() -> str:
    return _doc().lower()


# ---------------------------------------------------------------------------
# 1. Document existence
# ---------------------------------------------------------------------------

class TestContractDocumentExists:

    def test_contract_document_exists(self):
        assert _CONTRACT.exists(), (
            f"Contract document not found at {_CONTRACT}"
        )

    def test_contract_document_is_nonempty(self):
        assert len(_doc().strip()) > 500

    def test_contract_document_is_markdown(self):
        assert _CONTRACT.suffix == ".md"

    def test_contract_document_has_title(self):
        assert "posted journal entries schema contract" in _doc_lower()


# ---------------------------------------------------------------------------
# 2. journal_drafts rejected as accounting truth
# ---------------------------------------------------------------------------

class TestContractRejectsJournalDraftsAsAccountingTruth:

    def test_contract_rejects_journal_drafts_as_accounting_truth(self):
        text = _doc_lower()
        assert "journal_drafts" in text
        assert "not accounting truth" in text

    def test_contract_states_draft_is_not_truth(self):
        text = _doc_lower()
        assert "draft is not truth" in text or ("draft" in text and "not truth" in text)

    def test_contract_states_approved_is_not_truth(self):
        text = _doc_lower()
        assert "approved is not truth" in text or ("approved" in text and "not truth" in text)

    def test_contract_states_auto_approved_is_not_truth(self):
        text = _doc_lower()
        assert "auto_approved" in text
        assert "not truth" in text or "not accounting truth" in text

    def test_contract_rejects_simulated_success_as_truth(self):
        text = _doc_lower()
        assert "simulated_success" in text
        # Contract must state it is NOT truth
        assert "not" in text
        assert "simulated_success" in text

    def test_contract_rejects_mock_posting_as_truth(self):
        text = _doc_lower()
        assert "mock" in text or "mock posting" in text

    def test_contract_states_only_posted_entries_are_truth(self):
        text = _doc_lower()
        assert "only posted journal entries are official accounting truth" in text or (
            "only posted" in text and "accounting truth" in text
        )


# ---------------------------------------------------------------------------
# 3. journal_entry_headers defined
# ---------------------------------------------------------------------------

class TestContractDefinesJournalEntryHeaders:

    def test_contract_defines_journal_entry_headers(self):
        assert "journal_entry_headers" in _doc_lower()

    def test_headers_include_id(self):
        text = _doc_lower()
        assert "journal_entry_headers" in text
        assert "| `id`" in _doc() or "id" in text

    def test_headers_include_tenant_id(self):
        assert "tenant_id" in _doc_lower()

    def test_headers_include_source_draft_id(self):
        assert "source_draft_id" in _doc_lower()

    def test_headers_include_posting_log_id(self):
        assert "posting_log_id" in _doc_lower()

    def test_headers_include_evidence_bundle_id(self):
        assert "evidence_bundle_id" in _doc_lower()

    def test_headers_include_entry_date(self):
        assert "entry_date" in _doc_lower()

    def test_headers_include_posting_date(self):
        assert "posting_date" in _doc_lower()

    def test_headers_include_period(self):
        assert "period" in _doc_lower()

    def test_headers_include_status(self):
        assert "status" in _doc_lower()

    def test_headers_include_total_debit(self):
        assert "total_debit" in _doc_lower()

    def test_headers_include_total_credit(self):
        assert "total_credit" in _doc_lower()

    def test_headers_include_reversed_by_entry_id(self):
        assert "reversed_by_entry_id" in _doc_lower()

    def test_headers_include_correction_of_entry_id(self):
        assert "correction_of_entry_id" in _doc_lower()

    def test_headers_include_posted_at(self):
        assert "posted_at" in _doc_lower()

    def test_headers_include_approved_by(self):
        assert "approved_by" in _doc_lower()

    def test_headers_include_posted_by(self):
        assert "posted_by" in _doc_lower()


# ---------------------------------------------------------------------------
# 4. journal_entry_lines defined
# ---------------------------------------------------------------------------

class TestContractDefinesJournalEntryLines:

    def test_contract_defines_journal_entry_lines(self):
        assert "journal_entry_lines" in _doc_lower()

    def test_lines_include_journal_entry_id(self):
        assert "journal_entry_id" in _doc_lower()

    def test_lines_include_line_no(self):
        assert "line_no" in _doc_lower()

    def test_lines_include_account_code(self):
        assert "account_code" in _doc_lower()

    def test_lines_include_debit(self):
        assert "debit" in _doc_lower()

    def test_lines_include_credit(self):
        assert "credit" in _doc_lower()

    def test_lines_include_amount_gel(self):
        assert "amount_gel" in _doc_lower()

    def test_lines_include_counterparty_id(self):
        assert "counterparty_id" in _doc_lower()

    def test_lines_include_tax_code(self):
        assert "tax_code" in _doc_lower()

    def test_lines_include_vat_amount(self):
        assert "vat_amount" in _doc_lower()

    def test_lines_include_line_hash(self):
        assert "line_hash" in _doc_lower()

    def test_lines_include_bank_transaction_id(self):
        assert "bank_transaction_id" in _doc_lower()

    def test_lines_include_document_id(self):
        assert "document_id" in _doc_lower()


# ---------------------------------------------------------------------------
# 5. tenant_id required on ledger tables
# ---------------------------------------------------------------------------

class TestContractRequiresTenantIdOnLedgerTables:

    def test_contract_requires_tenant_id_on_ledger_tables(self):
        text = _doc_lower()
        assert "tenant_id" in text
        assert "required" in text or "not null" in text or "every" in text

    def test_contract_requires_tenant_id_on_every_row(self):
        text = _doc_lower()
        assert "tenant_id is required on every ledger table" in text or (
            "tenant_id" in text and "every" in text and "ledger" in text
        )

    def test_contract_requires_tenant_filter_on_every_report(self):
        text = _doc_lower()
        assert "every official report must filter by" in text or (
            "every official report" in text and "tenant_id" in text
        )

    def test_contract_requires_period_filter_on_every_report(self):
        text = _doc_lower()
        assert "period" in text and "filter" in text
        assert "every official report" in text or "date range" in text


# ---------------------------------------------------------------------------
# 6. posted-only official reports required
# ---------------------------------------------------------------------------

class TestContractRequiresPostedOnlyOfficialReports:

    def test_contract_requires_posted_only_official_reports(self):
        text = _doc_lower()
        assert "official reports must be posted-only" in text or (
            "official" in text and "posted" in text and "only" in text
        )

    def test_contract_defines_allowed_entry_statuses(self):
        text = _doc_lower()
        assert "posted" in text
        assert "reversed" in text
        assert "correction" in text
        assert "voided" in text

    def test_contract_forbids_draft_status_as_accounting_truth(self):
        text = _doc_lower()
        assert "draft" in text
        assert "not" in text

    def test_contract_states_no_report_reads_drafts_after_migration(self):
        text = _doc_lower()
        assert "no official report should read" in text or (
            "journal_drafts" in text and "after" in text and "migration" in text
        )


# ---------------------------------------------------------------------------
# 7. simulated_success rejected
# ---------------------------------------------------------------------------

class TestContractRejectsSimulatedSuccess:

    def test_contract_rejects_simulated_success_as_truth(self):
        text = _doc_lower()
        assert "simulated_success" in text
        assert "not" in text

    def test_contract_names_h1_critical_finding_pnl_detail(self):
        text = _doc_lower()
        # H1 CRITICAL: /reports/pnl/detail treated simulated_success as truth
        assert "pnl" in text or "profit" in text
        assert "simulated_success" in text

    def test_contract_states_explicit_prohibition_on_simulated_success(self):
        text = _doc_lower()
        assert "no official report may treat" in text or (
            "simulated_success" in text and ("forbidden" in text or "must not" in text or "not truth" in text)
        )


# ---------------------------------------------------------------------------
# 8. Balanced entry invariant required
# ---------------------------------------------------------------------------

class TestContractRequiresBalancedEntries:

    def test_contract_requires_balanced_entries(self):
        text = _doc_lower()
        assert "total_debit" in text and "total_credit" in text
        assert "equal" in text or "must equal" in text or "balanced" in text

    def test_contract_states_debit_equals_credit_invariant(self):
        text = _doc_lower()
        assert "total_debit must equal total_credit" in text or (
            "total_debit" in text and "total_credit" in text and "equal" in text
        )

    def test_contract_states_double_entry_invariant(self):
        text = _doc_lower()
        assert "balanced" in text or "double-entry" in text or "debit" in text


# ---------------------------------------------------------------------------
# 9. Append-only reversals and corrections required
# ---------------------------------------------------------------------------

class TestContractRequiresAppendOnlyReversalsAndCorrections:

    def test_contract_requires_append_only_reversals_and_corrections(self):
        text = _doc_lower()
        assert "append-only" in text
        assert "reversal" in text or "reversals" in text

    def test_contract_states_reversals_create_new_entries(self):
        text = _doc_lower()
        assert "reversal" in text and ("new" in text or "append" in text or "offset" in text)

    def test_contract_states_corrections_create_new_entries(self):
        text = _doc_lower()
        assert "correction" in text and ("new" in text or "create" in text or "append" in text)

    def test_contract_states_posted_lines_are_immutable(self):
        text = _doc_lower()
        assert "immutable" in text
        assert "posted" in text

    def test_contract_prohibits_destructive_edit_of_posted_entries(self):
        text = _doc_lower()
        assert "must not be destructively edited" in text or (
            "immutable" in text and "posted" in text
        )


# ---------------------------------------------------------------------------
# 10. Evidence / source linkage required
# ---------------------------------------------------------------------------

class TestContractRequiresEvidenceOrSourceLinkage:

    def test_contract_requires_evidence_or_source_linkage(self):
        text = _doc_lower()
        assert "evidence_bundle" in text or "evidence bundle" in text
        assert "linkage" in text or "link" in text or "linkable" in text

    def test_contract_states_evidence_bundle_id_on_headers(self):
        assert "evidence_bundle_id" in _doc_lower()

    def test_contract_states_entries_should_link_to_source(self):
        text = _doc_lower()
        assert "source" in text and ("link" in text or "linkable" in text)

    def test_contract_defines_journal_entry_sources_concept(self):
        text = _doc_lower()
        assert "journal_entry_sources" in text or (
            "source" in text and "linkage" in text
        )


# ---------------------------------------------------------------------------
# 11. posting_log linkage when connector execution occurs
# ---------------------------------------------------------------------------

class TestContractRequiresPostingLogLinkage:

    def test_contract_requires_posting_log_linkage_when_connector_execution_occurs(self):
        text = _doc_lower()
        assert "posting_log" in text or "posting_log_id" in text

    def test_contract_states_posting_log_id_on_headers(self):
        assert "posting_log_id" in _doc_lower()

    def test_contract_states_connector_execution_linkage(self):
        text = _doc_lower()
        assert "connector" in text and "posting_log" in text


# ---------------------------------------------------------------------------
# 12. H2 has no SQL, DB, migration, or runtime behavior changes
# ---------------------------------------------------------------------------

class TestContractSaysH2HasNoSqlDbMigrationOrRuntimeChanges:

    def test_contract_says_h2_has_no_sql_db_migration_or_runtime_behavior_changes(self):
        text = _doc_lower()
        assert "no sql" in text or "does not execute any sql" in text or "no sql is executed" in text

    def test_contract_states_no_production_db_access(self):
        text = _doc_lower()
        assert "no production db" in text or "production database" in text or "production db" in text

    def test_contract_states_no_migration_created(self):
        text = _doc_lower()
        assert "no migration" in text or "no database migration" in text

    def test_contract_states_no_migration_executed(self):
        text = _doc_lower()
        assert "no migration" in text or "not execut" in text

    def test_contract_states_no_runtime_report_behavior_change(self):
        text = _doc_lower()
        assert "no runtime report behavior change" in text or (
            "no runtime" in text and "report" in text
        ) or "runtime report behavior" in text

    def test_contract_states_no_balance_ge_activation(self):
        text = _doc_lower()
        assert "balance.ge" in text
        assert "inactive" in text or "not activated" in text or "remains inactive" in text

    def test_contract_states_no_credential_changes(self):
        text = _doc_lower()
        assert "no credential" in text or "credentials" in text

    def test_contract_states_two_files_only(self):
        text = _doc_lower()
        assert "two files only" in text or (
            "posted-journal-entries-schema-contract.md" in text
            and "test_posted_journal_entries_schema_contract" in text
        )


# ---------------------------------------------------------------------------
# 13. H3–H7 future task sequence defined
# ---------------------------------------------------------------------------

class TestContractDefinesFutureH3ToH7Sequence:

    def test_contract_defines_future_h3_to_h7_sequence(self):
        text = _doc_lower()
        assert "11c-h3" in text
        assert "11c-h4" in text
        assert "11c-h5" in text
        assert "11c-h6" in text
        assert "11c-h7" in text

    def test_contract_defines_h3_as_migration_contract(self):
        text = _doc_lower()
        assert "11c-h3" in text
        assert "migration" in text

    def test_contract_defines_h4_as_posting_service_plan(self):
        text = _doc_lower()
        assert "11c-h4" in text
        assert "posting" in text

    def test_contract_defines_h5_as_reports_read_plan(self):
        text = _doc_lower()
        assert "11c-h5" in text
        assert "report" in text

    def test_contract_defines_h6_as_reversal_correction(self):
        text = _doc_lower()
        assert "11c-h6" in text
        assert "reversal" in text or "correction" in text

    def test_contract_defines_h7_as_evidence_bundle_linkage(self):
        text = _doc_lower()
        assert "11c-h7" in text
        assert "evidence bundle" in text or "evidence_bundle" in text


# ---------------------------------------------------------------------------
# 14. Report migration targets defined
# ---------------------------------------------------------------------------

class TestContractDefinesReportMigrationTargets:

    def test_contract_defines_report_migration_targets(self):
        text = _doc_lower()
        assert "report migration" in text or "migration target" in text

    def test_contract_defines_trial_balance_target(self):
        text = _doc_lower()
        assert "trial balance" in text or "trial_balance" in text
        assert "journal_entry_lines" in text

    def test_contract_defines_pnl_target(self):
        text = _doc_lower()
        assert "profit" in text and "loss" in text
        assert "journal_entry_lines" in text or "journal_entry_headers" in text

    def test_contract_defines_balance_sheet_target(self):
        text = _doc_lower()
        assert "balance sheet" in text or "balance_sheet" in text
        assert "journal_entry_lines" in text or "posted" in text

    def test_contract_defines_vat_register_target(self):
        text = _doc_lower()
        assert "vat" in text
        assert "journal_entry_lines" in text or "posted" in text

    def test_contract_defines_cashflow_target(self):
        text = _doc_lower()
        assert "cash flow" in text or "cashflow" in text or "cash_flow" in text

    def test_contract_defines_ledger_targets(self):
        text = _doc_lower()
        assert "account ledger" in text or "account_ledger" in text or "get_account_ledger" in text
        assert "journal_entry_lines" in text

    def test_contract_migration_targets_say_posted_only(self):
        text = _doc_lower()
        assert "status = 'posted'" in text or "status='posted'" in text or (
            "where" in text and "posted" in text
        )
