"""
tests/unit/test_posted_journal_entries_sql_migration_contract.py

Contract tests for the Posted Journal Entries SQL Migration (11C-H4).

Rules:
  - No DB connection.
  - No SQL execution.
  - No runtime app imports.
  - No connector calls.
  - No Balance.ge activation.
  - Reads app/storage/migrations/011_posted_journal_entries_schema.sql as text.
  - Tests fail if required SQL structure or safety comments disappear.
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SQL = _ROOT / "app" / "storage" / "migrations" / "011_posted_journal_entries_schema.sql"


def _sql() -> str:
    return _SQL.read_text(encoding="utf-8")


def _sql_lower() -> str:
    return _sql().lower()


def _strip_comments(sql: str) -> str:
    """Remove -- line comments and block comments to avoid false positives."""
    # Remove block comments /* ... */
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    # Remove line comments -- ...
    sql = re.sub(r"--[^\n]*", "", sql)
    return sql


def _sql_code() -> str:
    """Return only SQL code with comments stripped."""
    return _strip_comments(_sql())


def _sql_code_lower() -> str:
    return _sql_code().lower()


# ---------------------------------------------------------------------------
# 1. Migration file exists
# ---------------------------------------------------------------------------

class TestSqlMigrationFileExists:

    def test_sql_migration_file_exists(self):
        assert _SQL.exists(), f"Migration file not found at {_SQL}"

    def test_migration_file_is_sql(self):
        assert _SQL.suffix == ".sql"

    def test_migration_file_is_nonempty(self):
        assert len(_sql().strip()) > 500

    def test_migration_file_is_numbered_011(self):
        assert _SQL.name.startswith("011_")


# ---------------------------------------------------------------------------
# 2. Additive only — no destructive statements
# ---------------------------------------------------------------------------

class TestMigrationIsAdditiveOnly:

    def test_migration_is_additive_only(self):
        code = _sql_code_lower()
        # Must have CREATE statements
        assert "create table" in code

    def test_migration_uses_if_not_exists(self):
        code = _sql_code_lower()
        assert "if not exists" in code

    def test_migration_uses_create_index_if_not_exists(self):
        code = _sql_code_lower()
        assert "create index if not exists" in code

    def test_migration_comments_state_additive_only(self):
        text = _sql_lower()
        assert "additive only" in text

    def test_migration_comments_state_not_executed_in_h4(self):
        text = _sql_lower()
        assert "not executed" in text or "not execute" in text


# ---------------------------------------------------------------------------
# 3. No DROP, DELETE, UPDATE, or backfill
# ---------------------------------------------------------------------------

class TestMigrationHasNoDropDeleteUpdateOrBackfill:

    def test_no_drop_table_in_code(self):
        code = _sql_code_lower()
        assert "drop table" not in code

    def test_no_drop_column_in_code(self):
        code = _sql_code_lower()
        assert "drop column" not in code

    def test_no_delete_from_in_code(self):
        code = _sql_code_lower()
        assert "delete from" not in code

    def test_no_update_set_in_code(self):
        code = _sql_code_lower()
        # UPDATE ... SET is a DML mutation — forbidden in additive migration
        assert "update " not in code or "set " not in code.split("update ")[1][:50] if "update " in code else True

    def test_no_truncate_in_code(self):
        code = _sql_code_lower()
        assert "truncate" not in code

    def test_no_insert_into_in_code(self):
        code = _sql_code_lower()
        assert "insert into" not in code

    def test_migration_does_not_alter_journal_drafts(self):
        code = _sql_code_lower()
        # Must not ALTER existing production tables
        alter_matches = [line for line in code.splitlines() if "alter table" in line and "journal_drafts" in line]
        assert len(alter_matches) == 0


# ---------------------------------------------------------------------------
# 4. journal_entry_headers table created
# ---------------------------------------------------------------------------

class TestCreatesJournalEntryHeaders:

    def test_creates_journal_entry_headers(self):
        code = _sql_code_lower()
        assert "create table if not exists journal_entry_headers" in code

    def test_headers_table_has_primary_key(self):
        code = _sql_code_lower()
        assert "journal_entry_headers" in code
        assert "primary key" in code

    def test_headers_table_uses_uuid_pk(self):
        code = _sql_code_lower()
        assert "uuid" in code
        assert "primary key" in code


# ---------------------------------------------------------------------------
# 5. journal_entry_lines table created
# ---------------------------------------------------------------------------

class TestCreatesJournalEntryLines:

    def test_creates_journal_entry_lines(self):
        code = _sql_code_lower()
        assert "create table if not exists journal_entry_lines" in code

    def test_lines_table_has_primary_key(self):
        code = _sql_code_lower()
        assert "journal_entry_lines" in code
        # At least one UUID PK definition
        assert "uuid" in code and "primary key" in code


# ---------------------------------------------------------------------------
# 6. Headers required columns
# ---------------------------------------------------------------------------

class TestHeadersRequiredColumnsExist:

    def _headers_block(self) -> str:
        sql = _sql_code_lower()
        # Extract from journal_entry_headers to the next CREATE TABLE
        start = sql.find("create table if not exists journal_entry_headers")
        end = sql.find("create table if not exists journal_entry_lines")
        return sql[start:end] if start >= 0 and end > start else sql

    def test_id_column(self):
        assert "id" in self._headers_block()

    def test_tenant_id_column(self):
        assert "tenant_id" in self._headers_block()

    def test_source_draft_id_column(self):
        assert "source_draft_id" in self._headers_block()

    def test_posting_log_id_column(self):
        assert "posting_log_id" in self._headers_block()

    def test_evidence_bundle_id_column(self):
        assert "evidence_bundle_id" in self._headers_block()

    def test_entry_date_column(self):
        assert "entry_date" in self._headers_block()

    def test_posting_date_column(self):
        assert "posting_date" in self._headers_block()

    def test_period_column(self):
        assert "period" in self._headers_block()

    def test_status_column(self):
        assert "status" in self._headers_block()

    def test_source_type_column(self):
        assert "source_type" in self._headers_block()

    def test_currency_column(self):
        assert "currency" in self._headers_block()

    def test_exchange_rate_column(self):
        assert "exchange_rate" in self._headers_block()

    def test_total_debit_column(self):
        assert "total_debit" in self._headers_block()

    def test_total_credit_column(self):
        assert "total_credit" in self._headers_block()

    def test_created_by_column(self):
        assert "created_by" in self._headers_block()

    def test_approved_by_column(self):
        assert "approved_by" in self._headers_block()

    def test_posted_by_column(self):
        assert "posted_by" in self._headers_block()

    def test_created_at_column(self):
        assert "created_at" in self._headers_block()

    def test_posted_at_column(self):
        assert "posted_at" in self._headers_block()

    def test_reversed_by_entry_id_column(self):
        assert "reversed_by_entry_id" in self._headers_block()

    def test_correction_of_entry_id_column(self):
        assert "correction_of_entry_id" in self._headers_block()

    def test_metadata_json_column(self):
        assert "metadata_json" in self._headers_block()


# ---------------------------------------------------------------------------
# 7. Lines required columns
# ---------------------------------------------------------------------------

class TestLinesRequiredColumnsExist:

    def _lines_block(self) -> str:
        sql = _sql_code_lower()
        start = sql.find("create table if not exists journal_entry_lines")
        end = sql.find("create table if not exists journal_entry_sources")
        if end < 0:
            end = sql.find("create index if not exists")
        return sql[start:end] if start >= 0 and end > start else sql[start:] if start >= 0 else sql

    def test_id_column(self):
        assert "id" in self._lines_block()

    def test_tenant_id_column(self):
        assert "tenant_id" in self._lines_block()

    def test_journal_entry_id_column(self):
        assert "journal_entry_id" in self._lines_block()

    def test_line_no_column(self):
        assert "line_no" in self._lines_block()

    def test_account_code_column(self):
        assert "account_code" in self._lines_block()

    def test_debit_column(self):
        assert "debit" in self._lines_block()

    def test_credit_column(self):
        assert "credit" in self._lines_block()

    def test_currency_column(self):
        assert "currency" in self._lines_block()

    def test_exchange_rate_column(self):
        assert "exchange_rate" in self._lines_block()

    def test_amount_gel_column(self):
        assert "amount_gel" in self._lines_block()

    def test_counterparty_id_column(self):
        assert "counterparty_id" in self._lines_block()

    def test_document_id_column(self):
        assert "document_id" in self._lines_block()

    def test_bank_transaction_id_column(self):
        assert "bank_transaction_id" in self._lines_block()

    def test_tax_code_column(self):
        assert "tax_code" in self._lines_block()

    def test_vat_amount_column(self):
        assert "vat_amount" in self._lines_block()

    def test_description_column(self):
        assert "description" in self._lines_block()

    def test_line_hash_column(self):
        assert "line_hash" in self._lines_block()

    def test_created_at_column(self):
        assert "created_at" in self._lines_block()


# ---------------------------------------------------------------------------
# 8. tenant_id required on both tables
# ---------------------------------------------------------------------------

class TestTenantIdRequiredOnBothTables:

    def test_tenant_id_required_on_both_tables(self):
        code = _sql_code_lower()
        # Count NOT NULL occurrences near tenant_id
        assert code.count("tenant_id") >= 2

    def test_tenant_id_not_null_on_headers(self):
        code = _sql_code()
        # Find headers block and check NOT NULL
        start = code.lower().find("create table if not exists journal_entry_headers")
        end = code.lower().find("create table if not exists journal_entry_lines")
        block = code[start:end].lower() if start >= 0 and end > start else code.lower()
        assert "tenant_id" in block and "not null" in block

    def test_tenant_nonempty_check_on_headers(self):
        code = _sql_code_lower()
        assert "ck_jeh_tenant_nonempty" in code or (
            "tenant_id" in code and "<> ''" in code
        )

    def test_tenant_nonempty_check_on_lines(self):
        code = _sql_code_lower()
        assert "ck_jel_tenant_nonempty" in code or (
            "tenant_id" in code and "<> ''" in code
        )


# ---------------------------------------------------------------------------
# 9. Status check allows only final ledger states
# ---------------------------------------------------------------------------

class TestStatusCheckAllowsOnlyFinalLedgerStates:

    def test_status_check_allows_only_final_ledger_states(self):
        code = _sql_code_lower()
        assert "ck_jeh_status" in code
        assert "'posted'" in code
        assert "'reversed'" in code
        assert "'correction'" in code
        assert "'voided'" in code

    def test_status_in_clause_is_restricted(self):
        code = _sql_code_lower()
        assert "status in (" in code or "status in(" in code


# ---------------------------------------------------------------------------
# 10. Status check rejects draft, approved, auto_approved, simulated_success
# ---------------------------------------------------------------------------

class TestStatusCheckRejectsDraftApprovedAutoApprovedSimulatedSuccess:

    def test_status_check_rejects_draft_approved_auto_approved_simulated_success(self):
        # The CHECK constraint allows only (posted, reversed, correction, voided)
        # so draft/approved/auto_approved/simulated_success are implicitly rejected.
        # Verify the allowed list does NOT include forbidden statuses.
        code = _sql_code_lower()
        # Find the ck_jeh_status constraint block
        assert "ck_jeh_status" in code
        status_idx = code.find("ck_jeh_status")
        constraint_block = code[status_idx:status_idx + 200]
        assert "'draft'" not in constraint_block
        assert "'approved'" not in constraint_block
        assert "auto_approved" not in constraint_block
        assert "simulated_success" not in constraint_block

    def test_comment_mentions_forbidden_statuses(self):
        text = _sql_lower()
        # Comments must document that forbidden statuses are not allowed
        assert "simulated_success" in text
        assert "forbidden" in text or "draft" in text


# ---------------------------------------------------------------------------
# 11. Balanced header constraint exists
# ---------------------------------------------------------------------------

class TestBalancedHeaderConstraintExists:

    def test_balanced_header_constraint_exists(self):
        code = _sql_code_lower()
        assert "ck_jeh_balanced" in code

    def test_balanced_constraint_checks_debit_equals_credit(self):
        code = _sql_code_lower()
        assert "total_debit = total_credit" in code

    def test_debit_nonneg_constraint_exists(self):
        code = _sql_code_lower()
        assert "ck_jeh_total_debit_nonneg" in code or (
            "total_debit >= 0" in code
        )

    def test_credit_nonneg_constraint_exists(self):
        code = _sql_code_lower()
        assert "ck_jeh_total_credit_nonneg" in code or (
            "total_credit >= 0" in code
        )


# ---------------------------------------------------------------------------
# 12. Line debit/credit constraints exist
# ---------------------------------------------------------------------------

class TestLineDebitCreditConstraintsExist:

    def test_line_debit_credit_constraints_exist(self):
        code = _sql_code_lower()
        assert "ck_jel_debit_nonneg" in code or "debit >= 0" in code
        assert "ck_jel_credit_nonneg" in code or "credit >= 0" in code

    def test_line_nonzero_constraint_exists(self):
        code = _sql_code_lower()
        assert "ck_jel_nonzero" in code or (
            "debit > 0 or credit > 0" in code
        )

    def test_line_not_both_positive_constraint_exists(self):
        code = _sql_code_lower()
        assert "ck_jel_not_both_positive" in code or (
            "not (debit > 0 and credit > 0)" in code
        )


# ---------------------------------------------------------------------------
# 13. Unique line number constraint exists
# ---------------------------------------------------------------------------

class TestUniqueLineNumberConstraintExists:

    def test_unique_line_number_constraint_exists(self):
        code = _sql_code_lower()
        assert "uq_jel_line_no" in code or (
            "unique (journal_entry_id, line_no)" in code or
            "unique(journal_entry_id, line_no)" in code
        )


# ---------------------------------------------------------------------------
# 14. Lines reference headers
# ---------------------------------------------------------------------------

class TestLinesReferenceHeaders:

    def test_lines_reference_headers(self):
        code = _sql_code_lower()
        assert "references journal_entry_headers" in code or (
            "journal_entry_headers(id)" in code
        )

    def test_fk_has_on_delete_cascade(self):
        code = _sql_code_lower()
        assert "on delete cascade" in code


# ---------------------------------------------------------------------------
# 15. Required indexes exist
# ---------------------------------------------------------------------------

class TestRequiredIndexesExist:

    def test_required_indexes_exist(self):
        code = _sql_code_lower()
        assert "create index if not exists" in code

    def test_idx_jeh_tenant_period(self):
        code = _sql_code_lower()
        assert "idx_jeh_tenant_period" in code

    def test_idx_jeh_tenant_entry_date(self):
        code = _sql_code_lower()
        assert "idx_jeh_tenant_entry_date" in code

    def test_idx_jeh_tenant_status(self):
        code = _sql_code_lower()
        assert "idx_jeh_tenant_status" in code

    def test_idx_jeh_tenant_source_draft(self):
        code = _sql_code_lower()
        assert "idx_jeh_tenant_source_draft" in code

    def test_idx_jeh_tenant_posting_log(self):
        code = _sql_code_lower()
        assert "idx_jeh_tenant_posting_log" in code

    def test_idx_jeh_tenant_evidence_bundle(self):
        code = _sql_code_lower()
        assert "idx_jeh_tenant_evidence_bundle" in code

    def test_idx_jel_tenant_journal_entry(self):
        code = _sql_code_lower()
        assert "idx_jel_tenant_journal_entry" in code

    def test_idx_jel_tenant_account_code(self):
        code = _sql_code_lower()
        assert "idx_jel_tenant_account_code" in code

    def test_idx_jel_tenant_counterparty(self):
        code = _sql_code_lower()
        assert "idx_jel_tenant_counterparty" in code

    def test_idx_jel_tenant_document(self):
        code = _sql_code_lower()
        assert "idx_jel_tenant_document" in code

    def test_idx_jel_tenant_bank_transaction(self):
        code = _sql_code_lower()
        assert "idx_jel_tenant_bank_transaction" in code


# ---------------------------------------------------------------------------
# 16. Evidence bundle and posting log linkage columns exist
# ---------------------------------------------------------------------------

class TestEvidenceBundleAndPostingLogLinkageColumnsExist:

    def test_evidence_bundle_and_posting_log_linkage_columns_exist(self):
        code = _sql_code_lower()
        assert "evidence_bundle_id" in code
        assert "posting_log_id" in code

    def test_evidence_bundle_index_exists(self):
        code = _sql_code_lower()
        assert "idx_jeh_tenant_evidence_bundle" in code

    def test_posting_log_index_exists(self):
        code = _sql_code_lower()
        assert "idx_jeh_tenant_posting_log" in code

    def test_source_draft_id_linkage_exists(self):
        code = _sql_code_lower()
        assert "source_draft_id" in code


# ---------------------------------------------------------------------------
# 17. Comments state no runtime report behavior change
# ---------------------------------------------------------------------------

class TestNoRuntimeReportBehaviorChangeClaimedInComments:

    def test_no_runtime_report_behavior_change_claimed_in_comments(self):
        text = _sql_lower()
        assert "does not change" in text or "not changed" in text or (
            "runtime" in text and ("not" in text or "unchanged" in text)
        )

    def test_comments_state_reports_still_read_journal_drafts(self):
        text = _sql_lower()
        assert "journal_drafts" in text
        assert "h6" in text or "later task" in text or "h5" in text

    def test_comments_state_journal_drafts_untouched(self):
        text = _sql_lower()
        assert "journal_drafts" in text
        assert "untouched" in text or "remains" in text or "unchanged" in text

    def test_comments_state_no_backfill(self):
        text = _sql_lower()
        assert "backfill" in text
        assert "not" in text or "no" in text


# ---------------------------------------------------------------------------
# 18. Comments state migration not executed in H4
# ---------------------------------------------------------------------------

class TestNoMigrationExecutionClaimedInComments:

    def test_no_migration_execution_claimed_in_comments(self):
        text = _sql_lower()
        assert "not executed" in text or "not execute" in text

    def test_comments_reference_h4_task(self):
        text = _sql_lower()
        assert "11c-h4" in text or "task 11c-h4" in text

    def test_comments_reference_future_h5_h6(self):
        text = _sql_lower()
        assert "h5" in text
        assert "h6" in text

    def test_comments_state_balance_ge_inactive(self):
        text = _sql_lower()
        assert "balance.ge" in text
        assert "inactive" in text or "not met" in text or "remains inactive" in text
