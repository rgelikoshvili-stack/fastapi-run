"""
tests/unit/test_evidence_bundle_migration_schema.py

Read-only schema tests for migration 010_evidence_bundle_schema.sql.

Rules:
  - Reads SQL file as text only.
  - Does not import runtime modules.
  - Does not connect to any database.
  - Does not execute SQL.
  - Asserts structure, safety, and absence of destructive patterns.
"""
from __future__ import annotations

import pathlib
import re

import pytest

MIGRATION_PATH = pathlib.Path(
    "app/storage/migrations/010_evidence_bundle_schema.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"Migration file not found: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A) File presence and basic structure
# ---------------------------------------------------------------------------

class TestFilePresentAndStructured:

    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists()

    def test_migration_file_nonempty(self, sql):
        assert len(sql.strip()) > 200

    def test_migration_file_has_header_comment(self, sql):
        assert "Migration 010" in sql

    def test_migration_file_has_not_executed_notice(self, sql):
        assert "NOT executed" in sql or "NOT execute" in sql


# ---------------------------------------------------------------------------
# B) evidence_bundles table presence and required fields
# ---------------------------------------------------------------------------

class TestEvidenceBundlesTable:

    def test_evidence_bundles_table_exists(self, sql):
        assert "CREATE TABLE IF NOT EXISTS evidence_bundles" in sql

    def test_id_field(self, sql):
        assert "id" in sql
        assert "gen_random_uuid()" in sql

    def test_tenant_id_field(self, sql):
        assert "tenant_id" in sql

    def test_source_type_field(self, sql):
        assert "source_type" in sql

    def test_source_id_field(self, sql):
        assert "source_id" in sql

    def test_source_file_id_field(self, sql):
        assert "source_file_id" in sql

    def test_source_file_hash_field(self, sql):
        assert "source_file_hash" in sql

    def test_bank_transaction_id_field(self, sql):
        assert "bank_transaction_id" in sql

    def test_document_id_field(self, sql):
        assert "document_id" in sql

    def test_ocr_result_id_field(self, sql):
        assert "ocr_result_id" in sql

    def test_journal_draft_id_field(self, sql):
        assert "journal_draft_id" in sql

    def test_journal_entry_id_field(self, sql):
        assert "journal_entry_id" in sql

    def test_approval_event_id_field(self, sql):
        assert "approval_event_id" in sql

    def test_posting_log_id_field(self, sql):
        assert "posting_log_id" in sql

    def test_connector_provider_field(self, sql):
        assert "connector_provider" in sql

    def test_connector_operation_field(self, sql):
        assert "connector_operation" in sql

    def test_payload_preview_hash_field(self, sql):
        assert "payload_preview_hash" in sql

    def test_ai_reasoning_field(self, sql):
        assert "ai_reasoning" in sql
        assert "JSONB" in sql

    def test_extracted_fields_field(self, sql):
        assert "extracted_fields" in sql

    def test_risk_flags_field(self, sql):
        assert "risk_flags" in sql

    def test_confidence_field(self, sql):
        assert "confidence" in sql
        assert "NUMERIC" in sql

    def test_status_field(self, sql):
        assert "status" in sql

    def test_created_at_field(self, sql):
        assert "created_at" in sql
        assert "TIMESTAMPTZ" in sql

    def test_updated_at_field(self, sql):
        assert "updated_at" in sql

    def test_created_by_field(self, sql):
        assert "created_by" in sql

    def test_updated_by_field(self, sql):
        assert "updated_by" in sql


# ---------------------------------------------------------------------------
# C) evidence_bundle_events table presence and required fields
# ---------------------------------------------------------------------------

class TestEvidenceBundleEventsTable:

    def test_evidence_bundle_events_table_exists(self, sql):
        assert "CREATE TABLE IF NOT EXISTS evidence_bundle_events" in sql

    def test_events_id_field(self, sql):
        section = sql[sql.find("evidence_bundle_events"):]
        assert "id" in section

    def test_events_tenant_id(self, sql):
        section = sql[sql.find("evidence_bundle_events"):]
        assert "tenant_id" in section

    def test_events_evidence_bundle_id(self, sql):
        assert "evidence_bundle_id" in sql

    def test_events_event_type(self, sql):
        assert "event_type" in sql

    def test_events_actor(self, sql):
        section = sql[sql.find("evidence_bundle_events"):]
        assert "actor" in section

    def test_events_event_ref_type(self, sql):
        assert "event_ref_type" in sql

    def test_events_event_ref_id(self, sql):
        assert "event_ref_id" in sql

    def test_events_metadata_jsonb(self, sql):
        section = sql[sql.find("evidence_bundle_events"):]
        assert "metadata" in section
        assert "JSONB" in section

    def test_events_created_at(self, sql):
        section = sql[sql.find("evidence_bundle_events"):]
        assert "created_at" in section

    def test_events_fk_reference(self, sql):
        assert "REFERENCES evidence_bundles(id)" in sql


# ---------------------------------------------------------------------------
# D) Constraints
# ---------------------------------------------------------------------------

class TestConstraints:

    def test_source_type_nonempty_constraint(self, sql):
        assert "source_type <> ''" in sql

    def test_status_allowed_values_constraint(self, sql):
        assert "'draft'" in sql
        assert "'ready'" in sql
        assert "'approved'" in sql
        assert "'posted'" in sql
        assert "'failed'" in sql
        assert "'archived'" in sql

    def test_confidence_range_constraint(self, sql):
        assert "confidence >= 0" in sql
        assert "confidence <= 1" in sql

    def test_event_type_nonempty_constraint(self, sql):
        assert "event_type <> ''" in sql


# ---------------------------------------------------------------------------
# E) Indexes presence
# ---------------------------------------------------------------------------

class TestIndexes:

    def test_idx_evidence_bundles_tenant(self, sql):
        assert "idx_evidence_bundles_tenant" in sql

    def test_idx_evidence_bundles_source(self, sql):
        assert "idx_evidence_bundles_source" in sql

    def test_idx_evidence_bundles_journal_draft(self, sql):
        assert "idx_evidence_bundles_journal_draft" in sql

    def test_idx_evidence_bundles_journal_entry(self, sql):
        assert "idx_evidence_bundles_journal_entry" in sql

    def test_idx_evidence_bundles_approval(self, sql):
        assert "idx_evidence_bundles_approval" in sql

    def test_idx_evidence_bundles_posting_log(self, sql):
        assert "idx_evidence_bundles_posting_log" in sql

    def test_idx_evidence_bundle_events_bundle(self, sql):
        assert "idx_evidence_bundle_events_bundle" in sql

    def test_idx_evidence_bundle_events_tenant_created(self, sql):
        assert "idx_evidence_bundle_events_tenant_created" in sql


# ---------------------------------------------------------------------------
# F) Destructive SQL patterns must be absent
# ---------------------------------------------------------------------------

class TestNoDestructiveSQL:

    @pytest.mark.parametrize("pattern", [
        r"\bDROP\s+TABLE\b",
        r"\bDROP\s+COLUMN\b",
        r"\bDROP\s+CONSTRAINT\b",
        r"\bTRUNCATE\b",
        r"\bDELETE\s+FROM\b",
        r"\bUPDATE\s+\w",
        r"\bALTER\s+TABLE\b.+\bDROP\b",
    ])
    def test_no_destructive_pattern(self, sql, pattern):
        matches = re.findall(pattern, sql, re.IGNORECASE)
        assert not matches, f"Forbidden destructive pattern found: {pattern!r} → {matches}"


# ---------------------------------------------------------------------------
# G) No Balance.ge activation wording
# ---------------------------------------------------------------------------

class TestNoBalanceGeActivation:

    @pytest.mark.parametrize("forbidden", [
        "BALANCE_API_KEY",
        "activate_balance",
        "balance_activation",
        "balance.ge live",
        "enable_balance",
    ])
    def test_no_balance_ge_activation(self, sql, forbidden):
        assert forbidden.lower() not in sql.lower(), (
            f"Forbidden Balance.ge activation term found: {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# H) No credential/secret fields introduced
# ---------------------------------------------------------------------------

class TestNoSecretFields:

    @staticmethod
    def _strip_comments(sql_text: str) -> str:
        """Remove -- line comments and COMMENT ON ... IS '...' blocks."""
        lines = []
        for line in sql_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            lines.append(line)
        code = "\n".join(lines)
        # Remove COMMENT ON ... IS '...'; blocks (may span lines)
        code = re.sub(r"COMMENT\s+ON\b[^;]*;", "", code, flags=re.DOTALL | re.IGNORECASE)
        return code

    @pytest.mark.parametrize("forbidden_col", [
        "api_key",
        "password",
        "raw_secret",
        "decrypted_value",
        "plaintext_",
    ])
    def test_no_secret_column_introduced(self, sql, forbidden_col):
        # Strip comment text so that documentation saying "No api_key..."
        # does not trigger a false positive; only actual column definitions count.
        code = self._strip_comments(sql)
        assert forbidden_col.lower() not in code.lower(), (
            f"Forbidden secret-like column name found in migration DDL: {forbidden_col!r}"
        )

    def test_payload_preview_is_hash_only(self, sql):
        assert "payload_preview_hash" in sql
        assert "raw_connector_payload" not in sql
        assert "payload_body" not in sql

    def test_ai_reasoning_no_api_key(self, sql):
        # ai_reasoning column defined as JSONB — ensure no api_key column defined
        code = self._strip_comments(sql)
        assert "api_key" not in code.lower()

    def test_no_data_backfill(self, sql):
        assert "INSERT INTO" not in sql
        assert "COPY " not in sql


# ---------------------------------------------------------------------------
# I) IF NOT EXISTS guards
# ---------------------------------------------------------------------------

class TestIdempotencyGuards:

    def test_evidence_bundles_if_not_exists(self, sql):
        assert "CREATE TABLE IF NOT EXISTS evidence_bundles" in sql

    def test_evidence_bundle_events_if_not_exists(self, sql):
        assert "CREATE TABLE IF NOT EXISTS evidence_bundle_events" in sql

    def test_indexes_use_if_not_exists(self, sql):
        index_creates = re.findall(r"CREATE INDEX", sql, re.IGNORECASE)
        if_not_exists = re.findall(r"CREATE INDEX IF NOT EXISTS", sql, re.IGNORECASE)
        assert len(index_creates) == len(if_not_exists), (
            "All CREATE INDEX statements must use IF NOT EXISTS"
        )
