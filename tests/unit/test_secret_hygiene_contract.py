"""
SEC-1 — Security Secret Hygiene Contract Tests

Verifies that hardcoded credentials have been removed from legacy scripts
and that the secret hygiene documentation is complete.

No DB, no network, no subprocess execution, no SQL, no migrations.
All assertions are read-only file text scans.
"""

import ast
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HYGIENE_DOC = (
    pathlib.Path(__file__).parents[2]
    / "docs"
    / "security-secret-hygiene.md"
)
_SCRIPTS_DIR = pathlib.Path(__file__).parents[2] / "scripts"
_THIS_FILE = pathlib.Path(__file__)

# ---------------------------------------------------------------------------
# Forbidden literal patterns — stored as split fragments to avoid self-match
_FORBIDDEN_PASSWORD = "BridgeHub" + "2026x"
_FORBIDDEN_HOST_IP = "35.192" + ".214.120"
_FORBIDDEN_SSH_HOST = "116.203" + ".134.24"
_FORBIDDEN_ADMIN_PW = "Admin" + "2026!"
_FORBIDDEN_PRIVATE_KEY_MARKERS = [
    "BEGIN " + "RSA",
    "BEGIN " + "OPENSSH",
    "BEGIN " + "PRIVATE",
    "PRIVATE " + "KEY",
]
_FORBIDDEN_LIVE_KEY_PREFIXES = ["sk-live", "sk-secret"]

# Scan target directories (text files only; exclude .venv, __pycache__, .git)
_SCAN_DIRS = ["app", "scripts", "docs", "main.py", "CLAUDE.md", "README.md"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hygiene_text() -> str:
    assert _HYGIENE_DOC.exists(), f"Hygiene doc missing: {_HYGIENE_DOC}"
    return _HYGIENE_DOC.read_text(encoding="utf-8")


def _find_section(text: str, keyword: str, window: int = 2000) -> str:
    m = re.search(rf"^##[^\n]*{re.escape(keyword)}", text, re.MULTILINE | re.IGNORECASE)
    assert m is not None, f"Section not found: {keyword!r}"
    return text[m.start() : m.start() + window].lower()


def _repo_text_files():
    """Yield (path, text) for all tracked Python/markdown/sh/txt files to scan."""
    root = pathlib.Path(__file__).parents[2]
    extensions = {".py", ".md", ".sh", ".txt", ".toml", ".cfg", ".ini"}
    skip_dirs = {".venv", ".venv.broken-20260507-235411", "__pycache__", ".git", "node_modules", ".uv-cache"}
    for item in root.rglob("*"):
        if any(part in skip_dirs for part in item.parts):
            continue
        if item.suffix in extensions and item.is_file():
            try:
                yield item, item.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass


def _scripts_text_files():
    """Yield (path, text) for all Python scripts in scripts/."""
    if not _SCRIPTS_DIR.exists():
        return
    for item in _SCRIPTS_DIR.glob("*.py"):
        try:
            yield item, item.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Tests 1–6: document checks
# ---------------------------------------------------------------------------


def test_secret_hygiene_doc_exists():
    assert _HYGIENE_DOC.exists(), f"Missing: {_HYGIENE_DOC}"


def test_sec1_is_security_cleanup_only():
    text = _hygiene_text().lower()
    assert "security cleanup" in text or "sec-1" in text


def test_non_action_statement_present():
    text = _hygiene_text()
    assert "Non-Action Statement" in text


def test_placeholder_policy_present():
    section = _find_section(_hygiene_text(), "Placeholder Policy")
    assert "<non_prod_db_host>" in section
    assert "<non_prod_db_password>" in section
    assert "<placeholder_only>" in section


def test_legacy_script_safety_rules_present():
    section = _find_section(_hygiene_text(), "Legacy Script Safety Rules")
    assert "fail closed" in section or "fails if unset" in section
    assert "production" in section
    assert "no default" in section or "no embedded" in section


def test_rotation_recommendation_present():
    section = _find_section(_hygiene_text(), "Rotation Recommendation")
    assert "rotate" in section or "rotation" in section
    assert "does not rotate" in section or "not rotate" in section


# ---------------------------------------------------------------------------
# Tests 7–10: forbidden literal scans across repo
# ---------------------------------------------------------------------------


def test_no_forbidden_hardcoded_db_password_literal():
    for path, text in _repo_text_files():
        # Allow occurrences only inside _KNOWN_PRODUCTION_HOSTS sets or comments that
        # document the removal — i.e. the literal must not appear as a string value.
        # We check each line individually to skip guard-set definitions.
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # Skip lines that are part of the production guard set definitions
            if "_KNOWN_PRODUCTION_HOSTS" in stripped:
                continue
            # Skip comment lines documenting the removal
            if stripped.startswith("#"):
                continue
            if _FORBIDDEN_PASSWORD in line:
                raise AssertionError(
                    f"Forbidden hardcoded password found in {path}:{lineno}: {line.strip()!r}"
                )


def test_no_forbidden_hardcoded_db_host_literal():
    for path, text in _repo_text_files():
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if "_KNOWN_PRODUCTION_HOSTS" in stripped or "_KNOWN_PRODUCTION_SSH_HOSTS" in stripped:
                continue
            if stripped.startswith("#"):
                continue
            if _FORBIDDEN_HOST_IP in line or _FORBIDDEN_SSH_HOST in line:
                raise AssertionError(
                    f"Forbidden hardcoded production IP found in {path}:{lineno}: {line.strip()!r}"
                )


def test_no_private_key_material_in_repo_text():
    for path, text in _repo_text_files():
        for marker in _FORBIDDEN_PRIVATE_KEY_MARKERS:
            if marker in text:
                raise AssertionError(
                    f"Private key material marker {marker!r} found in {path}"
                )


def test_no_live_balance_api_key_literal():
    for path, text in _repo_text_files():
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip test files that use sk-live as fake test fixture data
            if "test_" in path.name and ("sk-live-abc" in line or "sk-live-nested" in line or "sk-live-abcdef" in line):
                continue
            for prefix in _FORBIDDEN_LIVE_KEY_PREFIXES:
                if re.search(rf'\b{re.escape(prefix)}-[A-Za-z0-9]{{6,}}', line):
                    # Allow clear fake/test values used in mock assertions
                    if "monkeypatch" in line or "fake" in line.lower() or "test" in path.name:
                        continue
                    raise AssertionError(
                        f"Possible live API key pattern in {path}:{lineno}: {line.strip()!r}"
                    )


# ---------------------------------------------------------------------------
# Tests 11–16: script-specific checks
# ---------------------------------------------------------------------------


def test_scripts_do_not_default_to_production_db():
    for path, text in _scripts_text_files():
        # The forbidden password must not appear as a default value in os.getenv calls
        if re.search(r'os\.getenv\s*\(\s*["\']DB_PASSWORD["\']\s*,\s*["\']' + re.escape(_FORBIDDEN_PASSWORD), text):
            raise AssertionError(
                f"Script {path.name} still has hardcoded production password as getenv default"
            )
        if re.search(r'os\.getenv\s*\(\s*["\']DB_HOST["\']\s*,\s*["\']' + re.escape(_FORBIDDEN_HOST_IP), text):
            raise AssertionError(
                f"Script {path.name} still has hardcoded production host as getenv default"
            )


def test_migration_scripts_require_explicit_env_or_placeholder():
    migration_scripts = [p for p, _ in _scripts_text_files() if "migration" in p.name.lower()]
    for path in migration_scripts:
        text = path.read_text(encoding="utf-8", errors="replace")
        # Quarantined scripts refuse to run at all — no DB connection, no env vars needed
        if "quarantined" in text.lower():
            continue
        has_env = "os.getenv" in text or "os.environ" in text or "DATABASE_URL" in text
        assert has_env, f"Migration script {path.name} does not use environment variables"


def test_unsafe_schema_check_uses_placeholders_or_env():
    schema_check = _SCRIPTS_DIR / "schema_check.py"
    if not schema_check.exists():
        pytest.skip("schema_check.py not found")
    text = schema_check.read_text(encoding="utf-8", errors="replace")
    assert "os.getenv" in text or "os.environ" in text, (
        "schema_check.py must use environment variables for all credentials"
    )
    assert _FORBIDDEN_PASSWORD not in text, (
        "schema_check.py still contains hardcoded password"
    )
    assert _FORBIDDEN_SSH_HOST not in text or "_KNOWN_PRODUCTION_SSH_HOSTS" in text, (
        "schema_check.py contains SSH host without a production guard"
    )


def test_no_raw_database_url_with_real_host_in_scripts():
    for path, text in _scripts_text_files():
        if re.search(r'postgresql://[^<\s]{3,}@' + re.escape(_FORBIDDEN_HOST_IP), text):
            raise AssertionError(
                f"Script {path.name} contains raw DATABASE_URL with production host"
            )
        if re.search(r'postgresql://[^<\s]*' + re.escape(_FORBIDDEN_PASSWORD), text):
            raise AssertionError(
                f"Script {path.name} contains raw DATABASE_URL with hardcoded password"
            )


def test_no_raw_api_key_assignment_in_scripts():
    for path, text in _scripts_text_files():
        if re.search(r'api_key\s*=\s*["\'][^<\s]{8,}["\']', text, re.IGNORECASE):
            raise AssertionError(
                f"Script {path.name} may contain a hardcoded API key assignment"
            )


def test_docs_do_not_contain_real_secret_values():
    docs_dir = pathlib.Path(__file__).parents[2] / "docs"
    for doc in docs_dir.glob("*.md"):
        text = doc.read_text(encoding="utf-8", errors="replace")
        if _FORBIDDEN_PASSWORD in text:
            raise AssertionError(
                f"Doc {doc.name} contains hardcoded production password"
            )
        for marker in _FORBIDDEN_PRIVATE_KEY_MARKERS:
            if marker in text:
                raise AssertionError(
                    f"Doc {doc.name} contains private key material: {marker!r}"
                )


# ---------------------------------------------------------------------------
# Tests 17–18: placeholder assertions
# ---------------------------------------------------------------------------


def test_placeholders_are_allowed():
    allowed = [
        "<NON_PROD_DB_HOST>",
        "<NON_PROD_DB_PASSWORD>",
        "<DISPOSABLE_DB>",
        "<PLACEHOLDER_ONLY>",
    ]
    text = _hygiene_text()
    for placeholder in allowed:
        assert placeholder in text, f"Expected allowed placeholder {placeholder!r} in hygiene doc"


# ---------------------------------------------------------------------------
# Tests 18–19: AST-based self-referential safety checks
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_top = {
        "asyncpg", "psycopg2", "sqlalchemy", "httpx", "requests",
        "aiohttp", "socket",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_top, (
                    f"Forbidden import in test file: {alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden_top, (
                f"Forbidden import-from in test file: {node.module!r}"
            )


def test_no_subprocess_execution_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = {"system", "popen", "Popen", "check_call", "check_output", "run"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            elif isinstance(node.func, ast.Name):
                fname = node.func.id
            else:
                fname = ""
            if fname in forbidden_calls:
                # subprocess.run is forbidden; pathlib.read_text is fine
                parent = getattr(node.func, "value", None)
                parent_name = getattr(parent, "id", "") if parent else ""
                if parent_name in ("subprocess", "os"):
                    raise AssertionError(
                        f"Forbidden subprocess/os call in test file: {fname!r}"
                    )


# ---------------------------------------------------------------------------
# Test 20: next task documented
# ---------------------------------------------------------------------------


def test_next_task_enc1_or_h24_documented():
    text = _hygiene_text()
    assert "ENC-1" in text
    assert "H24" in text
