"""Read-only tests for the trade partner additive migration.

These checks inspect SQL text only. They do not execute SQL, connect to a
database, import trade runtime code, or validate trade business logic.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "app" / "storage" / "migrations" / "007_trade_partner_schema.sql"

REQUIRED_TABLES = {
    "customers",
    "customer_interactions",
}

EXCLUDED_TABLES = {
    "purchase_orders",
    "purchase_order_lines",
    "outgoing_invoices",
    "invoice_counters",
    "invoices",
    "invoice_lines",
    "recurring_invoice_templates",
}

REQUIRED_INDEXES = {
    "idx_customers_tenant_id",
    "idx_customers_tenant_type_status",
    "idx_customer_interactions_tenant_customer",
    "idx_customer_interactions_tenant_created_at",
}


def _sql() -> str:
    assert MIGRATION.exists(), "trade partner migration file is missing"
    return MIGRATION.read_text(encoding="utf-8")


def _table_block(sql: str, table: str) -> str:
    pattern = re.compile(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\s*\((.*?)\);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    assert match, f"missing CREATE TABLE IF NOT EXISTS block for {table}"
    return match.group(1)


def test_trade_migration_file_exists_and_is_additive_sql():
    sql = _sql().upper()
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql


def test_trade_migration_contains_only_partner_tables():
    sql = _sql()
    for table in REQUIRED_TABLES:
        _table_block(sql, table)

    lowered = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE).lower()
    for table in EXCLUDED_TABLES:
        assert table not in lowered, f"{table} must be deferred from trade partner migration"


def test_trade_migration_contains_required_indexes():
    sql = _sql().lower()
    for index in REQUIRED_INDEXES:
        assert f"create index if not exists {index}" in sql


def test_trade_migration_has_no_destructive_statements():
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


def test_trade_partner_tables_are_tenant_scoped():
    sql = _sql()
    for table in REQUIRED_TABLES:
        block = _table_block(sql, table).lower()
        assert "tenant_id" in block, f"{table} must include tenant_id"
        assert "not null" in block, f"{table} tenant_id must be NOT NULL"

    interactions = _table_block(sql, "customer_interactions").lower()
    assert "customer_id" in interactions
    assert "references customers(id)" in interactions


def test_trade_partner_migration_keeps_runtime_schema_shape():
    sql = re.sub(r"\s+", " ", _sql().lower())
    expected_fragments = [
        "tenant_id text not null default 'default'",
        "type text default 'client'",
        "status text default 'active'",
        "customer_id integer references customers(id) on delete cascade",
        "amount numeric",
    ]
    for fragment in expected_fragments:
        assert fragment in sql


def test_trade_partner_indexes_are_tenant_first():
    sql = re.sub(r"\s+", " ", _sql().lower())
    assert "on customers(tenant_id)" in sql
    assert "on customers(tenant_id, type, status)" in sql
    assert "on customer_interactions(tenant_id, customer_id)" in sql
    assert "on customer_interactions(tenant_id, created_at desc)" in sql
