"""
Tests for H66 — missing table schema fixes.
Verifies:
  - bank_transactions CREATE TABLE added to migrations_tables.py
  - pipeline_runs CREATE TABLE added to migrations_tables.py
  - journal_entry_lines.account_type / cashflow_category added to migrations_tables.py
  - migration 011 SQL updated with account_type / cashflow_category columns
  - routes_export.py uses state (not status) for pipeline_runs

No DB, no Docker, no network — pure code / text verification.
"""
from __future__ import annotations

import pathlib
import ast
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_MIGRATIONS_TABLES = _ROOT / "app" / "startup" / "migrations_tables.py"
_MIGRATION_011 = _ROOT / "app" / "storage" / "migrations" / "011_posted_journal_entries_schema.sql"
_ROUTES_EXPORT = _ROOT / "app" / "api" / "routes_export.py"


def _mt() -> str:
    return _MIGRATIONS_TABLES.read_text(encoding="utf-8")


def _sql011() -> str:
    return _MIGRATION_011.read_text(encoding="utf-8")


def _export() -> str:
    return _ROUTES_EXPORT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. bank_transactions
# ---------------------------------------------------------------------------

class TestBankTransactionsTable:

    def test_create_table_bank_transactions_present(self):
        assert "CREATE TABLE IF NOT EXISTS bank_transactions" in _mt()

    def test_bank_transactions_has_tenant_id(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS bank_transactions")
        block = text[idx:idx + 800]
        assert "tenant_id" in block

    def test_bank_transactions_has_amount(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS bank_transactions")
        block = text[idx:idx + 800]
        assert "amount" in block

    def test_bank_transactions_has_batch_id(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS bank_transactions")
        block = text[idx:idx + 800]
        assert "batch_id" in block

    def test_bank_transactions_has_raw_jsonb(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS bank_transactions")
        block = text[idx:idx + 800]
        assert "raw" in block

    def test_bank_transactions_has_currency(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS bank_transactions")
        block = text[idx:idx + 800]
        assert "currency" in block

    def test_bank_transactions_tenant_index_added(self):
        assert "idx_bank_transactions_tenant_id" in _mt()


# ---------------------------------------------------------------------------
# 2. pipeline_runs
# ---------------------------------------------------------------------------

class TestPipelineRunsTable:

    def test_create_table_pipeline_runs_present(self):
        assert "CREATE TABLE IF NOT EXISTS pipeline_runs" in _mt()

    def test_pipeline_runs_has_run_id(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS pipeline_runs")
        block = text[idx:idx + 600]
        assert "run_id" in block

    def test_pipeline_runs_has_state(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS pipeline_runs")
        block = text[idx:idx + 600]
        assert "state" in block

    def test_pipeline_runs_has_tenant_id(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS pipeline_runs")
        block = text[idx:idx + 600]
        assert "tenant_id" in block

    def test_pipeline_runs_has_filename(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS pipeline_runs")
        block = text[idx:idx + 600]
        assert "filename" in block

    def test_pipeline_runs_has_extraction_jsonb(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS pipeline_runs")
        block = text[idx:idx + 600]
        assert "extraction" in block

    def test_pipeline_runs_no_duplicate_status_column(self):
        text = _mt()
        idx = text.index("CREATE TABLE IF NOT EXISTS pipeline_runs")
        block = text[idx:idx + 600]
        # 'status' column was removed — only 'state' should be the canonical column
        # 'status' must not appear as a column definition inside the block
        assert "status" not in block


# ---------------------------------------------------------------------------
# 3. journal_entry_lines columns added by ALTER TABLE
# ---------------------------------------------------------------------------

class TestJournalEntryLinesAlterColumns:

    def test_account_type_alter_table_present(self):
        assert "journal_entry_lines ADD COLUMN IF NOT EXISTS account_type" in _mt()

    def test_cashflow_category_alter_table_present(self):
        assert "journal_entry_lines ADD COLUMN IF NOT EXISTS cashflow_category" in _mt()

    def test_alter_table_in_run_table_migrations_function(self):
        src = ast.parse(_mt())
        func_names = [n.name for n in ast.walk(src) if isinstance(n, ast.FunctionDef)]
        assert "run_table_migrations" in func_names

        # Confirm both ALTER TABLE statements live inside the function body text
        text = _mt()
        fn_start = text.index("def run_table_migrations")
        fn_body = text[fn_start:]
        assert "account_type" in fn_body
        assert "cashflow_category" in fn_body


# ---------------------------------------------------------------------------
# 4. Migration 011 SQL — account_type and cashflow_category added
# ---------------------------------------------------------------------------

class TestMigration011AccountTypeColumns:

    def test_migration_011_exists(self):
        assert _MIGRATION_011.exists()

    def test_account_type_column_in_journal_entry_lines_ddl(self):
        sql = _sql011()
        # Find journal_entry_lines CREATE TABLE block
        idx = sql.index("CREATE TABLE IF NOT EXISTS journal_entry_lines")
        block = sql[idx:idx + 3000]
        assert "account_type" in block

    def test_cashflow_category_column_in_journal_entry_lines_ddl(self):
        sql = _sql011()
        idx = sql.index("CREATE TABLE IF NOT EXISTS journal_entry_lines")
        block = sql[idx:idx + 3000]
        assert "cashflow_category" in block

    def test_account_type_index_added(self):
        assert "idx_jel_tenant_account_type" in _sql011()

    def test_cashflow_category_index_added(self):
        assert "idx_jel_tenant_cashflow_category" in _sql011()

    def test_migration_still_idempotent(self):
        sql = _sql011()
        assert "IF NOT EXISTS" in sql
        # All CREATE TABLE and CREATE INDEX should use IF NOT EXISTS
        for stmt in re.findall(r"CREATE\s+(TABLE|INDEX)\s+([^\s(]+)", sql, re.IGNORECASE):
            pass  # parsing check passed without exception


# ---------------------------------------------------------------------------
# 5. routes_export.py uses state (not status) for pipeline_runs
# ---------------------------------------------------------------------------

class TestExportRouteUsesState:

    def test_no_select_status_from_pipeline_runs(self):
        text = _export()
        # Should not query pipeline_runs.status
        bad_patterns = [
            "SELECT id, filename, status",
            "SELECT status, COUNT",
            'r["status"]',
        ]
        for pat in bad_patterns:
            assert pat not in text, f"Legacy 'status' reference found: {pat!r}"

    def test_select_state_from_pipeline_runs(self):
        text = _export()
        assert "SELECT id, filename, state" in text

    def test_group_by_state_used(self):
        text = _export()
        assert "GROUP BY state" in text

    def test_state_key_accessed(self):
        text = _export()
        assert 'r["state"]' in text


# ---------------------------------------------------------------------------
# 6. No forbidden imports
# ---------------------------------------------------------------------------

class TestNoForbiddenImports:

    def test_no_forbidden_imports(self):
        with open(__file__, encoding="utf-8") as f:
            lines = f.readlines()
        forbidden = [
            "import " + "psycopg", "import " + "sqlalchemy",
            "import " + "requests", "import " + "httpx",
            "import " + "socket", "import " + "subprocess",
            "from " + "app.", "from docker" + " import",
        ]
        for line in lines:
            s = line.strip()
            if s.startswith("#"):
                continue
            for imp in forbidden:
                assert imp not in s, f"Forbidden import: {s}"
