"""Read-only tests for Credential Vault Design documents.

These tests verify that the credential vault design and interface contract
documents exist and contain all required content.

They do not import runtime app code, connect to a database, execute SQL,
or change any runtime credential behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DESIGN_DOC = ROOT / "docs" / "credential-vault-design.md"
INTERFACE_DOC = ROOT / "docs" / "credential-vault-interface-contract.md"
SCRIPTS_DIR = ROOT / "scripts"


def _design() -> str:
    assert DESIGN_DOC.exists(), "credential-vault-design.md is missing"
    return DESIGN_DOC.read_text(encoding="utf-8")


def _interface() -> str:
    assert INTERFACE_DOC.exists(), "credential-vault-interface-contract.md is missing"
    return INTERFACE_DOC.read_text(encoding="utf-8")


def _python_execute_string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = ""
        if isinstance(func, ast.Attribute):
            func_name = func.attr
        elif isinstance(func, ast.Name):
            func_name = func.id
        if func_name not in {"execute", "executemany"}:
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            literals.append(first_arg.value)
    return literals


# ---------------------------------------------------------------------------
# Document existence
# ---------------------------------------------------------------------------

def test_both_credential_vault_docs_exist():
    assert DESIGN_DOC.exists(), "credential-vault-design.md missing"
    assert INTERFACE_DOC.exists(), "credential-vault-interface-contract.md missing"


# ---------------------------------------------------------------------------
# Design doc: required vault components
# ---------------------------------------------------------------------------

def test_design_mentions_credential_vault_service():
    text = _design()
    assert "CredentialVaultService" in text, "design must mention CredentialVaultService"


def test_design_mentions_secret_crypto_provider():
    text = _design()
    assert "SecretCryptoProvider" in text, "design must mention SecretCryptoProvider"


def test_design_mentions_credential_repository():
    text = _design()
    assert "CredentialRepository" in text, "design must mention CredentialRepository"


def test_design_mentions_credential_status_service():
    text = _design()
    assert "CredentialStatusService" in text, "design must mention CredentialStatusService"


def test_design_mentions_connector_credential_provider():
    text = _design()
    assert "ConnectorCredentialProvider" in text, (
        "design must mention ConnectorCredentialProvider"
    )


def test_design_mentions_credential_audit_logger():
    text = _design()
    assert "CredentialAuditLogger" in text, "design must mention CredentialAuditLogger"


# ---------------------------------------------------------------------------
# Design doc: required storage fields
# ---------------------------------------------------------------------------

def test_design_requires_encrypted_value():
    text = _design().lower()
    assert "encrypted_value" in text, "design must require encrypted_value field"


def test_design_requires_key_version():
    text = _design().lower()
    assert "key_version" in text, "design must require key_version field"


def test_design_requires_masked_hint():
    text = _design().lower()
    assert "masked_hint" in text, "design must require masked_hint field"


def test_design_requires_rotation_metadata():
    text = _design().lower()
    rotation_fields = ["rotated_at", "last_used_at", "last_tested_at", "last_test_status"]
    for field in rotation_fields:
        assert field in text, f"design must require rotation metadata field: {field}"


# ---------------------------------------------------------------------------
# Design doc: security rules
# ---------------------------------------------------------------------------

def test_design_requires_audit_logging_without_raw_secrets():
    text = _design().lower()
    assert "audit" in text, "design must require audit logging"
    assert "no raw secret" in text or "never log" in text or "must not" in text, (
        "design must require audit logging without raw secrets"
    )


def test_design_explicitly_forbids_raw_secret_exposure():
    text = _design().lower()
    forbidden_phrases = [
        "never return a raw secret",
        "never return raw secret",
        "must not return raw",
        "never return the raw",
    ]
    assert any(p in text for p in forbidden_phrases), (
        "design must explicitly forbid raw secret exposure in API responses"
    )


def test_design_explicitly_says_balance_ge_remains_inactive():
    text = _design().lower()
    assert "balance.ge" in text, "design must mention Balance.ge"
    inactive_phrases = [
        "balance.ge must stay inactive",
        "balance.ge remains inactive",
        "balance.ge activation remains blocked",
    ]
    assert any(p in text for p in inactive_phrases), (
        "design must explicitly state Balance.ge remains inactive"
    )


def test_design_explicitly_says_no_migration_in_this_task():
    text = _design().lower()
    no_migration_phrases = [
        "no migration in this task",
        "no migration is created",
        "no migration",
    ]
    assert any(p in text for p in no_migration_phrases), (
        "design must explicitly state no migration in this task"
    )


def test_design_explicitly_says_no_runtime_behavior_change():
    text = _design().lower()
    no_change_phrases = [
        "no runtime behavior change",
        "no runtime code is changed",
        "runtime code is not changed",
        "does not implement encryption or change runtime",
    ]
    assert any(p in text for p in no_change_phrases), (
        "design must explicitly state no runtime behavior change in this task"
    )


# ---------------------------------------------------------------------------
# Interface contract: required service methods
# ---------------------------------------------------------------------------

def test_interface_contract_includes_get_secret_for_connector_use():
    text = _interface()
    assert "get_secret_for_connector_use" in text, (
        "interface contract must include get_secret_for_connector_use"
    )


def test_interface_contract_includes_get_credential_status():
    text = _interface()
    assert "get_credential_status" in text, (
        "interface contract must include get_credential_status"
    )


def test_interface_contract_includes_rotate_and_revoke():
    text = _interface()
    assert "rotate_secret" in text, "interface contract must include rotate_secret"
    assert "revoke_secret" in text, "interface contract must include revoke_secret"


# ---------------------------------------------------------------------------
# Interface contract: CredentialStatus allowed/forbidden fields
# ---------------------------------------------------------------------------

def test_interface_contract_defines_credential_status_allowed_fields():
    text = _interface()
    required_fields = [
        "configured",
        "masked_hint",
        "last_tested_at",
        "last_test_status",
        "last_used_at",
        "rotated_at",
        "is_active",
    ]
    for field in required_fields:
        assert field in text, f"interface contract must define CredentialStatus field: {field}"


def test_interface_contract_forbids_raw_secret_fields_in_status():
    text = _interface()
    forbidden_in_status = [
        "api_key",
        "password",
        "token",
        "secret",
        "encrypted_value",
        "totp_secret",
        "webhook_secret",
    ]
    for field in forbidden_in_status:
        assert field in text, (
            f"interface contract must explicitly list '{field}' as forbidden in status responses"
        )


def test_interface_contract_states_public_apis_use_status_methods_only():
    text = _interface().lower()
    status_method_phrases = [
        "public/status apis must use status methods only",
        "public api responses and ui displays must use this object only",
        "status apis",
    ]
    assert any(p in text for p in status_method_phrases), (
        "interface contract must require public/status APIs to use status methods only"
    )


def test_interface_contract_requires_secrets_in_memory_only_for_connectors():
    text = _interface().lower()
    memory_phrases = [
        "in memory only",
        "in-memory only",
        "memory only",
    ]
    assert any(p in text for p in memory_phrases), (
        "interface contract must state that raw secrets are held in memory only for connector paths"
    )


# ---------------------------------------------------------------------------
# Safety: active scripts must not contain executable DROP TABLE IF EXISTS users
# ---------------------------------------------------------------------------

def test_active_scripts_do_not_execute_drop_table_users():
    if not SCRIPTS_DIR.exists():
        return
    executable_drop_users = []
    for path in SCRIPTS_DIR.rglob("*.py"):
        try:
            for literal in _python_execute_string_literals(path):
                normalized = " ".join(literal.lower().split())
                if "drop table if exists users" in normalized:
                    executable_drop_users.append(path.relative_to(ROOT).as_posix())
        except SyntaxError:
            pass
    assert not executable_drop_users, (
        "active scripts must not execute DROP TABLE IF EXISTS users: "
        f"{executable_drop_users}"
    )
