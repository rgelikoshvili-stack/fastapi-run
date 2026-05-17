"""H46 fixture hash evidence plan contract tests."""

from pathlib import Path


DOC = Path("docs/fixture-hash-evidence-plan.md")
FIXTURE = "tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json"


def _read() -> str:
    return DOC.read_text(encoding="utf-8")


def test_h46_doc_exists():
    assert DOC.is_file()


def test_fixture_target_documented():
    assert FIXTURE in _read()


def test_non_action_statement_present():
    text = _read()
    for phrase in ["does not modify the fixture", "does not load the fixture", "does not create DB", "does not run SQL"]:
        assert phrase in text


def test_hash_command_templates_documented():
    text = _read()
    assert "Get-FileHash" in text
    assert "sha256sum" in text
    assert "SHA256" in text or "SHA-256" in text


def test_hash_evidence_packet_documented():
    text = _read()
    for field in ["fixture_path", "algorithm", "sha256", "generated_at", "generated_by", "safe_to_use"]:
        assert field in text


def test_no_go_blockers_documented():
    text = _read()
    for phrase in ["fixture missing", "hash missing", "file modified unexpectedly"]:
        assert phrase in text


def test_decision_outputs_documented():
    text = _read()
    for decision in ["READY_FOR_FIXTURE_HASH_CAPTURE", "BLOCKED_FIXTURE_MISSING", "BLOCKED_HASH_NOT_CAPTURED"]:
        assert decision in text


def test_fixture_path_is_synthetic_fixture():
    text = _read()
    assert "synthetic_posted_ledger_fixture_pack.json" in text


def test_no_fixture_modification_required():
    assert "does not modify the fixture" in _read()


def test_no_db_network_docker_execution_imports():
    src = Path(__file__).read_text(encoding="utf-8")
    forbidden = ["import " + token for token in ["psycopg", "sqlalchemy", "requests", "httpx", "socket", "subprocess", "docker"]]
    for token in forbidden:
        assert token not in src
