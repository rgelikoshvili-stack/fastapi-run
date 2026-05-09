"""Read-only contract checks for Task 10E core schema hardening.

These tests inspect documentation, scripts, and manifest metadata only. They do
not import app startup code, connect to a database, execute SQL, or run
migrations.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "core-schema-hardening-plan.md"
MANIFEST = ROOT / "tests" / "fixtures" / "schema_manifest.json"

AUTH_TENANT_TABLES = {
    "users",
    "password_reset_tokens",
    "tenants",
}

CREDENTIAL_TABLES = {
    "tenant_secrets",
    "tenant_email_credentials",
    "tenant_balance_credentials",
    "webhooks",
    "webhook_deliveries",
}

ACCOUNTING_TABLES = {
    "journal_drafts",
    "draft_comments",
    "journal_entries",
    "posting_logs",
    "audit_events",
}

MANIFEST_CORE_TABLES = (
    AUTH_TENANT_TABLES
    | CREDENTIAL_TABLES
    | ACCOUNTING_TABLES
    | {"tenant_settings"}
)


def _plan_text() -> str:
    assert PLAN.exists(), "core schema hardening plan is missing"
    return PLAN.read_text(encoding="utf-8")


def _manifest_tables() -> dict[str, dict]:
    assert MANIFEST.exists(), "schema manifest fixture is missing"
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tables = data.get("tables")
    assert isinstance(tables, list) and tables
    return {row["table_name"]: row for row in tables}


def _python_execute_string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = ""
        if isinstance(func, ast.Attribute):
            func_name = func.attr
        elif isinstance(func, ast.Name):
            func_name = func.id
        if func_name not in {"execute", "executemany"} or not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            literals.append(first_arg.value)
    return literals


def test_core_schema_hardening_plan_exists_and_names_required_tables():
    text = _plan_text().lower()
    required_tables = AUTH_TENANT_TABLES | CREDENTIAL_TABLES | ACCOUNTING_TABLES
    missing = [table for table in sorted(required_tables) if table not in text]
    assert not missing, f"core hardening plan missing tables: {missing}"


def test_core_schema_plan_requires_security_and_accounting_invariants():
    text = _plan_text().lower()
    required_phrases = [
        "encryption-at-rest",
        "encrypted value",
        "masked secret reads",
        "tenant isolation",
        "approval-first",
        "posted-only",
        "destructive migrations are forbidden",
        "production db must not be touched",
        "runtime ddl removal must wait",
        "additive migrations",
        "idempotency",
        "audit metadata",
        "rotation metadata",
    ]
    missing = [phrase for phrase in required_phrases if phrase not in text]
    assert not missing, f"core hardening plan missing required principles: {missing}"


def test_core_schema_plan_separates_10e_staged_slices():
    text = _plan_text().lower()
    expected = [
        "task 10e-c",
        "credential and security schema contract",
        "task 10e-d",
        "accounting truth schema contract",
        "task 10e-e",
        "auth and tenant schema contract",
    ]
    missing = [phrase for phrase in expected if phrase not in text]
    assert not missing, f"core hardening plan missing staged roadmap items: {missing}"


def test_schema_manifest_tracks_key_core_tables_and_keeps_risks_honest():
    tables = _manifest_tables()
    missing = [table for table in sorted(MANIFEST_CORE_TABLES) if table not in tables]
    assert not missing, f"schema manifest missing core tables: {missing}"

    for table in MANIFEST_CORE_TABLES:
        row = tables[table]
        assert row["migration_coverage"] in {"none", "partial", "full"}
        if table not in {"webhooks", "webhook_deliveries", "draft_comments", "audit_events"}:
            assert row["migration_coverage"] != "full", f"{table} must not be marked complete yet"
        assert row["risk"] in {"medium", "high", "critical"}

    secret_holding_tables = {
        "tenant_secrets",
        "tenant_email_credentials",
        "tenant_balance_credentials",
        "webhooks",
        "users",
    }
    for table in secret_holding_tables:
        assert tables[table]["risk"] in {"high", "critical"}, f"{table} must remain high-risk"


def test_active_scripts_do_not_execute_drop_table_users():
    scripts = ROOT / "scripts"
    assert scripts.exists()
    offenders: list[str] = []
    for path in scripts.rglob("*.py"):
        for literal in _python_execute_string_literals(path):
            normalized = " ".join(literal.lower().split())
            if "drop table if exists users" in normalized:
                offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, f"active scripts execute DROP TABLE IF EXISTS users: {offenders}"
