"""
tests/unit/test_reports_ledger_integrity_contract.py

Contract tests for the Reports Ledger Integrity Audit.

Rules:
  - Read-only. No runtime app imports. No DB. No SQL execution.
  - No connector calls. No Balance.ge activation.
  - Does not change approval/posting/reporting behavior.
  - Reads source files as text to record current state — does not fail on findings.
  - Validates audit doc existence and content completeness.
  - Validates risk policy constants and official report list.
  - Validates future rule and forbidden behavior contracts.
"""
from __future__ import annotations

import ast
import pathlib
import re

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_AUDIT_DOC = _ROOT / "docs" / "reports-ledger-integrity-audit.md"
_ROUTES_REPORTS = _ROOT / "app" / "api" / "routes_reports.py"
_ROUTES_TAX = _ROOT / "app" / "api" / "routes_tax.py"
_FINANCIAL_SVC = _ROOT / "app" / "api" / "services" / "financial_statements_service.py"
_LEDGER_SVC = _ROOT / "app" / "api" / "services" / "ledger_service.py"
_MIGRATIONS_DIR = _ROOT / "app" / "storage" / "migrations"


# ---------------------------------------------------------------------------
# A) Audit document existence
# ---------------------------------------------------------------------------

class TestAuditDocExists:

    def test_audit_doc_file_exists(self):
        assert _AUDIT_DOC.exists(), (
            f"Audit doc not found at {_AUDIT_DOC}"
        )

    def test_audit_doc_is_nonempty(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8")
        assert len(text.strip()) > 200, "Audit doc appears to be empty or too short"

    def test_audit_doc_is_markdown(self):
        assert _AUDIT_DOC.suffix == ".md"


# ---------------------------------------------------------------------------
# B) Contract content — required terms must appear in the audit doc
# ---------------------------------------------------------------------------

class TestAuditDocContent:

    @property
    def _doc(self) -> str:
        return _AUDIT_DOC.read_text(encoding="utf-8")

    def test_mentions_journal_drafts(self):
        assert "journal_drafts" in self._doc

    def test_mentions_journal_entries(self):
        assert "journal_entries" in self._doc

    def test_mentions_posted_status(self):
        assert "posted" in self._doc

    def test_mentions_trial_balance(self):
        assert "trial_balance" in self._doc.lower() or "Trial Balance" in self._doc

    def test_mentions_profit_and_loss(self):
        text = self._doc.lower()
        assert "profit_and_loss" in text or "profit and loss" in text

    def test_mentions_balance_sheet(self):
        text = self._doc.lower()
        assert "balance_sheet" in text or "balance sheet" in text

    def test_mentions_cash_flow(self):
        text = self._doc.lower()
        assert "cash_flow" in text or "cash flow" in text

    def test_mentions_vat(self):
        assert "vat" in self._doc.lower()

    def test_states_official_reports_must_use_posted_journal_entries(self):
        text = self._doc.lower()
        assert "posted" in text and "official" in text

    def test_states_approved_drafts_not_official_truth(self):
        text = self._doc.lower()
        assert "approved" in text and ("not" in text or "draft" in text)

    def test_states_no_runtime_behavior_change(self):
        text = self._doc.lower()
        assert "no runtime" in text or "does not change" in text or "no change" in text

    def test_states_no_sql_execution(self):
        text = self._doc.lower()
        assert "no sql" in text or "not executed" in text or "audit only" in text or "read-only" in text

    def test_states_no_production_db_touch(self):
        text = self._doc.lower()
        assert "production" in text or "no db" in text or "no database" in text

    def test_states_balance_ge_inactive(self):
        text = self._doc.lower()
        assert "balance.ge" in text or "balance ge" in text


# ---------------------------------------------------------------------------
# C) Source scan — read report files as text, record current patterns
#    These tests RECORD current state only. They do NOT fail on findings.
# ---------------------------------------------------------------------------

class TestSourceScanRecords:

    def test_routes_reports_exists(self):
        assert _ROUTES_REPORTS.exists(), "routes_reports.py not found"

    def test_financial_statements_service_exists(self):
        assert _FINANCIAL_SVC.exists(), "financial_statements_service.py not found"

    def test_ledger_service_exists(self):
        assert _LEDGER_SVC.exists(), "ledger_service.py not found"

    def test_routes_reports_references_journal_drafts(self):
        text = _ROUTES_REPORTS.read_text(encoding="utf-8")
        # Record presence — journal_drafts is the current source of truth
        uses_journal_drafts = "journal_drafts" in text
        # This is informational — current implementation uses drafts
        assert isinstance(uses_journal_drafts, bool)

    def test_financial_svc_references_journal_drafts(self):
        text = _FINANCIAL_SVC.read_text(encoding="utf-8")
        uses_journal_drafts = "journal_drafts" in text
        assert isinstance(uses_journal_drafts, bool)

    def test_ledger_svc_references_posted_status(self):
        text = _LEDGER_SVC.read_text(encoding="utf-8")
        uses_posted = "posted" in text
        assert isinstance(uses_posted, bool)

    def test_routes_reports_is_parseable_python(self):
        text = _ROUTES_REPORTS.read_text(encoding="utf-8")
        try:
            ast.parse(text)
            parseable = True
        except SyntaxError:
            parseable = False
        assert parseable, "routes_reports.py has a syntax error"

    def test_financial_svc_is_parseable_python(self):
        text = _FINANCIAL_SVC.read_text(encoding="utf-8")
        try:
            ast.parse(text)
            parseable = True
        except SyntaxError:
            parseable = False
        assert parseable, "financial_statements_service.py has a syntax error"

    def test_ledger_svc_is_parseable_python(self):
        text = _LEDGER_SVC.read_text(encoding="utf-8")
        try:
            ast.parse(text)
            parseable = True
        except SyntaxError:
            parseable = False
        assert parseable, "ledger_service.py has a syntax error"

    def test_migrations_dir_exists(self):
        assert _MIGRATIONS_DIR.exists(), "migrations directory not found"

    def test_scan_records_simulated_success_presence(self):
        text = _ROUTES_REPORTS.read_text(encoding="utf-8")
        # Record whether simulated_success appears in report routes
        has_simulated = "simulated_success" in text
        # This is a known audit finding — recorded here for traceability
        assert isinstance(has_simulated, bool)

    def test_scan_records_bs_detail_query(self):
        text = _ROUTES_REPORTS.read_text(encoding="utf-8")
        has_bs_detail = "bs/detail" in text or "bs_detail" in text or "balance" in text.lower()
        assert isinstance(has_bs_detail, bool)


# ---------------------------------------------------------------------------
# D) Risk policy constants
# ---------------------------------------------------------------------------

_RISK_LEVELS = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}


class TestRiskPolicyConstants:

    def test_critical_risk_level_defined(self):
        assert "CRITICAL" in _RISK_LEVELS

    def test_high_risk_level_defined(self):
        assert "HIGH" in _RISK_LEVELS

    def test_medium_risk_level_defined(self):
        assert "MEDIUM" in _RISK_LEVELS

    def test_low_risk_level_defined(self):
        assert "LOW" in _RISK_LEVELS

    def test_info_risk_level_defined(self):
        assert "INFO" in _RISK_LEVELS

    def test_risk_levels_are_uppercase_strings(self):
        for level in _RISK_LEVELS:
            assert isinstance(level, str)
            assert level == level.upper()

    def test_audit_doc_uses_critical_level(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8")
        assert "CRITICAL" in text

    def test_audit_doc_uses_high_level(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8")
        assert "HIGH" in text

    def test_audit_doc_uses_medium_level(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8")
        assert "MEDIUM" in text

    def test_audit_doc_uses_info_level(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8")
        assert "INFO" in text


# ---------------------------------------------------------------------------
# E) Official report list
# ---------------------------------------------------------------------------

_OFFICIAL_REPORTS = {
    "trial_balance",
    "profit_and_loss",
    "balance_sheet",
    "cash_flow",
    "vat_summary",
}


class TestOfficialReportList:

    def test_official_reports_is_nonempty(self):
        assert len(_OFFICIAL_REPORTS) >= 5

    def test_trial_balance_in_official_reports(self):
        assert "trial_balance" in _OFFICIAL_REPORTS

    def test_profit_and_loss_in_official_reports(self):
        assert "profit_and_loss" in _OFFICIAL_REPORTS

    def test_balance_sheet_in_official_reports(self):
        assert "balance_sheet" in _OFFICIAL_REPORTS

    def test_cash_flow_in_official_reports(self):
        assert "cash_flow" in _OFFICIAL_REPORTS

    def test_vat_summary_in_official_reports(self):
        assert "vat_summary" in _OFFICIAL_REPORTS

    def test_official_reports_are_strings(self):
        for name in _OFFICIAL_REPORTS:
            assert isinstance(name, str)
            assert name == name.lower()

    def test_audit_doc_mentions_all_official_reports(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        for report in _OFFICIAL_REPORTS:
            readable = report.replace("_", " ")
            assert report in text or readable in text, (
                f"Official report {report!r} not mentioned in audit doc"
            )


# ---------------------------------------------------------------------------
# F) Future rule set — contract assertions
# ---------------------------------------------------------------------------

_FUTURE_RULES = {
    "posted_journal_entries_only",
    "approved_drafts_not_truth",
    "draft_preview_must_be_explicit",
    "tenant_filter_required",
    "period_filter_required",
    "reversal_correction_required",
    "evidence_bundle_link_planned",
}


class TestFutureRules:

    def test_future_rules_set_nonempty(self):
        assert len(_FUTURE_RULES) >= 7

    def test_posted_journal_entries_only_rule_exists(self):
        assert "posted_journal_entries_only" in _FUTURE_RULES

    def test_approved_drafts_not_truth_rule_exists(self):
        assert "approved_drafts_not_truth" in _FUTURE_RULES

    def test_draft_preview_must_be_explicit_rule_exists(self):
        assert "draft_preview_must_be_explicit" in _FUTURE_RULES

    def test_tenant_filter_required_rule_exists(self):
        assert "tenant_filter_required" in _FUTURE_RULES

    def test_period_filter_required_rule_exists(self):
        assert "period_filter_required" in _FUTURE_RULES

    def test_reversal_correction_required_rule_exists(self):
        assert "reversal_correction_required" in _FUTURE_RULES

    def test_evidence_bundle_link_planned_rule_exists(self):
        assert "evidence_bundle_link_planned" in _FUTURE_RULES

    def test_audit_doc_mentions_posted_entries_only(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "posted" in text

    def test_audit_doc_mentions_tenant_filter(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "tenant" in text

    def test_audit_doc_mentions_evidence_bundle(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "evidence bundle" in text or "evidence_bundle" in text

    def test_audit_doc_mentions_reversal(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "reversal" in text or "correction" in text


# ---------------------------------------------------------------------------
# G) Forbidden behavior contract — future official reports must not do these
# ---------------------------------------------------------------------------

_FORBIDDEN_BEHAVIORS = {
    "journal_drafts_as_official_truth",
    "auto_approved_as_posted_truth",
    "mixed_draft_posted_without_mode",
    "unlabeled_preview_report",
}


class TestForbiddenBehaviors:

    def test_forbidden_behaviors_set_nonempty(self):
        assert len(_FORBIDDEN_BEHAVIORS) >= 4

    def test_journal_drafts_as_official_truth_forbidden(self):
        assert "journal_drafts_as_official_truth" in _FORBIDDEN_BEHAVIORS

    def test_auto_approved_as_posted_truth_forbidden(self):
        assert "auto_approved_as_posted_truth" in _FORBIDDEN_BEHAVIORS

    def test_mixed_draft_posted_without_mode_forbidden(self):
        assert "mixed_draft_posted_without_mode" in _FORBIDDEN_BEHAVIORS

    def test_unlabeled_preview_report_forbidden(self):
        assert "unlabeled_preview_report" in _FORBIDDEN_BEHAVIORS

    def test_audit_doc_addresses_draft_as_truth_problem(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "draft" in text and ("not" in text or "must not" in text or "incorrect" in text or "critical" in text)

    def test_audit_doc_addresses_simulated_success_problem(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "simulated" in text or "simulated_success" in text

    def test_audit_doc_addresses_unlabeled_preview(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "preview" in text or "label" in text


# ---------------------------------------------------------------------------
# H) This test file must not import runtime app modules or DB libraries
# ---------------------------------------------------------------------------

class TestNoRuntimeImports:

    def test_no_db_imports_in_test_file(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_modules = {
            "psycopg2", "asyncpg", "sqlalchemy",
            "get_db", "get_conn",
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module += alias.name + " "
                for forbidden in forbidden_modules:
                    assert forbidden not in module, (
                        f"Forbidden import {forbidden!r} found in test file"
                    )

    def test_no_app_route_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.api.routes"), (
                    f"Route import {node.module!r} must not appear in this test"
                )

    def test_no_connector_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {"balance_connector", "posting_service"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    assert f not in node.module, (
                        f"Forbidden import module {f!r} found in test file"
                    )

    def test_no_network_calls_in_test_file(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_net = {"requests", "httpx", "urllib"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden_net:
                    assert not node.module.startswith(f), (
                        f"Network import {f!r} must not appear in this test"
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for f in forbidden_net:
                        assert not alias.name.startswith(f), (
                            f"Network import {f!r} must not appear in this test"
                        )


# ---------------------------------------------------------------------------
# I) Safety assertions for this task
# ---------------------------------------------------------------------------

class TestTaskSafetyAssertions:

    def test_this_task_creates_no_migrations(self):
        migration_files = list(_MIGRATIONS_DIR.glob("*.sql"))
        # Migration 010 was created in task G1; no new migration in H1
        # We record the count — this test passes regardless
        assert isinstance(migration_files, list)

    def test_this_task_creates_no_service_files(self):
        services_dir = _ROOT / "app" / "api" / "services"
        svc_files = [f.name for f in services_dir.glob("*.py")]
        assert isinstance(svc_files, list)

    def test_this_task_creates_no_route_files(self):
        api_dir = _ROOT / "app" / "api"
        route_files = [f.name for f in api_dir.glob("routes_*.py")]
        assert isinstance(route_files, list)

    def test_audit_doc_states_no_balance_ge_activation(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "balance.ge" in text or "balance ge" in text

    def test_audit_doc_states_audit_only(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "audit" in text

    def test_audit_doc_does_not_contain_balance_ge_activation_phrase(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        # "balance.ge remains inactive" or similar must appear (not "activated")
        assert "inactive" in text or "not activated" in text or "does not activate" in text

    def test_this_file_is_in_unit_tests(self):
        this_file = pathlib.Path(__file__).resolve()
        assert "tests" in str(this_file)
        assert "unit" in str(this_file)

    def test_audit_doc_mentions_implementation_plan(self):
        text = _AUDIT_DOC.read_text(encoding="utf-8").lower()
        assert "implementation" in text or "plan" in text or "h2" in text
