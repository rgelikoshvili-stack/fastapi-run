"""H48 owner approval finalization plan contract tests."""

from pathlib import Path


DOC = Path("docs/owner-approval-finalization-plan.md")


def _read() -> str:
    return DOC.read_text(encoding="utf-8")


def test_h48_doc_exists():
    assert DOC.is_file()


def test_h43_context_documented():
    text = _read()
    assert "H43" in text
    assert "APPROVAL_PACKET_READY_PENDING_SIGNATURE" in text


def test_non_action_statement_present():
    text = _read()
    for phrase in ["no approval auto-signing", "does not run Docker", "does not create DB", "does not execute SQL"]:
        assert phrase in text


def test_required_approval_fields_documented():
    text = _read()
    for field in [
        "approval_id",
        "approved_by",
        "requested_by",
        "scope",
        "allowed_operations",
        "forbidden_operations",
        "cleanup_policy",
        "retention_policy",
        "expires_at",
        "status",
    ]:
        assert field in text


def test_approval_criteria_documented():
    text = _read()
    for phrase in ["Docker evidence clean", "cleanup ready", "fixture hash captured", "migration hash captured", "no production risk"]:
        assert phrase in text


def test_no_go_blockers_documented():
    text = _read()
    for phrase in ["no approver", "unclear scope", "cleanup missing", "Docker unavailable"]:
        assert phrase in text


def test_decision_outputs_documented():
    text = _read()
    for decision in ["APPROVAL_READY_FOR_SIGNATURE", "BLOCKED_NO_APPROVER", "BLOCKED_SCOPE_UNCLEAR", "BLOCKED_CLEANUP_MISSING"]:
        assert decision in text


def test_next_task_documented():
    text = _read()
    assert "H49 - Docker Recheck Evidence Capture" in text
    assert "H50 - Local Docker PostgreSQL Provisioning Dry-Run Execution" in text


def test_no_auto_signing():
    assert "no approval auto-signing" in _read()


def test_no_db_network_docker_execution_imports():
    src = Path(__file__).read_text(encoding="utf-8")
    forbidden = ["import " + token for token in ["psycopg", "sqlalchemy", "requests", "httpx", "socket", "subprocess", "docker"]]
    for token in forbidden:
        assert token not in src
