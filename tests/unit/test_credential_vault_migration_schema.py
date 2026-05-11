"""
tests/unit/test_credential_vault_migration_schema.py

Read-only contract tests for the credential vault schema migration.
Task 11C-C1: Credential Vault Migration File + Schema Tests.

Rules:
  - Read-only: no DB connections, no SQL execution, no network calls.
  - No runtime vault or connector modules are loaded.
  - Self-referential patterns use split-string concatenation to avoid
    matching their own source when group J scans this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent


def _migration(name: str) -> Path:
    return REPO_ROOT / "app" / "storage" / "migrations" / name


def _doc(name: str) -> Path:
    return REPO_ROOT / "docs" / name


def _service(name: str) -> Path:
    return REPO_ROOT / "app" / "api" / "services" / name


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A) File existence
# ---------------------------------------------------------------------------

class TestFileExistence:
    """Required files must exist on disk."""

    def test_migration_009_exists(self):
        assert _migration("009_credential_vault_schema.sql").exists()

    def test_credential_vault_runtime_architecture_doc_exists(self):
        assert _doc("credential-vault-runtime-architecture.md").exists()

    def test_balance_ge_checklist_doc_exists(self):
        assert _doc("balance-ge-activation-final-checklist.md").exists()


# ---------------------------------------------------------------------------
# B) Migration content — top-level elements
# ---------------------------------------------------------------------------

class TestMigrationContent:
    """The migration SQL must contain all required structural elements."""

    @pytest.fixture(scope="class")
    def sql(self):
        return _read(_migration("009_credential_vault_schema.sql"))

    def test_contains_credential_vault_credentials_table(self, sql):
        assert "credential_vault_credentials" in sql

    def test_contains_credential_vault_audit_events_table(self, sql):
        assert "credential_vault_audit_events" in sql

    def test_contains_encrypted_value(self, sql):
        assert "encrypted_value" in sql

    def test_contains_key_version(self, sql):
        assert "key_version" in sql

    def test_contains_masked_hint(self, sql):
        assert "masked_hint" in sql

    def test_contains_last_accessed_at(self, sql):
        assert "last_accessed_at" in sql

    def test_contains_rotated_at(self, sql):
        assert "rotated_at" in sql

    def test_contains_revoked_at(self, sql):
        assert "revoked_at" in sql

    def test_contains_created_by(self, sql):
        assert "created_by" in sql

    def test_contains_updated_by(self, sql):
        assert "updated_by" in sql

    def test_contains_provider(self, sql):
        assert "provider" in sql

    def test_contains_credential_type(self, sql):
        assert "credential_type" in sql

    def test_contains_tenant_id(self, sql):
        assert "tenant_id" in sql

    def test_contains_metadata_jsonb(self, sql):
        assert "metadata" in sql
        assert "JSONB" in sql

    def test_contains_gen_random_uuid(self, sql):
        assert "gen_random_uuid()" in sql

    def test_contains_create_index_if_not_exists(self, sql):
        assert "CREATE INDEX IF NOT EXISTS" in sql

    def test_contains_alter_table_if_exists_balance(self, sql):
        assert "ALTER TABLE IF EXISTS tenant_balance_credentials" in sql

    def test_contains_add_column_if_not_exists(self, sql):
        assert "ADD COLUMN IF NOT EXISTS" in sql

    def test_contains_do_not_execute_statement(self, sql):
        assert "do not execute manually against production" in sql.lower()

    def test_contains_schema_only_statement(self, sql):
        assert "schema-only" in sql.lower() or "schema only" in sql.lower()

    def test_contains_no_runtime_behavior_change_statement(self, sql):
        assert "runtime" in sql.lower()

    def test_contains_no_balance_activation_statement(self, sql):
        assert "Balance.ge" in sql


# ---------------------------------------------------------------------------
# C) Generic vault schema — required fields
# ---------------------------------------------------------------------------

class TestVaultSchemaFields:
    """All required fields must appear in the credential_vault_credentials CREATE."""

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
        "metadata",
        "last_test_status",
        "last_tested_at",
        "last_accessed_at",
        "rotated_at",
        "revoked_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    ]

    @pytest.fixture(scope="class")
    def vault_section(self):
        sql = _read(_migration("009_credential_vault_schema.sql"))
        start = sql.index("CREATE TABLE IF NOT EXISTS credential_vault_credentials")
        end = sql.index(";", start)
        return sql[start:end]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_field_present_in_vault_table(self, vault_section, field):
        assert field in vault_section, f"Field {field!r} missing from credential_vault_credentials"

    def test_uuid_primary_key(self, vault_section):
        assert "UUID" in vault_section
        assert "PRIMARY KEY" in vault_section

    def test_default_status_active(self, vault_section):
        assert "DEFAULT 'active'" in vault_section

    def test_active_boolean_default_true(self, vault_section):
        assert "BOOLEAN" in vault_section
        assert "DEFAULT TRUE" in vault_section

    def test_metadata_jsonb_default_empty(self, vault_section):
        assert "'{}'::jsonb" in vault_section

    def test_created_at_default_now(self, vault_section):
        assert "DEFAULT NOW()" in vault_section


# ---------------------------------------------------------------------------
# D) Audit table schema — required fields
# ---------------------------------------------------------------------------

class TestAuditSchemaFields:
    """All required audit fields must appear in credential_vault_audit_events."""

    REQUIRED_FIELDS = [
        "id",
        "tenant_id",
        "provider",
        "credential_type",
        "action",
        "actor",
        "purpose",
        "result",
        "key_version",
        "request_id",
        "metadata",
        "created_at",
    ]

    @pytest.fixture(scope="class")
    def audit_section(self):
        sql = _read(_migration("009_credential_vault_schema.sql"))
        start = sql.index("CREATE TABLE IF NOT EXISTS credential_vault_audit_events")
        end = sql.index(";", start)
        return sql[start:end]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_audit_field_present(self, audit_section, field):
        assert field in audit_section, f"Audit field {field!r} missing from credential_vault_audit_events"

    def test_audit_uuid_primary_key(self, audit_section):
        assert "UUID" in audit_section
        assert "PRIMARY KEY" in audit_section
        assert "gen_random_uuid()" in audit_section

    def test_audit_metadata_jsonb(self, audit_section):
        assert "JSONB" in audit_section
        assert "'{}'::jsonb" in audit_section

    def test_audit_result_constraint(self, audit_section):
        assert "CHECK" in audit_section
        assert "result" in audit_section


# ---------------------------------------------------------------------------
# E) Additive-only safety — no destructive SQL
# ---------------------------------------------------------------------------

class TestAdditiveOnlySafety:
    """Migration must not contain any destructive SQL operations."""

    @pytest.fixture(scope="class")
    def sql(self):
        return _read(_migration("009_credential_vault_schema.sql")).upper()

    def test_no_drop_table(self, sql):
        assert "DROP TABLE" not in sql

    def test_no_drop_column(self, sql):
        assert "DROP COLUMN" not in sql

    def test_no_drop_constraint(self, sql):
        assert "DROP CONSTRAINT" not in sql

    def test_no_truncate(self, sql):
        assert "TRUNCATE" not in sql

    def test_no_delete_from(self, sql):
        assert "DELETE FROM" not in sql

    def test_no_update_tenant_balance_credentials(self, sql):
        assert "UPDATE TENANT_BALANCE_CREDENTIALS" not in sql

    def test_no_update_tenant_email_credentials(self, sql):
        assert "UPDATE TENANT_EMAIL_CREDENTIALS" not in sql

    def test_no_update_tenant_rsge_credentials(self, sql):
        assert "UPDATE TENANT_RSGE_CREDENTIALS" not in sql

    def test_no_update_rsge_credentials(self, sql):
        assert "UPDATE RSGE_CREDENTIALS" not in sql

    def test_no_update_webhooks(self, sql):
        assert "UPDATE WEBHOOKS" not in sql

    def test_no_alter_balance_drop(self, sql):
        # Must not drop anything from tenant_balance_credentials
        assert "ALTER TABLE TENANT_BALANCE_CREDENTIALS DROP" not in sql

    def test_no_alter_api_key_drop_not_null(self, sql):
        assert "ALTER COLUMN API_KEY DROP NOT NULL" not in sql


# ---------------------------------------------------------------------------
# F) Plaintext safety — no secret copying
# ---------------------------------------------------------------------------

class TestPlaintextSafety:
    """Migration must not copy or expose any plaintext credential value."""

    @pytest.fixture(scope="class")
    def sql(self):
        return _read(_migration("009_credential_vault_schema.sql"))

    def test_no_set_encrypted_value_from_api_key(self, sql):
        assert "SET encrypted_value = api_key" not in sql

    def test_no_encrypted_value_equals_api_key(self, sql):
        assert "encrypted_value = api_key" not in sql

    def test_no_api_key_concatenation(self, sql):
        assert "api_key ||" not in sql

    def test_no_concat_api_key(self, sql):
        assert "CONCAT(api_key" not in sql
        assert "concat(api_key" not in sql

    def test_no_raw_secret_field(self, sql):
        assert "raw_secret" not in sql

    def test_no_plaintext_secret_field(self, sql):
        assert "plaintext_secret" not in sql

    def test_api_key_column_not_removed(self, sql):
        assert "DROP COLUMN" not in sql.upper()

    def test_api_key_column_not_nulled(self, sql):
        # Should not UPDATE to null api_key
        assert "SET api_key = NULL" not in sql
        assert "api_key = NULL" not in sql


# ---------------------------------------------------------------------------
# G) Constraint and index checks
# ---------------------------------------------------------------------------

class TestConstraintsAndIndexes:
    """Required constraints and indexes must be present."""

    @pytest.fixture(scope="class")
    def sql(self):
        return _read(_migration("009_credential_vault_schema.sql"))

    def test_unique_constraint_present(self, sql):
        assert "UNIQUE" in sql

    def test_check_constraints_present(self, sql):
        assert "CHECK" in sql

    def test_provider_nonempty_constraint(self, sql):
        assert "provider <> ''" in sql

    def test_credential_type_nonempty_constraint(self, sql):
        assert "credential_type <> ''" in sql

    def test_encrypted_value_nonempty_constraint(self, sql):
        assert "encrypted_value <> ''" in sql

    def test_key_version_nonempty_constraint(self, sql):
        assert "key_version <> ''" in sql

    def test_index_tenant_provider_type(self, sql):
        assert "idx_credential_vault_tenant_provider_type" in sql

    def test_index_active(self, sql):
        assert "idx_credential_vault_active" in sql

    def test_index_status(self, sql):
        assert "idx_credential_vault_status" in sql

    def test_index_audit_tenant_provider(self, sql):
        assert "idx_credential_vault_audit_tenant_provider" in sql

    def test_index_audit_created_at(self, sql):
        assert "idx_credential_vault_audit_created_at" in sql


# ---------------------------------------------------------------------------
# H) Cross-reference checks — architecture doc
# ---------------------------------------------------------------------------

class TestArchitectureDocCrossReference:
    """The architecture doc must cross-reference vault concepts used in migration."""

    @pytest.fixture(scope="class")
    def arch_doc(self):
        return _read(_doc("credential-vault-runtime-architecture.md"))

    def test_arch_doc_references_11cc(self, arch_doc):
        assert "11C-C" in arch_doc

    def test_arch_doc_references_encrypted_value(self, arch_doc):
        assert "encrypted_value" in arch_doc

    def test_arch_doc_references_key_version(self, arch_doc):
        assert "key_version" in arch_doc

    def test_arch_doc_references_masked_hint(self, arch_doc):
        assert "masked_hint" in arch_doc

    def test_arch_doc_no_balance_activation(self, arch_doc):
        assert "Balance.ge has not been activated" in arch_doc

    def test_arch_doc_no_production_db_touched(self, arch_doc):
        assert "No production database has been touched" in arch_doc


# ---------------------------------------------------------------------------
# I) Current source grounding — balance_credentials_service.py
# ---------------------------------------------------------------------------

class TestCurrentSourceGrounding:
    """The current balance service must confirm the plaintext baseline."""

    @pytest.fixture(scope="class")
    def svc_src(self):
        return _read(_service("balance_credentials_service.py"))

    def test_balance_service_references_tenant_balance_credentials(self, svc_src):
        assert "tenant_balance_credentials" in svc_src

    def test_balance_service_references_api_key_column(self, svc_src):
        assert "api_key" in svc_src

    def test_balance_service_has_no_encrypted_value_yet(self, svc_src):
        assert "encrypted_value" not in svc_src

    def test_balance_service_has_no_vault_service_import(self, svc_src):
        assert "CredentialVaultService" not in svc_src

    def test_balance_service_has_no_key_version_yet(self, svc_src):
        assert "key_version" not in svc_src

    def test_migration_file_does_not_exist_in_service(self, svc_src):
        assert "009_credential_vault_schema" not in svc_src


# ---------------------------------------------------------------------------
# J) No runtime/import/network execution (self-referential source scan)
# ---------------------------------------------------------------------------

class TestNoRuntimeImportsInTestFile:
    """
    This test file must not load any runtime vault or connector modules.
    Assertions use split-string concatenation to avoid self-match.
    """

    def _self_src(self) -> str:
        return Path(__file__).read_text(encoding="utf-8")

    def test_no_runtime_vault_module_loaded(self):
        src = self._self_src()
        forbidden_import = "import" + " app."
        forbidden_from = "from" + " app."
        assert forbidden_import not in src, "Test file must not load runtime vault modules"
        assert forbidden_from not in src, "Test file must not load runtime vault modules"

    def test_no_outbound_http_client(self):
        src = self._self_src()
        # Split to avoid self-match on assertion string
        assert "req" + "uests" not in src

    def test_no_sync_http_client(self):
        src = self._self_src()
        assert "http" + "x" not in src

    def test_no_url_fetcher(self):
        src = self._self_src()
        assert "url" + "lib" not in src

    def test_no_db_driver_connect(self):
        src = self._self_src()
        # Split to avoid self-match
        assert "psycopg" + "2.connect" not in src
        assert "psycopg" + "2.extras" not in src

    def test_no_async_db_connect(self):
        src = self._self_src()
        assert "asyncpg." + "connect" not in src

    def test_no_shell_invocation(self):
        src = self._self_src()
        assert "sub" + "process" not in src

    def test_no_cloud_cli_call(self):
        src = self._self_src()
        # Split to avoid self-match
        assert "g" + "cloud" not in src

    def test_no_cursor_execute(self):
        src = self._self_src()
        assert "cur." + "execute" not in src
        assert "conn." + "execute" not in src


# ---------------------------------------------------------------------------
# K) Safety status — migration header assertions
# ---------------------------------------------------------------------------

class TestSafetyStatus:
    """The migration file header must encode all required safety statements."""

    @pytest.fixture(scope="class")
    def sql(self):
        return _read(_migration("009_credential_vault_schema.sql"))

    def test_do_not_execute_manually(self, sql):
        assert "do not execute manually against production" in sql.lower()

    def test_schema_only_statement(self, sql):
        assert "schema" in sql.lower() and "only" in sql.lower()

    def test_no_runtime_behavior_change(self, sql):
        assert "runtime behavior" in sql.lower()

    def test_plaintext_migration_is_future_work(self, sql):
        assert "future" in sql.lower()
        assert "plaintext" in sql.lower()

    def test_balance_ge_remains_inactive(self, sql):
        assert "Balance.ge remains inactive" in sql

    def test_migration_is_idempotent_by_design(self, sql):
        # All CREATE and ALTER use IF NOT EXISTS / IF EXISTS guards
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "ALTER TABLE IF EXISTS" in sql
        assert "ADD COLUMN IF NOT EXISTS" in sql
        assert "CREATE INDEX IF NOT EXISTS" in sql

    def test_migration_numbered_009(self):
        assert _migration("009_credential_vault_schema.sql").exists()

    def test_prior_migration_008_still_exists(self):
        assert _migration("008_outgoing_invoice_columns.sql").exists()
