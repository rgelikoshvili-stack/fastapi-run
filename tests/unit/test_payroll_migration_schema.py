"""Read-only tests for the payroll and employee additive migration.

These checks inspect SQL text only. They do not execute SQL, connect to a
database, import payroll runtime code, or validate payroll formulas.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "app" / "storage" / "migrations" / "006_payroll_employee_schema.sql"

REQUIRED_TABLES = {
    "employees",
    "pension_transfers",
    "payroll_runs",
    "payroll_run_lines",
}

REQUIRED_INDEXES = {
    "idx_employees_tenant_status",
    "idx_payroll_runs_tenant_period_status",
    "idx_payroll_run_lines_tenant_run",
    "idx_pension_transfers_tenant_period_status",
}


def _sql() -> str:
    assert MIGRATION.exists(), "payroll/employee migration file is missing"
    return MIGRATION.read_text(encoding="utf-8")


def _table_block(sql: str, table: str) -> str:
    pattern = re.compile(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\s*\((.*?)\);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    assert match, f"missing CREATE TABLE IF NOT EXISTS block for {table}"
    return match.group(1)


def test_payroll_migration_file_exists_and_is_additive_sql():
    sql = _sql().upper()
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql


def test_payroll_migration_contains_required_tables():
    sql = _sql()
    for table in REQUIRED_TABLES:
        _table_block(sql, table)


def test_payroll_migration_contains_required_indexes():
    sql = _sql().lower()
    for index in REQUIRED_INDEXES:
        assert f"create index if not exists {index}" in sql


def test_payroll_migration_has_no_destructive_statements():
    sql = _sql()
    normalized = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    upper = normalized.upper()

    forbidden_patterns = {
        "DROP TABLE": r"\bDROP\s+TABLE\b",
        "TRUNCATE": r"\bTRUNCATE\b",
        "DELETE FROM": r"\bDELETE\s+FROM\b",
        "UPDATE": r"\bUPDATE\b",
        "ALTER": r"\bALTER\b",
    }
    for label, pattern in forbidden_patterns.items():
        assert not re.search(pattern, upper), f"destructive or non-additive SQL detected: {label}"


def test_payroll_employee_tables_are_tenant_scoped():
    sql = _sql()
    for table in REQUIRED_TABLES:
        block = _table_block(sql, table).lower()
        assert "tenant_id" in block, f"{table} must include tenant_id"
        assert "not null" in block, f"{table} tenant_id must be NOT NULL"


def test_payroll_migration_keeps_runtime_schema_shape():
    sql = re.sub(r"\s+", " ", _sql().lower())
    expected_fragments = [
        "unique(tenant_id, personal_number)",
        "draft_ids jsonb default '[]'::jsonb",
        "run_id int not null references payroll_runs(id) on delete cascade",
        "pit_20pct numeric(12,2) not null",
        "employee_pension_2pct numeric(12,2) not null",
        "employer_pension_2pct numeric(12,2) not null",
        "net_salary numeric(12,2) not null",
    ]
    for fragment in expected_fragments:
        assert fragment in sql


def test_payroll_migration_index_shapes_are_tenant_first():
    sql = re.sub(r"\s+", " ", _sql().lower())
    assert "on employees(tenant_id, status)" in sql
    assert "on payroll_runs(tenant_id, period, status)" in sql
    assert "on payroll_run_lines(tenant_id, run_id)" in sql
    assert "on pension_transfers(tenant_id, period, status)" in sql
