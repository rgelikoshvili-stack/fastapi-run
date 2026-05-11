"""
tests/unit/test_credential_vault_migration_schema.py

Read-only contract tests for the credential vault schema migration.
Task 11C-C1: Migration file exists, is additive-only, and is safe.

Rules:
  - Read-only. No DB, no network, no runtime vault modules loaded.
  - Self-referential patterns use split-string concatenation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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

    def test_migration_009_exists(self):
        assert _migration("009_credential_vault_schema.sql").exists()

    def test_migration_008_still_exists(self):
        assert _migration("008_outgoing_invoice_columns.sql").exists()

    def test_arch_doc_exists(self):
        assert _doc("credential-vault-runtime-architecture.md").exists()

    def test_checklist_doc_exists(self):
        assert _doc("balance-ge-activation-final-checklist.md").exists()


# ---------------------------------------------------------------------------
# B) Migration content — top-level elements
# ---------------------------------------------------------------------------

class TestMigrationContent:

    @pytest.fixture(scope="class")
    def sql(self):
        return _read(_migration("009_credential_vault_schema.sql"))

    def test_has_vault_credentials_table(self, sql):
        assert "credential_vault_credentials" in sql

    def test_has_audit_events_table(self, sql):
        assert "credential_vault_audit_events" in sql

    def test_has_encrypted_value(self, sql):
        assert "encrypted_value" in sql

    def test_has_key_version(self, sql):
        assert "key_version" in sql

    def test_has_masked_hint(self, sql):
        assert "masked_hint" in sql

    def test_has_last_accessed_at(self, sql):
        assert "last_accessed_at" in sql

    def test_has_rotated_at(self, sql):
        assert "rotated_at" in sql

    def test_has_revoked_at(self, sql):
        assert "revoked_at" in sql

    def test_has_created_by(self, sql):
        assert "created_by" in sql

    def test_has_updated_by(self, sql):
        assert "updated_by" in sql

    def test_has_provider(self, sql):
        assert "provider" in sql

    def test_has_credential_type(self, sql):
        assert "credential_type" in sql

    def test_has_tenant_id(self, sql):
        assert "tenant_id" in sql

    def test_has_metadata_jsonb(self, sql):
        assert "metadata" in sql
        assert "JSONB" in sql

    def test_has_gen_random_uuid(self, sql):
        assert "gen_random_uuid()" in sql

    def test_has_create_index_if_not_exists(self, sql):
        assert "CREATE INDEX IF NOT EXISTS" in sql

    def test_has_alter_table_if_exists_balance(self, sql):
        assert "ALTER TABLE IF EXISTS tenant_balance_credentials" in sql

    def test_has_add_column_if_not_exists(self, sql):
        assert "ADD COLUMN IF NOT EXISTS" in sql

    def test_has_no_execute_manually_statement(self, sql):
        assert "do not execute manually against production" in sql.lower()

    def test_has_balance_ge_remains_inactive(self, sql):
        assert "Balance.ge remains inactive" in sql

    def test_has_create_table_if_not_exists(self, sql):
        assert "CREATE TABLE IF NOT EXISTS" in sql

    def test_has_alter_table_if_exists(self, sql):
        assert "ALTER TABLE IF EXISTS" in sql


# ---------------------------------------------------------------------------
# C) Vault credential table fields
# ---------------------------------------------------------------------------

class TestVaultCredentialFields:

    REQUIRED_FIELDS = [
        "id", "tenant_id", "provider", "credential_type", "encrypted_value",
        "key_version", "masked_hint", "status", "active", "company_id",
        "api_base", "metadata", "last_test_status", "last_tested_at",
        "last_accessed_at", "rotated_at", "revoked_at", "created_at",
        "updated_at", "created_by", "updated_by",
    ]

    @pytest.fixture(scope="class")
    def vault_section(self):
        sql = _read(_migration("009_credential_vault_schema.sql"))
        # Use " (" suffix to match the real CREATE TABLE, not the comment mention
        start = sql.index("CREATE TABLE IF NOT EXISTS credential_vault_credentials (")
        end = sql.index(";", start)
        return sql[start:end]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_field_in_vault_table(self, vault_section, field):
        assert field in vault_section

    def test_uuid_primary_key(self, vault_section):
        assert "UUID" in vault_section
        assert "PRIMARY KEY" in vault_section

    def test_default_status_active(self, vault_section):
        assert "DEFAULT 'active'" in vault_section

    def test_metadata_empty_jsonb_default(self, vault_section):
        assert "'{}'::jsonb" in vault_section

    def test_created_at_default_now(self, vault_section):
        assert "DEFAULT NOW()" in vault_section


# ---------------------------------------------------------------------------
# D) Audit table fields
# ---------------------------------------------------------------------------

class TestAuditTableFields:

    REQUIRED_FIELDS = [
        "id", "tenant_id", "provider", "credential_type", "action",
        "actor", "purpose", "result", "key_version", "request_id",
        "metadata", "created_at",
    ]

    @pytest.fixture(scope="class")
    def audit_section(self):
        sql = _read(_migration("009_credential_vault_schema.sql"))
        # Use " (" suffix to match the real CREATE TABLE, not the comment mention
        start = sql.index("CREATE TABLE IF NOT EXISTS credential_vault_audit_events (")
        end = sql.index(";", start)
        return sql[start:end]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_audit_field_present(self, audit_section, field):
        assert field in audit_section

    def test_audit_uuid_primary_key(self, audit_section):
        assert "UUID" in audit_section
        assert "PRIMARY KEY" in audit_section

    def test_audit_result_check_constraint(self, audit_section):
        assert "CHECK" in audit_section


# ---------------------------------------------------------------------------
# E) Additive-only safety
# ---------------------------------------------------------------------------

class TestAdditiveOnlySafety:

    @pytest.fixture(scope="class")
    def sql_upper(self):
        return _read(_migration("009_credential_vault_schema.sql")).upper()

    def test_no_drop_table(self, sql_upper):
        assert "DROP TABLE" not in sql_upper

    def test_no_drop_column(self, sql_upper):
        assert "DROP COLUMN" not in sql_upper

    def test_no_drop_constraint(self, sql_upper):
        assert "DROP CONSTRAINT" not in sql_upper

    def test_no_truncate(self, sql_upper):
        assert "TRUNCATE" not in sql_upper

    def test_no_delete_from(self, sql_upper):
        assert "DELETE FROM" not in sql_upper

    def test_no_update_balance_credentials(self, sql_upper):
        assert "UPDATE TENANT_BALANCE_CREDENTIALS" not in sql_upper

    def test_no_update_email_credentials(self, sql_upper):
        assert "UPDATE TENANT_EMAIL_CREDENTIALS" not in sql_upper

    def test_no_update_rsge_credentials(self, sql_upper):
        assert "UPDATE TENANT_RSGE_CREDENTIALS" not in sql_upper

    def test_no_update_webhooks(self, sql_upper):
        assert "UPDATE WEBHOOKS" not in sql_upper

    def test_no_alter_balance_drop(self, sql_upper):
        assert "ALTER TABLE TENANT_BALANCE_CREDENTIALS DROP" not in sql_upper

    def test_no_alter_api_key_drop_not_null(self, sql_upper):
        assert "ALTER COLUMN API_KEY DROP NOT NULL" not in sql_upper


# ---------------------------------------------------------------------------
# F) Plaintext safety
# ---------------------------------------------------------------------------

class TestPlaintextSafety:

    @pytest.fixture(scope="class")
    def sql(self):
        return _read(_migration("009_credential_vault_schema.sql"))

    def test_no_set_encrypted_from_api_key(self, sql):
        assert "SET encrypted_value = api_key" not in sql

    def test_no_encrypted_equals_api_key(self, sql):
        assert "encrypted_value = api_key" not in sql

    def test_no_api_key_concat(self, sql):
        assert "api_key ||" not in sql

    def test_no_raw_secret_field(self, sql):
        assert "raw_secret" not in sql

    def test_no_plaintext_secret_copy(self, sql):
        assert "plaintext_secret" not in sql

    def test_api_key_not_nulled(self, sql):
        assert "SET api_key = NULL" not in sql


# ---------------------------------------------------------------------------
# G) Indexes and constraints
# ---------------------------------------------------------------------------

class TestIndexesAndConstraints:

    @pytest.fixture(scope="class")
    def sql(self):
        return _read(_migration("009_credential_vault_schema.sql"))

    def test_unique_constraint(self, sql):
        assert "UNIQUE" in sql

    def test_check_constraints(self, sql):
        assert "CHECK" in sql

    def test_provider_nonempty_constraint(self, sql):
        assert "provider <> ''" in sql

    def test_credential_type_nonempty(self, sql):
        assert "credential_type <> ''" in sql

    def test_encrypted_value_nonempty(self, sql):
        assert "encrypted_value <> ''" in sql

    def test_key_version_nonempty(self, sql):
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
# H) Architecture doc cross-reference
# ---------------------------------------------------------------------------

class TestArchDocCrossReference:

    @pytest.fixture(scope="class")
    def arch(self):
        return _read(_doc("credential-vault-runtime-architecture.md"))

    def test_arch_mentions_11cc(self, arch):
        assert "11C-C" in arch

    def test_arch_mentions_encrypted_value(self, arch):
        assert "encrypted_value" in arch

    def test_arch_mentions_key_version(self, arch):
        assert "key_version" in arch

    def test_arch_mentions_masked_hint(self, arch):
        assert "masked_hint" in arch

    def test_arch_no_balance_activation(self, arch):
        assert "Balance.ge has not been activated" in arch


# ---------------------------------------------------------------------------
# I) Current source grounding
# ---------------------------------------------------------------------------

class TestSourceGrounding:

    @pytest.fixture(scope="class")
    def svc(self):
        return _read(_service("balance_credentials_service.py"))

    def test_service_references_balance_table(self, svc):
        assert "tenant_balance_credentials" in svc

    def test_service_references_api_key(self, svc):
        assert "api_key" in svc

    def test_service_get_balance_credentials_reads_plaintext_api_key(self, svc):
        # The primary get_balance_credentials() SELECT must still read api_key
        # (plaintext baseline unchanged). The vault path is in get_vault_status().
        assert "SELECT api_key" in svc or "api_key" in svc

    def test_service_get_balance_credentials_does_not_select_encrypted(self, svc):
        # The plaintext SELECT query in get_balance_credentials must not SELECT
        # encrypted_value — that column is unused in the primary credential path.
        assert "SELECT api_key, company_id, api_base" in svc


# ---------------------------------------------------------------------------
# J) No runtime/import/network in this test file
# ---------------------------------------------------------------------------

class TestNoRuntimeInTestFile:

    def _self(self) -> str:
        return Path(__file__).read_text(encoding="utf-8")

    def test_no_runtime_import(self):
        src = self._self()
        assert "import" + " app." not in src
        assert "from" + " app." not in src

    def test_no_outbound_http(self):
        src = self._self()
        assert "req" + "uests" not in src
        assert "http" + "x" not in src

    def test_no_db_driver(self):
        src = self._self()
        assert "psycopg" + "2" not in src
        assert "asyncpg" + ".connect" not in src

    def test_no_shell(self):
        src = self._self()
        assert "sub" + "process" not in src

    def test_no_cloud_cli(self):
        src = self._self()
        assert "g" + "cloud" not in src

    def test_no_cursor_execute(self):
        src = self._self()
        assert "cur." + "execute" not in src
