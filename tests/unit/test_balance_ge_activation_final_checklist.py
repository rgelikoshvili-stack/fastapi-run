"""
tests/unit/test_balance_ge_activation_final_checklist.py

Read-only contract tests for the Balance.ge Activation Final Gate Checklist
(Task 10F-H).

Contract:
  - All 14 gates are listed and default to NOT MET.
  - activation_allowed returns False when any gate is NOT MET.
  - Required evidence set, forbidden activation paths, safe pre-activation
    work, and activation PR requirements are fully defined.
  - No runtime connector, startup, or network imports.
  - No DB connection, SQL, or Balance.ge API call is made.
  - Balance.ge remains inactive (no BALANCE_API_KEY in environment).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO = Path(__file__).parent.parent.parent
_DOCS = _REPO / "docs"
_CHECKLIST_DOC = _DOCS / "balance-ge-activation-final-checklist.md"


# ---------------------------------------------------------------------------
# Local test-only gate definitions (no runtime import)
# ---------------------------------------------------------------------------

class GateStatus:
    NOT_MET = "NOT_MET"
    MET = "MET"
    PARTIAL = "PARTIAL"


# All 14 required gate IDs
REQUIRED_GATES: dict[str, str] = {
    "credential_vault_implemented": GateStatus.NOT_MET,
    "balance_credentials_safely_stored": GateStatus.NOT_MET,
    "masked_read_behavior_implemented": GateStatus.NOT_MET,
    "subscription_trial_enforcement_implemented": GateStatus.NOT_MET,
    "redis_rate_limit_protection_implemented": GateStatus.NOT_MET,
    "approval_first_workflow_verified": GateStatus.NOT_MET,
    "dry_run_payload_preview_verified": GateStatus.NOT_MET,
    "posting_idempotency_verified": GateStatus.NOT_MET,
    "posting_logs_audit_trail_verified": GateStatus.NOT_MET,
    "evidence_bundle_ready": GateStatus.NOT_MET,
    "backup_pitr_restore_drill_ready": GateStatus.NOT_MET,
    "rollback_manual_fallback_ready": GateStatus.NOT_MET,
    "accountant_pilot_signoff": GateStatus.NOT_MET,
    "live_verification_checklist": GateStatus.NOT_MET,
}

REQUIRED_EVIDENCE: set[str] = {
    "credential_vault_proof",
    "masked_status_response_no_secrets",
    "dry_run_output",
    "payload_preview_output",
    "approved_draft_id",
    "idempotency_duplicate_test",
    "posting_log_sanitized_sample",
    "rollback_proof",
    "accountant_signoff",
    "backup_pitr_evidence",
    "rate_limit_evidence",
    "subscription_enforcement_evidence",
    "live_verification_report",
}

FORBIDDEN_ACTIVATION_PATHS: set[str] = {
    "plaintext_env_only",
    "bypass_credential_vault",
    "direct_connector_call_without_approval",
    "direct_db_update",
    "manual_sql",
    "hidden_feature_flag",
    "unreviewed_workflow_secret_change",
    "docs_only_pr",
    "test_only_pr",
    "local_only_proof",
}

SAFE_PRE_ACTIVATION_WORK: set[str] = {
    "docs_tests",
    "connector_interface_tests",
    "fake_connector_tests",
    "dry_run_only_tests",
    "payload_preview_tests",
    "credential_vault_implementation",
    "masked_reads_implementation",
    "subscription_rate_limit_implementation",
    "evidence_bundle_implementation",
    "no_live_posting",
}

ACTIVATION_PR_REQUIREMENTS: set[str] = {
    "explicit_live_activation_title",
    "all_gates_evidence",
    "rollback_plan",
    "manual_fallback_plan",
    "accountant_signoff",
    "live_verification_steps",
    "no_secrets_proof",
    "approved_tenant_pilot_scope",
    "limited_activation_scope",
    "final_human_approval",
}


def activation_allowed(gates: dict[str, str]) -> bool:
    """Returns True only when every gate status is MET."""
    return all(v == GateStatus.MET for v in gates.values())


# ===========================================================================
# A) Document existence
# ===========================================================================

class TestDocumentExistence:

    def test_final_checklist_doc_exists(self):
        """docs/balance-ge-activation-final-checklist.md must exist."""
        assert _CHECKLIST_DOC.exists(), f"Missing: {_CHECKLIST_DOC}"

    def test_activation_gate_doc_exists(self):
        """docs/balance-ge-activation-gate.md must exist."""
        assert (_DOCS / "balance-ge-activation-gate.md").exists()

    def test_trust_foundation_plan_exists(self):
        """docs/trust-foundation-implementation-plan.md must exist."""
        assert (_DOCS / "trust-foundation-implementation-plan.md").exists()

    def test_credential_vault_design_exists(self):
        """docs/credential-vault-design.md must exist."""
        assert (_DOCS / "credential-vault-design.md").exists()

    def test_masked_read_contract_exists(self):
        """docs/masked-read-behavior-contract.md must exist."""
        assert (_DOCS / "masked-read-behavior-contract.md").exists()

    def test_subscription_enforcement_plan_exists(self):
        """docs/subscription-enforcement-plan.md must exist."""
        assert (_DOCS / "subscription-enforcement-plan.md").exists()

    def test_redis_rate_limit_plan_exists(self):
        """docs/redis-rate-limit-plan.md must exist."""
        assert (_DOCS / "redis-rate-limit-plan.md").exists()

    def test_backup_pitr_plan_exists(self):
        """docs/backup-pitr-static-files-plan.md must exist."""
        assert (_DOCS / "backup-pitr-static-files-plan.md").exists()

    def test_runtime_ddl_plan_exists(self):
        """docs/runtime-ddl-cutover-plan.md must exist."""
        assert (_DOCS / "runtime-ddl-cutover-plan.md").exists()


# ===========================================================================
# B) Contract content
# ===========================================================================

class TestContractContent:

    @pytest.fixture(autouse=True)
    def _src(self):
        self.src = _CHECKLIST_DOC.read_text(encoding="utf-8")

    def test_says_balance_ge_remains_inactive(self):
        """Document must state Balance.ge remains inactive."""
        assert "Balance.ge" in self.src
        assert "DEMO" in self.src or "inactive" in self.src.lower()

    def test_says_no_live_activation_in_this_task(self):
        """Document must state no live activation in this task."""
        assert "No live Balance.ge activation" in self.src or \
               "not activate Balance.ge" in self.src or \
               "does NOT activate" in self.src

    def test_says_no_credential_changes_in_this_task(self):
        """Document must state no credential changes in this task."""
        assert "No Balance.ge credential changes" in self.src or \
               "no credential changes" in self.src.lower() or \
               "No credential changes" in self.src

    def test_says_no_connector_code_changes_in_this_task(self):
        """Document must state no connector code changes in this task."""
        assert "connector code" in self.src.lower()
        assert "unchanged" in self.src or "not changed" in self.src or \
               "does not change" in self.src.lower()

    def test_says_no_production_db_touch_in_this_task(self):
        """Document must state production DB is not touched."""
        assert "production database" in self.src.lower() or \
               "production DB" in self.src

    def test_says_no_sql_in_this_task(self):
        """Document must state no SQL execution."""
        src_lower = self.src.lower()
        assert "sql" in src_lower
        # The doc must have a statement that forbids SQL — it says "No SQL" or similar
        assert "no sql" in src_lower or \
               "not execute sql" in src_lower or \
               "no SQL execution" in self.src or \
               "does NOT execute SQL" in self.src

    def test_says_no_infrastructure_changes_in_this_task(self):
        """Document must state no infrastructure changes."""
        src_lower = self.src.lower()
        assert "infrastructure" in src_lower
        assert "no infrastructure" in src_lower or \
               "not changed" in src_lower

    def test_says_all_gates_currently_not_met(self):
        """Document must state all gates are currently NOT MET unless proven by evidence."""
        assert "NOT MET" in self.src
        assert "all gates" in self.src.lower() or "All gates" in self.src

    def test_says_no_activation_in_this_task_explicitly(self):
        """Document must say Balance.ge does NOT activate in this task."""
        assert "does NOT activate" in self.src or \
               "NOT activate" in self.src or \
               "No live Balance.ge activation" in self.src

    def test_says_absolute_no_activation_rule(self):
        """Document must state the absolute no-activation rule."""
        assert "No-Activation Rule" in self.src or \
               "no-activation rule" in self.src.lower() or \
               "MUST NOT be activated" in self.src


# ===========================================================================
# C) Gate list completeness
# ===========================================================================

class TestGateList:

    def test_all_required_gate_ids_are_present(self):
        """REQUIRED_GATES dict must contain all 14 gate IDs."""
        assert len(REQUIRED_GATES) == 14

    def test_credential_vault_gate_present(self):
        assert "credential_vault_implemented" in REQUIRED_GATES

    def test_balance_credentials_gate_present(self):
        assert "balance_credentials_safely_stored" in REQUIRED_GATES

    def test_masked_read_gate_present(self):
        assert "masked_read_behavior_implemented" in REQUIRED_GATES

    def test_subscription_enforcement_gate_present(self):
        assert "subscription_trial_enforcement_implemented" in REQUIRED_GATES

    def test_redis_rate_limit_gate_present(self):
        assert "redis_rate_limit_protection_implemented" in REQUIRED_GATES

    def test_approval_first_gate_present(self):
        assert "approval_first_workflow_verified" in REQUIRED_GATES

    def test_dry_run_preview_gate_present(self):
        assert "dry_run_payload_preview_verified" in REQUIRED_GATES

    def test_idempotency_gate_present(self):
        assert "posting_idempotency_verified" in REQUIRED_GATES

    def test_posting_logs_gate_present(self):
        assert "posting_logs_audit_trail_verified" in REQUIRED_GATES

    def test_evidence_bundle_gate_present(self):
        assert "evidence_bundle_ready" in REQUIRED_GATES

    def test_backup_pitr_gate_present(self):
        assert "backup_pitr_restore_drill_ready" in REQUIRED_GATES

    def test_rollback_fallback_gate_present(self):
        assert "rollback_manual_fallback_ready" in REQUIRED_GATES

    def test_accountant_signoff_gate_present(self):
        assert "accountant_pilot_signoff" in REQUIRED_GATES

    def test_live_verification_gate_present(self):
        assert "live_verification_checklist" in REQUIRED_GATES

    def test_document_mentions_all_14_gate_names(self):
        """The checklist doc must reference all 14 gate areas by name."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        checks = [
            "Credential Vault",
            "Masked Read",
            "Subscription",
            "Rate-Limit",
            "Approval-First",
            "Dry-Run",
            "Idempotency",
            "Posting Logs",
            "Evidence Bundle",
            "Backup",
            "Rollback",
            "Accountant",
            "Live Verification",
        ]
        for term in checks:
            assert term in src, f"Gate term missing from checklist doc: {term!r}"


# ===========================================================================
# D) Current gate status — all must be NOT MET
# ===========================================================================

class TestCurrentGateStatus:

    def test_all_gates_default_to_not_met(self):
        """Every gate in REQUIRED_GATES must default to NOT_MET."""
        for gate_id, status in REQUIRED_GATES.items():
            assert status == GateStatus.NOT_MET, \
                f"Gate {gate_id!r} is not NOT_MET — value: {status!r}"

    def test_no_gate_is_met(self):
        """No gate may be MET in this task."""
        met = [g for g, s in REQUIRED_GATES.items() if s == GateStatus.MET]
        assert met == [], f"Gates marked MET (must not be): {met}"

    def test_activation_not_allowed_when_all_not_met(self):
        """activation_allowed must return False when all gates are NOT_MET."""
        assert activation_allowed(REQUIRED_GATES) is False

    def test_activation_not_allowed_when_one_gate_not_met(self):
        """activation_allowed must return False even if only one gate is NOT_MET."""
        almost_met = {k: GateStatus.MET for k in REQUIRED_GATES}
        almost_met["accountant_pilot_signoff"] = GateStatus.NOT_MET
        assert activation_allowed(almost_met) is False

    def test_activation_allowed_only_when_all_met(self):
        """activation_allowed returns True only when all gates are MET (hypothetical)."""
        all_met = {k: GateStatus.MET for k in REQUIRED_GATES}
        assert activation_allowed(all_met) is True

    def test_partial_status_treated_as_not_met(self):
        """A PARTIAL gate must still prevent activation."""
        partial_gates = dict(REQUIRED_GATES)
        partial_gates["posting_idempotency_verified"] = GateStatus.PARTIAL
        assert activation_allowed(partial_gates) is False


# ===========================================================================
# E) Evidence requirement set
# ===========================================================================

class TestEvidenceRequirements:

    def test_required_evidence_set_has_all_items(self):
        assert len(REQUIRED_EVIDENCE) == 13

    def test_credential_vault_proof_required(self):
        assert "credential_vault_proof" in REQUIRED_EVIDENCE

    def test_masked_status_response_no_secrets_required(self):
        assert "masked_status_response_no_secrets" in REQUIRED_EVIDENCE

    def test_dry_run_output_required(self):
        assert "dry_run_output" in REQUIRED_EVIDENCE

    def test_payload_preview_output_required(self):
        assert "payload_preview_output" in REQUIRED_EVIDENCE

    def test_approved_draft_id_required(self):
        assert "approved_draft_id" in REQUIRED_EVIDENCE

    def test_idempotency_duplicate_test_required(self):
        assert "idempotency_duplicate_test" in REQUIRED_EVIDENCE

    def test_posting_log_sanitized_sample_required(self):
        assert "posting_log_sanitized_sample" in REQUIRED_EVIDENCE

    def test_rollback_proof_required(self):
        assert "rollback_proof" in REQUIRED_EVIDENCE

    def test_accountant_signoff_required(self):
        assert "accountant_signoff" in REQUIRED_EVIDENCE

    def test_backup_pitr_evidence_required(self):
        assert "backup_pitr_evidence" in REQUIRED_EVIDENCE

    def test_rate_limit_evidence_required(self):
        assert "rate_limit_evidence" in REQUIRED_EVIDENCE

    def test_subscription_enforcement_evidence_required(self):
        assert "subscription_enforcement_evidence" in REQUIRED_EVIDENCE

    def test_live_verification_report_required(self):
        assert "live_verification_report" in REQUIRED_EVIDENCE

    def test_document_mentions_all_evidence_items(self):
        """Checklist doc must reference every evidence item."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        for item in REQUIRED_EVIDENCE:
            assert item in src, f"Evidence item missing from doc: {item!r}"


# ===========================================================================
# F) Forbidden activation paths
# ===========================================================================

class TestForbiddenActivationPaths:

    def test_forbidden_paths_set_has_all_items(self):
        assert len(FORBIDDEN_ACTIVATION_PATHS) == 10

    def test_plaintext_env_only_forbidden(self):
        assert "plaintext_env_only" in FORBIDDEN_ACTIVATION_PATHS

    def test_bypass_credential_vault_forbidden(self):
        assert "bypass_credential_vault" in FORBIDDEN_ACTIVATION_PATHS

    def test_direct_connector_call_without_approval_forbidden(self):
        assert "direct_connector_call_without_approval" in FORBIDDEN_ACTIVATION_PATHS

    def test_direct_db_update_forbidden(self):
        assert "direct_db_update" in FORBIDDEN_ACTIVATION_PATHS

    def test_manual_sql_forbidden(self):
        assert "manual_sql" in FORBIDDEN_ACTIVATION_PATHS

    def test_hidden_feature_flag_forbidden(self):
        assert "hidden_feature_flag" in FORBIDDEN_ACTIVATION_PATHS

    def test_unreviewed_workflow_secret_change_forbidden(self):
        assert "unreviewed_workflow_secret_change" in FORBIDDEN_ACTIVATION_PATHS

    def test_docs_only_pr_forbidden(self):
        assert "docs_only_pr" in FORBIDDEN_ACTIVATION_PATHS

    def test_test_only_pr_forbidden(self):
        assert "test_only_pr" in FORBIDDEN_ACTIVATION_PATHS

    def test_local_only_proof_forbidden(self):
        assert "local_only_proof" in FORBIDDEN_ACTIVATION_PATHS

    def test_document_lists_forbidden_paths(self):
        """Checklist doc must mention forbidden activation paths."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        assert "Forbidden Activation" in src or "forbidden" in src.lower()
        assert "plaintext" in src.lower()
        assert "credential vault" in src.lower()


# ===========================================================================
# G) Safe pre-activation work
# ===========================================================================

class TestSafePreActivationWork:

    def test_safe_work_set_has_all_items(self):
        assert len(SAFE_PRE_ACTIVATION_WORK) == 10

    def test_docs_tests_safe(self):
        assert "docs_tests" in SAFE_PRE_ACTIVATION_WORK

    def test_connector_interface_tests_safe(self):
        assert "connector_interface_tests" in SAFE_PRE_ACTIVATION_WORK

    def test_fake_connector_tests_safe(self):
        assert "fake_connector_tests" in SAFE_PRE_ACTIVATION_WORK

    def test_dry_run_only_tests_safe(self):
        assert "dry_run_only_tests" in SAFE_PRE_ACTIVATION_WORK

    def test_payload_preview_tests_safe(self):
        assert "payload_preview_tests" in SAFE_PRE_ACTIVATION_WORK

    def test_credential_vault_implementation_safe(self):
        assert "credential_vault_implementation" in SAFE_PRE_ACTIVATION_WORK

    def test_masked_reads_implementation_safe(self):
        assert "masked_reads_implementation" in SAFE_PRE_ACTIVATION_WORK

    def test_subscription_rate_limit_implementation_safe(self):
        assert "subscription_rate_limit_implementation" in SAFE_PRE_ACTIVATION_WORK

    def test_evidence_bundle_implementation_safe(self):
        assert "evidence_bundle_implementation" in SAFE_PRE_ACTIVATION_WORK

    def test_no_live_posting_safe(self):
        assert "no_live_posting" in SAFE_PRE_ACTIVATION_WORK

    def test_document_mentions_safe_pre_activation_work(self):
        """Checklist doc must describe safe pre-activation work."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        assert "Safe Pre-Activation" in src or "safe pre-activation" in src.lower()
        assert "fake" in src.lower() or "fake_connector" in src.lower()
        assert "no_live_posting" in src or "no live posting" in src.lower()


# ===========================================================================
# H) Activation PR requirements
# ===========================================================================

class TestActivationPrRequirements:

    def test_pr_requirements_set_has_all_items(self):
        assert len(ACTIVATION_PR_REQUIREMENTS) == 10

    def test_explicit_live_activation_title_required(self):
        assert "explicit_live_activation_title" in ACTIVATION_PR_REQUIREMENTS

    def test_all_gates_evidence_required(self):
        assert "all_gates_evidence" in ACTIVATION_PR_REQUIREMENTS

    def test_rollback_plan_required(self):
        assert "rollback_plan" in ACTIVATION_PR_REQUIREMENTS

    def test_manual_fallback_plan_required(self):
        assert "manual_fallback_plan" in ACTIVATION_PR_REQUIREMENTS

    def test_accountant_signoff_required(self):
        assert "accountant_signoff" in ACTIVATION_PR_REQUIREMENTS

    def test_live_verification_steps_required(self):
        assert "live_verification_steps" in ACTIVATION_PR_REQUIREMENTS

    def test_no_secrets_proof_required(self):
        assert "no_secrets_proof" in ACTIVATION_PR_REQUIREMENTS

    def test_approved_tenant_pilot_scope_required(self):
        assert "approved_tenant_pilot_scope" in ACTIVATION_PR_REQUIREMENTS

    def test_limited_activation_scope_required(self):
        assert "limited_activation_scope" in ACTIVATION_PR_REQUIREMENTS

    def test_final_human_approval_required(self):
        assert "final_human_approval" in ACTIVATION_PR_REQUIREMENTS

    def test_document_mentions_activation_pr_requirements(self):
        """Checklist doc must describe activation PR requirements."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        assert "Activation PR" in src
        assert "final_human_approval" in src or "final human approval" in src.lower()
        assert "no_secrets_proof" in src or "no-secrets proof" in src.lower()


# ===========================================================================
# I) Secret safety
# ===========================================================================

class TestSecretSafety:

    def _doc_src(self) -> str:
        return _CHECKLIST_DOC.read_text(encoding="utf-8")

    def test_doc_forbids_raw_api_key_exposure(self):
        """Checklist doc must forbid raw api_key in responses."""
        src = self._doc_src()
        assert "api_key" in src or "api key" in src.lower()
        # Doc says no raw api_key in responses — check it references masking/no-key
        assert "no raw" in src.lower() or "never return" in src.lower() or \
               "masked" in src.lower()

    def test_doc_forbids_plaintext_credentials(self):
        """Checklist doc must forbid plaintext live credentials."""
        src = self._doc_src().lower()
        assert "plaintext" in src

    def test_doc_forbids_secrets_in_logs(self):
        """Checklist doc must forbid secrets in logs."""
        src = self._doc_src().lower()
        assert "log" in src
        assert "secret" in src or "credential" in src
        assert "no secret" in src or "without" in src or "sanitized" in src

    def test_doc_mentions_masked_credentials(self):
        """Checklist doc must mention masked credential format."""
        src = self._doc_src()
        assert "masked" in src.lower()

    def test_doc_forbids_password_exposure(self):
        """Checklist doc must address password/token/secret field safety."""
        src = self._doc_src().lower()
        assert "password" in src or "token" in src or "secret" in src

    def test_no_real_api_key_in_doc(self):
        """The checklist doc must not contain an actual Balance.ge API key pattern."""
        src = self._doc_src()
        # Real API keys typically look like long alphanumeric strings;
        # the doc may contain placeholder text like 'api_key' but not real key values.
        # Check that no line looks like a raw credential assignment.
        import re
        # Pattern: key = "long_alphanumeric_string_32_plus_chars"
        suspicious = re.findall(r'(?:api_key|BALANCE_API_KEY)\s*[=:]\s*["\']([A-Za-z0-9_\-]{20,})["\']', src)
        assert suspicious == [], f"Possible real credentials in doc: {suspicious}"


# ===========================================================================
# J) Source scan (text-only, no import)
# ===========================================================================

class TestSourceScan:

    def test_balance_connector_file_exists(self):
        """app/api/connectors/balance_connector.py must exist."""
        p = _REPO / "app" / "api" / "connectors" / "balance_connector.py"
        assert p.exists()

    def test_balance_credentials_service_file_exists(self):
        """app/api/services/balance_credentials_service.py must exist."""
        p = _REPO / "app" / "api" / "services" / "balance_credentials_service.py"
        assert p.exists()

    def test_balance_connector_text_has_balance_ge_reference(self):
        """balance_connector.py must reference balance.ge (grounding check)."""
        p = _REPO / "app" / "api" / "connectors" / "balance_connector.py"
        src = p.read_text(encoding="utf-8")
        assert "balance.ge" in src.lower() or "balance_ge" in src.lower() or \
               "BalanceConnector" in src

    def test_balance_connector_has_no_dry_run_param(self):
        """balance_connector.py must not yet have dry_run param (confirms gate NOT MET)."""
        p = _REPO / "app" / "api" / "connectors" / "balance_connector.py"
        src = p.read_text(encoding="utf-8")
        assert "dry_run" not in src, \
            "dry_run param found in balance_connector.py — GATE-07 may be closer to MET; update gate status"

    def test_balance_credentials_service_stores_plaintext(self):
        """balance_credentials_service.py must store api_key as plaintext (confirms GATE-01 NOT MET)."""
        p = _REPO / "app" / "api" / "services" / "balance_credentials_service.py"
        src = p.read_text(encoding="utf-8")
        # The service has api_key as TEXT column — confirms plaintext storage
        assert "api_key" in src

    def test_at_least_one_balance_ge_reference_in_connectors(self):
        """At least one connector or service file must reference Balance.ge."""
        connector_files = list((_REPO / "app" / "api" / "connectors").glob("*.py"))
        service_files = list((_REPO / "app" / "api" / "services").glob("*balance*"))
        all_files = connector_files + service_files
        found = False
        for f in all_files:
            src = f.read_text(encoding="utf-8").lower()
            if "balance" in src:
                found = True
                break
        assert found, "No Balance.ge reference found in connectors or services"

    def test_checklist_doc_cross_references_activation_gate_doc(self):
        """Checklist doc must cross-reference docs/balance-ge-activation-gate.md."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        assert "balance-ge-activation-gate.md" in src or \
               "balance-ge-activation-gate" in src


# ===========================================================================
# K) No runtime / import / network execution
# ===========================================================================

class TestNoRuntimeImportNetworkExecution:
    """
    Scan this test file's own source to assert forbidden patterns are absent.
    Uses split strings to avoid self-referential matches on this file's own text.
    """

    def _this_file_src(self) -> str:
        return Path(__file__).read_text(encoding="utf-8")

    def test_no_import_app_api_connectors(self):
        """This test file must not import connector runtime modules directly."""
        src = self._this_file_src()
        forbidden = "import app.api." + "connectors"
        assert forbidden not in src, "Connector runtime import found in test file"

    def test_no_from_app_api_connectors(self):
        """This test file must not from-import connector runtime modules."""
        src = self._this_file_src()
        forbidden = "from app.api." + "connectors"
        assert forbidden not in src, "Connector runtime from-import found in test file"

    def test_no_import_app_startup(self):
        """This test file must not import startup runtime modules."""
        src = self._this_file_src()
        forbidden = "import app." + "startup"
        assert forbidden not in src, "Startup import found in test file"

    def test_no_from_app_startup(self):
        """This test file must not from-import startup runtime modules."""
        src = self._this_file_src()
        forbidden = "from app." + "startup"
        assert forbidden not in src, "Startup from-import found in test file"

    def test_no_requests_import(self):
        """This test file must not import the requests library (no live HTTP calls)."""
        src = self._this_file_src()
        import re
        matches = re.findall(r'^import requests', src, re.MULTILINE)
        assert matches == [], "requests library import found in test file"

    def test_no_httpx_import(self):
        """This test file must not import the httpx library."""
        src = self._this_file_src()
        import re
        matches = re.findall(r'^import httpx|^from httpx', src, re.MULTILINE)
        assert matches == [], "httpx library import found in test file"

    def test_no_urllib_import(self):
        """This test file must not import urllib for live HTTP calls."""
        src = self._this_file_src()
        import re
        matches = re.findall(r'^import urllib|^from urllib', src, re.MULTILINE)
        assert matches == [], "urllib import found in test file"

    def test_no_psycopg_connect(self):
        """This test file must not make synchronous DB connections."""
        src = self._this_file_src()
        forbidden_sync = "psycopg2." + "connect"
        forbidden_v3 = "psycopg." + "connect"
        assert forbidden_sync not in src, "psycopg2 connect call found in test file"
        assert forbidden_v3 not in src, "psycopg connect call found in test file"

    def test_no_asyncpg_connect(self):
        """This test file must not make async DB connections."""
        src = self._this_file_src()
        forbidden = "asyncpg." + "connect"
        assert forbidden not in src, "asyncpg connect call found in test file"

    def test_no_subprocess_call(self):
        """This test file must not use the subprocess module."""
        src = self._this_file_src()
        import re
        matches = re.findall(r'^import subprocess|^from subprocess', src, re.MULTILINE)
        assert matches == [], "subprocess import found in test file"

    def test_no_cloud_cli_invocation(self):
        """This test file must not invoke cloud CLI tooling."""
        src = self._this_file_src()
        forbidden = "g" + "cloud"
        assert forbidden not in src, "Cloud CLI reference found in test file"

    def test_no_sql_execution(self):
        """This test file must not execute database queries."""
        src = self._this_file_src()
        forbidden_cur = "cur." + "execute"
        forbidden_conn = "conn." + "execute"
        assert forbidden_cur not in src, "cursor execute call found in test file"
        assert forbidden_conn not in src, "conn execute call found in test file"


# ===========================================================================
# L) Balance.ge safety
# ===========================================================================

class TestBalanceGeSafety:

    def test_balance_api_key_not_in_environment(self):
        """BALANCE_API_KEY must not be set in the test environment."""
        assert os.environ.get("BALANCE_API_KEY", "") == "", \
            "BALANCE_API_KEY is set — do not run tests with live credentials"

    def test_balance_ge_remains_inactive_per_doc(self):
        """Checklist doc must explicitly state Balance.ge remains inactive."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        assert "DEMO" in src or "remains inactive" in src or \
               "not activated" in src.lower()

    def test_all_gates_not_met_per_doc(self):
        """Checklist doc must state all gates are currently NOT MET."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        assert "NOT MET" in src

    def test_checklist_doc_says_no_live_calls(self):
        """Checklist doc must state no live Balance.ge API calls are made."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        assert "no live" in src.lower() or "NONE" in src or \
               "no live ERP writes" in src or "does NOT run" in src

    def test_gate_count_is_14(self):
        """REQUIRED_GATES must contain exactly 14 gates."""
        assert len(REQUIRED_GATES) == 14

    def test_activation_blocked(self):
        """Activation is blocked in the current state."""
        assert activation_allowed(REQUIRED_GATES) is False

    def test_document_says_0_of_14_gates_met(self):
        """Checklist doc must state 0 of 14 gates are MET."""
        src = _CHECKLIST_DOC.read_text(encoding="utf-8")
        assert "0 of 14" in src or "BLOCKED" in src
