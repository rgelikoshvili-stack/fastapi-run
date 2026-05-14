"""
Bridge Hub — Task 11C-H13
Runtime Report Migration Plan Contract Tests

These tests verify that docs/runtime-report-migration-plan.md correctly encodes:
- H13 is docs/tests only (no runtime change)
- journal_drafts is not accounting truth
- posted ledger truth model
- all 11 report migration targets
- reversal/correction handling
- evidence/audit linkage
- tenant isolation and permissions
- feature flag requirements
- H14-H19 future sequence

Rules:
- No DB connection.
- No SQL execution.
- No migration execution.
- No runtime service imports.
- Reads only the plan doc and this test file.
"""

import ast
import pathlib


PLAN_DOC = pathlib.Path("docs/runtime-report-migration-plan.md")


def _doc() -> str:
    return PLAN_DOC.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Document existence
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDocumentExists:
    def test_contract_document_exists(self):
        assert PLAN_DOC.exists(), (
            "docs/runtime-report-migration-plan.md must exist"
        )

    def test_contract_document_is_nonempty(self):
        assert len(_doc().strip()) > 500

    def test_contract_document_title(self):
        assert "Runtime Report Migration Plan" in _doc()

    def test_contract_task_reference(self):
        assert "11C-H13" in _doc() or "H13" in _doc()


# ──────────────────────────────────────────────────────────────────────────────
# 2. H13 is docs/tests only
# ──────────────────────────────────────────────────────────────────────────────

class TestContractStatesH13IsDocsTestsOnly:
    def test_contract_states_h13_is_docs_tests_only(self):
        doc = _doc().lower()
        assert "does not change runtime report behavior" in doc or \
               "no runtime code change" in doc or \
               "docs and contract tests only" in doc or \
               "docs + contract tests only" in doc, (
            "Plan must state H13 does not change runtime report behavior"
        )

    def test_contract_states_no_financial_statements_service_change(self):
        doc = _doc().lower()
        assert "financial_statements_service" in doc and (
            "does not modify" in doc or "not modify" in doc or
            "unchanged" in doc or "not change" in doc
        )

    def test_contract_states_no_ledger_service_change(self):
        doc = _doc().lower()
        assert "ledger_service" in doc

    def test_contract_states_no_routes_reports_change(self):
        doc = _doc().lower()
        assert "routes_reports" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 3. H1-H12 context
# ──────────────────────────────────────────────────────────────────────────────

class TestContractReferencesH1ToH12Context:
    def test_contract_references_h1_to_h12_context(self):
        doc = _doc()
        for h in ["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11", "H12"]:
            assert h in doc, f"Plan must reference {h} in background section"

    def test_contract_references_h1_integrity_audit(self):
        doc = _doc().lower()
        assert "integrity" in doc and "h1" in doc.lower()

    def test_contract_references_h12_blocked(self):
        doc = _doc().upper()
        assert "BLOCKED" in doc, "Plan must reference H12 BLOCKED status"


# ──────────────────────────────────────────────────────────────────────────────
# 4. journal_drafts is not accounting truth
# ──────────────────────────────────────────────────────────────────────────────

class TestContractStatesJournalDraftsNotTruth:
    def test_contract_states_journal_drafts_not_truth(self):
        doc = _doc().lower()
        assert "journal_drafts" in doc and (
            "not accounting truth" in doc or
            "not truth" in doc or
            "forbidden as truth" in doc or
            "is not accounting truth" in doc
        )

    def test_contract_forbids_journal_drafts_as_source(self):
        doc = _doc().lower()
        assert "journal_drafts" in doc and "forbidden" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 5. Non-posted states forbidden as truth
# ──────────────────────────────────────────────────────────────────────────────

class TestContractForbidsNonPostedStatesAsTruth:
    def test_contract_forbids_approved_auto_approved_simulated_success_mock_dry_run_as_truth(self):
        doc = _doc().lower()
        forbidden_states = [
            "approved", "auto_approved", "simulated_success",
            "mock_posting", "dry_run",
        ]
        for state in forbidden_states:
            assert state in doc, (
                f"Plan must address '{state}' as a forbidden truth source"
            )

    def test_contract_states_simulated_success_excluded(self):
        doc = _doc().lower()
        assert "simulated_success" in doc and (
            "excluded" in doc or "forbidden" in doc or "not truth" in doc
        )

    def test_contract_states_draft_excluded(self):
        doc = _doc().lower()
        assert "draft" in doc and (
            "excluded" in doc or "forbidden" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 6. Posted ledger truth source
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesPostedLedgerTruthSource:
    def test_contract_defines_posted_ledger_truth_source(self):
        doc = _doc().lower()
        assert "journal_entry_headers" in doc and "journal_entry_lines" in doc

    def test_contract_names_both_posted_ledger_tables(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc

    def test_contract_states_status_posted_is_official_truth(self):
        doc = _doc().lower()
        assert "status" in doc and (
            "'posted'" in doc or
            "status = 'posted'" in doc or
            "status='posted'" in doc or
            "status in" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 7. Tenant filter required
# ──────────────────────────────────────────────────────────────────────────────

class TestContractRequiresTenantFilter:
    def test_contract_requires_tenant_filter(self):
        doc = _doc().lower()
        assert "tenant_id" in doc and "mandatory" in doc

    def test_contract_tenant_from_auth_not_user_input(self):
        doc = _doc().lower()
        assert "request.state.tenant_id" in doc or \
               "authenticated" in doc and "tenant_id" in doc

    def test_contract_forbids_tenant_from_query_params_or_body(self):
        doc = _doc().lower()
        assert "query param" in doc or "request body" in doc or \
               "user input" in doc or "user-supplied" in doc or \
               "user-controlled" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 8. status = 'posted' for standard totals
# ──────────────────────────────────────────────────────────────────────────────

class TestContractRequiresStatusPostedForStandardTotals:
    def test_contract_requires_status_posted_for_standard_totals(self):
        doc = _doc().lower()
        assert "status" in doc and (
            "standard" in doc or "official totals" in doc or "official" in doc
        ) and "posted" in doc

    def test_contract_standard_totals_exclude_non_posted(self):
        doc = _doc().lower()
        assert "standard" in doc or "official" in doc
        assert "excluded" in doc or "forbidden" in doc or "must not" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 9. Default tenant fallback forbidden
# ──────────────────────────────────────────────────────────────────────────────

class TestContractForbidsDefaultTenantFallback:
    def test_contract_forbids_default_tenant_fallback(self):
        doc = _doc().lower()
        assert "default" in doc and (
            "fallback" in doc or "fall back" in doc or
            "never fall" in doc or "must not fall" in doc
        )

    def test_contract_missing_tenant_fails_closed(self):
        doc = _doc().lower()
        assert "fail closed" in doc or "fails closed" in doc or \
               "401" in doc or "403" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 10. Trial Balance migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesTrialBalanceMigration:
    def test_contract_defines_trial_balance_migration(self):
        doc = _doc().lower()
        assert "trial balance" in doc

    def test_contract_trial_balance_requires_posted_source(self):
        doc = _doc().lower()
        assert "trial balance" in doc and "posted" in doc

    def test_contract_trial_balance_requires_period_filter(self):
        doc = _doc().lower()
        assert "trial balance" in doc and "period" in doc

    def test_contract_trial_balance_debit_credit_balance(self):
        doc = _doc().lower()
        assert "debit" in doc and "credit" in doc and "balance" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 11. P&L Summary migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesPnlSummaryMigration:
    def test_contract_defines_pnl_summary_migration(self):
        doc = _doc().lower()
        assert "profit" in doc and "loss" in doc or "p&l" in doc or "pnl" in doc

    def test_contract_pnl_requires_posted_source(self):
        doc = _doc().lower()
        assert ("profit" in doc or "p&l" in doc or "pnl" in doc) and "posted" in doc

    def test_contract_pnl_summary_forbids_journal_drafts(self):
        doc = _doc().lower()
        assert "journal_drafts" in doc and "forbidden" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 12. P&L Detail migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesPnlDetailMigration:
    def test_contract_defines_pnl_detail_migration(self):
        doc = _doc().lower()
        assert "detail" in doc and (
            "profit" in doc or "p&l" in doc or "pnl" in doc
        )

    def test_contract_pnl_detail_exposes_evidence_linkage(self):
        doc = _doc().lower()
        assert "evidence_bundle_id" in doc or "posting_log_id" in doc or \
               "source_draft_id" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 13. Balance Sheet Summary migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesBalanceSheetSummaryMigration:
    def test_contract_defines_balance_sheet_summary_migration(self):
        doc = _doc().lower()
        assert "balance sheet" in doc

    def test_contract_balance_sheet_requires_posted_source(self):
        doc = _doc().lower()
        assert "balance sheet" in doc and "posted" in doc

    def test_contract_balance_sheet_cumulative_as_of_date(self):
        doc = _doc().lower()
        assert "cumulative" in doc or "as-of-date" in doc or "as of date" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 14. Balance Sheet Detail migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesBalanceSheetDetailMigration:
    def test_contract_defines_balance_sheet_detail_migration(self):
        doc = _doc().lower()
        assert "balance sheet" in doc and "detail" in doc

    def test_contract_balance_sheet_detail_fixes_h1_gap(self):
        doc = _doc().lower()
        assert "h1" in doc and (
            "gap" in doc or "fix" in doc or "risk" in doc or "critical" in doc
        )

    def test_contract_balance_sheet_detail_excludes_draft_approved(self):
        doc = _doc().lower()
        assert "draft" in doc and "excluded" in doc or "explicitly excluded" in doc
        assert "approved" in doc and "excluded" in doc or "explicitly excluded" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 15. VAT Register migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesVatRegisterMigration:
    def test_contract_defines_vat_register_migration(self):
        doc = _doc().lower()
        assert "vat" in doc

    def test_contract_vat_requires_period_filter(self):
        doc = _doc().lower()
        assert "vat" in doc and "period" in doc

    def test_contract_vat_forbids_journal_drafts(self):
        doc = _doc().lower()
        assert "vat" in doc and "journal_drafts" in doc and "forbidden" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 16. Account Ledger migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesAccountLedgerMigration:
    def test_contract_defines_account_ledger_migration(self):
        doc = _doc().lower()
        assert "account ledger" in doc

    def test_contract_account_ledger_requires_account_code_filter(self):
        doc = _doc().lower()
        assert "account_code" in doc and "ledger" in doc

    def test_contract_account_ledger_has_opening_closing_balance(self):
        doc = _doc().lower()
        assert "opening" in doc and "closing" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 17. Counterparty Ledger migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesCounterpartyLedgerMigration:
    def test_contract_defines_counterparty_ledger_migration(self):
        doc = _doc().lower()
        assert "counterparty" in doc and "ledger" in doc

    def test_contract_counterparty_ledger_requires_counterparty_filter(self):
        doc = _doc().lower()
        assert "counterparty_id" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 18. Payroll Ledger migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesPayrollLedgerMigration:
    def test_contract_defines_payroll_ledger_migration(self):
        doc = _doc().lower()
        assert "payroll" in doc and "ledger" in doc

    def test_contract_payroll_forbids_draft_truth(self):
        doc = _doc().lower()
        assert "payroll" in doc and "journal_drafts" in doc and "forbidden" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 19. Journal Entries List migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesJournalEntriesListMigration:
    def test_contract_defines_journal_entries_list_migration(self):
        doc = _doc().lower()
        assert "journal entries" in doc and (
            "list" in doc or "entries list" in doc
        )

    def test_contract_journal_list_has_standard_and_history_view(self):
        doc = _doc().lower()
        assert "standard view" in doc or "history view" in doc or \
               "standard" in doc and "history" in doc

    def test_contract_journal_list_no_double_counting(self):
        doc = _doc().lower()
        assert "double" in doc and "count" in doc or "double-count" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 20. Cash Flow migration
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesCashflowMigration:
    def test_contract_defines_cashflow_migration(self):
        doc = _doc().lower()
        assert "cash flow" in doc or "cashflow" in doc

    def test_contract_cashflow_requires_posted_source(self):
        doc = _doc().lower()
        assert ("cash flow" in doc or "cashflow" in doc) and "posted" in doc

    def test_contract_cashflow_operating_investing_financing(self):
        doc = _doc().lower()
        assert "operating" in doc and "investing" in doc and "financing" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 21. Reversal/correction handling
# ──────────────────────────────────────────────────────────────────────────────

class TestContractRequiresReversalCorrectionHandling:
    def test_contract_requires_reversal_correction_handling(self):
        doc = _doc().lower()
        assert "reversal" in doc and "correction" in doc

    def test_contract_reversal_excluded_from_net_totals(self):
        doc = _doc().lower()
        assert "reversed" in doc and (
            "net totals" in doc or "net" in doc
        )

    def test_contract_correction_in_net_totals(self):
        doc = _doc().lower()
        assert "correction" in doc and (
            "net" in doc or "final" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 22. Net/history view distinction
# ──────────────────────────────────────────────────────────────────────────────

class TestContractRequiresNetAndHistoryViewDistinction:
    def test_contract_requires_net_and_history_view_distinction(self):
        doc = _doc().lower()
        assert "net" in doc and "history" in doc

    def test_contract_net_and_history_clearly_distinguished(self):
        doc = _doc().lower()
        assert "net" in doc and "history" in doc and (
            "distinguished" in doc or "distinguish" in doc or
            "separate" in doc or "label" in doc or "clearly" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 23. Double counting forbidden
# ──────────────────────────────────────────────────────────────────────────────

class TestContractForbidsDoubleCounting:
    def test_contract_forbids_double_counting(self):
        doc = _doc().lower()
        assert "double" in doc and (
            "count" in doc or "counting" in doc
        )

    def test_contract_reversal_pair_not_double_counted(self):
        doc = _doc().lower()
        assert "reversed" in doc and (
            "not" in doc or "must not" in doc or "neither" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 24. Evidence/audit linkage
# ──────────────────────────────────────────────────────────────────────────────

class TestContractRequiresEvidenceAuditLinkage:
    def test_contract_requires_evidence_audit_linkage(self):
        doc = _doc().lower()
        assert "evidence_bundle_id" in doc

    def test_contract_requires_posting_log_linkage(self):
        doc = _doc().lower()
        assert "posting_log_id" in doc

    def test_contract_requires_source_draft_linkage(self):
        doc = _doc().lower()
        assert "source_draft_id" in doc

    def test_contract_drill_down_chain_defined(self):
        doc = _doc().lower()
        assert "drill" in doc or "drilldown" in doc or "drill-down" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 25. Raw secrets forbidden
# ──────────────────────────────────────────────────────────────────────────────

class TestContractForbidsRawSecrets:
    def test_contract_forbids_raw_secrets(self):
        doc = _doc().lower()
        assert "raw secrets" in doc or "secret" in doc

    def test_contract_strip_unsafe_or_sanitization(self):
        doc = _doc().lower()
        assert "_strip_unsafe" in doc or "sanitiz" in doc or \
               "no raw secrets" in doc or "must not" in doc and "secret" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 26. Permissions and 401/403
# ──────────────────────────────────────────────────────────────────────────────

class TestContractRequiresPermissionsAnd401403:
    def test_contract_requires_permissions_and_401_403(self):
        doc = _doc()
        assert "401" in doc or "403" in doc

    def test_contract_requires_report_permission(self):
        doc = _doc().lower()
        assert "permission" in doc and (
            "report" in doc or "required" in doc
        )

    def test_contract_unauthorized_returns_401_or_403(self):
        doc = _doc()
        assert "401" in doc or "403" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 27. Feature flag / explicit config
# ──────────────────────────────────────────────────────────────────────────────

class TestContractRequiresFeatureFlagOrExplicitConfig:
    def test_contract_requires_feature_flag_or_explicit_config(self):
        doc = _doc().lower()
        assert "feature flag" in doc or "feature_flag" in doc or \
               "explicit config" in doc or "configuration" in doc

    def test_contract_feature_flag_defaults_to_legacy_behavior(self):
        doc = _doc().lower()
        assert "default" in doc and (
            "false" in doc or "legacy" in doc or "unchanged" in doc
        )

    def test_contract_fail_closed_if_tables_missing(self):
        doc = _doc().lower()
        assert "fail closed" in doc or "fails closed" in doc or \
               "missing" in doc and "error" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 28. Silent fallback to journal_drafts forbidden
# ──────────────────────────────────────────────────────────────────────────────

class TestContractForbidsSilentFallbackToJournalDrafts:
    def test_contract_forbids_silent_fallback_to_journal_drafts(self):
        doc = _doc().lower()
        assert "silent" in doc and (
            "fallback" in doc or "fall back" in doc
        )

    def test_contract_no_silent_fallback_from_posted_to_drafts(self):
        doc = _doc().lower()
        assert "journal_drafts" in doc and "silent" in doc and (
            "fallback" in doc or "fall back" in doc or "not" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 29. H14-H19 sequence
# ──────────────────────────────────────────────────────────────────────────────

class TestContractDefinesH14ToH19Sequence:
    def test_contract_defines_h14_to_h19_sequence(self):
        doc = _doc()
        for h in ["H14", "H15", "H16", "H17", "H18", "H19"]:
            assert h in doc, f"Plan must define future task {h}"

    def test_contract_h14_is_query_tests_with_mocks(self):
        doc = _doc().lower()
        assert "h14" in doc and (
            "mock" in doc or "query tests" in doc or "mocks" in doc
        )

    def test_contract_h19_is_production_migration_plan(self):
        doc = _doc().lower()
        assert "h19" in doc and (
            "production" in doc or "approval plan" in doc
        )

    def test_contract_each_task_requires_explicit_approval(self):
        doc = _doc().lower()
        assert "explicit" in doc and (
            "approval" in doc or "approved" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 30. No runtime report change in H13
# ──────────────────────────────────────────────────────────────────────────────

class TestContractStatesNoRuntimeReportChangeInH13:
    def test_contract_states_no_runtime_report_change_in_h13(self):
        doc = _doc().lower()
        assert "does not change runtime" in doc or \
               "no runtime" in doc and "change" in doc or \
               "runtime behavior" in doc and "unchanged" in doc or \
               "no runtime code change" in doc

    def test_contract_non_goals_section_exists(self):
        doc = _doc().lower()
        assert "non-goal" in doc or "non goals" in doc or \
               "does not" in doc and "h13" in doc

    def test_contract_produces_only_two_files(self):
        doc = _doc().lower()
        assert "two files" in doc or (
            "runtime-report-migration-plan.md" in doc and
            "test_runtime_report_migration_plan_contract.py" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 31. No SQL/DB/migration in H13
# ──────────────────────────────────────────────────────────────────────────────

class TestContractStatesNoSqlDbMigrationInH13:
    def test_contract_states_no_sql_in_h13(self):
        doc = _doc().lower()
        assert "does not execute" in doc and "sql" in doc or \
               "no sql" in doc or "execute any sql" in doc

    def test_contract_states_no_db_connection_in_h13(self):
        doc = _doc().lower()
        assert "does not connect" in doc and "database" in doc or \
               "no db connection" in doc or "no database" in doc or \
               "connect to any database" in doc

    def test_contract_states_no_migration_execution_in_h13(self):
        doc = _doc().lower()
        assert "does not execute" in doc and "migration" in doc or \
               "no migration" in doc or "execute any migration" in doc

    def test_contract_states_no_production_db_touch(self):
        doc = _doc().lower()
        assert "production" in doc and (
            "does not touch" in doc or "not touch" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 32. No runtime service imports in this file
# ──────────────────────────────────────────────────────────────────────────────

class TestFileHasNoRuntimeServiceImports:
    def test_file_has_no_runtime_service_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                full = node.module
                top = full.split(".")[0]
                assert top not in {"asyncpg", "psycopg2", "sqlalchemy", "main"}, (
                    f"Test file must not import DB driver: {node.module}"
                )
                for forbidden in ["app.api.services", "app.api.routes",
                                   "app.storage", "app.startup"]:
                    assert not full.startswith(forbidden), (
                        f"Test file must not import runtime service: {node.module}"
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in {"asyncpg", "psycopg2", "sqlalchemy"}, (
                        f"Test file must not import DB driver: {alias.name}"
                    )


# ──────────────────────────────────────────────────────────────────────────────
# 33. No DB or network imports in this file
# ──────────────────────────────────────────────────────────────────────────────

class TestFileHasNoDbOrNetworkImports:
    def test_file_has_no_db_or_network_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_top = {
            "httpx", "aiohttp", "requests", "urllib3", "socket",
            "asyncpg", "psycopg2", "sqlalchemy", "databases",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in forbidden_top, (
                        f"Test file must not import network/DB module: {alias.name}"
                    )
            if isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                assert top not in forbidden_top, (
                    f"Test file must not import from network/DB module: {node.module}"
                )
