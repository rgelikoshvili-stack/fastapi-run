"""Read-only tests for outgoing invoice additive column migration.

These checks inspect SQL text only. They do not execute SQL, connect to a
database, import runtime invoice code, or validate invoice business behavior.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "app" / "storage" / "migrations" / "008_outgoing_invoice_columns.sql"

EXPECTED_COLUMNS = {
    "sent_at": "TIMESTAMPTZ",
    "invoice_date": "DATE",
    "delivery_date": "DATE",
    "seller_name": "TEXT",
    "seller_inn": "TEXT",
    "seller_address": "TEXT",
    "seller_phone": "TEXT",
    "seller_bank": "TEXT",
    "seller_swift": "TEXT",
    "seller_account": "TEXT",
    "buyer_address": "TEXT",
    "buyer_phone": "TEXT",
    "due_date": "DATE",
    "currency": "TEXT DEFAULT 'GEL'",
    "exchange_rate": "NUMERIC(18,6)",
    "reminder_sent_at": "TIMESTAMP",
}

EXCLUDED_OBJECTS = {
    "invoice_counters",
    "invoices",
    "invoice_lines",
    "purchase_orders",
    "purchase_order_lines",
    "customers",
    "customer_interactions",
}


def _sql() -> str:
    assert MIGRATION.exists(), "outgoing invoice column migration file is missing"
    return MIGRATION.read_text(encoding="utf-8")


def _sql_without_comments() -> str:
    return re.sub(r"--.*?$", "", _sql(), flags=re.MULTILINE)


def test_outgoing_invoice_migration_file_exists_and_uses_add_column():
    sql = _sql_without_comments().upper()
    assert "ALTER TABLE OUTGOING_INVOICES" in sql
    assert "ADD COLUMN IF NOT EXISTS" in sql


def test_outgoing_invoice_migration_contains_expected_columns_and_types():
    normalized = re.sub(r"\s+", " ", _sql_without_comments().lower())
    for column, column_type in EXPECTED_COLUMNS.items():
        expected = f"add column if not exists {column} {column_type.lower()}"
        assert expected in normalized, f"missing expected outgoing_invoices column: {expected}"


def test_outgoing_invoice_migration_is_column_only():
    normalized = re.sub(r"\s+", " ", _sql_without_comments().lower()).strip()
    assert normalized.startswith("alter table outgoing_invoices")
    assert normalized.endswith(";")
    assert "create table" not in normalized
    assert "create index" not in normalized
    assert "enable row level security" not in normalized
    assert "create policy" not in normalized
    assert "drop constraint" not in normalized
    assert "add constraint" not in normalized


def test_outgoing_invoice_migration_has_no_destructive_or_dml_statements():
    upper = _sql_without_comments().upper()
    forbidden_patterns = {
        "DROP": r"\bDROP\b",
        "TRUNCATE": r"\bTRUNCATE\b",
        "DELETE": r"\bDELETE\b",
        "UPDATE": r"\bUPDATE\b",
        "CREATE TABLE": r"\bCREATE\s+TABLE\b",
    }
    for label, pattern in forbidden_patterns.items():
        assert not re.search(pattern, upper), f"forbidden SQL detected: {label}"


def test_outgoing_invoice_migration_mentions_no_deferred_objects():
    lowered = _sql_without_comments().lower()
    for name in EXCLUDED_OBJECTS:
        assert not re.search(rf"\b{name}\b", lowered), (
            f"{name} must be deferred from outgoing invoice column migration"
        )


def test_outgoing_invoice_migration_changes_only_outgoing_invoices():
    targets = re.findall(r"\balter\s+table\s+([a-z_]+)", _sql_without_comments(), flags=re.IGNORECASE)
    assert targets
    assert set(target.lower() for target in targets) == {"outgoing_invoices"}
