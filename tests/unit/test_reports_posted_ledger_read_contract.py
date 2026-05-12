"""
Bridge Hub — Task 11C-H7
Contract tests for docs/reports-posted-ledger-read-contract.md

Rules:
- No import of financial_statements_service, ledger_service, or routes_reports.
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
    / "reports-posted-ledger-read-contract.md"
)


def _doc() -> str:
    return _CONTRACT.read_text(encoding="utf-8")


class TestContractDocumentExists:
    def test_contract_document_exists(self):
        assert _CONTRACT.exists(), "docs/reports-posted-ledger-read-contract.md must exist"

    def test_contract_document_is_nonempty(self):
        assert len(_doc()) > 500

    def test_contract_document_title(self):
        assert "Reports Posted-Ledger Read Contract" in _doc()

    def test_contract_task_reference(self):
        assert "11C-H7" in _doc()


class TestContractRejectsJournalDraftsAsReportTruth:
    def test_contract_rejects_journal_drafts_as_report_truth(self):
        doc = _doc()
        assert "journal_drafts" in doc
        assert "not official" in doc.lower() or "NOT" in doc

    def test_contract_states_journal_drafts_jsonb_is_not_truth(self):
        doc = _doc()
        assert "journal_drafts" in doc
        assert "JSONB" in doc
        assert "not official accounting truth" in doc.lower() or \
               "is not official" in doc.lower() or \
               "not official report truth" in doc.lower()

    def test_contract_identifies_current_report_problem(self):
        doc = _doc()
        assert "journal_drafts" in doc
        assert "JSONB" in doc

    def test_contract_defines_journal_entry_headers_as_truth_source(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc


class TestContractRejectsNonPostedStatesAsReportTruth:
    def test_contract_rejects_drafts_approved_auto_approved_simulated_success_mock_dry_run(self):
        doc = _doc()
        assert "auto_approved" in doc
        assert "simulated_success" in doc
        assert "mock_posting" in doc
        assert "dry_run" in doc

    def test_contract_rejects_draft_status(self):
        doc = _doc()
        assert "draft" in doc.lower()
        assert "NO" in doc

    def test_contract_rejects_approved_status(self):
        doc = _doc()
        assert "approved" in doc.lower()
        assert "not yet ERP-confirmed" in doc or "NOT" in doc

    def test_contract_rejects_auto_approved(self):
        doc = _doc()
        assert "auto_approved" in doc
        assert "NO" in doc

    def test_contract_rejects_simulated_success(self):
        doc = _doc()
        assert "simulated_success" in doc
        assert "NO" in doc

    def test_contract_rejects_mock_posting(self):
        doc = _doc()
        assert "mock_posting" in doc
        assert "NO" in doc

    def test_contract_rejects_dry_run(self):
        doc = _doc()
        assert "dry_run" in doc
        assert "NO" in doc

    def test_contract_rejects_voided_from_official_totals(self):
        doc = _doc()
        assert "voided" in doc.lower() or "voided" in doc
        assert "NO" in doc or "excluded" in doc.lower()

    def test_contract_rejects_failed_connector_attempts(self):
        doc = _doc()
        assert "failed" in doc.lower()
        assert "connector" in doc.lower()


class TestContractRequiresPostedLedgerSources:
    def test_contract_requires_posted_ledger_sources(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "status" in doc and "posted" in doc.lower()

    def test_contract_only_posted_is_truth(self):
        doc = _doc()
        assert "status='posted'" in doc or "status = 'posted'" in doc

    def test_contract_correction_entries_also_truth(self):
        doc = _doc()
        assert "correction" in doc.lower()

    def test_contract_reversed_entries_excluded_from_net(self):
        doc = _doc()
        assert "reversed" in doc.lower()
        assert "excluded" in doc.lower() or "exclude" in doc.lower()


class TestContractDefinesTrialBalanceSource:
    def test_contract_defines_trial_balance_source(self):
        doc = _doc()
        assert "Trial Balance" in doc or "trial balance" in doc.lower() or "trial-balance" in doc.lower()

    def test_trial_balance_reads_from_posted_lines(self):
        doc = _doc()
        assert "journal_entry_lines" in doc
        assert "journal_entry_headers" in doc
        assert "trial" in doc.lower()

    def test_trial_balance_requires_tenant_and_period_filter(self):
        doc = _doc()
        assert "tenant_id" in doc
        assert "period" in doc.lower()

    def test_trial_balance_three_column_view(self):
        doc = _doc()
        assert "opening balance" in doc.lower() or "opening" in doc.lower()
        assert "period movement" in doc.lower() or "movement" in doc.lower()
        assert "closing balance" in doc.lower() or "closing" in doc.lower()


class TestContractDefinesPnlSummaryAndDetailSources:
    def test_contract_defines_pnl_summary_and_detail_sources(self):
        doc = _doc()
        assert "P&L" in doc or "pnl" in doc.lower() or "PnL" in doc

    def test_pnl_filters_to_income_expense_accounts(self):
        doc = _doc()
        assert "income" in doc.lower()
        assert "expense" in doc.lower()

    def test_pnl_never_includes_simulated_success(self):
        doc = _doc()
        assert "simulated_success" in doc
        assert "Never include" in doc or "never include" in doc.lower() or "never" in doc.lower()

    def test_pnl_is_period_only(self):
        doc = _doc()
        assert "period" in doc.lower()
        assert "P&L" in doc or "pnl" in doc.lower()

    def test_pnl_detail_line_level_fields(self):
        doc = _doc()
        assert "account_code" in doc
        assert "entry_date" in doc or "posting_date" in doc


class TestContractDefinesBalanceSheetSummaryAndDetailSources:
    def test_contract_defines_balance_sheet_summary_and_detail_sources(self):
        doc = _doc()
        assert "Balance Sheet" in doc or "balance sheet" in doc.lower()

    def test_balance_sheet_filters_to_asset_liability_equity(self):
        doc = _doc()
        assert "asset" in doc.lower()
        assert "liability" in doc.lower()
        assert "equity" in doc.lower()

    def test_balance_sheet_is_cumulative_as_of_date(self):
        doc = _doc()
        assert "as-of" in doc.lower() or "as of" in doc.lower()
        assert "cumulative" in doc.lower()

    def test_balance_sheet_supports_opening_balance(self):
        doc = _doc()
        assert "opening balance" in doc.lower() or "opening" in doc.lower()

    def test_balance_sheet_never_includes_simulated_success(self):
        doc = _doc()
        assert "simulated_success" in doc
        assert "Never include" in doc or "never include" in doc.lower()


class TestContractDefinesVatRegisterSource:
    def test_contract_defines_vat_register_source(self):
        doc = _doc()
        assert "VAT" in doc

    def test_vat_reads_from_posted_lines_with_tax_code(self):
        doc = _doc()
        assert "tax_code" in doc
        assert "vat_amount" in doc
        assert "journal_entry_lines" in doc

    def test_vat_requires_period_filter(self):
        doc = _doc()
        assert "VAT" in doc
        assert "period" in doc.lower()

    def test_vat_requires_status_posted(self):
        doc = _doc()
        assert "status" in doc and "posted" in doc.lower()


class TestContractDefinesAccountLedgerSource:
    def test_contract_defines_account_ledger_source(self):
        doc = _doc()
        assert "Account Ledger" in doc or "account ledger" in doc.lower() or "account-ledger" in doc.lower()

    def test_account_ledger_filters_by_account_code(self):
        doc = _doc()
        assert "account_code" in doc

    def test_account_ledger_requires_tenant_and_period(self):
        doc = _doc()
        assert "tenant_id" in doc
        assert "period" in doc.lower() or "date" in doc.lower()

    def test_account_ledger_includes_opening_closing_balances(self):
        doc = _doc()
        assert "opening" in doc.lower() and "closing" in doc.lower()


class TestContractDefinesCounterpartyLedgerSource:
    def test_contract_defines_counterparty_ledger_source(self):
        doc = _doc()
        assert "Counterparty" in doc or "counterparty" in doc.lower()

    def test_counterparty_ledger_filters_by_counterparty_id(self):
        doc = _doc()
        assert "counterparty_id" in doc

    def test_counterparty_ledger_requires_posted_status(self):
        doc = _doc()
        assert "status" in doc and "posted" in doc.lower()

    def test_counterparty_ledger_requires_tenant_filter(self):
        doc = _doc()
        assert "tenant_id" in doc


class TestContractDefinesPayrollLedgerSource:
    def test_contract_defines_payroll_ledger_source(self):
        doc = _doc()
        assert "Payroll" in doc or "payroll" in doc.lower()

    def test_payroll_ledger_source_type_filter(self):
        doc = _doc()
        assert "source_type" in doc
        assert "payroll" in doc.lower()

    def test_payroll_ledger_requires_posted_status(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "posted" in doc.lower()

    def test_payroll_ledger_requires_period_filter(self):
        doc = _doc()
        assert "payroll" in doc.lower()
        assert "period" in doc.lower()


class TestContractDefinesJournalEntriesListSource:
    def test_contract_defines_journal_entries_list_source(self):
        doc = _doc()
        assert "Journal Entries" in doc or "journal entries" in doc.lower() or "journal_entries" in doc

    def test_journal_entries_list_reads_from_headers_and_lines(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc

    def test_journal_entries_list_supports_status_filter(self):
        doc = _doc()
        assert "posted" in doc.lower()
        assert "correction" in doc.lower()
        assert "reversed" in doc.lower()

    def test_journal_entries_list_requires_tenant_and_period(self):
        doc = _doc()
        assert "tenant_id" in doc
        assert "period" in doc.lower() or "date" in doc.lower()


class TestContractDefinesCashflowSource:
    def test_contract_defines_cashflow_source(self):
        doc = _doc()
        assert "Cashflow" in doc or "cashflow" in doc.lower() or "cash flow" in doc.lower()

    def test_cashflow_reads_from_posted_cash_bank_lines(self):
        doc = _doc()
        assert "cash" in doc.lower()
        assert "bank" in doc.lower()
        assert "journal_entry_lines" in doc

    def test_cashflow_requires_period_filter(self):
        doc = _doc()
        assert "cashflow" in doc.lower() or "Cashflow" in doc
        assert "period" in doc.lower()

    def test_cashflow_operating_investing_financing(self):
        doc = _doc()
        assert "operating" in doc.lower()
        assert "investing" in doc.lower()
        assert "financing" in doc.lower()


class TestContractRequiresTenantFilter:
    def test_contract_requires_tenant_filter(self):
        doc = _doc()
        assert "tenant_id" in doc
        assert "tenant" in doc.lower()

    def test_tenant_filter_mandatory_on_all_queries(self):
        doc = _doc()
        assert "Mandatory" in doc or "mandatory" in doc.lower() or "must" in doc.lower()
        assert "tenant_id" in doc

    def test_no_silent_default_tenant_fallback(self):
        doc = _doc()
        assert "default" in doc.lower()
        assert "silently" in doc.lower() or "silent" in doc.lower()

    def test_no_cross_tenant_aggregation(self):
        doc = _doc()
        assert "cross-tenant" in doc.lower() or "cross tenant" in doc.lower()

    def test_tenant_from_request_state(self):
        doc = _doc()
        assert "request.state.tenant_id" in doc


class TestContractRequiresPeriodOrDateFilter:
    def test_contract_requires_period_or_date_filter(self):
        doc = _doc()
        assert "period" in doc.lower()
        assert "date" in doc.lower()

    def test_period_filter_required_for_flow_reports(self):
        doc = _doc()
        assert "flow" in doc.lower() or "P&L" in doc
        assert "period" in doc.lower()

    def test_balance_sheet_uses_as_of_date(self):
        doc = _doc()
        assert "as-of" in doc.lower() or "as of" in doc.lower()
        assert "balance sheet" in doc.lower() or "Balance Sheet" in doc

    def test_period_definition_stated(self):
        doc = _doc()
        assert "2026-05" in doc or "period" in doc.lower()


class TestContractRequiresStatusPostedFilter:
    def test_contract_requires_status_posted_filter(self):
        doc = _doc()
        assert "status" in doc
        assert "posted" in doc.lower()
        assert "status='posted'" in doc or "status = 'posted'" in doc

    def test_voided_excluded_from_all_reports(self):
        doc = _doc()
        assert "voided" in doc.lower()
        assert "excluded" in doc.lower() or "exclude" in doc.lower()

    def test_status_filter_required_on_headers(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "status" in doc


class TestContractDefinesReversalCorrectionHandling:
    def test_contract_defines_reversal_correction_handling(self):
        doc = _doc()
        assert "Reversal" in doc or "reversal" in doc.lower()
        assert "Correction" in doc or "correction" in doc.lower()

    def test_reversed_entries_excluded_from_net_view(self):
        doc = _doc()
        assert "reversed" in doc.lower()
        assert "excluded" in doc.lower() or "net" in doc.lower()

    def test_correction_entries_included_in_net(self):
        doc = _doc()
        assert "correction" in doc.lower()
        assert "included" in doc.lower()

    def test_void_excluded_from_official_totals(self):
        doc = _doc()
        assert "voided" in doc.lower() or "void" in doc.lower()
        assert "excluded" in doc.lower()

    def test_no_destructive_edits_in_report_implementation(self):
        doc = _doc()
        assert "UPDATE" in doc or "DELETE" in doc or "destructive" in doc.lower()
        assert "append-only" in doc.lower() or "immutable" in doc.lower()

    def test_no_double_counting_original_and_correction(self):
        doc = _doc()
        assert "double-count" in doc.lower() or "double counting" in doc.lower()


class TestContractDefinesOpeningBalanceAndPeriodBoundaries:
    def test_contract_defines_opening_balance_and_period_boundaries(self):
        doc = _doc()
        assert "opening balance" in doc.lower() or "Opening balance" in doc
        assert "period" in doc.lower()

    def test_trial_balance_three_columns(self):
        doc = _doc()
        assert "opening" in doc.lower()
        assert "movement" in doc.lower()
        assert "closing" in doc.lower()

    def test_balance_sheet_cumulative_to_as_of_date(self):
        doc = _doc()
        assert "cumulative" in doc.lower()
        assert "as-of" in doc.lower() or "as of" in doc.lower()

    def test_pnl_period_only(self):
        doc = _doc()
        assert "period only" in doc.lower() or "period-only" in doc.lower() or \
               "selected period only" in doc.lower() or "selected period" in doc.lower()

    def test_cashflow_uses_period_opening_closing(self):
        doc = _doc()
        assert "cashflow" in doc.lower() or "Cashflow" in doc
        assert "opening" in doc.lower() and "closing" in doc.lower()


class TestContractForbidsRuntimeReportChangesInH7:
    def test_contract_forbids_runtime_report_changes_in_h7(self):
        doc = _doc()
        assert "financial_statements_service.py" in doc
        assert "not modified" in doc.lower() or "No runtime" in doc or "does not" in doc.lower()

    def test_contract_financial_statements_service_not_modified(self):
        doc = _doc()
        assert "financial_statements_service.py" in doc
        assert "Modify" in doc or "modify" in doc.lower()

    def test_contract_ledger_service_not_modified(self):
        doc = _doc()
        assert "ledger_service.py" in doc

    def test_contract_routes_reports_not_modified(self):
        doc = _doc()
        assert "routes_reports.py" in doc

    def test_contract_non_goals_section_exists(self):
        doc = _doc()
        assert "Non-Goals" in doc or "Non-goals" in doc or "non-goals" in doc.lower()

    def test_contract_h7_produces_only_two_files(self):
        doc = _doc()
        assert "docs/reports-posted-ledger-read-contract.md" in doc
        assert "tests/unit/test_reports_posted_ledger_read_contract.py" in doc


class TestContractForbidsSqlDbMigrationExecutionInH7:
    def test_contract_forbids_sql_db_migration_execution_in_h7(self):
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

    def test_contract_balance_ge_not_activated(self):
        doc = _doc()
        assert "Balance.ge" in doc
        assert "inactive" in doc.lower() or "remains" in doc.lower()


class TestContractDefinesFutureH8ToH12Sequence:
    def test_contract_defines_future_h8_to_h12_sequence(self):
        doc = _doc()
        assert "H8" in doc
        assert "H9" in doc
        assert "H10" in doc
        assert "H11" in doc
        assert "H12" in doc

    def test_contract_h8_is_report_query_mock_tests(self):
        doc = _doc()
        assert "H8" in doc
        assert "mock" in doc.lower() or "Mock" in doc

    def test_contract_h9_is_reversal_correction(self):
        doc = _doc()
        assert "H9" in doc
        assert "reversal" in doc.lower() or "Reversal" in doc

    def test_contract_h11_is_controlled_migration(self):
        doc = _doc()
        assert "H11" in doc
        assert "migration" in doc.lower()
        assert "local" in doc.lower() or "controlled" in doc.lower()

    def test_contract_h12_is_runtime_report_migration(self):
        doc = _doc()
        assert "H12" in doc
        assert "runtime" in doc.lower()


class TestFileHasNoRuntimeReportImports:
    def test_file_has_no_runtime_report_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {
            "financial_statements_service",
            "ledger_service",
            "routes_reports",
            "posting_service",
            "approval_service",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    assert f not in node.module, f"Forbidden import: {node.module}"

    def test_no_runtime_service_imports_at_all(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_prefixes = {"app.api", "app.core", "app.knowledge"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden_prefixes:
                    assert not node.module.startswith(prefix), \
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
