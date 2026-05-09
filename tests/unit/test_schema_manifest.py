"""Non-destructive schema manifest and migration inventory checks.

These tests only read repository files. They do not import app startup code,
execute SQL, connect to a database, or run migrations.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "schema_manifest.json"

REQUIRED_TABLE_FIELDS = {
    "table_name",
    "owner_module",
    "current_creation_source",
    "migration_coverage",
    "runtime_created",
    "has_tenant_id",
    "has_indexes",
    "has_audit_fields",
    "risk",
    "recommended_next_action",
}

MIGRATION_COVERAGE = {"full", "partial", "none"}
TENANT_VALUES = {True, False, "unknown"}
COVERAGE_VALUES = {True, False, "partial", "unknown"}
RISK_VALUES = {"low", "medium", "high", "critical"}

ACCOUNTING_CRITICAL_TABLES = {
    "journal_drafts",
    "journal_entries",
    "posting_logs",
    "audit_events",
    "processed_documents",
    "inventory_items",
    "stock_movements",
    "purchase_orders",
    "payroll_runs",
    "payroll_run_lines",
    "outgoing_invoices",
    "invoice_counters",
    "tenant_balance_credentials",
    "tenant_email_credentials",
    "tenant_secrets",
}

ACCOUNTING_CORE_TABLES = {
    "journal_drafts",
    "journal_entries",
    "posting_logs",
    "audit_events",
}

CREDENTIAL_KEYWORDS = ("credential", "credentials", "secret", "secrets")

MIGRATION_LOCATIONS = [
    ROOT / "app" / "storage" / "migrations",
    ROOT / "app" / "api" / "migrations",
    ROOT / "migrations",
    ROOT / "app" / "startup",
    ROOT / "scripts",
]

RUNTIME_DDL_ROOTS = [
    ROOT / "app" / "startup",
    ROOT / "app" / "api" / "services",
    ROOT / "app" / "api" / "routes",
]

RUNTIME_DDL_PATTERNS = (
    "CREATE TABLE",
    "ALTER TABLE",
    "CREATE INDEX",
    "ensure_table",
    "_ensure_tables",
    "Base.metadata.create_all",
)


def _load_manifest() -> dict:
    assert MANIFEST_PATH.exists(), "schema manifest fixture is missing"
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _tables(manifest: dict) -> list[dict]:
    tables = manifest.get("tables")
    assert isinstance(tables, list), "manifest must contain a top-level tables list"
    assert tables, "manifest tables list must not be empty"
    return tables


def _iter_text_files(paths: list[Path]):
    for root in paths:
        if not root.exists():
            continue
        if root.is_file():
            yield root
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".sql"}:
                yield path


def test_schema_manifest_exists_and_has_table_records():
    manifest = _load_manifest()
    tables = _tables(manifest)
    assert manifest.get("schema_manifest_version")
    assert len(tables) >= len(ACCOUNTING_CRITICAL_TABLES)


def test_schema_manifest_required_fields_and_enums():
    manifest = _load_manifest()
    table_names = set()

    for row in _tables(manifest):
        missing = REQUIRED_TABLE_FIELDS - row.keys()
        assert not missing, f"{row.get('table_name', '<unknown>')} missing {sorted(missing)}"

        table_name = row["table_name"]
        assert isinstance(table_name, str) and table_name.strip()
        assert table_name not in table_names, f"duplicate table_name: {table_name}"
        table_names.add(table_name)

        assert row["migration_coverage"] in MIGRATION_COVERAGE
        assert isinstance(row["runtime_created"], bool)
        assert row["has_tenant_id"] in TENANT_VALUES
        assert row["has_indexes"] in COVERAGE_VALUES
        assert row["has_audit_fields"] in COVERAGE_VALUES
        assert row["risk"] in RISK_VALUES
        assert isinstance(row["recommended_next_action"], str)
        assert row["recommended_next_action"].strip()


def test_accounting_critical_tables_are_documented():
    manifest = _load_manifest()
    found = {row["table_name"] for row in _tables(manifest)}
    missing = ACCOUNTING_CRITICAL_TABLES - found
    assert not missing, f"critical tables missing from schema manifest: {sorted(missing)}"


def test_schema_manifest_risk_rules():
    manifest = _load_manifest()

    for row in _tables(manifest):
        table = row["table_name"]
        risk = row["risk"]
        owner = row["owner_module"].lower()
        action = row["recommended_next_action"].lower()
        source = row["current_creation_source"].lower()

        if any(key in table.lower() or key in owner or key in source for key in CREDENTIAL_KEYWORDS):
            assert risk in {"high", "critical"}, f"{table} is credential/secret related but risk={risk}"

        if row["runtime_created"]:
            assert risk != "low", f"{table} is runtime-created but low risk"

        if table in ACCOUNTING_CORE_TABLES:
            assert risk != "low", f"{table} is accounting core but low risk"

        if row["has_tenant_id"] is False:
            justification_text = f"{owner} {action}"
            assert any(token in justification_text for token in ("shared", "root", "global", "not scoped", "tenant")), (
                f"{table} has_tenant_id=false without explicit justification"
            )


def test_migration_file_inventory_and_destructive_script_detection():
    existing_locations = [path for path in MIGRATION_LOCATIONS if path.exists()]
    assert existing_locations, "no migration-like locations found"

    discovered = list(_iter_text_files(existing_locations))
    assert discovered, "migration-like locations contain no readable .py or .sql files"

    destructive = []
    for path in discovered:
        text = path.read_text(encoding="utf-8", errors="ignore").upper()
        if "DROP TABLE" in text:
            destructive.append(path.relative_to(ROOT).as_posix())

    assert destructive, "expected destructive scripts to remain detectable for migration hardening"
    assert "scripts/run_users_migration.py" in destructive


def test_runtime_ddl_sources_are_detected_and_manifested():
    scan_roots = RUNTIME_DDL_ROOTS + [ROOT / "main.py"]
    matches: dict[str, list[str]] = {}

    for path in _iter_text_files(scan_roots):
        text = path.read_text(encoding="utf-8", errors="ignore")
        found = [pattern for pattern in RUNTIME_DDL_PATTERNS if pattern in text]
        if found:
            matches[path.relative_to(ROOT).as_posix()] = found

    assert matches, "expected runtime DDL/ensure sources to be detected"

    manifest = _load_manifest()
    documented_sources = manifest.get("runtime_ddl_sources")
    assert isinstance(documented_sources, list)
    assert documented_sources, "manifest must document runtime DDL sources"

    documented = "\n".join(documented_sources)
    expected_fragments = [
        "main.py",
        "app/startup/migrations.py",
        "app/api/services/inventory_service.py",
        "app/api/services/payroll_service.py",
    ]
    for fragment in expected_fragments:
        assert fragment in documented, f"runtime DDL source missing from manifest: {fragment}"

    assert any("app/startup" in path for path in matches)
    assert any("app/api/services" in path for path in matches)
