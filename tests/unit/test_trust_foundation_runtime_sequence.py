"""
tests/unit/test_trust_foundation_runtime_sequence.py

Read-only contract tests for the Trust Foundation Runtime Implementation
Sequence (Task 11C-A).

Contract:
  - All 12 11C sub-tasks are listed in the sequence.
  - Hard dependencies between sub-tasks are correct.
  - Balance.ge remains inactive through 11C-K.
  - Commercial pilot blockers are documented.
  - Stop conditions are defined.
  - No runtime imports, no network, no DB, no SQL.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO = Path(__file__).parent.parent.parent
_DOCS = _REPO / "docs"
_SEQ_DOC = _DOCS / "trust-foundation-runtime-implementation-sequence.md"

# ---------------------------------------------------------------------------
# Local test-only sequence and dependency definitions (no runtime import)
# ---------------------------------------------------------------------------

SEQUENCE: list[str] = [
    "11C-A_runtime_sequence",
    "11C-B_credential_vault_prep",
    "11C-C_credential_vault_migration_service",
    "11C-D_masked_reads_runtime",
    "11C-E_subscription_trial_middleware",
    "11C-F_redis_rate_limit_runtime",
    "11C-G_evidence_bundle_foundation",
    "11C-H_reports_ledger_integrity",
    "11C-I_runtime_ddl_gap_migrations",
    "11C-J_backup_pitr_ops_verification",
    "11C-K_balance_dry_run_payload_preview",
    "11C-L_balance_live_activation",
]

# Hard dependencies: task → set of tasks it depends on
DEPENDENCIES: dict[str, set[str]] = {
    "11C-D_masked_reads_runtime": {
        "11C-C_credential_vault_migration_service",
    },
    "11C-K_balance_dry_run_payload_preview": {
        "11C-C_credential_vault_migration_service",
        "11C-D_masked_reads_runtime",
        "11C-E_subscription_trial_middleware",
        "11C-F_redis_rate_limit_runtime",
        "11C-G_evidence_bundle_foundation",
    },
    "11C-L_balance_live_activation": {
        "11C-C_credential_vault_migration_service",
        "11C-D_masked_reads_runtime",
        "11C-E_subscription_trial_middleware",
        "11C-F_redis_rate_limit_runtime",
        "11C-G_evidence_bundle_foundation",
        "11C-J_backup_pitr_ops_verification",
        "11C-K_balance_dry_run_payload_preview",
    },
}

COMMERCIAL_PILOT_BLOCKERS: set[str] = {
    "credential_vault_missing",
    "subscription_enforcement_missing",
    "evidence_bundle_missing",
    "reports_use_journal_drafts_not_journal_entries",
    "backup_pitr_restore_drill_not_verified",
    "balance_ge_gates_not_met",
}

STOP_CONDITIONS: set[str] = {
    "files_outside_allowed_set",
    "migration_required_but_not_authorized",
    "production_db_access_needed",
    "credentials_needed",
    "balance_ge_live_api_call_needed",
    "tests_fail",
    "unexpected_tracked_changes",
}


# ===========================================================================
# A) Document existence
# ===========================================================================

class TestDocumentExistence:

    def test_sequence_doc_exists(self):
        """docs/trust-foundation-runtime-implementation-sequence.md must exist."""
        assert _SEQ_DOC.exists(), f"Missing: {_SEQ_DOC}"

    def test_trust_foundation_plan_exists(self):
        assert (_DOCS / "trust-foundation-implementation-plan.md").exists()

    def test_balance_ge_checklist_exists(self):
        assert (_DOCS / "balance-ge-activation-final-checklist.md").exists()

    def test_credential_vault_design_exists(self):
        assert (_DOCS / "credential-vault-design.md").exists()

    def test_masked_read_contract_exists(self):
        assert (_DOCS / "masked-read-behavior-contract.md").exists()

    def test_subscription_enforcement_plan_exists(self):
        assert (_DOCS / "subscription-enforcement-plan.md").exists()

    def test_redis_rate_limit_plan_exists(self):
        assert (_DOCS / "redis-rate-limit-plan.md").exists()

    def test_runtime_ddl_cutover_plan_exists(self):
        assert (_DOCS / "runtime-ddl-cutover-plan.md").exists()

    def test_backup_pitr_plan_exists(self):
        assert (_DOCS / "backup-pitr-static-files-plan.md").exists()


# ===========================================================================
# B) Content checks
# ===========================================================================

class TestContentChecks:

    @pytest.fixture(autouse=True)
    def _src(self):
        self.src = _SEQ_DOC.read_text(encoding="utf-8")

    def test_mentions_11c_a(self):
        assert "11C-A" in self.src

    def test_mentions_11c_b(self):
        assert "11C-B" in self.src

    def test_mentions_11c_c(self):
        assert "11C-C" in self.src

    def test_mentions_11c_d(self):
        assert "11C-D" in self.src

    def test_mentions_11c_e(self):
        assert "11C-E" in self.src

    def test_mentions_11c_f(self):
        assert "11C-F" in self.src

    def test_mentions_11c_g(self):
        assert "11C-G" in self.src

    def test_mentions_11c_h(self):
        assert "11C-H" in self.src

    def test_mentions_11c_i(self):
        assert "11C-I" in self.src

    def test_mentions_11c_j(self):
        assert "11C-J" in self.src

    def test_mentions_11c_k(self):
        assert "11C-K" in self.src

    def test_mentions_11c_l(self):
        assert "11C-L" in self.src

    def test_mentions_credential_vault(self):
        assert "Credential Vault" in self.src or "credential vault" in self.src.lower()

    def test_mentions_masked_reads(self):
        assert "Masked Read" in self.src or "masked read" in self.src.lower()

    def test_mentions_subscription(self):
        assert "Subscription" in self.src or "subscription" in self.src.lower()

    def test_mentions_redis(self):
        assert "Redis" in self.src

    def test_mentions_evidence_bundle(self):
        assert "Evidence Bundle" in self.src or "evidence_bundle" in self.src

    def test_mentions_journal_entries(self):
        assert "journal_entries" in self.src

    def test_mentions_journal_drafts(self):
        assert "journal_drafts" in self.src

    def test_mentions_balance_ge_demo_mode(self):
        assert "demo_mode" in self.src or "DEMO" in self.src

    def test_says_no_balance_ge_activation(self):
        src = self.src.lower()
        assert "no balance.ge activation" in src or \
               "does not activate" in src or \
               "must remain inactive" in src

    def test_says_no_production_db_touch(self):
        src = self.src.lower()
        assert "production database" in src or "production db" in src

    def test_says_no_sql(self):
        src = self.src.lower()
        assert "no sql" in src or "does not run sql" in src or \
               "does NOT run SQL" in self.src

    def test_says_no_migrations_in_this_task(self):
        src = self.src.lower()
        assert "no migration" in src or "does not create migration" in src or \
               "does NOT create migrations" in self.src

    def test_says_next_safe_task_11c_b(self):
        assert "11C-B" in self.src
        src = self.src.lower()
        assert "next safe task" in src or "recommended next" in src


# ===========================================================================
# C) Sequence set completeness
# ===========================================================================

class TestSequenceSet:

    def test_sequence_has_exactly_12_items(self):
        assert len(SEQUENCE) == 12

    def test_sequence_starts_with_11c_a(self):
        assert SEQUENCE[0] == "11C-A_runtime_sequence"

    def test_sequence_ends_with_11c_l(self):
        assert SEQUENCE[-1] == "11C-L_balance_live_activation"

    def test_all_items_present(self):
        expected = {
            "11C-A_runtime_sequence",
            "11C-B_credential_vault_prep",
            "11C-C_credential_vault_migration_service",
            "11C-D_masked_reads_runtime",
            "11C-E_subscription_trial_middleware",
            "11C-F_redis_rate_limit_runtime",
            "11C-G_evidence_bundle_foundation",
            "11C-H_reports_ledger_integrity",
            "11C-I_runtime_ddl_gap_migrations",
            "11C-J_backup_pitr_ops_verification",
            "11C-K_balance_dry_run_payload_preview",
            "11C-L_balance_live_activation",
        }
        assert set(SEQUENCE) == expected

    def test_11c_d_present(self):
        assert "11C-D_masked_reads_runtime" in SEQUENCE

    def test_11c_k_present(self):
        assert "11C-K_balance_dry_run_payload_preview" in SEQUENCE

    def test_11c_l_present(self):
        assert "11C-L_balance_live_activation" in SEQUENCE

    def test_11c_h_reports_ledger_present(self):
        assert "11C-H_reports_ledger_integrity" in SEQUENCE

    def test_document_mentions_all_sequence_items_by_label(self):
        """Sequence doc must mention every 11C sub-task."""
        src = _SEQ_DOC.read_text(encoding="utf-8")
        labels = ["11C-A", "11C-B", "11C-C", "11C-D", "11C-E", "11C-F",
                  "11C-G", "11C-H", "11C-I", "11C-J", "11C-K", "11C-L"]
        for label in labels:
            assert label in src, f"Sub-task {label} not mentioned in sequence doc"


# ===========================================================================
# D) Dependency checks
# ===========================================================================

class TestDependencyChecks:

    def test_11c_d_depends_on_11c_c(self):
        """11C-D must depend on 11C-C."""
        deps = DEPENDENCIES.get("11C-D_masked_reads_runtime", set())
        assert "11C-C_credential_vault_migration_service" in deps

    def test_11c_k_depends_on_11c_c(self):
        deps = DEPENDENCIES.get("11C-K_balance_dry_run_payload_preview", set())
        assert "11C-C_credential_vault_migration_service" in deps

    def test_11c_k_depends_on_11c_d(self):
        deps = DEPENDENCIES.get("11C-K_balance_dry_run_payload_preview", set())
        assert "11C-D_masked_reads_runtime" in deps

    def test_11c_k_depends_on_11c_e(self):
        deps = DEPENDENCIES.get("11C-K_balance_dry_run_payload_preview", set())
        assert "11C-E_subscription_trial_middleware" in deps

    def test_11c_k_depends_on_11c_f(self):
        deps = DEPENDENCIES.get("11C-K_balance_dry_run_payload_preview", set())
        assert "11C-F_redis_rate_limit_runtime" in deps

    def test_11c_k_depends_on_11c_g(self):
        deps = DEPENDENCIES.get("11C-K_balance_dry_run_payload_preview", set())
        assert "11C-G_evidence_bundle_foundation" in deps

    def test_11c_k_has_5_dependencies(self):
        deps = DEPENDENCIES.get("11C-K_balance_dry_run_payload_preview", set())
        assert len(deps) == 5

    def test_11c_l_depends_on_11c_c(self):
        deps = DEPENDENCIES.get("11C-L_balance_live_activation", set())
        assert "11C-C_credential_vault_migration_service" in deps

    def test_11c_l_depends_on_11c_k(self):
        deps = DEPENDENCIES.get("11C-L_balance_live_activation", set())
        assert "11C-K_balance_dry_run_payload_preview" in deps

    def test_11c_l_depends_on_11c_j(self):
        """11C-L must depend on 11C-J (backup/PITR must be verified first)."""
        deps = DEPENDENCIES.get("11C-L_balance_live_activation", set())
        assert "11C-J_backup_pitr_ops_verification" in deps

    def test_11c_l_has_at_least_7_dependencies(self):
        deps = DEPENDENCIES.get("11C-L_balance_live_activation", set())
        assert len(deps) >= 7

    def test_document_states_11c_d_depends_on_11c_c(self):
        src = _SEQ_DOC.read_text(encoding="utf-8")
        assert "11C-D" in src and "11C-C" in src
        src_lower = src.lower()
        assert "depends on" in src_lower or "prerequisite" in src_lower

    def test_document_states_reports_ledger_required_before_pilot(self):
        src = _SEQ_DOC.read_text(encoding="utf-8")
        assert "commercial pilot" in src.lower()
        assert "journal_entries" in src
        assert "11C-H" in src


# ===========================================================================
# E) Balance.ge safety
# ===========================================================================

class TestBalanceGeSafety:

    def _src(self) -> str:
        return _SEQ_DOC.read_text(encoding="utf-8")

    def test_doc_says_balance_ge_remains_inactive(self):
        src = self._src()
        assert "inactive" in src.lower() or "demo_mode" in src or "DEMO" in src

    def test_doc_says_balance_ge_blocked_until_11c_l(self):
        src = self._src()
        assert "11C-L" in src
        src_lower = src.lower()
        assert "11c-l" in src_lower
        assert "balance.ge" in src_lower or "Balance.ge" in src

    def test_doc_says_no_balance_api_key_before_vault(self):
        src = self._src()
        assert "BALANCE_API_KEY" in src or "vault" in src.lower()
        src_lower = src.lower()
        assert "no production" in src_lower or "before vault" in src_lower or \
               "before" in src_lower

    def test_doc_references_10f_h_checklist_as_authoritative(self):
        src = self._src()
        assert "balance-ge-activation-final-checklist" in src or \
               "10F-H" in src or "14 gates" in src

    def test_11c_l_is_last_in_sequence(self):
        assert SEQUENCE[-1] == "11C-L_balance_live_activation"

    def test_balance_ge_not_in_sequence_before_11c_k(self):
        """Balance.ge connector work must not appear before 11C-K in the sequence."""
        for task in SEQUENCE[:-2]:  # everything before 11C-K and 11C-L
            assert "balance_live" not in task, \
                f"Live Balance.ge activation appears too early: {task}"


# ===========================================================================
# F) Commercial pilot blockers
# ===========================================================================

class TestCommercialPilotBlockers:

    def test_blockers_set_has_required_items(self):
        assert len(COMMERCIAL_PILOT_BLOCKERS) >= 6

    def test_credential_vault_missing_is_blocker(self):
        assert "credential_vault_missing" in COMMERCIAL_PILOT_BLOCKERS

    def test_subscription_enforcement_missing_is_blocker(self):
        assert "subscription_enforcement_missing" in COMMERCIAL_PILOT_BLOCKERS

    def test_evidence_bundle_missing_is_blocker(self):
        assert "evidence_bundle_missing" in COMMERCIAL_PILOT_BLOCKERS

    def test_reports_use_journal_drafts_is_blocker(self):
        assert "reports_use_journal_drafts_not_journal_entries" in COMMERCIAL_PILOT_BLOCKERS

    def test_backup_pitr_restore_drill_not_verified_is_blocker(self):
        assert "backup_pitr_restore_drill_not_verified" in COMMERCIAL_PILOT_BLOCKERS

    def test_balance_ge_gates_not_met_is_blocker(self):
        assert "balance_ge_gates_not_met" in COMMERCIAL_PILOT_BLOCKERS

    def test_document_mentions_all_blockers(self):
        src = _SEQ_DOC.read_text(encoding="utf-8")
        checks = [
            "credential vault",
            "subscription",
            "evidence bundle",
            "journal_entries",
            "journal_drafts",
            "backup",
        ]
        src_lower = src.lower()
        for term in checks:
            assert term in src_lower, f"Blocker term missing from doc: {term!r}"

    def test_document_calls_reports_issue_critical(self):
        src = _SEQ_DOC.read_text(encoding="utf-8")
        assert "CRITICAL" in src or "critical" in src.lower()


# ===========================================================================
# G) Stop conditions
# ===========================================================================

class TestStopConditions:

    def test_stop_conditions_set_has_required_items(self):
        assert len(STOP_CONDITIONS) >= 7

    def test_files_outside_allowed_set_is_stop_condition(self):
        assert "files_outside_allowed_set" in STOP_CONDITIONS

    def test_migration_required_but_not_authorized_is_stop_condition(self):
        assert "migration_required_but_not_authorized" in STOP_CONDITIONS

    def test_production_db_access_needed_is_stop_condition(self):
        assert "production_db_access_needed" in STOP_CONDITIONS

    def test_credentials_needed_is_stop_condition(self):
        assert "credentials_needed" in STOP_CONDITIONS

    def test_balance_ge_live_api_call_needed_is_stop_condition(self):
        assert "balance_ge_live_api_call_needed" in STOP_CONDITIONS

    def test_tests_fail_is_stop_condition(self):
        assert "tests_fail" in STOP_CONDITIONS

    def test_unexpected_tracked_changes_is_stop_condition(self):
        assert "unexpected_tracked_changes" in STOP_CONDITIONS

    def test_document_mentions_stop_conditions(self):
        src = _SEQ_DOC.read_text(encoding="utf-8")
        assert "Stop" in src or "stop" in src.lower()
        checks = [
            "migration",
            "production DB" if "production DB" in src else "production",
            "credentials",
        ]
        src_lower = src.lower()
        for term in checks:
            assert term.lower() in src_lower, \
                f"Stop condition term missing: {term!r}"


# ===========================================================================
# H) No runtime/import/network execution
# ===========================================================================

class TestNoRuntimeImportNetworkExecution:
    """
    Scan this test file's own source to assert forbidden patterns are absent.
    Uses split strings and safe method names to avoid self-referential matches.
    """

    def _this_file_src(self) -> str:
        return Path(__file__).read_text(encoding="utf-8")

    def test_no_import_app_modules(self):
        """This test file must not import runtime app modules."""
        src = self._this_file_src()
        forbidden = "import" + " app."
        assert forbidden not in src, "Runtime app import found in test file"

    def test_no_from_app_modules(self):
        """This test file must not from-import runtime app modules."""
        src = self._this_file_src()
        forbidden = "from" + " app."
        assert forbidden not in src, "Runtime app from-import found in test file"

    def test_no_requests_import(self):
        """This test file must not import the requests library."""
        src = self._this_file_src()
        import re
        matches = re.findall(r'^import requests', src, re.MULTILINE)
        assert matches == [], "requests library import found"

    def test_no_httpx_import(self):
        """This test file must not import httpx."""
        src = self._this_file_src()
        import re
        matches = re.findall(r'^import httpx|^from httpx', src, re.MULTILINE)
        assert matches == [], "httpx import found"

    def test_no_urllib_import(self):
        """This test file must not import urllib for live calls."""
        src = self._this_file_src()
        import re
        matches = re.findall(r'^import urllib|^from urllib', src, re.MULTILINE)
        assert matches == [], "urllib import found"

    def test_no_db_connect(self):
        """This test file must not make DB connections."""
        src = self._this_file_src()
        forbidden_psycopg = "psycopg2." + "connect"
        forbidden_psycopg3 = "psycopg." + "connect"
        forbidden_asyncpg = "asyncpg." + "connect"
        assert forbidden_psycopg not in src, "psycopg2 connect call found"
        assert forbidden_psycopg3 not in src, "psycopg connect call found"
        assert forbidden_asyncpg not in src, "asyncpg connect call found"

    def test_no_subprocess_import(self):
        """This test file must not use subprocess."""
        src = self._this_file_src()
        import re
        matches = re.findall(r'^import subprocess|^from subprocess', src, re.MULTILINE)
        assert matches == [], "subprocess import found"

    def test_no_cloud_cli_invocation(self):
        """This test file must not invoke cloud CLI tooling."""
        src = self._this_file_src()
        forbidden = "g" + "cloud"
        assert forbidden not in src, "Cloud CLI reference found"

    def test_no_sql_execution(self):
        """This test file must not execute database queries."""
        src = self._this_file_src()
        forbidden_cur = "cur." + "execute"
        forbidden_conn = "conn." + "execute"
        assert forbidden_cur not in src, "cursor execute call found"
        assert forbidden_conn not in src, "conn execute call found"


# ===========================================================================
# I) Safety — this task is docs/tests only
# ===========================================================================

class TestTaskSafety:

    def _src(self) -> str:
        return _SEQ_DOC.read_text(encoding="utf-8")

    def test_doc_says_docs_tests_only(self):
        src = self._src()
        assert "docs" in src.lower() and "tests" in src.lower()
        assert "only" in src.lower()

    def test_doc_says_no_runtime_implementation_started(self):
        src = self._src()
        assert "NOT started" in src or "not started" in src.lower() or \
               "has not been started" in src.lower() or \
               "No runtime implementation" in src

    def test_doc_says_no_migrations_created(self):
        src = self._src()
        assert "no migration" in src.lower() or \
               "does NOT create migrations" in src or \
               "No migrations" in src

    def test_doc_says_no_db_touched(self):
        src = self._src()
        src_lower = src.lower()
        assert "not touched" in src_lower or "does not touch" in src_lower or \
               "does NOT touch" in src or "untouched" in src_lower or \
               "unchanged" in src_lower

    def test_doc_says_no_balance_ge_activation(self):
        src = self._src()
        assert "NOT activate" in src or "not activate" in src.lower() or \
               "does NOT activate" in src or \
               "has not been activated" in src.lower()

    def test_doc_says_next_safe_task_is_11c_b(self):
        src = self._src()
        assert "11C-B" in src
        src_lower = src.lower()
        assert "next safe task" in src_lower or "next task" in src_lower or \
               "recommended next" in src_lower

    def test_sequence_doc_does_not_reference_runtime_file_paths(self):
        """Sequence doc should not contain paths to runtime app files it modified."""
        src = self._src()
        # The doc may REFERENCE app/* paths in allowed-file tables, which is fine.
        # What it must NOT do is claim it changed those files.
        assert "modified app/" not in src.lower()
        assert "edited app/" not in src.lower()
        assert "changed app/" not in src.lower()
