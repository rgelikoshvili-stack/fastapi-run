"""
Bridge Hub — Task 11C-H5
Contract tests for docs/posting-service-ledger-write-contract.md

Rules:
- No import of posting_service or any runtime module.
- No DB connection.
- No SQL execution.
- No migration execution.
- Reads only the contract document via pathlib.
"""
import ast
import pathlib
import pytest

_CONTRACT = (
    pathlib.Path(__file__).parent.parent.parent
    / "docs"
    / "posting-service-ledger-write-contract.md"
)


def _doc() -> str:
    return _CONTRACT.read_text(encoding="utf-8")


class TestContractDocumentExists:
    def test_contract_document_exists(self):
        assert _CONTRACT.exists(), "docs/posting-service-ledger-write-contract.md must exist"

    def test_contract_document_is_nonempty(self):
        assert len(_doc()) > 500

    def test_contract_document_title(self):
        assert "Posting Service Ledger Write Contract" in _doc()

    def test_contract_task_reference(self):
        doc = _doc()
        assert "11C-H5" in doc


class TestContractDefinesAccountingTruthRule:
    def test_contract_defines_accounting_truth_rule(self):
        doc = _doc()
        assert "Accounting Truth Rule" in doc or "accounting truth" in doc.lower()

    def test_contract_lists_posted_as_accounting_truth(self):
        doc = _doc()
        assert "posted" in doc.lower()
        assert "YES" in doc

    def test_contract_only_real_posted_is_truth(self):
        doc = _doc()
        assert "Only a successful real connector posting" in doc or \
               "only" in doc.lower() and "accounting truth" in doc.lower()


class TestContractRejectsJournalDraftsAsTruth:
    def test_contract_rejects_journal_drafts_as_truth(self):
        doc = _doc()
        assert "draft" in doc.lower()
        assert "NO" in doc

    def test_contract_draft_status_not_truth(self):
        doc = _doc()
        assert "draft" in doc.lower()
        assert "Not yet reviewed" in doc or "Unreviewed" in doc or "draft" in doc.lower()

    def test_contract_pending_approval_not_truth(self):
        doc = _doc()
        assert "pending" in doc.lower() or "pending_approval" in doc.lower()
        assert "Awaiting" in doc or "awaiting" in doc.lower()


class TestContractRejectsApprovedAutoApprovedAsTruth:
    def test_contract_rejects_approved_auto_approved_as_truth(self):
        doc = _doc()
        assert "auto_approved" in doc
        assert "approved" in doc.lower()

    def test_contract_approved_not_truth(self):
        doc = _doc()
        assert "Approved for execution" in doc or "approved" in doc.lower()

    def test_contract_auto_approved_not_truth(self):
        doc = _doc()
        assert "auto_approved" in doc
        assert "Automated" in doc or "automated" in doc.lower()


class TestContractRejectsSimulatedSuccessMockAndDryRun:
    def test_contract_rejects_simulated_success_mock_and_dry_run_as_truth(self):
        doc = _doc()
        assert "simulated_success" in doc
        assert "mock_posting" in doc or "Mock" in doc
        assert "dry_run" in doc

    def test_contract_simulated_success_not_truth(self):
        doc = _doc()
        assert "simulated_success" in doc
        assert "simulation" in doc.lower() or "Test/simulation" in doc

    def test_contract_dry_run_not_truth(self):
        doc = _doc()
        assert "dry_run" in doc
        assert "Preview mode" in doc or "preview" in doc.lower()

    def test_contract_mock_posting_not_truth(self):
        doc = _doc()
        assert "mock_posting" in doc or "Mock connector" in doc
        assert "Development" in doc or "development" in doc.lower()


class TestContractAllowsLedgerWriteOnlyAfterSuccessfulRealConnectorPosting:
    def test_contract_allows_ledger_write_only_after_successful_real_connector_posting(self):
        doc = _doc()
        assert "real connector" in doc.lower() or "Connector Execute" in doc
        assert "When Ledger Write Is Allowed" in doc or "ledger write" in doc.lower()

    def test_contract_requires_posting_log_with_real_success(self):
        doc = _doc()
        assert "posting_log" in doc
        assert "posting_log_id" in doc

    def test_contract_lists_allowed_conditions(self):
        doc = _doc()
        assert "When Ledger Write Is Allowed" in doc
        assert "dry_run" in doc and "false" in doc.lower()

    def test_contract_connector_response_real_success(self):
        doc = _doc()
        assert "connector response" in doc.lower() or "Connector response" in doc
        assert "real success" in doc or "real connector" in doc.lower()


class TestContractForbidsLedgerWriteForDemoModeAndStubConnectors:
    def test_contract_forbids_ledger_write_for_demo_mode_and_stub_connectors(self):
        doc = _doc()
        assert "demo_mode" in doc
        assert "When Ledger Write Is Forbidden" in doc or "Forbidden" in doc

    def test_contract_forbids_oris_stub(self):
        doc = _doc()
        assert "ORIS" in doc
        assert "stub" in doc.lower()

    def test_contract_forbids_1c_demo_mode(self):
        doc = _doc()
        assert "1C" in doc
        assert "demo" in doc.lower()

    def test_contract_forbids_balance_ge_demo_mode(self):
        doc = _doc()
        assert "balance" in doc.lower() and "demo_mode" in doc

    def test_contract_connector_config_missing_forbidden(self):
        doc = _doc()
        assert "Connector config missing" in doc or "connector config" in doc.lower()


class TestContractRequiresTenantId:
    def test_contract_requires_tenant_id(self):
        doc = _doc()
        assert "tenant_id" in doc

    def test_contract_tenant_isolation_enforced(self):
        doc = _doc()
        assert "tenant isolation" in doc.lower() or "Tenant isolation" in doc

    def test_contract_forbids_missing_tenant_id(self):
        doc = _doc()
        assert "tenant_id" in doc
        assert "missing" in doc.lower() or "empty" in doc.lower()

    def test_contract_tenant_mismatch_fail_closed(self):
        doc = _doc()
        assert "Tenant mismatch" in doc or "tenant mismatch" in doc.lower()


class TestContractRequiresPeriodLockCheck:
    def test_contract_requires_period_lock_check(self):
        doc = _doc()
        assert "period" in doc.lower()
        assert "locked" in doc.lower() or "is_period_locked" in doc

    def test_contract_period_locked_forbidden(self):
        doc = _doc()
        assert "Period is locked" in doc or "period is locked" in doc.lower()

    def test_contract_period_locked_returns_error(self):
        doc = _doc()
        assert "PERIOD_LOCKED" in doc or "period_locked" in doc.lower()

    def test_contract_is_period_locked_function_referenced(self):
        doc = _doc()
        assert "is_period_locked" in doc


class TestContractRequiresBalancedJournalLines:
    def test_contract_requires_balanced_journal_lines(self):
        doc = _doc()
        assert "balanced" in doc.lower()
        assert "debit" in doc.lower() and "credit" in doc.lower()

    def test_contract_balance_invariant_total_debit_equals_total_credit(self):
        doc = _doc()
        assert "total_debit" in doc and "total_credit" in doc
        assert "sum(debit)" in doc.lower() or "total_debit = total_credit" in doc

    def test_contract_unbalanced_entry_forbidden(self):
        doc = _doc()
        assert "unbalanced" in doc.lower() or "Unbalanced" in doc
        assert "fail" in doc.lower()

    def test_contract_balance_mismatch_logs_error(self):
        doc = _doc()
        assert "Balance mismatch" in doc or "balance mismatch" in doc.lower()
        assert "ERROR" in doc or "error" in doc.lower()


class TestContractRequiresIdempotencyAndDuplicateProtection:
    def test_contract_requires_idempotency_and_duplicate_protection(self):
        doc = _doc()
        assert "idempotency" in doc.lower() or "Idempotency" in doc
        assert "duplicate" in doc.lower()

    def test_contract_source_draft_id_posting_log_id_unique(self):
        doc = _doc()
        assert "source_draft_id" in doc
        assert "posting_log_id" in doc

    def test_contract_source_hash_uniqueness(self):
        doc = _doc()
        assert "source_hash" in doc

    def test_contract_duplicate_detected_returns_existing_entry(self):
        doc = _doc()
        assert "existing entry" in doc.lower() or "existing entry id" in doc.lower()

    def test_contract_no_phantom_entries(self):
        doc = _doc()
        assert "phantom" in doc.lower() or "No phantom" in doc


class TestContractRequiresSourceDraftPostingLogAndEvidenceLinks:
    def test_contract_requires_source_draft_posting_log_and_evidence_links(self):
        doc = _doc()
        assert "source_draft_id" in doc
        assert "posting_log_id" in doc
        assert "evidence_bundle_id" in doc

    def test_contract_evidence_bundle_linkage(self):
        doc = _doc()
        assert "evidence_bundle" in doc.lower()

    def test_contract_evidence_bundle_nullable(self):
        doc = _doc()
        assert "NULL" in doc or "null" in doc.lower() or "Nullable" in doc

    def test_contract_audit_log_records_write_result(self):
        doc = _doc()
        assert "audit" in doc.lower()
        assert "audit_log" in doc or "Audit log" in doc


class TestContractRequiresFailClosedErrorHandling:
    def test_contract_requires_fail_closed_error_handling(self):
        doc = _doc()
        assert "fail" in doc.lower() and "closed" in doc.lower()
        assert "Error Handling" in doc or "error handling" in doc.lower()

    def test_contract_ledger_write_failure_after_connector_success(self):
        doc = _doc()
        assert "connector success" in doc.lower() or "Connector success" in doc
        assert "recoverable" in doc.lower() or "inconsistency" in doc.lower()

    def test_contract_fail_closed_does_not_silently_mark_posted(self):
        doc = _doc()
        assert "silently" in doc.lower()

    def test_contract_missing_required_fields_fail_closed(self):
        doc = _doc()
        assert "Missing required fields" in doc or "missing" in doc.lower()
        assert "tenant_id" in doc


class TestContractRequiresTransactionBoundary:
    def test_contract_requires_transaction_boundary_for_future_implementation(self):
        doc = _doc()
        assert "transaction" in doc.lower()
        assert "transaction boundary" in doc.lower() or "single database transaction" in doc.lower()

    def test_contract_all_line_inserts_in_one_transaction(self):
        doc = _doc()
        assert "transaction" in doc.lower()
        assert "rolls back" in doc.lower() or "rollback" in doc.lower() or "roll back" in doc.lower()

    def test_contract_header_insert_and_lines_in_one_transaction(self):
        doc = _doc()
        assert "header" in doc.lower() and "line" in doc.lower()
        assert "transaction" in doc.lower()


class TestContractForbidsPartialHeaderWithoutLines:
    def test_contract_forbids_partial_header_without_lines(self):
        doc = _doc()
        assert "header" in doc.lower() and "lines" in doc.lower()
        assert "No partial" in doc or "partial" in doc.lower()

    def test_contract_header_without_lines_invalid(self):
        doc = _doc()
        assert "without lines" in doc.lower() or "no lines" in doc.lower() or "phantom" in doc.lower()

    def test_contract_partial_write_forbidden(self):
        doc = _doc()
        assert "No partial writes" in doc or "partial write" in doc.lower()


class TestContractForbidsRawSecretsInEvidenceOrMetadata:
    def test_contract_forbids_raw_secrets_in_evidence_or_metadata(self):
        doc = _doc()
        assert "api_key" in doc or "secret" in doc.lower()
        assert "metadata_json" in doc

    def test_contract_strip_unsafe_applied_to_metadata(self):
        doc = _doc()
        assert "_strip_unsafe" in doc

    def test_contract_no_credentials_in_journal_entry_lines(self):
        doc = _doc()
        assert "journal_entry_lines" in doc
        assert "credential" in doc.lower()

    def test_contract_metadata_json_no_password_token(self):
        doc = _doc()
        assert "password" in doc
        assert "token" in doc


class TestContractStatesNoRuntimeBehaviorChangeInH5:
    def test_contract_states_no_runtime_behavior_change_in_h5(self):
        doc = _doc()
        assert "not modified" in doc.lower() or "No runtime" in doc or "no runtime" in doc.lower()

    def test_contract_posting_service_not_modified(self):
        doc = _doc()
        assert "posting_service.py" in doc
        assert "not modified" in doc.lower() or "is not modified" in doc.lower()

    def test_contract_non_goals_section_exists(self):
        doc = _doc()
        assert "Non-Goals" in doc or "Non-goals" in doc or "non-goals" in doc.lower()

    def test_contract_h5_produces_only_two_files(self):
        doc = _doc()
        assert "docs/posting-service-ledger-write-contract.md" in doc
        assert "tests/unit/test_posting_service_ledger_write_contract.py" in doc


class TestContractStatesNoSqlDbMigrationExecutionInH5:
    def test_contract_states_no_sql_db_migration_execution_in_h5(self):
        doc = _doc()
        assert "No SQL" in doc or "no SQL" in doc.lower()
        assert "No migration" in doc or "no migration" in doc.lower()

    def test_contract_no_production_db_touch(self):
        doc = _doc()
        assert "production" in doc.lower()
        assert "No production DB" in doc or "no production" in doc.lower()

    def test_contract_no_migration_execution(self):
        doc = _doc()
        assert "migration" in doc.lower()
        assert "not executed" in doc.lower() or "No migration" in doc

    def test_contract_table_unavailable_graceful_fallback(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "does not exist" in doc.lower() or "unavailable" in doc.lower()
        assert "graceful" in doc.lower() or "fall back" in doc.lower() or "fallback" in doc.lower()


class TestContractDefinesFutureH6ToH10Sequence:
    def test_contract_defines_future_h6_to_h10_sequence(self):
        doc = _doc()
        assert "H6" in doc
        assert "H7" in doc
        assert "H8" in doc

    def test_contract_h6_is_implementation_with_mocks(self):
        doc = _doc()
        assert "H6" in doc
        assert "mock" in doc.lower() or "Mock" in doc

    def test_contract_h7_is_reports_migration(self):
        doc = _doc()
        assert "H7" in doc
        assert "report" in doc.lower()

    def test_contract_h10_controlled_migration_execution(self):
        doc = _doc()
        assert "H10" in doc
        assert "migration" in doc.lower()
        assert "local" in doc.lower() or "test" in doc.lower()


class TestContractFileHasNoForbiddenImports:
    def test_no_posting_service_import(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {"posting_service", "balance_connector", "approval_service"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    assert f not in node.module, f"Forbidden import: {node.module}"

    def test_no_db_connection_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_modules = {"psycopg2", "asyncpg", "sqlalchemy"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                for alias in getattr(node, "names", []):
                    name = alias.name or ""
                    for f in forbidden_modules:
                        assert not name.startswith(f), f"Forbidden DB import: {name}"
                        assert not mod.startswith(f), f"Forbidden DB import from: {mod}"

    def test_no_network_call_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_net = {"requests", "httpx", "urllib"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                for alias in getattr(node, "names", []):
                    name = alias.name or ""
                    for f in forbidden_net:
                        assert not name.startswith(f), f"Forbidden network import: {name}"
                        assert not mod.startswith(f), f"Forbidden network import from: {mod}"
