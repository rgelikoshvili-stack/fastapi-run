"""H47 migration 011 review/hash evidence plan contract tests."""

from pathlib import Path


DOC = Path("docs/migration-011-review-hash-evidence-plan.md")
MIGRATION = "app/storage/migrations/011_posted_journal_entries_schema.sql"


def _read() -> str:
    return DOC.read_text(encoding="utf-8")


def test_h47_doc_exists():
    assert DOC.is_file()


def test_migration_target_documented():
    text = _read()
    assert MIGRATION in text
    assert Path(MIGRATION).is_file()


def test_non_action_statement_present():
    text = _read()
    for phrase in ["does not execute migration 011", "does not execute SQL", "does not create DB", "does not modify migration files"]:
        assert phrase in text


def test_review_checklist_documented():
    text = _read()
    for phrase in ["additive-only", "IF NOT EXISTS", "no `DROP`", "tenant_id checks", "foreign keys documented"]:
        assert phrase in text


def test_hash_command_templates_documented():
    text = _read()
    assert "Get-FileHash" in text
    assert "sha256sum" in text
    assert "SHA256" in text or "SHA-256" in text


def test_evidence_packet_documented():
    text = _read()
    for field in ["migration_path", "algorithm", "sha256", "additive_review_status", "reviewed_by", "reviewed_at"]:
        assert field in text


def test_no_go_blockers_documented():
    text = _read()
    for phrase in ["migration missing", "destructive SQL found", "hash missing", "review missing"]:
        assert phrase in text


def test_decision_outputs_documented():
    text = _read()
    for decision in [
        "READY_FOR_MIGRATION_HASH_CAPTURE",
        "BLOCKED_MIGRATION_MISSING",
        "BLOCKED_DESTRUCTIVE_SQL",
        "BLOCKED_HASH_NOT_CAPTURED",
    ]:
        assert decision in text


def test_no_migration_execution_required():
    assert "does not execute the migration" in _read()


def test_no_db_network_docker_execution_imports():
    src = Path(__file__).read_text(encoding="utf-8")
    forbidden = ["import " + token for token in ["psycopg", "sqlalchemy", "requests", "httpx", "socket", "subprocess", "docker"]]
    for token in forbidden:
        assert token not in src
