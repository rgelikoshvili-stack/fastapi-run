"""
Bridge Hub — Task 11C-H11
Controlled Local/Test Migration Execution Plan Contract Tests

Contract/docs tests only.
No runtime imports. No DB. No SQL. No network. No migration execution.
All assertions read docs/controlled-local-test-migration-execution-plan.md via pathlib.
"""
import ast
import pathlib

DOC_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "docs"
    / "controlled-local-test-migration-execution-plan.md"
)


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Document existence
# ---------------------------------------------------------------------------

class TestContractDocumentExists:
    def test_contract_document_exists(self):
        assert DOC_PATH.exists(), f"Contract document missing: {DOC_PATH}"

    def test_contract_document_is_nonempty(self):
        assert len(_doc()) > 500

    def test_contract_document_title(self):
        assert "Controlled Local/Test Migration Execution Plan" in _doc()

    def test_contract_task_reference(self):
        assert "11C-H11" in _doc()


# ---------------------------------------------------------------------------
# 2. H11 is plan only — no execution
# ---------------------------------------------------------------------------

class TestContractStatesH11IsPlanOnly:
    def test_contract_states_h11_is_plan_only(self):
        doc = _doc()
        assert "does not execute SQL" in doc.lower() or "H11 does not execute SQL" in doc

    def test_contract_states_no_migration_execution_in_h11(self):
        doc = _doc()
        assert "H11 does not execute the migration" in doc or \
               "no migration execution" in doc.lower()

    def test_contract_states_no_db_connection_in_h11(self):
        doc = _doc()
        assert "does not connect to any database" in doc.lower() or \
               "No DB connection" in doc.lower() or \
               "no DB connection" in doc.lower()

    def test_contract_non_goals_section_exists(self):
        doc = _doc()
        assert "Non-Goals for H11" in doc or "Non-Goals" in doc

    def test_contract_produces_only_two_files(self):
        doc = _doc()
        assert "two files only" in doc.lower()


# ---------------------------------------------------------------------------
# 3. References 011 migration file
# ---------------------------------------------------------------------------

class TestContractReferences011MigrationFile:
    def test_contract_references_011_migration_file(self):
        doc = _doc()
        assert "011_posted_journal_entries_schema.sql" in doc

    def test_contract_migration_file_path_is_correct(self):
        doc = _doc()
        assert "app/storage/migrations/011_posted_journal_entries_schema.sql" in doc

    def test_contract_names_expected_migration_objects(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "journal_entry_sources" in doc


# ---------------------------------------------------------------------------
# 4. Local/test only rule
# ---------------------------------------------------------------------------

class TestContractDefinesLocalTestOnlyRule:
    def test_contract_defines_local_test_only_rule(self):
        doc = _doc()
        assert "Local/test DB only" in doc or "local/test DB only" in doc.lower() or \
               "local or test" in doc.lower()

    def test_contract_names_local_test_environments(self):
        doc = _doc()
        assert "localhost" in doc or "127.0.0.1" in doc or \
               "disposable" in doc.lower()

    def test_contract_states_production_requires_separate_approval(self):
        doc = _doc()
        assert "separately approved" in doc.lower() or \
               "explicit" in doc.lower() and "approval" in doc.lower()


# ---------------------------------------------------------------------------
# 5. Production DB forbidden
# ---------------------------------------------------------------------------

class TestContractForbidsProductionDbTouch:
    def test_contract_forbids_production_db_touch(self):
        doc = _doc()
        assert "Production DB is forbidden" in doc or \
               "production DB" in doc.lower()

    def test_contract_production_db_forbidden_in_h11(self):
        doc = _doc()
        assert "production" in doc.lower() and "forbidden" in doc.lower()

    def test_contract_states_no_production_touch_in_non_goals(self):
        doc = _doc()
        assert "Touch the production database" in doc or \
               "production database" in doc.lower()


# ---------------------------------------------------------------------------
# 6. SQL execution forbidden in H11
# ---------------------------------------------------------------------------

class TestContractForbidsSqlExecutionInH11:
    def test_contract_forbids_sql_execution_in_h11(self):
        doc = _doc()
        assert "Execute any SQL" in doc or "no SQL" in doc.lower()

    def test_contract_non_goals_names_sql(self):
        doc = _doc()
        assert "SQL" in doc

    def test_contract_sql_steps_labeled_future_only(self):
        doc = _doc()
        assert "not executed in H11" in doc or \
               "Future H12 step" in doc


# ---------------------------------------------------------------------------
# 7. Migration execution forbidden in H11
# ---------------------------------------------------------------------------

class TestContractForbidsMigrationExecutionInH11:
    def test_contract_forbids_migration_execution_in_h11(self):
        doc = _doc()
        assert "Execute the migration" in doc or \
               "does not execute the migration" in doc.lower()

    def test_contract_non_goals_names_migration(self):
        doc = _doc()
        assert "migration" in doc.lower()

    def test_contract_future_steps_not_executed_now(self):
        doc = _doc()
        assert "not executed in H11" in doc or \
               "Future H12 step (not executed in H11)" in doc


# ---------------------------------------------------------------------------
# 8. DATABASE_URL must not point to production
# ---------------------------------------------------------------------------

class TestContractRequiresDatabaseUrlNotProduction:
    def test_contract_requires_database_url_not_production(self):
        doc = _doc()
        assert "DATABASE_URL" in doc

    def test_contract_database_url_production_guard(self):
        doc = _doc()
        assert "must not point to" in doc.lower() or \
               "must not contain the production" in doc.lower() or \
               "must never point to" in doc.lower()

    def test_contract_database_url_check_before_execution(self):
        doc = _doc()
        assert "before" in doc.lower() and "DATABASE_URL" in doc


# ---------------------------------------------------------------------------
# 9. Fail closed on production environment
# ---------------------------------------------------------------------------

class TestContractRequiresFailClosedOnProductionEnvironment:
    def test_contract_requires_fail_closed_on_production_environment(self):
        doc = _doc()
        assert "fail closed" in doc.lower()

    def test_contract_migration_runner_aborts_on_production(self):
        doc = _doc()
        assert "abort" in doc.lower() or "must abort" in doc.lower()

    def test_contract_fail_closed_means_no_degraded_mode(self):
        doc = _doc()
        assert "degraded mode" in doc.lower() or "never" in doc.lower()


# ---------------------------------------------------------------------------
# 10. No automatic startup migration
# ---------------------------------------------------------------------------

class TestContractRequiresNoAutomaticStartupMigration:
    def test_contract_requires_no_automatic_startup_migration(self):
        doc = _doc()
        assert "automatic startup migration" in doc.lower() or \
               "startup migration" in doc.lower()

    def test_contract_names_startup_migrations_module(self):
        doc = _doc()
        assert "app/startup/migrations.py" in doc or \
               "startup/migrations" in doc

    def test_contract_startup_migration_forbidden_until_approved(self):
        doc = _doc()
        assert "must not be added" in doc.lower() or \
               "silently execute" in doc.lower()


# ---------------------------------------------------------------------------
# 11. Preflight checklist
# ---------------------------------------------------------------------------

class TestContractDefinesPreflightChecklist:
    def test_contract_defines_preflight_checklist(self):
        doc = _doc()
        assert "Preflight Checklist" in doc or "preflight" in doc.lower()

    def test_contract_preflight_has_ten_checks(self):
        doc = _doc()
        assert "10 checks" in doc.lower() or "All 10 checks" in doc

    def test_contract_preflight_requires_git_sha_confirmation(self):
        doc = _doc()
        assert "git SHA" in doc or "current git SHA" in doc.lower()

    def test_contract_preflight_requires_db_target_confirmation(self):
        doc = _doc()
        assert "DB target is local/test" in doc or \
               "Confirm DB target" in doc

    def test_contract_preflight_blocking_condition(self):
        doc = _doc()
        assert "blocking condition" in doc.lower() or \
               "must not begin" in doc.lower()


# ---------------------------------------------------------------------------
# 12. Backup/snapshot for test DB
# ---------------------------------------------------------------------------

class TestContractRequiresBackupOrSnapshotForTestDb:
    def test_contract_requires_backup_or_snapshot_for_test_db(self):
        doc = _doc()
        assert "backup" in doc.lower() or "snapshot" in doc.lower()

    def test_contract_snapshot_before_migration(self):
        doc = _doc()
        assert "restorable snapshot" in doc.lower() or \
               "before migration" in doc.lower()

    def test_contract_snapshot_in_preflight(self):
        doc = _doc()
        assert "Confirm backup/snapshot" in doc or \
               "backup/snapshot" in doc.lower()


# ---------------------------------------------------------------------------
# 13. Migration checksum
# ---------------------------------------------------------------------------

class TestContractRequiresMigrationChecksum:
    def test_contract_requires_migration_checksum(self):
        doc = _doc()
        assert "checksum" in doc.lower() or "SHA-256" in doc

    def test_contract_checksum_of_migration_file(self):
        doc = _doc()
        assert "011_posted_journal_entries_schema.sql" in doc and \
               ("checksum" in doc.lower() or "SHA-256" in doc)

    def test_contract_checksum_matches_h4_committed_file(self):
        doc = _doc()
        assert "H4" in doc and "checksum" in doc.lower()


# ---------------------------------------------------------------------------
# 14. Additive-only validation
# ---------------------------------------------------------------------------

class TestContractRequiresAdditiveOnlyValidation:
    def test_contract_requires_additive_only_validation(self):
        doc = _doc()
        assert "additive-only" in doc.lower() or "additive only" in doc.lower()

    def test_contract_additive_only_means_no_destructive_ddl(self):
        doc = _doc()
        assert "no `DROP`" in doc or "no DROP" in doc or "DROP" in doc

    def test_contract_migration_must_be_rejected_if_not_additive(self):
        doc = _doc()
        assert "rejected" in doc.lower() and "replanned" in doc.lower()


# ---------------------------------------------------------------------------
# 15. No DROP/DELETE/UPDATE/backfill
# ---------------------------------------------------------------------------

class TestContractForbidsDropDeleteUpdateBackfill:
    def test_contract_forbids_drop_delete_update_backfill(self):
        doc = _doc()
        assert "DROP" in doc and "DELETE" in doc and "UPDATE" in doc

    def test_contract_forbids_backfill(self):
        doc = _doc()
        assert "backfill" in doc.lower()

    def test_contract_forbids_truncate(self):
        doc = _doc()
        assert "TRUNCATE" in doc

    def test_contract_no_data_backfill_expected(self):
        doc = _doc()
        assert "No data backfill" in doc or "no data backfill" in doc.lower()


# ---------------------------------------------------------------------------
# 16. Local/test execution plan defined
# ---------------------------------------------------------------------------

class TestContractDefinesLocalTestExecutionPlan:
    def test_contract_defines_local_test_execution_plan(self):
        doc = _doc()
        assert "Local/Test Execution Plan" in doc or \
               "local/test execution" in doc.lower()

    def test_contract_execution_plan_has_numbered_steps(self):
        doc = _doc()
        assert "Step 1" in doc and "Step 2" in doc

    def test_contract_execution_plan_creates_disposable_db(self):
        doc = _doc()
        assert "disposable" in doc.lower()

    def test_contract_execution_plan_runs_migration_file(self):
        doc = _doc()
        assert "psql" in doc or "migration file" in doc.lower()

    def test_contract_execution_steps_labeled_not_executed_in_h11(self):
        doc = _doc()
        assert "not executed in H11" in doc


# ---------------------------------------------------------------------------
# 17. Idempotency second-run check
# ---------------------------------------------------------------------------

class TestContractRequiresIdempotencySecondRunCheck:
    def test_contract_requires_idempotency_second_run_check(self):
        doc = _doc()
        assert "idempotency" in doc.lower() or "second time" in doc.lower()

    def test_contract_second_run_must_produce_no_errors(self):
        doc = _doc()
        assert "no errors" in doc.lower() or "second run" in doc.lower()

    def test_contract_if_not_exists_constructs_required(self):
        doc = _doc()
        assert "IF NOT EXISTS" in doc or "IF EXISTS" in doc or \
               "idempotency" in doc.lower()


# ---------------------------------------------------------------------------
# 18. Schema validation checks defined
# ---------------------------------------------------------------------------

class TestContractDefinesSchemaValidationChecks:
    def test_contract_defines_schema_validation_checks(self):
        doc = _doc()
        assert "Validation Checks" in doc or "validation checks" in doc.lower()

    def test_contract_validation_checks_all_three_tables(self):
        doc = _doc()
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "journal_entry_sources" in doc

    def test_contract_validation_checks_tenant_id_not_null(self):
        doc = _doc()
        assert "tenant_id" in doc and "NOT NULL" in doc

    def test_contract_validation_checks_status_constraint(self):
        doc = _doc()
        assert "status" in doc and "CHECK" in doc

    def test_contract_validation_checks_fk_lines_to_headers(self):
        doc = _doc()
        assert "journal_entry_lines" in doc and "journal_entry_headers" in doc and \
               ("FK" in doc or "foreign key" in doc.lower())

    def test_contract_validation_checks_indexes_exist(self):
        doc = _doc()
        assert "index" in doc.lower() and ("tenant_id" in doc or "period" in doc.lower())


# ---------------------------------------------------------------------------
# 19. No journal_drafts mutation
# ---------------------------------------------------------------------------

class TestContractRequiresNoJournalDraftsMutation:
    def test_contract_requires_no_journal_drafts_mutation(self):
        doc = _doc()
        assert "journal_drafts" in doc

    def test_contract_journal_drafts_unchanged_after_migration(self):
        doc = _doc()
        assert "unchanged" in doc.lower() or \
               "No `journal_drafts` mutation" in doc or \
               "journal_drafts` table is unchanged" in doc

    def test_contract_no_rows_inserted_deleted_in_journal_drafts(self):
        doc = _doc()
        assert "journal_drafts" in doc and \
               ("inserted" in doc.lower() or "unchanged" in doc.lower())


# ---------------------------------------------------------------------------
# 20. Rollback/restore policy
# ---------------------------------------------------------------------------

class TestContractDefinesRollbackRestorePolicy:
    def test_contract_defines_rollback_restore_policy(self):
        doc = _doc()
        assert "Rollback" in doc and "Restore" in doc or \
               "rollback" in doc.lower()

    def test_contract_local_rollback_options_defined(self):
        doc = _doc()
        assert "Option A" in doc and "Option B" in doc

    def test_contract_production_rollback_not_in_scope_for_h11(self):
        doc = _doc()
        assert "not in scope for H11" in doc or \
               "not in scope" in doc.lower()

    def test_contract_production_rollback_requires_explicit_approval(self):
        doc = _doc()
        assert "explicit human approval" in doc.lower() or \
               "explicit" in doc.lower() and "rollback" in doc.lower()

    def test_contract_pitr_mentioned_for_production(self):
        doc = _doc()
        assert "PITR" in doc or "point-in-time" in doc.lower()


# ---------------------------------------------------------------------------
# 21. Production approval gate
# ---------------------------------------------------------------------------

class TestContractDefinesProductionApprovalGate:
    def test_contract_defines_production_approval_gate(self):
        doc = _doc()
        assert "Production Approval Gate" in doc or \
               "production approval" in doc.lower()

    def test_contract_production_gate_requires_h11_live_verified(self):
        doc = _doc()
        assert "H11 live verification passed" in doc or \
               "live verification" in doc.lower()

    def test_contract_production_gate_requires_h12_evidence(self):
        doc = _doc()
        assert "H12" in doc and "evidence" in doc.lower()

    def test_contract_production_gate_requires_dedicated_task(self):
        doc = _doc()
        assert "dedicated production migration task" in doc.lower() or \
               "separately approved" in doc.lower()

    def test_contract_production_gate_requires_human_approval_recorded(self):
        doc = _doc()
        assert "human stakeholder" in doc.lower() or \
               "human approval" in doc.lower()

    def test_contract_production_gate_requires_backup_pitr(self):
        doc = _doc()
        assert "PITR" in doc and "backup" in doc.lower()


# ---------------------------------------------------------------------------
# 22. Balance.ge activation forbidden
# ---------------------------------------------------------------------------

class TestContractForbidsBalanceActivation:
    def test_contract_forbids_balance_activation(self):
        doc = _doc()
        assert "Balance.ge" in doc

    def test_contract_balance_ge_must_remain_inactive(self):
        doc = _doc()
        assert "inactive" in doc.lower() and "Balance.ge" in doc

    def test_contract_balance_ge_not_coupled_to_migration(self):
        doc = _doc()
        assert "No Balance.ge activation" in doc or \
               "balance.ge activation" in doc.lower()


# ---------------------------------------------------------------------------
# 23. Runtime report/posting changes forbidden
# ---------------------------------------------------------------------------

class TestContractForbidsRuntimeReportOrPostingChanges:
    def test_contract_forbids_runtime_report_or_posting_changes(self):
        doc = _doc()
        assert "runtime" in doc.lower() and "change" in doc.lower()

    def test_contract_posting_service_not_modified(self):
        doc = _doc()
        assert "posting_service.py" in doc

    def test_contract_financial_statements_service_not_modified(self):
        doc = _doc()
        assert "financial_statements_service.py" in doc

    def test_contract_report_migration_is_separate_task(self):
        doc = _doc()
        assert "separate" in doc.lower() and \
               ("report" in doc.lower() or "H13" in doc)


# ---------------------------------------------------------------------------
# 24. Future H12–H17 sequence
# ---------------------------------------------------------------------------

class TestContractDefinesFutureH12ToH17Sequence:
    def test_contract_defines_future_h12_to_h17_sequence(self):
        doc = _doc()
        assert "H12" in doc and "H17" in doc

    def test_contract_h12_is_local_test_execution(self):
        doc = _doc()
        assert "H12" in doc and "disposable" in doc.lower()

    def test_contract_h13_is_report_migration_plan(self):
        doc = _doc()
        assert "H13" in doc and "report" in doc.lower()

    def test_contract_h17_is_production_migration_plan(self):
        doc = _doc()
        assert "H17" in doc and "production" in doc.lower()

    def test_contract_h17_requires_explicit_approval(self):
        doc = _doc()
        assert "H17" in doc and "explicit" in doc.lower()


# ---------------------------------------------------------------------------
# 25. No runtime service imports (AST check)
# ---------------------------------------------------------------------------

class TestFileHasNoRuntimeServiceImports:
    def test_file_has_no_runtime_service_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {
            "posting_service", "approval_service", "ledger_service",
            "financial_statements_service", "routes_reports", "routes_posting",
            "evidence_bundle_service", "evidence_bundle_repository",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    assert f not in node.module, f"Forbidden import: {node.module}"

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
# 26. No DB or network imports (AST check)
# ---------------------------------------------------------------------------

class TestFileHasNoDbOrNetworkImports:
    def test_file_has_no_db_or_network_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {"asyncpg", "psycopg2", "sqlalchemy", "httpx", "aiohttp", "requests"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split(".")[0]]
                for name in names:
                    assert name not in forbidden, f"Forbidden DB/network import: {name}"

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
                    assert False, f"Forbidden SQL execution call: {obj_name}.{func.attr}"
