"""Read-only tests for the inventory ERP additive migration.

These checks inspect SQL text only. They do not execute SQL, connect to a
database, or import inventory runtime code.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "app" / "storage" / "migrations" / "005_inventory_erp_schema.sql"

REQUIRED_TABLES = {
    "inventory_categories",
    "warehouses",
    "inventory_items",
    "stock_movements",
    "purchase_orders",
    "purchase_order_lines",
}

DIRECT_TENANT_TABLES = REQUIRED_TABLES - {"purchase_order_lines"}

REQUIRED_INDEXES = {
    "idx_inventory_items_tenant",
    "idx_stock_movements_tenant_item",
    "idx_purchase_orders_tenant_status",
}


def _sql() -> str:
    assert MIGRATION.exists(), "inventory migration file is missing"
    return MIGRATION.read_text(encoding="utf-8")


def _table_block(sql: str, table: str) -> str:
    pattern = re.compile(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\s*\((.*?)\);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    assert match, f"missing CREATE TABLE IF NOT EXISTS block for {table}"
    return match.group(1)


def test_inventory_migration_file_exists_and_is_additive_sql():
    sql = _sql()
    assert "CREATE TABLE IF NOT EXISTS" in sql.upper()
    assert "CREATE INDEX IF NOT EXISTS" in sql.upper()


def test_inventory_migration_contains_required_tables():
    sql = _sql()
    for table in REQUIRED_TABLES:
        _table_block(sql, table)


def test_inventory_migration_contains_required_indexes():
    sql = _sql().lower()
    for index in REQUIRED_INDEXES:
        assert f"create index if not exists {index}" in sql


def test_inventory_migration_has_no_destructive_statements():
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


def test_inventory_tenant_scoping_is_explicit_or_parent_scoped():
    sql = _sql()
    for table in DIRECT_TENANT_TABLES:
        block = _table_block(sql, table).lower()
        assert "tenant_id" in block, f"{table} must include tenant_id"
        assert "not null" in block, f"{table} tenant_id must be NOT NULL"

    po_lines = _table_block(sql, "purchase_order_lines").lower()
    assert "po_id" in po_lines
    assert "references purchase_orders(id)" in po_lines
    assert "item_id" in po_lines
    assert "references inventory_items(id)" in po_lines


def test_inventory_migration_keeps_runtime_index_shape():
    sql = re.sub(r"\s+", " ", _sql().lower())
    assert "on inventory_items(tenant_id, is_active)" in sql
    assert "on stock_movements(tenant_id, item_id, movement_date desc)" in sql
    assert "on purchase_orders(tenant_id, status)" in sql
