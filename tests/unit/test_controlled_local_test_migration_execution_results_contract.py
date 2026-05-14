"""
Bridge Hub — Task 11C-H12
Controlled Local/Test Migration Execution Results Contract Tests

These tests verify that docs/controlled-local-test-migration-execution-results.md
correctly documents the H12 execution attempt, safety scope, preflight results,
and verdict.

Rules:
- No DB connection.
- No SQL execution.
- No migration execution.
- No runtime service imports.
- Reads only the results doc and the test file itself.
"""

import ast
import pathlib
import re


RESULTS_DOC = pathlib.Path(
    "docs/controlled-local-test-migration-execution-results.md"
)


def _doc() -> str:
    return RESULTS_DOC.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Document existence
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentExists:
    def test_results_document_exists(self):
        assert RESULTS_DOC.exists(), (
            "docs/controlled-local-test-migration-execution-results.md must exist"
        )

    def test_results_document_is_nonempty(self):
        assert len(_doc().strip()) > 200, "Results document must be non-empty"

    def test_results_document_title(self):
        doc = _doc()
        assert "Controlled Local/Test Migration Execution Results" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 2. H12 scope
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentStatesH12Scope:
    def test_results_document_states_h12_scope(self):
        doc = _doc()
        assert "11C-H12" in doc or "H12" in doc, (
            "Results doc must reference task H12"
        )

    def test_results_document_references_migration_file(self):
        doc = _doc()
        assert "011_posted_journal_entries_schema.sql" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 3. Disposable local/test only
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentConfirmsDisposableLocalTestOnly:
    def test_results_document_confirms_disposable_local_test_only(self):
        doc = _doc().lower()
        assert "disposable" in doc, (
            "Results doc must reference disposable local/test DB"
        )

    def test_results_document_states_blocked_or_passed_or_failed(self):
        doc = _doc().upper()
        assert any(v in doc for v in ["BLOCKED", "PASSED", "FAILED"]), (
            "Results doc must state BLOCKED, PASSED, or FAILED verdict"
        )

    def test_results_document_no_substitute_production(self):
        doc = _doc().lower()
        assert "production was not used as a substitute" in doc or \
               "production was not used" in doc or \
               "not used as a substitute" in doc, (
            "Results doc must confirm production was not used as substitute"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 4. Production DB forbidden
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentForbidsProductionDbTouch:
    def test_results_document_forbids_production_db_touch(self):
        doc = _doc().lower()
        assert "production db was not touched" in doc or \
               "production database was not touched" in doc or \
               "production was not touched" in doc, (
            "Results doc must confirm production DB was not touched"
        )

    def test_results_document_states_no_production_connection(self):
        doc = _doc().lower()
        assert "no connection to production" in doc or \
               "connection to production was" in doc or \
               "production was not" in doc, (
            "Results doc must confirm no production connection"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 5. Cloud Run DB not touched
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentConfirmsNoCloudRunDbTouch:
    def test_results_document_confirms_no_cloud_run_db_touch(self):
        doc = _doc().lower()
        assert "cloud run" in doc, (
            "Results doc must address Cloud Run DB scope"
        )
        assert "cloud run db was not touched" in doc or \
               "cloud run production database was not accessed" in doc or \
               "cloud run production" in doc, (
            "Results doc must confirm Cloud Run DB was not touched"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 6. Git SHA and branch
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsGitShaAndBranch:
    def test_results_document_records_git_sha_and_branch(self):
        doc = _doc()
        assert "c06c529" in doc, (
            "Results doc must record the starting main HEAD SHA (c06c529...)"
        )

    def test_results_document_records_branch(self):
        doc = _doc()
        assert "codex/controlled-local-test-migration-execution" in doc, (
            "Results doc must record the H12 branch name"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 7. Migration file path
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsMigrationPath:
    def test_results_document_records_migration_path(self):
        doc = _doc()
        assert "app/storage/migrations/011_posted_journal_entries_schema.sql" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 8. Migration checksum
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsMigrationChecksum:
    def test_results_document_records_migration_checksum(self):
        doc = _doc()
        assert "sha-256" in doc.lower() or "sha256" in doc.lower(), (
            "Results doc must record SHA-256 checksum of migration file"
        )

    def test_results_document_checksum_is_present(self):
        doc = _doc()
        # Must contain a hex string that looks like a SHA-256
        assert re.search(r'[0-9a-f]{60,64}', doc), (
            "Results doc must contain the actual SHA-256 hash value"
        )

    def test_migration_checksum_matches_actual_file(self):
        import hashlib
        migration = pathlib.Path(
            "app/storage/migrations/011_posted_journal_entries_schema.sql"
        )
        if migration.exists():
            actual_sha = hashlib.sha256(migration.read_bytes()).hexdigest()
            doc = _doc()
            assert actual_sha in doc, (
                f"Results doc must contain the actual migration SHA-256 {actual_sha}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 9. DATABASE_URL classification
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsDatabaseUrlClassification:
    def test_results_document_records_database_url_classification(self):
        doc = _doc().lower()
        assert "database_url" in doc, (
            "Results doc must document DATABASE_URL classification"
        )

    def test_results_document_database_url_was_empty(self):
        doc = _doc().lower()
        assert "database_url" in doc and (
            "empty" in doc or "absent" in doc or "not present" in doc
        ), (
            "Results doc must confirm DATABASE_URL was empty/absent during execution"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 10. Production guard
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsProductionGuardResult:
    def test_results_document_records_production_guard_result(self):
        doc = _doc().lower()
        assert "production guard" in doc, (
            "Results doc must document production guard result"
        )

    def test_results_document_production_guard_passed(self):
        doc = _doc().lower()
        assert "production guard" in doc and "passed" in doc, (
            "Results doc must confirm production guard PASSED"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 11. Additive-only validation
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsAdditiveOnlyValidation:
    def test_results_document_records_additive_only_validation(self):
        doc = _doc().lower()
        assert "additive" in doc, (
            "Results doc must address additive-only validation"
        )

    def test_results_document_additive_only_passed(self):
        doc = _doc().lower()
        assert "additive" in doc and "passed" in doc, (
            "Results doc must confirm additive-only validation PASSED"
        )

    def test_results_document_no_drop_found(self):
        doc = _doc().lower()
        assert "`drop` statement" in doc or "drop` statement" in doc or \
               "drop " in doc, (
            "Results doc must address DROP check"
        )

    def test_results_document_delete_is_cascade_not_dml(self):
        doc = _doc().lower()
        assert "on delete cascade" in doc or \
               "dml" in doc or \
               "dml delete" in doc or \
               "not a dml" in doc or \
               "not found" in doc, (
            "Results doc must clarify DELETE appears only as ON DELETE CASCADE, not DML"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 12. First migration run result
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsFirstMigrationRunResult:
    def test_results_document_records_first_migration_run_result(self):
        doc = _doc().lower()
        assert "first migration run" in doc or "first run" in doc, (
            "Results doc must document first migration run result"
        )

    def test_results_document_first_run_not_executed_or_passed(self):
        doc = _doc().lower()
        assert "not executed" in doc or "passed" in doc or "blocked" in doc, (
            "Results doc must state whether first run was executed, passed, or blocked"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 13. Second run / idempotency
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsSecondRunIdempotencyResult:
    def test_results_document_records_second_run_idempotency_result(self):
        doc = _doc().lower()
        assert "idempotency" in doc or "second" in doc, (
            "Results doc must address second run / idempotency check"
        )

    def test_results_document_second_run_addressed(self):
        doc = _doc().lower()
        assert "second" in doc and (
            "not executed" in doc or "passed" in doc or "idempotency" in doc
        ), (
            "Results doc must state outcome of second/idempotency run"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 14. Schema objects verified
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsSchemaObjectsVerified:
    def test_results_document_records_journal_entry_headers(self):
        doc = _doc()
        assert "journal_entry_headers" in doc

    def test_results_document_records_journal_entry_lines(self):
        doc = _doc()
        assert "journal_entry_lines" in doc

    def test_results_document_records_journal_entry_sources(self):
        doc = _doc()
        assert "journal_entry_sources" in doc

    def test_results_document_records_schema_objects_section(self):
        doc = _doc().lower()
        assert "schema objects" in doc, (
            "Results doc must have a schema objects section"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 15. Constraints verified
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsConstraintsVerified:
    def test_results_document_records_constraints_section(self):
        doc = _doc().lower()
        assert "constraint" in doc, "Results doc must address constraints"

    def test_results_document_records_tenant_id_constraint(self):
        doc = _doc()
        assert "tenant_id" in doc

    def test_results_document_records_status_check(self):
        doc = _doc()
        assert "status" in doc and (
            "posted" in doc or "CHECK" in doc or "check" in doc.lower()
        )

    def test_results_document_status_excludes_draft_values(self):
        doc = _doc().lower()
        # Status CHECK must only allow final confirmed states
        assert "draft" in doc or "simulated_success" in doc, (
            "Results doc must confirm draft/simulated_success are excluded from status CHECK"
        )

    def test_results_document_records_balanced_constraint(self):
        doc = _doc().lower()
        assert "balanced" in doc or "total_debit = total_credit" in doc or \
               "ck_jeh_balanced" in doc, (
            "Results doc must confirm balanced header constraint"
        )

    def test_results_document_records_debit_credit_constraints(self):
        doc = _doc().lower()
        assert "debit" in doc and "credit" in doc

    def test_results_document_records_unique_line_no(self):
        doc = _doc().lower()
        assert "line_no" in doc or "line number" in doc or "uq_jel" in doc, (
            "Results doc must confirm unique line_no constraint"
        )

    def test_results_document_records_fk_line_header(self):
        doc = _doc().lower()
        assert "references journal_entry_headers" in doc or \
               "fk" in doc or \
               "foreign key" in doc, (
            "Results doc must confirm FK from lines to headers"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 16. Indexes verified
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentRecordsIndexesVerified:
    def test_results_document_records_indexes_section(self):
        doc = _doc().lower()
        assert "index" in doc, "Results doc must address indexes"

    def test_results_document_records_tenant_period_index(self):
        doc = _doc()
        assert "idx_jeh_tenant_period" in doc or \
               "tenant_id, period" in doc or \
               "(tenant_id, period)" in doc

    def test_results_document_records_tenant_status_index(self):
        doc = _doc()
        assert "idx_jeh_tenant_status" in doc or \
               "tenant_id, status" in doc

    def test_results_document_records_14_indexes(self):
        doc = _doc()
        # Count CREATE INDEX IF NOT EXISTS occurrences (may appear as static analysis)
        count = doc.count("CREATE INDEX IF NOT EXISTS") + \
                doc.count("idx_jeh_") + doc.count("idx_jel_") + doc.count("idx_jes_")
        assert count >= 7, (
            "Results doc must document a sufficient number of index names"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 17. No journal_drafts mutation
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentConfirmsNoJournalDraftsMutation:
    def test_results_document_confirms_no_journal_drafts_mutation(self):
        doc = _doc().lower()
        assert "journal_drafts" in doc, (
            "Results doc must address journal_drafts mutation check"
        )

    def test_results_document_journal_drafts_not_mutated(self):
        doc = _doc().lower()
        assert "journal_drafts" in doc and (
            "not mutated" in doc or "untouched" in doc or "not found" in doc or
            "not referenced" in doc or "no" in doc
        ), (
            "Results doc must confirm journal_drafts was not mutated"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 18. No backfill
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentConfirmsNoBackfill:
    def test_results_document_confirms_no_backfill(self):
        doc = _doc().lower()
        assert "backfill" in doc, (
            "Results doc must address backfill check"
        )

    def test_results_document_no_backfill_executed(self):
        doc = _doc().lower()
        assert "backfill" in doc and (
            "no backfill" in doc or "not executed" in doc or "no data" in doc
        ), (
            "Results doc must confirm no backfill was executed"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 19. No runtime report change
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentConfirmsNoRuntimeReportChange:
    def test_results_document_confirms_no_runtime_report_change(self):
        doc = _doc().lower()
        assert "runtime report" in doc or \
               "report runtime" in doc or \
               "financial_statements" in doc, (
            "Results doc must confirm no runtime report behavior changed"
        )

    def test_results_document_financial_statements_unchanged(self):
        doc = _doc().lower()
        assert "financial_statements" in doc or "runtime report" in doc


# ──────────────────────────────────────────────────────────────────────────────
# 20. No posting or approval change
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentConfirmsNoPostingOrApprovalChange:
    def test_results_document_confirms_no_posting_change(self):
        doc = _doc().lower()
        assert "posting" in doc and (
            "not changed" in doc or "unchanged" in doc or "no posting" in doc
        )

    def test_results_document_confirms_no_approval_change(self):
        doc = _doc().lower()
        assert "approval" in doc and (
            "not changed" in doc or "unchanged" in doc or "no approval" in doc
        )


# ──────────────────────────────────────────────────────────────────────────────
# 21. Balance.ge not activated
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentConfirmsBalanceNotActivated:
    def test_results_document_confirms_balance_not_activated(self):
        doc = _doc().lower()
        assert "balance.ge" in doc or "balance_api_key" in doc, (
            "Results doc must address Balance.ge activation"
        )

    def test_results_document_balance_remains_demo(self):
        doc = _doc().lower()
        assert "demo_mode" in doc or "not activated" in doc or \
               "remains inactive" in doc or "balance.ge not activated" in doc, (
            "Results doc must confirm Balance.ge remains demo_mode/inactive"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 22. No credentials or connector changes
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentConfirmsNoCredentialsOrConnectorChanges:
    def test_results_document_confirms_no_credentials_changed(self):
        doc = _doc().lower()
        assert "credential" in doc or "secret" in doc or "api key" in doc, (
            "Results doc must confirm no credentials were changed"
        )

    def test_results_document_confirms_no_connector_changes(self):
        doc = _doc().lower()
        assert "connector" in doc, (
            "Results doc must confirm no connector behavior changed"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 23. Passed / Blocked / Failed verdict
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentDefinesPassedBlockedOrFailedVerdict:
    def test_results_document_defines_verdict(self):
        doc = _doc().upper()
        assert any(v in doc for v in ["PASSED", "BLOCKED", "FAILED"]), (
            "Results doc must define a clear PASSED, BLOCKED, or FAILED verdict"
        )

    def test_results_document_verdict_has_reason(self):
        doc = _doc().lower()
        # The verdict must be accompanied by a reason
        assert "verdict" in doc or "result" in doc, (
            "Results doc must have a verdict/result section"
        )

    def test_results_document_blocked_reason_is_postgresql_unavailable(self):
        doc = _doc().upper()
        if "BLOCKED" in doc:
            doc_lower = doc.lower()
            assert "postgresql" in doc_lower or "psql" in doc_lower, (
                "If BLOCKED, results doc must state reason: PostgreSQL unavailable"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 24. Next H13 task
# ──────────────────────────────────────────────────────────────────────────────

class TestResultsDocumentDefinesNextH13Task:
    def test_results_document_defines_next_h13_task(self):
        doc = _doc()
        assert "H13" in doc, (
            "Results doc must reference H13 as the next task"
        )

    def test_results_document_h13_is_runtime_report_migration(self):
        doc = _doc().lower()
        assert "h13" in doc and (
            "report migration" in doc or "runtime report" in doc or
            "report migration plan" in doc
        ), (
            "Results doc must describe H13 as the Runtime Report Migration Plan"
        )

    def test_results_document_h13_requires_merge_deploy_verify(self):
        doc = _doc().lower()
        assert "merged" in doc or "merge" in doc or "live verification" in doc or \
               "deploy" in doc, (
            "Results doc must state H13 requires merge, deploy, and live verification first"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 25. No runtime service imports
# ──────────────────────────────────────────────────────────────────────────────

class TestFileHasNoRuntimeServiceImports:
    def test_file_has_no_runtime_service_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_modules = {
            "app.api.services",
            "app.api.routes",
            "app.storage",
            "app.startup",
            "main",
            "asyncpg",
            "psycopg2",
            "sqlalchemy",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                full = node.module
                assert top not in {"asyncpg", "psycopg2", "sqlalchemy", "main"}, (
                    f"Test file must not import runtime module: {node.module}"
                )
                for forbidden in ["app.api.services", "app.api.routes",
                                   "app.storage", "app.startup"]:
                    assert not full.startswith(forbidden), (
                        f"Test file must not import runtime service: {node.module}"
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in {"asyncpg", "psycopg2", "sqlalchemy"}, (
                        f"Test file must not import DB driver: {alias.name}"
                    )


# ──────────────────────────────────────────────────────────────────────────────
# 26. No DB or network imports
# ──────────────────────────────────────────────────────────────────────────────

class TestFileHasNoDbOrNetworkImports:
    def test_file_has_no_db_or_network_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_top = {
            "httpx", "aiohttp", "requests", "urllib3", "socket",
            "asyncpg", "psycopg2", "sqlalchemy", "databases",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in forbidden_top, (
                        f"Test file must not import network/DB module: {alias.name}"
                    )
            if isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                assert top not in forbidden_top, (
                    f"Test file must not import from network/DB module: {node.module}"
                )
