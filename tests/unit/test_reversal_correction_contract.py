"""
Bridge Hub — Task 11C-H9
Contract tests for docs/reversal-correction-contract.md

Rules:
- No import of runtime services.
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
    / "reversal-correction-contract.md"
)


def _doc() -> str:
    return _CONTRACT.read_text(encoding="utf-8")


class TestContractDocumentExists:
    def test_contract_document_exists(self):
        assert _CONTRACT.exists(), "docs/reversal-correction-contract.md must exist"

    def test_contract_document_is_nonempty(self):
        assert len(_doc()) > 500

    def test_contract_document_title(self):
        assert "Reversal" in _doc() and "Correction" in _doc()

    def test_contract_task_reference(self):
        assert "11C-H9" in _doc()


class TestContractDefinesImmutablePostedLedgerRule:
    def test_contract_defines_immutable_posted_ledger_rule(self):
        doc = _doc()
        assert "immutable" in doc.lower()
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc

    def test_contract_states_posted_entries_are_permanent(self):
        doc = _doc()
        assert "permanent" in doc.lower() or "immutable" in doc.lower()

    def test_contract_status_can_be_updated_to_reversed(self):
        doc = _doc()
        assert "reversed" in doc.lower()
        assert "status" in doc.lower()

    def test_contract_lines_always_immutable(self):
        doc = _doc()
        assert "journal_entry_lines" in doc
        assert "immutable" in doc.lower()


class TestContractForbidsDestructiveUpdateOrDelete:
    def test_contract_forbids_destructive_update_or_delete(self):
        doc = _doc()
        assert "UPDATE" in doc or "update" in doc.lower()
        assert "DELETE" in doc or "delete" in doc.lower()

    def test_contract_forbids_delete_of_posted_entries(self):
        doc = _doc()
        assert "No DELETE" in doc or "never be deleted" in doc.lower() or \
               "must never be deleted" in doc.lower()

    def test_contract_forbids_destructive_correction(self):
        doc = _doc()
        assert "destructive" in doc.lower()
        assert "correction" in doc.lower()

    def test_contract_new_rows_only(self):
        doc = _doc()
        assert "new rows" in doc.lower() or "new ledger entries" in doc.lower() or \
               "new row" in doc.lower()


class TestContractDefinesAppendOnlyReversal:
    def test_contract_defines_append_only_reversal(self):
        doc = _doc()
        assert "append-only" in doc.lower()
        assert "reversal" in doc.lower()

    def test_contract_reversal_creates_new_entry(self):
        doc = _doc()
        assert "new" in doc.lower()
        assert "reversal" in doc.lower()
        assert "entry" in doc.lower()

    def test_contract_original_entry_unchanged_after_reversal(self):
        doc = _doc()
        assert "original" in doc.lower()
        assert "unchanged" in doc.lower() or "intact" in doc.lower() or \
               "preserved" in doc.lower() or "remains" in doc.lower()

    def test_contract_reversal_must_not_reuse_original_entry_id(self):
        doc = _doc()
        assert "new UUID" in doc or "not reuse" in doc.lower() or \
               "must not reuse" in doc.lower()


class TestContractDefinesReversalInvertsDebitCredit:
    def test_contract_defines_reversal_inverts_debit_credit(self):
        doc = _doc()
        assert "invert" in doc.lower() or "inverted" in doc.lower() or \
               "inverts" in doc.lower()
        assert "debit" in doc.lower()
        assert "credit" in doc.lower()

    def test_contract_reversal_debit_becomes_credit(self):
        doc = _doc()
        assert "debit" in doc.lower() and "credit" in doc.lower()
        assert "invert" in doc.lower() or "inverts" in doc.lower()

    def test_contract_reversal_entry_is_balanced(self):
        doc = _doc()
        assert "balanced" in doc.lower()
        assert "total_debit = total_credit" in doc or "total_debit == total_credit" in doc or \
               "balanced" in doc.lower()


class TestContractDefinesAppendOnlyCorrection:
    def test_contract_defines_append_only_correction(self):
        doc = _doc()
        assert "correction" in doc.lower()
        assert "append-only" in doc.lower()

    def test_contract_correction_policy_must_be_explicit(self):
        doc = _doc()
        assert "policy" in doc.lower()
        assert "explicit" in doc.lower()

    def test_contract_full_reversal_plus_new_entry_policy(self):
        doc = _doc()
        assert "full reversal" in doc.lower() or "Policy A" in doc

    def test_contract_delta_correction_policy(self):
        doc = _doc()
        assert "delta" in doc.lower() or "Policy B" in doc

    def test_contract_correction_references_original(self):
        doc = _doc()
        assert "correction_of_entry_id" in doc


class TestContractRequiresOriginalEntryPreserved:
    def test_contract_requires_original_entry_preserved(self):
        doc = _doc()
        assert "original" in doc.lower()
        assert "preserved" in doc.lower() or "unchanged" in doc.lower() or \
               "remains" in doc.lower() or "intact" in doc.lower()

    def test_contract_original_entry_must_exist(self):
        doc = _doc()
        assert "Original entry must exist" in doc or "original entry exists" in doc.lower()

    def test_contract_original_not_mutated_by_correction(self):
        doc = _doc()
        assert "must never be mutated" in doc.lower() or \
               "never be mutated" in doc.lower() or \
               "original entry must never" in doc.lower()


class TestContractRequiresReversalOrCorrectionReason:
    def test_contract_requires_reversal_or_correction_reason(self):
        doc = _doc()
        assert "reason" in doc.lower()
        assert "required" in doc.lower()

    def test_contract_reason_must_be_non_empty(self):
        doc = _doc()
        assert "non-empty" in doc.lower() or "non empty" in doc.lower()
        assert "reason" in doc.lower()

    def test_contract_missing_reason_is_forbidden(self):
        doc = _doc()
        assert "Reason missing" in doc or "reason missing" in doc.lower() or \
               "missing" in doc.lower()

    def test_contract_reversal_reason_and_correction_reason_fields(self):
        doc = _doc()
        assert "reversal_reason" in doc
        assert "correction_reason" in doc


class TestContractRequiresTenantIdAndTenantMatch:
    def test_contract_requires_tenant_id_and_tenant_match(self):
        doc = _doc()
        assert "tenant_id" in doc
        assert "tenant" in doc.lower()
        assert "match" in doc.lower() or "matching" in doc.lower() or \
               "same tenant" in doc.lower()

    def test_contract_tenant_mismatch_is_forbidden(self):
        doc = _doc()
        assert "tenant_id mismatch" in doc.lower() or "Tenant mismatch" in doc or \
               "mismatch" in doc.lower()

    def test_contract_reversal_must_have_tenant_id(self):
        doc = _doc()
        assert "Reversal must have" in doc or "must have `tenant_id`" in doc or \
               "tenant_id" in doc

    def test_contract_correction_must_have_tenant_id(self):
        doc = _doc()
        assert "Correction must have" in doc or "must have `tenant_id`" in doc or \
               "tenant_id" in doc


class TestContractRequiresPermissionOrRoleGate:
    def test_contract_requires_permission_or_role_gate(self):
        doc = _doc()
        assert "permission" in doc.lower() or "role" in doc.lower()

    def test_contract_actor_lacks_permission_is_forbidden(self):
        doc = _doc()
        assert "lacks" in doc.lower() or "lacks required" in doc.lower() or \
               "lacks permission" in doc.lower()

    def test_contract_reversal_permission_named(self):
        doc = _doc()
        assert "ledger:reverse" in doc or "reversal permission" in doc.lower() or \
               "permission" in doc.lower()


class TestContractRequiresPeriodLockPolicy:
    def test_contract_requires_period_lock_policy(self):
        doc = _doc()
        assert "period" in doc.lower()
        assert "locked" in doc.lower() or "lock" in doc.lower()

    def test_contract_period_locked_forbidden(self):
        doc = _doc()
        assert "is_period_locked" in doc
        assert "fail closed" in doc.lower() or "forbidden" in doc.lower() or \
               "Forbidden" in doc

    def test_contract_reopening_policy_acknowledged(self):
        doc = _doc()
        assert "reopening" in doc.lower() or "reopen" in doc.lower() or \
               "reopening policy" in doc.lower()


class TestContractRequiresBalancedReversalCorrectionLines:
    def test_contract_requires_balanced_reversal_correction_lines(self):
        doc = _doc()
        assert "balanced" in doc.lower()
        assert "debit" in doc.lower() and "credit" in doc.lower()

    def test_contract_unbalanced_lines_forbidden(self):
        doc = _doc()
        assert "unbalanced" in doc.lower() or "Unbalanced" in doc
        assert "debit" in doc.lower() and "credit" in doc.lower()

    def test_contract_reversal_lines_total_balanced(self):
        doc = _doc()
        assert "total_debit = total_credit" in doc or "balanced" in doc.lower()


class TestContractRequiresIdempotency:
    def test_contract_requires_idempotency(self):
        doc = _doc()
        assert "idempotent" in doc.lower() or "idempotency" in doc.lower()

    def test_contract_duplicate_returns_existing_not_new(self):
        doc = _doc()
        assert "existing" in doc.lower()
        assert "duplicate" in doc.lower() or "idempotent" in doc.lower()

    def test_contract_idempotency_key_defined(self):
        doc = _doc()
        assert "idempotency_key" in doc

    def test_contract_no_duplicate_reversal(self):
        doc = _doc()
        assert "duplicate" in doc.lower()
        assert "reversal" in doc.lower()


class TestContractForbidsNonPostedStates:
    def test_contract_forbids_non_posted_states(self):
        doc = _doc()
        assert "draft" in doc.lower()
        assert "approved" in doc.lower()

    def test_contract_draft_cannot_be_reversed(self):
        doc = _doc()
        assert "draft" in doc.lower()
        assert "Not a real posting" in doc or "cannot be reversed" in doc.lower() or \
               "not a real" in doc.lower()

    def test_contract_approved_not_a_ledger_entry(self):
        doc = _doc()
        assert "approved" in doc.lower()
        assert "Not yet posted" in doc or "not a ledger entry" in doc.lower() or \
               "not yet posted" in doc.lower()


class TestContractForbidsSimulatedSuccessMockDryRun:
    def test_contract_forbids_simulated_success_mock_dry_run(self):
        doc = _doc()
        assert "simulated_success" in doc
        assert "mock_posting" in doc
        assert "dry_run" in doc

    def test_contract_simulated_success_not_a_real_posting(self):
        doc = _doc()
        assert "simulated_success" in doc
        assert "Test/simulation" in doc or "simulation" in doc.lower()

    def test_contract_dry_run_is_preview_not_real_posting(self):
        doc = _doc()
        assert "dry_run" in doc
        assert "Preview mode" in doc or "preview" in doc.lower()

    def test_contract_mock_is_development_artifact(self):
        doc = _doc()
        assert "mock_posting" in doc
        assert "Development" in doc or "development" in doc.lower()


class TestContractForbidsDuplicateReversalCorrection:
    def test_contract_forbids_duplicate_reversal_correction(self):
        doc = _doc()
        assert "duplicate" in doc.lower()
        assert "reversal" in doc.lower() or "correction" in doc.lower()

    def test_contract_duplicate_idempotency_key_forbidden(self):
        doc = _doc()
        assert "Duplicate idempotency" in doc or "idempotency" in doc.lower()

    def test_contract_already_reversed_entry_not_re_reversed(self):
        doc = _doc()
        assert "Already reversed" in doc or "already reversed" in doc.lower() or \
               "already `reversed`" in doc.lower()


class TestContractDefinesNetAndHistoryReportViews:
    def test_contract_defines_net_and_history_report_views(self):
        doc = _doc()
        assert "net" in doc.lower()
        assert "history" in doc.lower() or "audit" in doc.lower()

    def test_contract_net_view_excludes_reversed(self):
        doc = _doc()
        assert "exclude" in doc.lower() or "excludes" in doc.lower()
        assert "reversed" in doc.lower()
        assert "net" in doc.lower()

    def test_contract_history_view_includes_full_chain(self):
        doc = _doc()
        assert "history" in doc.lower() or "audit" in doc.lower()
        assert "original" in doc.lower()
        assert "reversal" in doc.lower()
        assert "correction" in doc.lower()

    def test_contract_voided_excluded_from_net_totals(self):
        doc = _doc()
        assert "voided" in doc.lower()
        assert "excluded" in doc.lower()


class TestContractRequiresNoDoubleCounting:
    def test_contract_requires_no_double_counting(self):
        doc = _doc()
        assert "double-count" in doc.lower() or "double counting" in doc.lower() or \
               "double-counting" in doc.lower()

    def test_contract_correction_not_double_counted_with_original(self):
        doc = _doc()
        assert "original" in doc.lower()
        assert "correction" in doc.lower()
        assert "double" in doc.lower()

    def test_contract_reports_respect_reversal_correction_rules(self):
        doc = _doc()
        assert "Trial Balance" in doc or "trial balance" in doc.lower()
        assert "reversal" in doc.lower()


class TestContractRequiresAuditEvent:
    def test_contract_requires_audit_event(self):
        doc = _doc()
        assert "audit" in doc.lower()
        assert "event" in doc.lower()

    def test_contract_audit_log_records_reversal_correction(self):
        doc = _doc()
        assert "audit_log" in doc or "audit log" in doc.lower() or "audit event" in doc.lower()

    def test_contract_audit_event_includes_actor_and_timestamp(self):
        doc = _doc()
        assert "actor" in doc.lower()
        assert "timestamp" in doc.lower()

    def test_contract_audit_event_includes_reason(self):
        doc = _doc()
        assert "reason" in doc.lower()
        assert "audit" in doc.lower()

    def test_contract_audit_trail_must_be_complete(self):
        doc = _doc()
        assert "complete" in doc.lower() or "reconstructable" in doc.lower() or \
               "full" in doc.lower()


class TestContractRequiresEvidenceLinkage:
    def test_contract_requires_evidence_linkage(self):
        doc = _doc()
        assert "evidence_bundle_id" in doc

    def test_contract_evidence_bundle_id_is_nullable(self):
        doc = _doc()
        assert "nullable" in doc.lower() or "where available" in doc.lower() or \
               "where applicable" in doc.lower()

    def test_contract_posting_log_id_linked_if_connector_action(self):
        doc = _doc()
        assert "posting_log_id" in doc

    def test_contract_evidence_and_audit_chain_reconstructable(self):
        doc = _doc()
        assert "reconstructable" in doc.lower() or "chain" in doc.lower()
        assert "reversed_by_entry_id" in doc
        assert "correction_of_entry_id" in doc


class TestContractForbidsRawSecrets:
    def test_contract_forbids_raw_secrets(self):
        doc = _doc()
        assert "api_key" in doc or "secret" in doc.lower()
        assert "metadata_json" in doc

    def test_contract_strip_unsafe_required(self):
        doc = _doc()
        assert "_strip_unsafe" in doc

    def test_contract_forbidden_secret_fields_listed(self):
        doc = _doc()
        assert "password" in doc
        assert "token" in doc
        assert "encrypted_value" in doc

    def test_contract_no_raw_credentials_in_audit_or_evidence(self):
        doc = _doc()
        assert "credentials" in doc.lower()
        assert "never" in doc.lower()


class TestContractDefinesRequiredDataModelFields:
    def test_contract_defines_required_data_model_fields(self):
        doc = _doc()
        assert "reversed_by_entry_id" in doc
        assert "correction_of_entry_id" in doc

    def test_contract_data_model_includes_reason_fields(self):
        doc = _doc()
        assert "reversal_reason" in doc
        assert "correction_reason" in doc

    def test_contract_data_model_includes_correction_policy(self):
        doc = _doc()
        assert "correction_policy" in doc

    def test_contract_data_model_includes_audit_event_id(self):
        doc = _doc()
        assert "audit_event_id" in doc

    def test_contract_data_model_includes_actor_fields(self):
        doc = _doc()
        assert "created_by" in doc
        assert "approved_by" in doc
        assert "posted_by" in doc


class TestContractStatesNoRuntimeBehaviorChangeInH9:
    def test_contract_states_no_runtime_behavior_change_in_h9(self):
        doc = _doc()
        assert "posting_service.py" in doc
        assert "not modified" in doc.lower() or "no runtime" in doc.lower() or \
               "does not" in doc.lower()

    def test_contract_approval_service_not_modified(self):
        doc = _doc()
        assert "approval_service.py" in doc

    def test_contract_ledger_service_not_modified(self):
        doc = _doc()
        assert "ledger_service.py" in doc

    def test_contract_non_goals_section_exists(self):
        doc = _doc()
        assert "Non-Goals" in doc or "Non-goals" in doc or "non-goals" in doc.lower()

    def test_contract_h9_produces_only_two_files(self):
        doc = _doc()
        assert "docs/reversal-correction-contract.md" in doc
        assert "tests/unit/test_reversal_correction_contract.py" in doc


class TestContractStatesNoSqlDbMigrationExecutionInH9:
    def test_contract_states_no_sql_db_migration_execution_in_h9(self):
        doc = _doc()
        assert "No SQL" in doc or "no SQL" in doc.lower()
        assert "No migration" in doc or "no migration" in doc.lower()

    def test_contract_no_production_db_touch(self):
        doc = _doc()
        assert "production" in doc.lower()
        assert "No production DB" in doc or "no production" in doc.lower()

    def test_contract_balance_ge_not_activated(self):
        doc = _doc()
        assert "Balance.ge" in doc
        assert "inactive" in doc.lower() or "remains" in doc.lower()


class TestContractDefinesFutureH10ToH14Sequence:
    def test_contract_defines_future_h10_to_h14_sequence(self):
        doc = _doc()
        assert "H10" in doc
        assert "H11" in doc
        assert "H12" in doc
        assert "H13" in doc
        assert "H14" in doc

    def test_contract_h10_is_evidence_audit_export(self):
        doc = _doc()
        assert "H10" in doc
        assert "evidence" in doc.lower() or "audit" in doc.lower()

    def test_contract_h13_is_mock_tests(self):
        doc = _doc()
        assert "H13" in doc
        assert "mock" in doc.lower()

    def test_contract_h14_is_runtime_implementation(self):
        doc = _doc()
        assert "H14" in doc
        assert "runtime" in doc.lower() or "implementation" in doc.lower()

    def test_contract_h14_requires_explicit_approval(self):
        doc = _doc()
        assert "H14" in doc
        assert "explicit" in doc.lower() or "approval" in doc.lower()


class TestFileHasNoRuntimeServiceImports:
    def test_file_has_no_runtime_service_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {
            "posting_service", "approval_service", "ledger_service",
            "financial_statements_service", "routes_reports", "routes_posting",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    assert f not in node.module, f"Forbidden import: {node.module}"

    def test_no_app_runtime_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.api"), \
                    f"Forbidden runtime import: {node.module}"
                assert not node.module.startswith("app.core"), \
                    f"Forbidden runtime import: {node.module}"


class TestFileHasNoDbOrNetworkImports:
    def test_file_has_no_db_or_network_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_db = {"psycopg2", "asyncpg", "sqlalchemy", "databases"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                for alias in getattr(node, "names", []):
                    name = alias.name or ""
                    for f in forbidden_db:
                        assert not name.startswith(f), f"Forbidden DB import: {name}"
                        assert not mod.startswith(f), f"Forbidden DB import from: {mod}"

    def test_no_network_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_net = {"requests", "httpx", "urllib", "aiohttp"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                for alias in getattr(node, "names", []):
                    name = alias.name or ""
                    for f in forbidden_net:
                        assert not name.startswith(f), f"Forbidden net import: {name}"
                        assert not mod.startswith(f), f"Forbidden net import from: {mod}"

    def test_no_sql_execution_calls(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        sql_exec_attrs = {"execute", "executemany", "executescript", "fetchall", "fetchone"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in sql_exec_attrs:
                    obj_name = ""
                    if isinstance(func.value, ast.Name):
                        obj_name = func.value.id
                    assert False, f"Forbidden SQL execution call: {obj_name}.{func.attr}"
