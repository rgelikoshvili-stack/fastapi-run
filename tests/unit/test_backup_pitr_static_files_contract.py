"""
tests/unit/test_backup_pitr_static_files_contract.py

Read-only contract tests for the Backup / PITR / Static Files GCS-CDN Plan.
Task 10F-G.

Rules:
- No DB connections.
- No network calls.
- No GCP/GCS/Cloud SQL calls.
- No runtime module imports (app.startup, app.api, etc.).
- No SQL execution.
- No infrastructure changes.
- No Balance.ge activation.
- File system reads only.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repository root
# ---------------------------------------------------------------------------

_REPO = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Local test-only contract definitions — no runtime imports
# ---------------------------------------------------------------------------

BACKUP_REQUIREMENTS: frozenset[str] = frozenset({
    "automated_backups_enabled",
    "pitr_enabled",
    "retention_policy_documented",
    "backup_region_documented",
    "encryption_documented",
    "restricted_restore_permissions",
    "backup_status_visible",
})

RESTORE_DRILL_REQUIREMENTS: frozenset[str] = frozenset({
    "non_production_clone",
    "no_production_overwrite",
    "schema_validation",
    "tenant_data_validation",
    "audit_event_validation",
    "journal_data_validation",
    "user_data_validation",
    "credential_metadata_validation",
    "document_metadata_validation",
    "restore_evidence_report",
    "rpo_rto_documented",
})

STORAGE_COMPONENTS: frozenset[str] = frozenset({
    "ObjectStorageService",
    "GCSObjectStorageBackend",
    "LocalObjectStorageBackend",
    "StaticAssetPublisher",
    "EvidenceBundleStorage",
    "SignedUrlService",
    "StorageAuditLogger",
})

PRIVATE_OBJECT_TYPES: frozenset[str] = frozenset({
    "uploaded_documents",
    "attachments",
    "ocr_source_files",
    "evidence_bundles",
    "exports",
    "generated_pdfs",
})

MIGRATION_PHASES: frozenset[str] = frozenset({
    "docs_tests_only",
    "storage_path_inventory",
    "storage_abstraction_interface_tests",
    "local_backend_parity",
    "fake_gcs_backend_tests",
    "write_new_to_gcs_read_old_fallback",
    "backfill_existing_objects",
    "signed_url_access_control",
    "cdn_public_static_assets_only",
    "production_cutover_live_verification",
})

SECURITY_REQUIREMENTS: frozenset[str] = frozenset({
    "no_cross_tenant_access",
    "short_lived_signed_urls",
    "audit_private_file_access",
    "no_secrets_in_object_names",
    "no_public_bucket_for_private_documents",
    "separate_public_assets_and_private_documents",
})

# ---------------------------------------------------------------------------
# Helper — read plan doc
# ---------------------------------------------------------------------------

def _plan_path() -> Path:
    return _REPO / "docs" / "backup-pitr-static-files-plan.md"


def _plan_text() -> str:
    return _plan_path().read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helper — AST-based import scanner (no self-referential string risk)
# ---------------------------------------------------------------------------

def _get_module_imports() -> set[str]:
    """Return top-level module names imported by this test file."""
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


# ===========================================================================
# A) Document existence
# ===========================================================================

class TestDocumentExistence:

    def test_plan_doc_exists(self):
        assert _plan_path().exists(), "docs/backup-pitr-static-files-plan.md must exist"

    def test_trust_foundation_plan_exists(self):
        p = _REPO / "docs" / "trust-foundation-implementation-plan.md"
        assert p.exists(), "docs/trust-foundation-implementation-plan.md must exist"

    def test_runtime_ddl_plan_exists(self):
        p = _REPO / "docs" / "runtime-ddl-cutover-plan.md"
        assert p.exists(), "docs/runtime-ddl-cutover-plan.md must exist"


# ===========================================================================
# B) Contract content
# ===========================================================================

class TestPlanContent:

    def test_mentions_backup(self):
        assert "backup" in _plan_text().lower()

    def test_mentions_pitr(self):
        assert "PITR" in _plan_text() or "point-in-time recovery" in _plan_text().lower()

    def test_mentions_point_in_time_recovery(self):
        assert "point-in-time recovery" in _plan_text().lower()

    def test_mentions_restore_drill(self):
        assert "restore drill" in _plan_text().lower()

    def test_mentions_rpo(self):
        assert "RPO" in _plan_text()

    def test_mentions_rto(self):
        assert "RTO" in _plan_text()

    def test_mentions_gcs(self):
        assert "GCS" in _plan_text()

    def test_mentions_cdn(self):
        assert "CDN" in _plan_text()

    def test_mentions_cloud_run_ephemeral(self):
        text = _plan_text().lower()
        assert "cloud run" in text and "ephemeral" in text

    def test_mentions_object_storage(self):
        assert "object storage" in _plan_text().lower()

    def test_mentions_signed_urls(self):
        assert "signed url" in _plan_text().lower() or "signed URL" in _plan_text()

    def test_mentions_tenant_isolation(self):
        text = _plan_text().lower()
        assert "tenant" in text and "isolation" in text

    def test_mentions_evidence_bundle(self):
        assert "evidence bundle" in _plan_text().lower()

    def test_mentions_balance_ge_inactive(self):
        text = _plan_text().lower()
        assert "balance.ge" in text and "inactive" in text

    def test_no_production_infrastructure_change(self):
        assert "No production infrastructure change" in _plan_text()

    def test_no_cloud_sql_change(self):
        assert "No Cloud SQL" in _plan_text() or "No Cloud SQL configuration" in _plan_text()

    def test_no_gcs_cdn_creation(self):
        assert "No GCS/CDN" in _plan_text()

    def test_no_runtime_code_change(self):
        assert "No runtime code" in _plan_text() or "No runtime code change" in _plan_text()

    def test_no_workflow_edit(self):
        assert "No workflow" in _plan_text()

    def test_no_migration(self):
        assert "No migration" in _plan_text()

    def test_no_sql_execution(self):
        text = _plan_text()
        assert "No SQL execution" in text or "No SQL" in text

    def test_no_db_touch(self):
        assert "No DB touch" in _plan_text() or "No DB" in _plan_text()

    def test_no_balance_ge_activation(self):
        assert "No Balance.ge activation" in _plan_text()


# ===========================================================================
# C) Backup requirement set
# ===========================================================================

class TestBackupRequirementSet:

    def test_set_is_not_empty(self):
        assert len(BACKUP_REQUIREMENTS) > 0

    def test_automated_backups_enabled(self):
        assert "automated_backups_enabled" in BACKUP_REQUIREMENTS

    def test_pitr_enabled(self):
        assert "pitr_enabled" in BACKUP_REQUIREMENTS

    def test_retention_policy_documented(self):
        assert "retention_policy_documented" in BACKUP_REQUIREMENTS

    def test_backup_region_documented(self):
        assert "backup_region_documented" in BACKUP_REQUIREMENTS

    def test_encryption_documented(self):
        assert "encryption_documented" in BACKUP_REQUIREMENTS

    def test_restricted_restore_permissions(self):
        assert "restricted_restore_permissions" in BACKUP_REQUIREMENTS

    def test_backup_status_visible(self):
        assert "backup_status_visible" in BACKUP_REQUIREMENTS

    def test_all_seven_requirements_present(self):
        assert len(BACKUP_REQUIREMENTS) == 7


# ===========================================================================
# D) Restore drill requirement set
# ===========================================================================

class TestRestoreDrillRequirements:

    def test_set_is_not_empty(self):
        assert len(RESTORE_DRILL_REQUIREMENTS) > 0

    def test_non_production_clone(self):
        assert "non_production_clone" in RESTORE_DRILL_REQUIREMENTS

    def test_no_production_overwrite(self):
        assert "no_production_overwrite" in RESTORE_DRILL_REQUIREMENTS

    def test_schema_validation(self):
        assert "schema_validation" in RESTORE_DRILL_REQUIREMENTS

    def test_tenant_data_validation(self):
        assert "tenant_data_validation" in RESTORE_DRILL_REQUIREMENTS

    def test_audit_event_validation(self):
        assert "audit_event_validation" in RESTORE_DRILL_REQUIREMENTS

    def test_journal_data_validation(self):
        assert "journal_data_validation" in RESTORE_DRILL_REQUIREMENTS

    def test_user_data_validation(self):
        assert "user_data_validation" in RESTORE_DRILL_REQUIREMENTS

    def test_credential_metadata_validation(self):
        assert "credential_metadata_validation" in RESTORE_DRILL_REQUIREMENTS

    def test_document_metadata_validation(self):
        assert "document_metadata_validation" in RESTORE_DRILL_REQUIREMENTS

    def test_restore_evidence_report(self):
        assert "restore_evidence_report" in RESTORE_DRILL_REQUIREMENTS

    def test_rpo_rto_documented(self):
        assert "rpo_rto_documented" in RESTORE_DRILL_REQUIREMENTS

    def test_all_eleven_requirements_present(self):
        assert len(RESTORE_DRILL_REQUIREMENTS) == 11


# ===========================================================================
# E) Storage component set
# ===========================================================================

class TestStorageComponents:

    def test_set_is_not_empty(self):
        assert len(STORAGE_COMPONENTS) > 0

    def test_object_storage_service(self):
        assert "ObjectStorageService" in STORAGE_COMPONENTS

    def test_gcs_backend(self):
        assert "GCSObjectStorageBackend" in STORAGE_COMPONENTS

    def test_local_backend(self):
        assert "LocalObjectStorageBackend" in STORAGE_COMPONENTS

    def test_static_asset_publisher(self):
        assert "StaticAssetPublisher" in STORAGE_COMPONENTS

    def test_evidence_bundle_storage(self):
        assert "EvidenceBundleStorage" in STORAGE_COMPONENTS

    def test_signed_url_service(self):
        assert "SignedUrlService" in STORAGE_COMPONENTS

    def test_storage_audit_logger(self):
        assert "StorageAuditLogger" in STORAGE_COMPONENTS

    def test_all_seven_components_present(self):
        assert len(STORAGE_COMPONENTS) == 7

    def test_components_mentioned_in_plan(self):
        text = _plan_text()
        for component in STORAGE_COMPONENTS:
            assert component in text, f"Plan must mention component: {component}"


# ===========================================================================
# F) Private storage object types
# ===========================================================================

class TestPrivateObjectTypes:

    def test_set_is_not_empty(self):
        assert len(PRIVATE_OBJECT_TYPES) > 0

    def test_uploaded_documents(self):
        assert "uploaded_documents" in PRIVATE_OBJECT_TYPES

    def test_attachments(self):
        assert "attachments" in PRIVATE_OBJECT_TYPES

    def test_ocr_source_files(self):
        assert "ocr_source_files" in PRIVATE_OBJECT_TYPES

    def test_evidence_bundles(self):
        assert "evidence_bundles" in PRIVATE_OBJECT_TYPES

    def test_exports(self):
        assert "exports" in PRIVATE_OBJECT_TYPES

    def test_generated_pdfs(self):
        assert "generated_pdfs" in PRIVATE_OBJECT_TYPES

    def test_all_six_types_present(self):
        assert len(PRIVATE_OBJECT_TYPES) == 6

    def test_object_types_mentioned_in_plan(self):
        text = _plan_text().lower()
        for obj_type in PRIVATE_OBJECT_TYPES:
            readable = obj_type.replace("_", " ")
            assert readable in text, f"Plan must mention object type: {readable}"


# ===========================================================================
# G) Static migration phase set
# ===========================================================================

class TestMigrationPhases:

    def test_set_is_not_empty(self):
        assert len(MIGRATION_PHASES) > 0

    def test_docs_tests_only(self):
        assert "docs_tests_only" in MIGRATION_PHASES

    def test_storage_path_inventory(self):
        assert "storage_path_inventory" in MIGRATION_PHASES

    def test_storage_abstraction_interface_tests(self):
        assert "storage_abstraction_interface_tests" in MIGRATION_PHASES

    def test_local_backend_parity(self):
        assert "local_backend_parity" in MIGRATION_PHASES

    def test_fake_gcs_backend_tests(self):
        assert "fake_gcs_backend_tests" in MIGRATION_PHASES

    def test_write_new_to_gcs_read_old_fallback(self):
        assert "write_new_to_gcs_read_old_fallback" in MIGRATION_PHASES

    def test_backfill_existing_objects(self):
        assert "backfill_existing_objects" in MIGRATION_PHASES

    def test_signed_url_access_control(self):
        assert "signed_url_access_control" in MIGRATION_PHASES

    def test_cdn_public_static_assets_only(self):
        assert "cdn_public_static_assets_only" in MIGRATION_PHASES

    def test_production_cutover_live_verification(self):
        assert "production_cutover_live_verification" in MIGRATION_PHASES

    def test_all_ten_phases_present(self):
        assert len(MIGRATION_PHASES) == 10

    def test_phases_mentioned_in_plan(self):
        text = _plan_text()
        for phase in MIGRATION_PHASES:
            assert phase in text, f"Plan must mention phase: {phase}"


# ===========================================================================
# H) Security requirement set
# ===========================================================================

class TestSecurityRequirements:

    def test_set_is_not_empty(self):
        assert len(SECURITY_REQUIREMENTS) > 0

    def test_no_cross_tenant_access(self):
        assert "no_cross_tenant_access" in SECURITY_REQUIREMENTS

    def test_short_lived_signed_urls(self):
        assert "short_lived_signed_urls" in SECURITY_REQUIREMENTS

    def test_audit_private_file_access(self):
        assert "audit_private_file_access" in SECURITY_REQUIREMENTS

    def test_no_secrets_in_object_names(self):
        assert "no_secrets_in_object_names" in SECURITY_REQUIREMENTS

    def test_no_public_bucket_for_private_documents(self):
        assert "no_public_bucket_for_private_documents" in SECURITY_REQUIREMENTS

    def test_separate_public_and_private(self):
        assert "separate_public_assets_and_private_documents" in SECURITY_REQUIREMENTS

    def test_all_six_requirements_present(self):
        assert len(SECURITY_REQUIREMENTS) == 6

    def test_security_requirements_mentioned_in_plan(self):
        text = _plan_text()
        for req in SECURITY_REQUIREMENTS:
            assert req in text, f"Plan must mention security requirement: {req}"


# ===========================================================================
# I) Source scan — read-only, no imports
# ===========================================================================

class TestSourceScan:
    """Read runtime source files as plain text; assert at least one
    static/upload/attachment/document/file reference is found.
    Does not require every file to exist or every keyword to match."""

    _KEYWORDS = ("static", "upload", "attachment", "document", "file")

    def _scan_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return ""

    def test_main_py_has_static_or_upload_reference(self):
        text = self._scan_file(_REPO / "main.py")
        assert any(kw in text.lower() for kw in self._KEYWORDS), (
            "main.py must reference at least one of: static, upload, attachment, document, file"
        )

    def test_storage_service_has_gcs_or_upload_reference(self):
        text = self._scan_file(_REPO / "app" / "api" / "services" / "storage_service.py")
        assert any(kw in text.lower() for kw in ("gcs", "upload", "bucket", "blob")), (
            "storage_service.py must reference GCS or upload concepts"
        )

    def test_routes_documents_has_upload_reference(self):
        text = self._scan_file(_REPO / "app" / "api" / "routes_documents.py")
        assert any(kw in text.lower() for kw in self._KEYWORDS), (
            "routes_documents.py must reference upload/document/file concepts"
        )

    def test_routes_approval_has_attachment_reference(self):
        text = self._scan_file(_REPO / "app" / "api" / "routes_approval.py")
        assert any(kw in text.lower() for kw in self._KEYWORDS), (
            "routes_approval.py must reference attachment/document/file concepts"
        )

    def test_deploy_workflow_inspected_without_edit(self):
        wf = _REPO / ".github" / "workflows" / "deploy.yml"
        if wf.exists():
            text = wf.read_text(encoding="utf-8")
            assert len(text) > 0
        else:
            pass  # workflow may not exist in this branch; not a failure

    def test_at_least_one_source_file_has_keyword(self):
        paths = [
            _REPO / "main.py",
            _REPO / "app" / "api" / "services" / "storage_service.py",
            _REPO / "app" / "api" / "routes_documents.py",
            _REPO / "app" / "api" / "routes_approval.py",
        ]
        found_any = False
        for p in paths:
            text = self._scan_file(p)
            if any(kw in text.lower() for kw in self._KEYWORDS):
                found_any = True
                break
        assert found_any, "At least one scanned source file must mention static/upload/attachment/document/file"

    def test_app_storage_directory_exists(self):
        p = _REPO / "app" / "storage"
        assert p.exists(), "app/storage/ directory must exist"

    def test_static_dir_mounted_in_main(self):
        text = self._scan_file(_REPO / "main.py")
        assert "static" in text.lower(), "main.py must reference static directory"


# ===========================================================================
# J) No infra/runtime execution in this test file
# ===========================================================================

class TestNoInfraExecution:
    """Verify this test file does not contain forbidden infra/runtime modules.
    Uses AST-based import checking to avoid self-referential string matching."""

    _FORBIDDEN_TOP_LEVEL = {
        "google",
        "requests",
        "httpx",
        "boto3",
        "subprocess",
        "psycopg2",
        "psycopg",
        "asyncpg",
    }

    def test_no_google_cloud_import(self):
        imported = _get_module_imports()
        assert "google" not in imported, "Test must not import google.cloud"

    def test_no_requests_import(self):
        imported = _get_module_imports()
        assert "requests" not in imported, "Test must not import requests (no HTTP calls)"

    def test_no_subprocess_import(self):
        imported = _get_module_imports()
        assert "subprocess" not in imported, "Test must not import subprocess"

    def test_no_psycopg2_import(self):
        imported = _get_module_imports()
        assert "psycopg2" not in imported and "psycopg" not in imported, (
            "Test must not import psycopg2 or psycopg"
        )

    def test_no_asyncpg_import(self):
        imported = _get_module_imports()
        assert "asyncpg" not in imported, "Test must not import asyncpg"

    def test_no_boto3_import(self):
        imported = _get_module_imports()
        assert "boto3" not in imported, "Test must not import boto3"

    def test_no_app_startup_import(self):
        imported = _get_module_imports()
        assert "app" not in imported, (
            "Test must not import app modules at top level"
        )

    def test_allowed_stdlib_imports_only(self):
        imported = _get_module_imports()
        forbidden_found = imported & self._FORBIDDEN_TOP_LEVEL
        assert not forbidden_found, f"Forbidden imports found: {forbidden_found}"

    def test_no_direct_cloud_db_string_in_source(self):
        text = Path(__file__).read_text(encoding="utf-8")
        needle = "cloud" + "sql"
        assert needle not in text.lower(), "Test must not reference direct cloud-db connections"

    def test_no_gcloud_subprocess_call_in_source(self):
        text = Path(__file__).read_text(encoding="utf-8")
        needle_run = "subprocess" + ".run"
        assert needle_run not in text, "Test must not use subprocess (no shell commands allowed)"


# ===========================================================================
# K) Balance.ge safety
# ===========================================================================

class TestBalanceGeSafety:

    def test_plan_says_balance_ge_inactive(self):
        text = _plan_text().lower()
        assert "balance.ge" in text, "Plan must mention Balance.ge"
        assert "inactive" in text, "Plan must state Balance.ge is inactive"

    def test_plan_defers_balance_ge_activation(self):
        text = _plan_text()
        assert "No Balance.ge activation" in text, (
            "Plan must explicitly state no Balance.ge activation in this task"
        )

    def test_plan_says_all_gates_not_met(self):
        text = _plan_text()
        assert "NOT MET" in text, (
            "Plan must state that Balance.ge activation gates are NOT MET"
        )

    def test_plan_references_activation_gate_doc(self):
        text = _plan_text()
        assert "balance-ge-activation-gate" in text or "Balance.ge activation gate" in text, (
            "Plan must reference the Balance.ge activation gate document"
        )

    def test_balance_ge_gate_doc_exists(self):
        p = _REPO / "docs" / "balance-ge-activation-gate.md"
        assert p.exists(), "docs/balance-ge-activation-gate.md must exist"
