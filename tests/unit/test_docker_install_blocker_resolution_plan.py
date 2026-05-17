"""H45 Docker install blocker resolution plan contract tests."""

from pathlib import Path


DOC = Path("docs/docker-install-blocker-resolution-plan.md")


def _read() -> str:
    return DOC.read_text(encoding="utf-8")


def test_h45_doc_exists():
    assert DOC.is_file()


def test_h45_context_documented():
    text = _read()
    assert "H41" in text
    assert "H44" in text
    assert "BLOCKED_DOCKER_UNAVAILABLE" in text


def test_h45_non_action_statement_present():
    text = _read()
    for phrase in ["does not install Docker", "does not run Docker", "does not create a container", "does not execute SQL"]:
        assert phrase in text


def test_supported_install_options_documented():
    text = _read()
    assert "Docker Desktop for Windows 11" in text
    assert "WSL2 backend" in text
    assert "Docker Engine alternative" in text


def test_required_user_actions_documented():
    text = _read()
    for phrase in ["Download and install Docker Desktop", "Enable WSL2 backend", "Reboot Windows", "docker --version"]:
        assert phrase in text


def test_safety_rules_documented():
    text = _read()
    for phrase in ["no production context", "no cloud context", "no DB/container yet", "no Balance.ge activation"]:
        assert phrase in text


def test_evidence_needed_after_install_documented():
    text = _read()
    for phrase in ["docker --version", "docker version", "docker context ls", "docker info"]:
        assert phrase in text


def test_no_go_blockers_documented():
    text = _read()
    for phrase in ["install unavailable", "daemon unavailable", "remote/cloud context", "raw secrets"]:
        assert phrase in text


def test_decision_outputs_documented():
    text = _read()
    for decision in [
        "READY_FOR_DOCKER_RECHECK",
        "BLOCKED_INSTALL_REQUIRED",
        "BLOCKED_REBOOT_REQUIRED",
        "BLOCKED_DAEMON_UNAVAILABLE",
        "BLOCKED_REMOTE_CONTEXT",
    ]:
        assert decision in text


def test_current_decision_blocked_install_required():
    assert "Current H45 decision: `BLOCKED_INSTALL_REQUIRED`" in _read()


def test_no_db_network_docker_execution_imports():
    src = Path(__file__).read_text(encoding="utf-8")
    forbidden = ["import " + token for token in ["psycopg", "sqlalchemy", "requests", "httpx", "socket", "subprocess", "docker"]]
    for token in forbidden:
        assert token not in src
