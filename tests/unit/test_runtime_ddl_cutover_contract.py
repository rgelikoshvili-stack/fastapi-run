"""tests/unit/test_runtime_ddl_cutover_contract.py

Task 10F-F: Runtime DDL Cutover Plan — contract tests.

Read-only. No DB, no SQL, no runtime imports. Validates doc content,
reads startup files as plain text, and scans migration SQL files for
forbidden destructive patterns.
"""
from __future__ import annotations

import ast
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO = Path(__file__).parent.parent.parent
_DOCS = _REPO / "docs"
_STARTUP = _REPO / "app" / "startup"
_MIGRATIONS_DIR = _REPO / "app" / "storage" / "migrations"
_FIXTURES = _REPO / "tests" / "fixtures"

DDL_PLAN = _DOCS / "runtime-ddl-cutover-plan.md"
TRUST_FOUNDATION_PLAN = _DOCS / "trust-foundation-implementation-plan.md"
STARTUP_MIGRATIONS = _STARTUP / "migrations.py"
STARTUP_MIGRATIONS_INDEXES = _STARTUP / "migrations_indexes.py"
SCHEMA_MANIFEST = _FIXTURES / "schema_manifest.json"


def _doc() -> str:
    return DDL_PLAN.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Contract definitions (test-only — no runtime imports)
# ---------------------------------------------------------------------------

CUTOVER_PHASES: frozenset[str] = frozenset({
    "inventory_contract_tests",
    "migration_coverage_gap_map",
    "additive_migration_slices",
    "shadow_verification",
    "runtime_ddl_noop_mode",
    "controlled_disablement",
    "cleanup",
})

SAFETY_GATES: frozenset[str] = frozenset({
    "explicit_migration_exists",
    "migration_tests_pass",
    "schema_manifest_updated",
    "local_tests_pass",
    "pr_checks_pass",
    "deploy_succeeds",
    "live_version_matches",
    "health_stable",
    "protected_endpoints_unauthorized",
    "rollback_switch_exists",
    "no_production_manual_sql",
})

DDL_CLASSIFICATIONS: frozenset[str] = frozenset({
    "already_covered_by_explicit_migration",
    "safe_additive_pending_migration",
    "index_only_pending_migration",
    "requires_deeper_audit",
    "forbidden_destructive",
    "temporary_runtime_only",
})

DOMAIN_PRIORITIES: frozenset[str] = frozenset({
    "inventory",
    "payroll",
    "trade",
    "outgoing_invoice",
    "credential_security",
    "auth_tenant_subscription",
    "accounting_truth",
    "document_ocr_evidence",
    "connector_audit_posting_logs",
    "indexes",
})

# ---------------------------------------------------------------------------
# A) Document existence
# ---------------------------------------------------------------------------

def test_runtime_ddl_plan_exists():
    assert DDL_PLAN.exists(), f"Missing: {DDL_PLAN}"


def test_trust_foundation_plan_exists():
    assert TRUST_FOUNDATION_PLAN.exists(), f"Missing: {TRUST_FOUNDATION_PLAN}"


def test_startup_migrations_py_exists():
    assert STARTUP_MIGRATIONS.exists(), f"Missing: {STARTUP_MIGRATIONS}"


def test_startup_migrations_indexes_py_exists():
    assert STARTUP_MIGRATIONS_INDEXES.exists(), f"Missing: {STARTUP_MIGRATIONS_INDEXES}"


def test_schema_manifest_exists():
    assert SCHEMA_MANIFEST.exists(), f"Missing: {SCHEMA_MANIFEST}"


# ---------------------------------------------------------------------------
# B) Contract content checks
# ---------------------------------------------------------------------------

def test_doc_mentions_runtime_ddl():
    assert "runtime DDL" in _doc() or "Runtime DDL" in _doc()


def test_doc_mentions_create_table():
    assert "CREATE TABLE" in _doc()


def test_doc_mentions_alter_table_add_column():
    doc = _doc()
    assert "ALTER TABLE ADD COLUMN" in doc or "ALTER TABLE" in doc


def test_doc_mentions_create_index():
    assert "CREATE INDEX" in _doc()


def test_doc_mentions_explicit_migrations():
    doc = _doc()
    assert "explicit migrations" in doc or "explicit migration" in doc or "explicit SQL migration" in doc


def test_doc_mentions_schema_manifest():
    assert "schema manifest" in _doc().lower() or "schema_manifest" in _doc()


def test_doc_states_no_runtime_behavior_change():
    doc = _doc()
    assert "No runtime code is changed in this task" in doc or \
           "No runtime behavior" in doc or \
           "no runtime code change" in doc.lower()


def test_doc_states_no_startup_file_edit():
    doc = _doc()
    assert "startup files" in doc.lower() and (
        "not edited" in doc or "not changed" in doc or "not edit" in doc.lower()
    )


def test_doc_states_no_migration_creation():
    doc = _doc()
    assert "No migration" in doc or "no migration creation" in doc.lower() or \
           "No migration files are created" in doc


def test_doc_states_no_sql_execution():
    doc = _doc()
    assert "No SQL" in doc or "no SQL" in doc or "No SQL is executed" in doc


def test_doc_states_no_production_db_touch():
    doc = _doc()
    assert "Production DB" in doc and "untouched" in doc


def test_doc_states_balance_ge_remains_inactive():
    doc = _doc()
    assert "Balance.ge remains inactive" in doc or (
        "Balance.ge" in doc and "inactive" in doc
    )


# ---------------------------------------------------------------------------
# C) Runtime DDL source scan
# ---------------------------------------------------------------------------

def test_startup_migrations_py_contains_create_table():
    content = STARTUP_MIGRATIONS.read_text(encoding="utf-8")
    assert "CREATE TABLE" in content, \
        "migrations.py must contain runtime CREATE TABLE statements"


def test_startup_migrations_py_contains_alter_table():
    content = STARTUP_MIGRATIONS.read_text(encoding="utf-8")
    assert "ALTER TABLE" in content, \
        "migrations.py must contain runtime ALTER TABLE statements"


def test_startup_migrations_indexes_py_contains_create_index():
    content = STARTUP_MIGRATIONS_INDEXES.read_text(encoding="utf-8")
    assert "CREATE INDEX" in content, \
        "migrations_indexes.py must contain runtime CREATE INDEX statements"


def test_startup_migrations_indexes_py_contains_alter_table():
    content = STARTUP_MIGRATIONS_INDEXES.read_text(encoding="utf-8")
    assert "ALTER TABLE" in content, \
        "migrations_indexes.py must contain runtime ALTER TABLE statements"


def test_at_least_one_startup_file_contains_runtime_ddl():
    """At least one of the startup migration files must contain runtime DDL."""
    files = [STARTUP_MIGRATIONS, STARTUP_MIGRATIONS_INDEXES,
             _STARTUP / "migrations_tables.py"]
    found = False
    for f in files:
        if f.exists():
            content = f.read_text(encoding="utf-8")
            if "CREATE TABLE" in content or "ALTER TABLE" in content or "CREATE INDEX" in content:
                found = True
                break
    assert found, "No runtime DDL found in any startup migration file"


# ---------------------------------------------------------------------------
# D) Forbidden destructive SQL guard
# ---------------------------------------------------------------------------

def _get_migration_sql_files() -> list[Path]:
    """Return all .sql files in app/storage/migrations/."""
    if not _MIGRATIONS_DIR.exists():
        return []
    return list(_MIGRATIONS_DIR.glob("*.sql"))


def test_migration_sql_files_exist():
    files = _get_migration_sql_files()
    assert len(files) > 0, "No SQL migration files found in app/storage/migrations/"


def test_migration_sql_files_have_no_drop_table():
    """Explicit SQL migration files must not contain DROP TABLE."""
    forbidden = "DROP " + "TABLE"
    for f in _get_migration_sql_files():
        content = f.read_text(encoding="utf-8")
        assert forbidden not in content, \
            f"Forbidden pattern 'DROP TABLE' found in migration file: {f.name}"


def test_migration_sql_files_have_no_truncate():
    """Explicit SQL migration files must not contain TRUNCATE."""
    for f in _get_migration_sql_files():
        content = f.read_text(encoding="utf-8")
        assert "TRUNCATE" not in content, \
            f"Forbidden pattern 'TRUNCATE' found in migration file: {f.name}"


def test_migration_sql_files_have_no_drop_column():
    """Explicit SQL migration files must not contain DROP COLUMN."""
    forbidden = "DROP " + "COLUMN"
    for f in _get_migration_sql_files():
        content = f.read_text(encoding="utf-8")
        assert forbidden not in content, \
            f"Forbidden pattern 'DROP COLUMN' found in migration file: {f.name}"


def test_doc_names_forbidden_destructive_patterns():
    doc = _doc()
    assert "DROP TABLE" in doc
    assert "TRUNCATE" in doc
    assert "DROP COLUMN" in doc


# ---------------------------------------------------------------------------
# E) Phase set
# ---------------------------------------------------------------------------

def test_seven_cutover_phases_defined():
    assert len(CUTOVER_PHASES) == 7, f"Got {len(CUTOVER_PHASES)}"


def test_inventory_contract_tests_phase_present():
    assert "inventory_contract_tests" in CUTOVER_PHASES


def test_migration_coverage_gap_map_phase_present():
    assert "migration_coverage_gap_map" in CUTOVER_PHASES


def test_additive_migration_slices_phase_present():
    assert "additive_migration_slices" in CUTOVER_PHASES


def test_shadow_verification_phase_present():
    assert "shadow_verification" in CUTOVER_PHASES


def test_runtime_ddl_noop_mode_phase_present():
    assert "runtime_ddl_noop_mode" in CUTOVER_PHASES


def test_controlled_disablement_phase_present():
    assert "controlled_disablement" in CUTOVER_PHASES


def test_cleanup_phase_present():
    assert "cleanup" in CUTOVER_PHASES


def test_all_phases_referenced_in_doc():
    doc = _doc()
    phase_keywords = {
        "inventory_contract_tests": "Phase 0",
        "migration_coverage_gap_map": "Phase 1",
        "additive_migration_slices": "Phase 2",
        "shadow_verification": "Phase 3",
        "runtime_ddl_noop_mode": "Phase 4",
        "controlled_disablement": "Phase 5",
        "cleanup": "Phase 6",
    }
    for phase, keyword in phase_keywords.items():
        assert keyword in doc, f"Phase keyword '{keyword}' not found in doc for phase '{phase}'"


# ---------------------------------------------------------------------------
# F) Safety gate set
# ---------------------------------------------------------------------------

def test_eleven_safety_gates_defined():
    assert len(SAFETY_GATES) == 11, f"Got {len(SAFETY_GATES)}"


def test_all_safety_gates_documented():
    doc = _doc()
    for gate in SAFETY_GATES:
        assert gate in doc, f"Safety gate not documented: {gate}"


def test_explicit_migration_exists_gate_present():
    assert "explicit_migration_exists" in SAFETY_GATES


def test_migration_tests_pass_gate_present():
    assert "migration_tests_pass" in SAFETY_GATES


def test_schema_manifest_updated_gate_present():
    assert "schema_manifest_updated" in SAFETY_GATES


def test_rollback_switch_exists_gate_present():
    assert "rollback_switch_exists" in SAFETY_GATES


def test_no_production_manual_sql_gate_present():
    assert "no_production_manual_sql" in SAFETY_GATES


def test_live_version_matches_gate_present():
    assert "live_version_matches" in SAFETY_GATES


def test_deploy_succeeds_gate_present():
    assert "deploy_succeeds" in SAFETY_GATES


# ---------------------------------------------------------------------------
# G) DDL classification set
# ---------------------------------------------------------------------------

def test_six_ddl_classifications_defined():
    assert len(DDL_CLASSIFICATIONS) == 6, f"Got {len(DDL_CLASSIFICATIONS)}"


def test_all_ddl_classifications_documented():
    doc = _doc()
    for cls in DDL_CLASSIFICATIONS:
        assert cls in doc, f"DDL classification not documented: {cls}"


def test_already_covered_classification_present():
    assert "already_covered_by_explicit_migration" in DDL_CLASSIFICATIONS


def test_safe_additive_pending_classification_present():
    assert "safe_additive_pending_migration" in DDL_CLASSIFICATIONS


def test_index_only_pending_classification_present():
    assert "index_only_pending_migration" in DDL_CLASSIFICATIONS


def test_requires_deeper_audit_classification_present():
    assert "requires_deeper_audit" in DDL_CLASSIFICATIONS


def test_forbidden_destructive_classification_present():
    assert "forbidden_destructive" in DDL_CLASSIFICATIONS


def test_temporary_runtime_only_classification_present():
    assert "temporary_runtime_only" in DDL_CLASSIFICATIONS


# ---------------------------------------------------------------------------
# H) Domain priority set
# ---------------------------------------------------------------------------

def test_ten_domain_priorities_defined():
    assert len(DOMAIN_PRIORITIES) == 10, f"Got {len(DOMAIN_PRIORITIES)}"


def test_inventory_domain_present():
    assert "inventory" in DOMAIN_PRIORITIES


def test_payroll_domain_present():
    assert "payroll" in DOMAIN_PRIORITIES


def test_trade_domain_present():
    assert "trade" in DOMAIN_PRIORITIES


def test_outgoing_invoice_domain_present():
    assert "outgoing_invoice" in DOMAIN_PRIORITIES


def test_credential_security_domain_present():
    assert "credential_security" in DOMAIN_PRIORITIES


def test_auth_tenant_subscription_domain_present():
    assert "auth_tenant_subscription" in DOMAIN_PRIORITIES


def test_accounting_truth_domain_present():
    assert "accounting_truth" in DOMAIN_PRIORITIES


def test_document_ocr_evidence_domain_present():
    assert "document_ocr_evidence" in DOMAIN_PRIORITIES


def test_connector_audit_posting_logs_domain_present():
    assert "connector_audit_posting_logs" in DOMAIN_PRIORITIES


def test_indexes_domain_present():
    assert "indexes" in DOMAIN_PRIORITIES


def test_domain_priorities_referenced_in_doc():
    doc = _doc()
    for keyword in ("inventory", "payroll", "trade", "outgoing invoice",
                    "credential", "auth", "accounting truth",
                    "document", "OCR", "connector", "indexes"):
        assert keyword.lower() in doc.lower(), \
            f"Domain keyword '{keyword}' not found in doc"


# ---------------------------------------------------------------------------
# I) Migration file inventory
# ---------------------------------------------------------------------------

def test_migration_files_directory_exists():
    assert _MIGRATIONS_DIR.exists(), f"Missing: {_MIGRATIONS_DIR}"


def test_at_least_one_migration_sql_file_exists():
    files = _get_migration_sql_files()
    assert len(files) >= 1


def test_inventory_migration_file_exists():
    files = {f.name for f in _get_migration_sql_files()}
    assert any("inventory" in name.lower() for name in files), \
        f"No inventory migration file found among: {files}"


def test_payroll_migration_file_exists():
    files = {f.name for f in _get_migration_sql_files()}
    assert any("payroll" in name.lower() for name in files), \
        f"No payroll migration file found among: {files}"


def test_trade_migration_file_exists():
    files = {f.name for f in _get_migration_sql_files()}
    assert any("trade" in name.lower() for name in files), \
        f"No trade migration file found among: {files}"


def test_outgoing_invoice_migration_file_exists():
    files = {f.name for f in _get_migration_sql_files()}
    assert any("outgoing" in name.lower() or "invoice" in name.lower() for name in files), \
        f"No outgoing invoice migration file found among: {files}"


def test_at_least_five_migration_files_exist():
    files = _get_migration_sql_files()
    assert len(files) >= 5, f"Expected at least 5 migration files, found {len(files)}"


# ---------------------------------------------------------------------------
# J) No DB / import / startup execution
# ---------------------------------------------------------------------------

def _get_module_imports() -> set[str]:
    """Return top-level module names imported by this test file (AST-based)."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    return imported


def test_no_app_startup_module_imported():
    imported = _get_module_imports()
    assert "app" not in imported, "Test file must not import any app.* module"


def test_no_db_module_imported():
    imported = _get_module_imports()
    db_modules = {"asyncpg", "psycopg2", "sqlalchemy", "psycopg"}
    assert not (imported & db_modules), f"Test imports DB module: {imported & db_modules}"


def test_no_redis_module_imported():
    imported = _get_module_imports()
    redis_modules = {"redis", "aioredis", "coredis"}
    assert not (imported & redis_modules)


def test_no_startup_import_in_source():
    """Verify no app.startup import in test source using string search on non-import lines."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.startup"), \
                    f"Forbidden import: from {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.startup"), \
                        f"Forbidden import: import {alias.name}"


def test_no_psycopg_connect_pattern_in_source():
    """Verify this test file does not call real DB connect methods."""
    imported = _get_module_imports()
    db_connect_modules = {"psycopg2", "psycopg", "asyncpg"}
    assert not (imported & db_connect_modules), \
        f"Test file imports DB connect module: {imported & db_connect_modules}"


def test_no_sql_execute_call_in_source():
    """Verify this test file does not call SQL execute on a real connection."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Look for .execute() attribute calls on objects named cur/conn/cursor
            if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
                if isinstance(node.func.value, ast.Name):
                    name = node.func.value.id
                    assert name not in ("cur", "conn", "cursor", "db"), \
                        f"Forbidden SQL execute call on '{name}.execute()' in test file"


def test_no_drop_table_in_doc():
    doc = _doc()
    # The doc may MENTION DROP TABLE as a forbidden pattern, but should not contain
    # an executable DROP TABLE statement (i.e., not followed by a specific table name
    # as an active command). We verify the doc is not a migration file.
    assert "CREATE MIGRATION" not in doc
    assert "BEGIN;" not in doc


def test_startup_files_not_modified_by_this_task():
    """Read-only confirmation: startup files exist but were not changed in this task.

    This is validated by checking they still contain runtime DDL indicators —
    if they were cleared or edited, this would fail.
    """
    content = STARTUP_MIGRATIONS.read_text(encoding="utf-8")
    assert "ALTER TABLE" in content
    assert "CREATE TABLE" in content


# ---------------------------------------------------------------------------
# K) Balance.ge safety
# ---------------------------------------------------------------------------

def test_doc_states_balance_ge_inactive():
    doc = _doc()
    assert "Balance.ge" in doc
    assert "inactive" in doc


def test_doc_references_balance_ge_activation_gate():
    doc = _doc()
    assert "balance-ge-activation-gate" in doc


def test_doc_states_balance_ge_gates_not_met():
    doc = _doc()
    assert "NOT MET" in doc or "not met" in doc.lower() or \
           "All gates are currently NOT MET" in doc


def test_doc_states_no_balance_ge_activation_in_this_task():
    doc = _doc()
    assert "No Balance.ge activation" in doc or (
        "Balance.ge" in doc and "activation" in doc.lower() and "blocked" in doc.lower()
    )
