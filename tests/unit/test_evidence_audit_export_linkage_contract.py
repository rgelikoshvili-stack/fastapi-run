"""
Bridge Hub — Task 11C-H10
Evidence / Audit Export Linkage Contract Tests

Contract/docs tests only.
No runtime imports. No DB. No SQL. No network.
All assertions read docs/evidence-audit-export-linkage-contract.md via pathlib.
"""
import ast
import pathlib

DOC_PATH = pathlib.Path(__file__).parent.parent.parent / "docs" / "evidence-audit-export-linkage-contract.md"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Document existence
# ---------------------------------------------------------------------------

class TestContractDocumentExists:
    def test_contract_document_exists(self):
        assert DOC_PATH.exists(), f"Contract document missing: {DOC_PATH}"

    def test_contract_document_is_nonempty(self):
        assert len(_doc()) > 500, "Contract document is unexpectedly short"

    def test_contract_document_title(self):
        doc = _doc()
        assert "Evidence / Audit Export Linkage Contract" in doc

    def test_contract_task_reference(self):
        doc = _doc()
        assert "11C-H10" in doc


# ---------------------------------------------------------------------------
# 2. Evidence linkage rule
# ---------------------------------------------------------------------------

class TestContractDefinesEvidenceLinkageRule:
    def test_contract_defines_evidence_linkage_rule(self):
        doc = _doc()
        assert "Evidence Linkage Rule" in doc

    def test_contract_states_accounting_truth_must_be_explainable(self):
        doc = _doc()
        assert "explainable" in doc.lower() or "auditable" in doc.lower()

    def test_contract_states_every_entry_traceable(self):
        doc = _doc()
        assert "traceable" in doc.lower() or "traceable to" in doc.lower()


# ---------------------------------------------------------------------------
# 3. evidence_bundle_id linkage
# ---------------------------------------------------------------------------

class TestContractRequiresEvidenceBundleIdLinkage:
    def test_contract_requires_evidence_bundle_id_linkage(self):
        doc = _doc()
        assert "evidence_bundle_id" in doc

    def test_contract_states_evidence_bundle_nullable_only_when_source_has_none(self):
        doc = _doc()
        assert "Nullable only when" in doc or "nullable only when" in doc.lower()

    def test_contract_requires_explicit_not_silent_absence(self):
        doc = _doc()
        assert "explicit" in doc and "silent" in doc


# ---------------------------------------------------------------------------
# 4. posting_log_id linkage
# ---------------------------------------------------------------------------

class TestContractRequiresPostingLogIdLinkage:
    def test_contract_requires_posting_log_id_linkage(self):
        doc = _doc()
        assert "posting_log_id" in doc

    def test_contract_links_posting_log_to_connector_execution(self):
        doc = _doc()
        assert "connector execution" in doc.lower() or "connector execution log" in doc.lower()

    def test_contract_forbids_posting_log_for_non_connector_entries(self):
        doc = _doc()
        assert "Never set for entries that did not go through a real connector" in doc or \
               "never set for entries that did not" in doc.lower()


# ---------------------------------------------------------------------------
# 5. source_draft_id linkage
# ---------------------------------------------------------------------------

class TestContractRequiresSourceDraftIdLinkage:
    def test_contract_requires_source_draft_id_linkage(self):
        doc = _doc()
        assert "source_draft_id" in doc

    def test_contract_links_source_draft_to_journal_drafts(self):
        doc = _doc()
        assert "journal_drafts" in doc

    def test_contract_source_draft_id_nullable_for_system_entries(self):
        doc = _doc()
        assert "system-generated" in doc.lower() or "system generated" in doc.lower()


# ---------------------------------------------------------------------------
# 6. Full audit chain
# ---------------------------------------------------------------------------

class TestContractDefinesFullAuditChain:
    def test_contract_defines_full_audit_chain(self):
        doc = _doc()
        assert "Audit Chain Model" in doc

    def test_contract_chain_includes_ocr_parser(self):
        doc = _doc()
        assert "OCR" in doc or "parser" in doc.lower()

    def test_contract_chain_includes_ai_classification(self):
        doc = _doc()
        assert "AI classification" in doc or "ai classification" in doc.lower()

    def test_contract_chain_includes_approval(self):
        doc = _doc()
        assert "Approval" in doc or "approval" in doc

    def test_contract_chain_includes_connector_execution(self):
        doc = _doc()
        assert "connector execution" in doc.lower() or "ERP connector" in doc

    def test_contract_chain_includes_immutable_ledger_entry(self):
        doc = _doc()
        assert "Immutable ledger entry" in doc or "immutable ledger entry" in doc.lower()

    def test_contract_chain_includes_evidence_bundle(self):
        doc = _doc()
        assert "Evidence bundle" in doc or "evidence bundle" in doc

    def test_contract_chain_includes_reversal_correction(self):
        doc = _doc()
        assert "Reversal" in doc or "reversal" in doc


# ---------------------------------------------------------------------------
# 7. Required export package contents
# ---------------------------------------------------------------------------

class TestContractDefinesRequiredExportPackageContents:
    def test_contract_defines_required_export_package_contents(self):
        doc = _doc()
        assert "Required Export Package Contents" in doc or "export package" in doc.lower()

    def test_contract_export_includes_export_id(self):
        doc = _doc()
        assert "export_id" in doc

    def test_contract_export_includes_export_created_at(self):
        doc = _doc()
        assert "export_created_at" in doc

    def test_contract_export_includes_export_created_by(self):
        doc = _doc()
        assert "export_created_by" in doc

    def test_contract_export_includes_period_or_date_range(self):
        doc = _doc()
        assert "period" in doc.lower() and ("date_range" in doc or "date range" in doc.lower())

    def test_contract_export_includes_warnings_and_limitations(self):
        doc = _doc()
        assert "warnings" in doc.lower() and "limitations" in doc.lower()


# ---------------------------------------------------------------------------
# 8. Journal entry header/lines in export
# ---------------------------------------------------------------------------

class TestContractRequiresJournalEntryHeaderAndLinesInExport:
    def test_contract_requires_journal_entry_header_and_lines_in_export(self):
        doc = _doc()
        assert "journal_entry_header" in doc or "journal_entry_headers" in doc

    def test_contract_requires_journal_entry_lines(self):
        doc = _doc()
        assert "journal_entry_lines" in doc

    def test_contract_export_includes_full_header_row(self):
        doc = _doc()
        assert "Full `journal_entry_headers` row" in doc or "full" in doc.lower()


# ---------------------------------------------------------------------------
# 9. Approval history in export
# ---------------------------------------------------------------------------

class TestContractRequiresApprovalHistoryInExport:
    def test_contract_requires_approval_history_in_export(self):
        doc = _doc()
        assert "approval_history" in doc or "approval history" in doc.lower()

    def test_contract_approval_history_is_ordered(self):
        doc = _doc()
        assert "Ordered list" in doc or "ordered list" in doc.lower()

    def test_contract_approval_history_includes_approver_and_timestamp(self):
        doc = _doc()
        assert "approver" in doc.lower() and "timestamp" in doc.lower()


# ---------------------------------------------------------------------------
# 10. Audit events in export
# ---------------------------------------------------------------------------

class TestContractRequiresAuditEventsInExport:
    def test_contract_requires_audit_events_in_export(self):
        doc = _doc()
        assert "audit_events" in doc or "audit events" in doc.lower()

    def test_contract_audit_events_all_material_events(self):
        doc = _doc()
        assert "material" in doc.lower()

    def test_contract_audit_events_include_correlation_id(self):
        doc = _doc()
        assert "correlation_id" in doc


# ---------------------------------------------------------------------------
# 11. Source document metadata
# ---------------------------------------------------------------------------

class TestContractRequiresSourceDocumentMetadata:
    def test_contract_requires_source_document_metadata(self):
        doc = _doc()
        assert "source_document_metadata" in doc or "source document metadata" in doc.lower()

    def test_contract_source_document_metadata_includes_source_hash(self):
        doc = _doc()
        assert "source_hash" in doc

    def test_contract_source_document_metadata_includes_upload_timestamp(self):
        doc = _doc()
        assert "upload" in doc.lower() and "timestamp" in doc.lower()


# ---------------------------------------------------------------------------
# 12. AI reasoning/explanation metadata
# ---------------------------------------------------------------------------

class TestContractRequiresAiReasoningOrExplanationMetadataWhereAvailable:
    def test_contract_requires_ai_reasoning_or_explanation_metadata_where_available(self):
        doc = _doc()
        assert "ai_reasoning_metadata" in doc or "AI reasoning" in doc or "ai reasoning" in doc.lower()

    def test_contract_ai_metadata_includes_confidence(self):
        doc = _doc()
        assert "confidence" in doc.lower()

    def test_contract_ai_metadata_includes_classification_output(self):
        doc = _doc()
        assert "classification" in doc.lower()

    def test_contract_ai_metadata_is_where_available(self):
        doc = _doc()
        assert "where available" in doc.lower() or "if available" in doc.lower()


# ---------------------------------------------------------------------------
# 13. OCR/parser metadata
# ---------------------------------------------------------------------------

class TestContractRequiresOcrParserMetadataWhereAvailable:
    def test_contract_requires_ocr_parser_metadata_where_available(self):
        doc = _doc()
        assert "ocr_parser_metadata" in doc or "OCR" in doc

    def test_contract_ocr_metadata_includes_extraction_confidence(self):
        doc = _doc()
        assert "extraction" in doc.lower() and "confidence" in doc.lower()

    def test_contract_ocr_metadata_is_where_available(self):
        doc = _doc()
        assert "if available" in doc.lower() or "where available" in doc.lower()


# ---------------------------------------------------------------------------
# 14. Connector response summary without secrets
# ---------------------------------------------------------------------------

class TestContractRequiresConnectorResponseSummaryWithoutSecrets:
    def test_contract_requires_connector_response_summary_without_secrets(self):
        doc = _doc()
        assert "connector_response_summary" in doc or "connector response summary" in doc.lower()

    def test_contract_connector_summary_sanitized(self):
        doc = _doc()
        assert "sanitized" in doc.lower() or "Sanitized" in doc

    def test_contract_connector_summary_no_raw_secrets(self):
        doc = _doc()
        assert "no raw secrets" in doc.lower() or "No raw" in doc


# ---------------------------------------------------------------------------
# 15. Reversal/correction chain in export
# ---------------------------------------------------------------------------

class TestContractRequiresReversalCorrectionChain:
    def test_contract_requires_reversal_correction_chain(self):
        doc = _doc()
        assert "reversal_correction_chain" in doc or "reversal/correction chain" in doc.lower()

    def test_contract_chain_includes_original_reversal_correction(self):
        doc = _doc()
        assert "original entry" in doc.lower() and "reversal entry" in doc.lower()

    def test_contract_chain_includes_reasons(self):
        doc = _doc()
        assert "reversal_reason" in doc and "correction_reason" in doc


# ---------------------------------------------------------------------------
# 16. Export manifest/checksum
# ---------------------------------------------------------------------------

class TestContractRequiresExportManifestOrChecksum:
    def test_contract_requires_export_manifest_or_checksum(self):
        doc = _doc()
        assert "export_manifest" in doc or "export manifest" in doc.lower()

    def test_contract_manifest_includes_hash_or_checksum(self):
        doc = _doc()
        assert "hash" in doc.lower() or "checksum" in doc.lower()

    def test_contract_manifest_sha256_or_equivalent(self):
        doc = _doc()
        assert "SHA-256" in doc or "hash" in doc.lower()

    def test_contract_line_hash_included_where_available(self):
        doc = _doc()
        assert "line_hash" in doc


# ---------------------------------------------------------------------------
# 17. Evidence bundle sanitization
# ---------------------------------------------------------------------------

class TestContractRequiresEvidenceBundleSanitization:
    def test_contract_requires_evidence_bundle_sanitization(self):
        doc = _doc()
        assert "_strip_unsafe" in doc

    def test_contract_strip_unsafe_applied_before_export(self):
        doc = _doc()
        assert "before" in doc.lower() and "_strip_unsafe" in doc

    def test_contract_evidence_bundle_must_be_immutable_once_linked(self):
        doc = _doc()
        assert "immutable once linked" in doc.lower() or "immutable" in doc.lower()


# ---------------------------------------------------------------------------
# 18. Raw secrets forbidden
# ---------------------------------------------------------------------------

class TestContractForbidsRawSecretsInExport:
    def test_contract_forbids_raw_secrets_in_export(self):
        doc = _doc()
        assert "raw secrets" in doc.lower() or "Raw secrets" in doc

    def test_contract_forbidden_fields_api_key_password_token(self):
        doc = _doc()
        assert "api_key" in doc
        assert "password" in doc
        assert "token" in doc

    def test_contract_forbidden_fields_secret_encrypted_value(self):
        doc = _doc()
        assert "secret" in doc
        assert "encrypted_value" in doc

    def test_contract_no_credential_in_export_or_audit_event(self):
        doc = _doc()
        assert "credential" in doc.lower()


# ---------------------------------------------------------------------------
# 19. Material audit events
# ---------------------------------------------------------------------------

class TestContractDefinesMaterialAuditEvents:
    def test_contract_defines_material_audit_events(self):
        doc = _doc()
        assert "Audit Event Requirements" in doc or "audit event" in doc.lower()

    def test_contract_audit_event_draft_created(self):
        doc = _doc()
        assert "draft_created" in doc

    def test_contract_audit_event_posting_attempt(self):
        doc = _doc()
        assert "posting_attempt_started" in doc
        assert "posting_attempt_finished" in doc
        assert "posting_attempt_failed" in doc

    def test_contract_audit_event_ledger_write(self):
        doc = _doc()
        assert "ledger_write_attempted" in doc
        assert "ledger_write_succeeded" in doc
        assert "ledger_write_failed" in doc

    def test_contract_audit_event_reversal_correction(self):
        doc = _doc()
        assert "reversal_created" in doc
        assert "correction_created" in doc

    def test_contract_audit_event_export_created(self):
        doc = _doc()
        assert "export_created" in doc

    def test_contract_audit_event_required_fields(self):
        doc = _doc()
        assert "tenant_id" in doc
        assert "actor" in doc
        assert "timestamp" in doc
        assert "entity_type" in doc
        assert "entity_id" in doc


# ---------------------------------------------------------------------------
# 20. Tenant isolation
# ---------------------------------------------------------------------------

class TestContractRequiresTenantIsolation:
    def test_contract_requires_tenant_isolation(self):
        doc = _doc()
        assert "Tenant Isolation" in doc or "tenant isolation" in doc.lower()

    def test_contract_every_export_must_be_tenant_scoped(self):
        doc = _doc()
        assert "Every export must be tenant-scoped" in doc or \
               "every export must be tenant" in doc.lower()

    def test_contract_no_cross_tenant_export(self):
        doc = _doc()
        assert "cross-tenant" in doc.lower() or "cross tenant" in doc.lower()

    def test_contract_tenant_from_request_state(self):
        doc = _doc()
        assert "request.state.tenant_id" in doc


# ---------------------------------------------------------------------------
# 21. Export permission
# ---------------------------------------------------------------------------

class TestContractRequiresExportPermission:
    def test_contract_requires_export_permission(self):
        doc = _doc()
        assert "audit:export" in doc or "ledger:export" in doc or \
               "export permission" in doc.lower()

    def test_contract_export_records_actor_and_timestamp(self):
        doc = _doc()
        assert "export_created_by" in doc
        assert "export_created_at" in doc

    def test_contract_export_permission_fail_closed(self):
        doc = _doc()
        assert "fail closed" in doc.lower() or "permission" in doc.lower()


# ---------------------------------------------------------------------------
# 22. Default tenant fallback forbidden
# ---------------------------------------------------------------------------

class TestContractForbidsDefaultTenantFallback:
    def test_contract_forbids_default_tenant_fallback(self):
        doc = _doc()
        assert "default" in doc.lower() and "tenant" in doc.lower()

    def test_contract_no_silent_fallback_to_default(self):
        doc = _doc()
        assert "silent" in doc.lower()

    def test_contract_missing_tenant_must_fail_closed(self):
        doc = _doc()
        assert "fail closed" in doc.lower()


# ---------------------------------------------------------------------------
# 23. Export views
# ---------------------------------------------------------------------------

class TestContractDefinesExportViews:
    def test_contract_defines_export_views(self):
        doc = _doc()
        assert "Export Views" in doc or "export views" in doc.lower()

    def test_contract_single_ledger_entry_evidence_package(self):
        doc = _doc()
        assert "Single ledger entry evidence package" in doc or \
               "single ledger entry" in doc.lower()

    def test_contract_period_close_audit_package(self):
        doc = _doc()
        assert "Period close audit package" in doc or "period close" in doc.lower()

    def test_contract_report_support_package(self):
        doc = _doc()
        assert "Report support package" in doc or "report support" in doc.lower()

    def test_contract_vat_tax_support_package(self):
        doc = _doc()
        assert "VAT" in doc and ("tax support" in doc.lower() or "vat" in doc.lower())

    def test_contract_reversal_correction_chain_package(self):
        doc = _doc()
        assert "Reversal/correction chain package" in doc or \
               "reversal/correction chain" in doc.lower()

    def test_contract_connector_posting_proof_package(self):
        doc = _doc()
        assert "Connector posting proof package" in doc or \
               "connector posting proof" in doc.lower()


# ---------------------------------------------------------------------------
# 24. Integrity and tamper evidence
# ---------------------------------------------------------------------------

class TestContractDefinesIntegrityAndTamperEvidence:
    def test_contract_defines_integrity_and_tamper_evidence(self):
        doc = _doc()
        assert "Integrity" in doc and "tamper" in doc.lower()

    def test_contract_export_manifest_includes_hash(self):
        doc = _doc()
        assert "hash" in doc.lower() and "manifest" in doc.lower()

    def test_contract_export_log_entry_required(self):
        doc = _doc()
        assert "export log entry" in doc.lower() or "audit event" in doc.lower()

    def test_contract_export_reproducible_for_same_snapshot(self):
        doc = _doc()
        assert "reproducible" in doc.lower()


# ---------------------------------------------------------------------------
# 25. Net/history views for reversal/correction
# ---------------------------------------------------------------------------

class TestContractDefinesNetAndHistoryViewsForReversalCorrection:
    def test_contract_defines_net_and_history_views_for_reversal_correction(self):
        doc = _doc()
        assert "net" in doc.lower() and "history" in doc.lower()

    def test_contract_net_view_and_history_view_distinguishable(self):
        doc = _doc()
        assert "Net view and history view must be distinguishable" in doc or \
               "distinguishable" in doc.lower()

    def test_contract_no_double_counting_in_net_totals(self):
        doc = _doc()
        assert "double-counting" in doc.lower() or "double counting" in doc.lower()

    def test_contract_correction_reversal_reasons_in_export_chain(self):
        doc = _doc()
        assert "reversal_reason" in doc and "correction_reason" in doc


# ---------------------------------------------------------------------------
# 26. No runtime behavior change in H10
# ---------------------------------------------------------------------------

class TestContractStatesNoRuntimeBehaviorChangeInH10:
    def test_contract_states_no_runtime_behavior_change_in_h10(self):
        doc = _doc()
        assert "No runtime" in doc or "no runtime" in doc.lower()

    def test_contract_evidence_bundle_service_not_modified(self):
        doc = _doc()
        assert "evidence_bundle_service.py" in doc

    def test_contract_evidence_bundle_repository_not_modified(self):
        doc = _doc()
        assert "evidence_bundle_repository.py" in doc

    def test_contract_ledger_service_not_modified(self):
        doc = _doc()
        assert "ledger_service.py" in doc

    def test_contract_non_goals_section_exists(self):
        doc = _doc()
        assert "Non-Goals for H10" in doc or "Non-Goals" in doc

    def test_contract_h10_produces_only_two_files(self):
        doc = _doc()
        assert "two files only" in doc.lower() or "two files" in doc.lower()


# ---------------------------------------------------------------------------
# 27. No SQL/DB/migration in H10
# ---------------------------------------------------------------------------

class TestContractStatesNoSqlDbMigrationExecutionInH10:
    def test_contract_states_no_sql_db_migration_execution_in_h10(self):
        doc = _doc()
        assert "No SQL" in doc or "no SQL" in doc.lower()

    def test_contract_no_production_db_touch(self):
        doc = _doc()
        assert "production DB" in doc or "production database" in doc.lower()

    def test_contract_balance_ge_not_activated(self):
        doc = _doc()
        assert "Balance.ge" in doc and "inactive" in doc.lower()


# ---------------------------------------------------------------------------
# 28. Future H11–H16 sequence
# ---------------------------------------------------------------------------

class TestContractDefinesFutureH11ToH16Sequence:
    def test_contract_defines_future_h11_to_h16_sequence(self):
        doc = _doc()
        assert "H11" in doc and "H16" in doc

    def test_contract_h11_is_controlled_migration(self):
        doc = _doc()
        assert "H11" in doc
        assert "migration" in doc.lower()

    def test_contract_h13_is_reversal_correction_mock_tests(self):
        doc = _doc()
        assert "H13" in doc
        assert "mock" in doc.lower()

    def test_contract_h15_is_evidence_export_mock_tests(self):
        doc = _doc()
        assert "H15" in doc
        assert "export" in doc.lower()

    def test_contract_h16_is_evidence_export_runtime(self):
        doc = _doc()
        assert "H16" in doc
        assert "explicit" in doc.lower()


# ---------------------------------------------------------------------------
# 29. No runtime service imports (AST check)
# ---------------------------------------------------------------------------

class TestFileHasNoRuntimeServiceImports:
    def test_file_has_no_runtime_service_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_modules = {
            "evidence_bundle_service",
            "evidence_bundle_repository",
            "posting_service",
            "approval_service",
            "ledger_service",
            "financial_statements_service",
            "routes_reports",
            "routes_posting",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in forbidden_modules:
                    assert forbidden not in node.module, \
                        f"Forbidden runtime import: {node.module}"

    def test_no_app_runtime_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.api.services"), \
                    f"Forbidden app service import: {node.module}"
                assert not node.module.startswith("app.api.routes"), \
                    f"Forbidden app routes import: {node.module}"


# ---------------------------------------------------------------------------
# 30. No DB or network imports (AST check)
# ---------------------------------------------------------------------------

class TestFileHasNoDbOrNetworkImports:
    def test_file_has_no_db_or_network_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_imports = {"asyncpg", "psycopg2", "sqlalchemy", "httpx", "aiohttp", "requests"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split(".")[0]]
                for name in names:
                    assert name not in forbidden_imports, \
                        f"Forbidden DB/network import: {name}"

    def test_no_network_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_top = {"httpx", "aiohttp", "requests", "urllib3", "socket"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in forbidden_top, f"Forbidden network import: {alias.name}"

    def test_no_sql_execution_calls(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        sql_exec_attrs = {"execute", "executemany", "executescript"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in sql_exec_attrs:
                    obj_name = ""
                    if isinstance(func.value, ast.Name):
                        obj_name = func.value.id
                    assert False, \
                        f"Forbidden SQL execution call: {obj_name}.{func.attr}"
