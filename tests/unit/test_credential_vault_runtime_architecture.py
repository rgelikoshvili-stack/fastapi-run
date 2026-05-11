"""
tests/unit/test_credential_vault_runtime_architecture.py

Contract tests for docs/credential-vault-runtime-architecture.md (Task 11C-B).

Rules:
  - Read-only: no DB, no network, no runtime vault or connector modules loaded.
  - All assertions derive from the architecture document text only.
  - Self-referential string patterns use split-string concatenation to avoid
    matching their own source when group L scans this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent


def _doc(name: str) -> Path:
    return REPO_ROOT / "docs" / name


def _read_doc(name: str) -> str:
    return _doc(name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A) Document existence
# ---------------------------------------------------------------------------

class TestDocumentExistence:
    """All six cross-referenced architecture documents must exist on disk."""

    def test_credential_vault_runtime_architecture_exists(self):
        assert _doc("credential-vault-runtime-architecture.md").exists()

    def test_credential_vault_design_exists(self):
        assert _doc("credential-vault-design.md").exists()

    def test_credential_vault_interface_contract_exists(self):
        assert _doc("credential-vault-interface-contract.md").exists()

    def test_masked_read_behavior_contract_exists(self):
        assert _doc("masked-read-behavior-contract.md").exists()

    def test_balance_ge_activation_checklist_exists(self):
        assert _doc("balance-ge-activation-final-checklist.md").exists()

    def test_trust_foundation_runtime_sequence_exists(self):
        assert _doc("trust-foundation-runtime-implementation-sequence.md").exists()


# ---------------------------------------------------------------------------
# B) Content structure checks
# ---------------------------------------------------------------------------

class TestDocumentContent:
    """The architecture document must contain all required sections."""

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    def test_has_purpose_section(self, src):
        assert "## A) Purpose" in src

    def test_has_current_baseline_section(self, src):
        assert "## B) Current Baseline" in src

    def test_has_target_architecture_section(self, src):
        assert "## C) Target Architecture" in src

    def test_has_future_schema_plan_section(self, src):
        assert "## D) Future Schema Plan" in src

    def test_has_migration_strategy_section(self, src):
        assert "## E) Migration Strategy" in src

    def test_has_runtime_service_interface_section(self, src):
        assert "## F) Runtime Service Interface" in src

    def test_has_masked_read_rules_section(self, src):
        assert "## G) Masked Read Rules" in src

    def test_has_connector_boundary_section(self, src):
        assert "## H) Connector Boundary" in src

    def test_has_key_management_section(self, src):
        assert "## I) Key Management" in src

    def test_has_audit_requirements_section(self, src):
        assert "## J) Audit Requirements" in src

    def test_has_error_model_section(self, src):
        assert "## K) Error Model" in src

    def test_has_allowed_forbidden_files_section(self, src):
        assert "## L) Allowed / Forbidden Files for 11C-C" in src

    def test_has_test_strategy_section(self, src):
        assert "## M) Test Strategy" in src

    def test_has_rollback_strategy_section(self, src):
        assert "## N) Rollback Strategy" in src

    def test_has_live_verification_section(self, src):
        assert "## O) Live Verification Standard" in src

    def test_has_stop_conditions_section(self, src):
        assert "## P) Stop Conditions" in src

    def test_has_final_status_section(self, src):
        assert "## Q) Final Status" in src

    def test_no_runtime_code_begins_here_statement(self, src):
        assert "No runtime implementation has been started" in src

    def test_no_migrations_created_statement(self, src):
        assert "No migrations have been created" in src

    def test_no_production_db_touched_statement(self, src):
        assert "No production database has been touched" in src

    def test_balance_not_activated_statement(self, src):
        assert "Balance.ge has not been activated" in src

    def test_11cc_not_started_statement(self, src):
        assert "Task 11C-C has not been started" in src


# ---------------------------------------------------------------------------
# C) Component set (9 components)
# ---------------------------------------------------------------------------

class TestComponentSet:
    """All nine vault service components must be named in the architecture doc."""

    REQUIRED_COMPONENTS = [
        "CredentialVaultService",
        "SecretCryptoProvider",
        "KeyProvider",
        "CredentialRepository",
        "CredentialStatusProvider",
        "ConnectorCredentialProvider",
        "CredentialAuditLogger",
        "MaskedCredentialFormatter",
        "CredentialRotationService",
    ]

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    @pytest.mark.parametrize("component", REQUIRED_COMPONENTS)
    def test_component_named_in_doc(self, src, component):
        assert component in src, f"Component {component!r} missing from architecture doc"

    def test_exactly_nine_components_defined(self, src):
        count = sum(
            1 for name in self.REQUIRED_COMPONENTS if f"### {name}" in src
        )
        assert count == 9, f"Expected 9 component sections, found {count}"


# ---------------------------------------------------------------------------
# D) Future schema fields (19 fields)
# ---------------------------------------------------------------------------

class TestSchemaFields:
    """All 19 target credential_vault table columns must appear in the doc."""

    REQUIRED_FIELDS = [
        "id",
        "tenant_id",
        "provider",
        "credential_type",
        "encrypted_value",
        "key_version",
        "masked_hint",
        "status",
        "active",
        "company_id",
        "api_base",
        "last_test_status",
        "last_tested_at",
        "last_accessed_at",
        "rotated_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    ]

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_schema_field_present(self, src, field):
        assert f"`{field}`" in src, f"Schema field {field!r} missing from doc"

    def test_target_table_name_defined(self, src):
        assert "credential_vault" in src

    def test_unique_constraint_defined(self, src):
        assert "(tenant_id, provider, credential_type)" in src

    def test_encrypted_value_column_is_nullable(self, src):
        assert "NULL until migration" in src

    def test_plaintext_transition_plan_present(self, src):
        assert "Plaintext api_key transition plan" in src


# ---------------------------------------------------------------------------
# E) Runtime method set (6 methods)
# ---------------------------------------------------------------------------

class TestRuntimeMethods:
    """All 6 service interface methods must be defined in the doc."""

    REQUIRED_METHODS = [
        "save_credential",
        "get_for_connector",
        "get_status",
        "rotate_credential",
        "disable_credential",
        "audit_access",
    ]

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    @pytest.mark.parametrize("method", REQUIRED_METHODS)
    def test_method_defined(self, src, method):
        assert method in src, f"Service method {method!r} missing from doc"

    def test_save_credential_raw_secret_never_returned(self, src):
        assert "save_credential" in src
        assert "**Raw secret returned:** Never" in src

    def test_get_for_connector_classified_internal(self, src):
        assert "Internal connector path only" in src

    def test_get_status_classified_public(self, src):
        assert "Public — safe for API" in src

    def test_rotate_credential_logs_key_versions(self, src):
        assert "old `key_version`" in src
        assert "new `key_version`" in src

    def test_audit_access_must_not_block_primary_op(self, src):
        assert "audit failures must not block the primary operation" in src


# ---------------------------------------------------------------------------
# F) Masked read rules (6 rules)
# ---------------------------------------------------------------------------

class TestMaskedReadRules:
    """The masked read section must contain all six enforcement rules."""

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    def test_api_endpoints_must_never_return_api_key(self, src):
        assert "MUST NEVER return raw `api_key`" in src

    def test_status_response_may_contain_configured(self, src):
        assert "`configured` (boolean)" in src

    def test_status_response_may_contain_masked_hint(self, src):
        # Check in the "may contain" subsection
        idx = src.index("Public/status credential response MAY contain")
        section = src[idx:idx + 500]
        assert "masked_hint" in section

    def test_connector_path_in_memory_only(self, src):
        assert "In memory only — never persisted or returned" in src

    def test_logs_must_never_include_raw_secrets(self, src):
        assert "Logs and exceptions MUST NEVER include raw secrets" in src

    def test_masked_hint_computed_once_at_save_time(self, src):
        assert "Masked hint is computed once at save time" in src

    def test_p0_security_incident_defined(self, src):
        assert "P0 security incident" in src

    def test_masked_hint_format_defined(self, src):
        assert "****" in src
        assert "last 4 characters" in src


# ---------------------------------------------------------------------------
# G) Migration phases (9 phases, Phase 0 through Phase 8)
# ---------------------------------------------------------------------------

class TestMigrationPhases:
    """All 9 migration phases must be defined in the doc."""

    REQUIRED_PHASES = [
        ("Phase 0", "docs_tests_only"),
        ("Phase 1", "additive_encrypted_fields"),
        ("Phase 2", "crypto_provider_test_mode"),
        ("Phase 3", "write_through_encrypted_service"),
        ("Phase 4", "connector_internal_decrypt_path"),
        ("Phase 5", "masked_status_path"),
        ("Phase 6", "migrate_plaintext_to_encrypted_value"),
        ("Phase 7", "null_plaintext_api_key"),
        ("Phase 8", "remove_plaintext_dependency"),
    ]

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    @pytest.mark.parametrize("phase_label,phase_slug", REQUIRED_PHASES)
    def test_migration_phase_present(self, src, phase_label, phase_slug):
        assert phase_label in src, f"{phase_label} missing from migration strategy"
        assert phase_slug in src, f"Phase slug {phase_slug!r} missing from doc"

    def test_total_nine_phases(self, src):
        count = sum(1 for i in range(9) if f"Phase {i}" in src)
        assert count == 9, f"Expected 9 phases (0-8), found {count}"

    def test_phase_0_is_this_task(self, src):
        assert "11C-B — this document and tests only" in src

    def test_phase_1_is_additive_only(self, src):
        assert "additive only, no column removal" in src

    def test_no_column_removal_before_backup(self, src):
        assert "No column removal before backup" in src or "no column removal" in src.lower()

    def test_explicit_authorization_required_per_phase(self, src):
        assert "separate explicit authorization per phase" in src

    def test_phase_1_requires_authorization(self, src):
        assert "11C-C may create Phase 1 migration only if explicitly authorized" in src


# ---------------------------------------------------------------------------
# H) Error codes (7 codes)
# ---------------------------------------------------------------------------

class TestErrorCodes:
    """All 7 error codes must be defined in the error model section."""

    REQUIRED_CODES = [
        "CREDENTIAL_NOT_FOUND",
        "CREDENTIAL_DISABLED",
        "CREDENTIAL_DECRYPT_FAILED",
        "CREDENTIAL_PROVIDER_NOT_CONFIGURED",
        "CREDENTIAL_ACCESS_DENIED",
        "CREDENTIAL_ROTATION_FAILED",
        "CREDENTIAL_STATUS_UNAVAILABLE",
    ]

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    @pytest.mark.parametrize("code", REQUIRED_CODES)
    def test_error_code_present(self, src, code):
        assert code in src, f"Error code {code!r} missing from doc"

    def test_exactly_seven_error_codes(self, src):
        count = sum(1 for code in self.REQUIRED_CODES if code in src)
        assert count == 7

    def test_errors_use_standard_envelope(self, src):
        assert '"ok":false' in src or '"ok": false' in src

    def test_errors_must_not_include_secret_in_details(self, src):
        assert "NO secret values" in src or "no secret field values" in src or "no `api_key`" in src


# ---------------------------------------------------------------------------
# I) Balance.ge safety
# ---------------------------------------------------------------------------

class TestBalanceGeSafety:
    """The doc must state that Balance.ge remains blocked throughout 11C-B and 11C-C."""

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    def test_balance_not_activated_in_11cb(self, src):
        assert "This task does NOT activate Balance.ge" in src

    def test_balance_blocked_until_11cl(self, src):
        assert "11C-L" in src
        assert "live activation remains blocked" in src.lower() or "blocked until 11C-L" in src

    def test_connector_must_remain_demo_mode(self, src):
        assert "demo_mode" in src

    def test_no_live_balance_api_call_in_11cc(self, src):
        assert "No live Balance.ge API call in 11C-B or 11C-C" in src

    def test_all_14_gates_referenced(self, src):
        assert "14 gates" in src

    def test_demo_mode_returned_on_credential_errors(self, src):
        assert "Return `demo_mode` response" in src or "Return demo_mode" in src or "demo/not_configured" in src


# ---------------------------------------------------------------------------
# J) Source scan — balance_credentials_service.py and balance_connector.py
# ---------------------------------------------------------------------------

class TestSourceAuditFindings:
    """Audit findings documented in the architecture doc must match actual source."""

    @pytest.fixture(scope="class")
    def creds_svc_src(self):
        p = REPO_ROOT / "app" / "api" / "services" / "balance_credentials_service.py"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    @pytest.fixture(scope="class")
    def connector_src(self):
        p = REPO_ROOT / "app" / "api" / "connectors" / "balance_connector.py"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def test_balance_credentials_service_exists(self):
        p = REPO_ROOT / "app" / "api" / "services" / "balance_credentials_service.py"
        assert p.exists()

    def test_balance_connector_exists(self):
        p = REPO_ROOT / "app" / "api" / "connectors" / "balance_connector.py"
        assert p.exists()

    def test_api_key_column_exists_in_service(self, creds_svc_src):
        assert "api_key" in creds_svc_src

    def test_get_balance_credentials_select_does_not_fetch_encrypted_column(self, creds_svc_src):
        # The primary get_balance_credentials SELECT must read api_key directly,
        # not encrypted_value — confirming plaintext credential path is still active.
        assert "SELECT api_key, company_id, api_base" in creds_svc_src

    def test_no_key_version_column_yet(self, creds_svc_src):
        assert "key_version" not in creds_svc_src

    def test_no_masked_hint_column_yet(self, creds_svc_src):
        assert "masked_hint" not in creds_svc_src

    def test_connector_has_demo_mode_logic(self, connector_src):
        assert "demo" in connector_src.lower()

    def test_connector_does_not_yet_use_credential_vault(self, connector_src):
        assert "CredentialVaultService" not in connector_src
        assert "ConnectorCredentialProvider" not in connector_src


# ---------------------------------------------------------------------------
# K) Stop conditions
# ---------------------------------------------------------------------------

class TestStopConditions:
    """All eight stop conditions must appear in the architecture document."""

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    def test_stop_condition_production_credential_requested(self, src):
        assert "Production credential is requested or needed" in src

    def test_stop_condition_migration_not_authorized(self, src):
        assert "Migration is needed but not authorized" in src

    def test_stop_condition_runtime_code_outside_allowed_files(self, src):
        assert "Runtime code outside the allowed file list" in src

    def test_stop_condition_db_access_not_provided(self, src):
        assert "DB access is required beyond what migrations provide" in src

    def test_stop_condition_live_balance_api_call(self, src):
        assert "Live Balance.ge API call is required" in src

    def test_stop_condition_tests_fail(self, src):
        assert "Tests fail" in src

    def test_stop_condition_plaintext_secret_in_fixture(self, src):
        assert "Plaintext secret appears in any test fixture" in src

    def test_stop_condition_unexpected_tracked_changes(self, src):
        assert "Working tree has unexpected tracked changes" in src

    def test_stop_conditions_section_present(self, src):
        assert "## P) Stop Conditions" in src


# ---------------------------------------------------------------------------
# L) No runtime/import/network execution (self-referential source scan)
# ---------------------------------------------------------------------------

class TestNoRuntimeImportsInTestFile:
    """
    This test file must not import runtime vault modules or connector modules.
    Assertions use split-string concatenation so the patterns do not self-match.
    """

    def _self_src(self) -> str:
        return Path(__file__).read_text(encoding="utf-8")

    def test_no_runtime_import_of_app_modules(self):
        src = self._self_src()
        # Split to avoid self-match in assertion strings
        forbidden_import = "import" + " app."
        forbidden_from = "from" + " app."
        assert forbidden_import not in src, "Test file must not load runtime vault modules"
        assert forbidden_from not in src, "Test file must not load runtime vault modules"

    def test_no_db_connection_in_test_file(self):
        src = self._self_src()
        forbidden_connect = "get_db" + "()"
        forbidden_asyncpg = "asyncpg." + "connect"
        forbidden_psycopg = "psycopg2." + "connect"
        assert forbidden_connect not in src
        assert forbidden_asyncpg not in src
        assert forbidden_psycopg not in src

    def test_no_sql_execution_in_test_file(self):
        src = self._self_src()
        # Check that no DB cursor calls appear in the test file
        assert "cursor." + "execute" not in src

    def test_no_network_calls_in_test_file(self):
        src = self._self_src()
        forbidden_requests = "requests." + "get"
        forbidden_httpx = "httpx." + "get"
        forbidden_aiohttp = "aiohttp." + "request"
        assert forbidden_requests not in src
        assert forbidden_httpx not in src
        assert forbidden_aiohttp not in src

    def test_no_vault_runtime_module_imported(self):
        src = self._self_src()
        forbidden_vault_svc = "credential_vault_service" + ".py"
        forbidden_crypto = "secret_crypto_provider" + ".py"
        assert forbidden_vault_svc not in src
        assert forbidden_crypto not in src

    def test_no_balance_connector_imported(self):
        src = self._self_src()
        # Split to avoid self-match
        forbidden_bal = "balance_connector" + " import"
        assert forbidden_bal not in src

    def test_only_pathlib_and_pytest_imports(self):
        src = self._self_src()
        # Confirm allowed imports are present
        assert "from pathlib import Path" in src
        assert "import pytest" in src


# ---------------------------------------------------------------------------
# M) Safety assertions
# ---------------------------------------------------------------------------

class TestSafetyAssertions:
    """Core safety invariants that the architecture document must encode."""

    @pytest.fixture(scope="class")
    def src(self):
        return _read_doc("credential-vault-runtime-architecture.md")

    def test_raw_secret_never_in_api_response(self, src):
        assert "MUST NEVER return raw" in src

    def test_raw_secret_never_in_logs(self, src):
        assert "MUST NEVER include raw secrets" in src

    def test_test_mode_key_defined(self, src):
        assert 'b"test-key-32bytes-for-unit-tests!"' in src

    def test_test_mode_key_not_for_production(self, src):
        assert "MUST NOT be used in production" in src or "must not use this key" in src.lower()

    def test_no_hardcoded_production_key(self, src):
        assert "No hardcoded production key" in src

    def test_production_key_from_secret_manager(self, src):
        assert "GCP Secret Manager" in src

    def test_vault_service_never_logs_raw_secret(self, src):
        assert "Must never log raw secret" in src or "Must not log plaintext" in src

    def test_credential_repository_never_exposes_encrypted_value(self, src):
        assert "Must not expose `encrypted_value` outside the vault" in src

    def test_credential_status_never_calls_crypto_provider(self, src):
        assert "Must never call `SecretCryptoProvider`" in src

    def test_connector_must_not_read_env_var_for_prod(self, src):
        assert "MUST NOT read `os.environ" in src or "MUST NOT read" in src

    def test_this_task_does_not_implement_runtime_code(self, src):
        assert "This task does NOT implement runtime code" in src

    def test_this_task_does_not_create_migrations(self, src):
        assert "This task does NOT create migrations" in src

    def test_this_task_does_not_touch_production_db(self, src):
        assert "This task does NOT touch the production database" in src

    def test_this_task_does_not_run_sql(self, src):
        assert "This task does NOT run SQL" in src

    def test_this_task_does_not_activate_balance(self, src):
        assert "This task does NOT activate Balance.ge" in src

    def test_audit_logger_required_fields_defined(self, src):
        required_fields = ["tenant_id", "provider", "actor", "purpose", "result", "timestamp"]
        for field in required_fields:
            assert f"`{field}`" in src, f"Audit field {field!r} not defined"

    def test_raw_secret_never_in_audit_log(self, src):
        assert "`raw_secret` | **NEVER**" in src

    def test_encrypted_value_never_in_audit_log(self, src):
        assert "`encrypted_value` | **NEVER**" in src
