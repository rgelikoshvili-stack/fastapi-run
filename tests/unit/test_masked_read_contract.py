"""Read-only tests for Masked Read Behavior Contract.

Validates that the masked read behavior contract document exists and contains
all required content. Also validates contract logic using local test-only
sample dicts — no runtime app imports, no DB connections, no SQL.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

MASKED_DOC = ROOT / "docs" / "masked-read-behavior-contract.md"
INTERFACE_DOC = ROOT / "docs" / "credential-vault-interface-contract.md"
DESIGN_DOC = ROOT / "docs" / "credential-vault-design.md"
SCRIPTS_DIR = ROOT / "scripts"

# ---------------------------------------------------------------------------
# Allowed and forbidden field sets (canonical contract definition)
# ---------------------------------------------------------------------------

ALLOWED_STATUS_FIELDS: frozenset[str] = frozenset({
    "provider",
    "credential_type",
    "configured",
    "status",
    "masked_hint",
    "last_tested_at",
    "last_test_status",
    "last_used_at",
    "rotated_at",
    "revoked_at",
    "is_active",
    "message",
    "reason",
    "error_code",
})

FORBIDDEN_STATUS_FIELDS: frozenset[str] = frozenset({
    "api_key",
    "raw_api_key",
    "password",
    "app_password",
    "imap_password",
    "rsge_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "webhook_secret",
    "totp_secret",
    "encrypted_value",
    "encrypted_secret",
    "decryption_key",
    "private_key",
    "client_secret",
    "authorization_header",
})

# ---------------------------------------------------------------------------
# Local test-only helpers
# ---------------------------------------------------------------------------

def _scan_forbidden_fields(payload: Any, forbidden: frozenset[str]) -> list[str]:
    """Recursively scan a dict/list payload and return found forbidden keys."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in forbidden:
                found.append(key)
            found.extend(_scan_forbidden_fields(value, forbidden))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found.extend(_scan_forbidden_fields(item, forbidden))
    return found


def _is_safe_status_response(response: dict) -> bool:
    """Return True if response contains no forbidden fields at any depth."""
    return len(_scan_forbidden_fields(response, FORBIDDEN_STATUS_FIELDS)) == 0


def _masked_doc() -> str:
    assert MASKED_DOC.exists(), "masked-read-behavior-contract.md is missing"
    return MASKED_DOC.read_text(encoding="utf-8")


def _interface_doc() -> str:
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
# A) Document existence
# ---------------------------------------------------------------------------

def test_all_three_credential_docs_exist():
    assert MASKED_DOC.exists(), "masked-read-behavior-contract.md missing"
    assert INTERFACE_DOC.exists(), "credential-vault-interface-contract.md missing"
    assert DESIGN_DOC.exists(), "credential-vault-design.md missing"


# ---------------------------------------------------------------------------
# B) Contract content: required topics in masked-read doc
# ---------------------------------------------------------------------------

def test_masked_doc_mentions_public_status_apis():
    text = _masked_doc().lower()
    assert "public" in text and "status" in text, (
        "masked-read doc must mention public/status APIs"
    )


def test_masked_doc_mentions_internal_connector_execution():
    text = _masked_doc().lower()
    phrases = [
        "internal connector",
        "connector execution",
        "connector credential provider",
        "connectorCredentialProvider".lower(),
    ]
    assert any(p in text for p in phrases), (
        "masked-read doc must mention internal connector execution path"
    )


def test_masked_doc_mentions_masked_hint():
    text = _masked_doc().lower()
    assert "masked_hint" in text, "masked-read doc must mention masked_hint"


def test_masked_doc_mentions_configured_and_not_configured():
    text = _masked_doc().lower()
    assert "configured" in text, "masked-read doc must mention configured"
    assert "not_configured" in text, "masked-read doc must mention not_configured"


def test_masked_doc_says_balance_ge_remains_inactive():
    text = _masked_doc().lower()
    inactive_phrases = [
        "balance.ge remains inactive",
        "balance.ge must stay inactive",
        "balance.ge activation remains blocked",
    ]
    assert any(p in text for p in inactive_phrases), (
        "masked-read doc must state Balance.ge remains inactive"
    )


def test_masked_doc_says_no_runtime_behavior_change():
    text = _masked_doc().lower()
    no_change_phrases = [
        "no runtime behavior change",
        "no runtime behavior is changed",
        "runtime behavior is unchanged",
        "runtime behavior:\n**unchanged",
        "runtime behavior status",
        "no runtime code is changed",
        "not changed in this task",
        "unchanged in this task",
    ]
    assert any(p in text for p in no_change_phrases), (
        "masked-read doc must state no runtime behavior change in this task"
    )


def test_masked_doc_says_no_migration():
    text = _masked_doc().lower()
    no_migration_phrases = [
        "no migration",
        "no migration is created",
        "no migration or ddl",
    ]
    assert any(p in text for p in no_migration_phrases), (
        "masked-read doc must state no migration in this task"
    )


def test_masked_doc_says_no_db_touch():
    text = _masked_doc().lower()
    no_db_phrases = [
        "no production database is touched",
        "production database is not touched",
        "production db untouched",
        "production database is\n**untouched",
        "no production db touch",
        "untouched in this task",
    ]
    assert any(p in text for p in no_db_phrases), (
        "masked-read doc must state no production DB touch in this task"
    )


def test_masked_doc_says_no_balance_ge_activation():
    text = _masked_doc().lower()
    no_activation_phrases = [
        "no balance.ge activation",
        "balance.ge remains inactive",
        "balance.ge activation remains blocked",
    ]
    assert any(p in text for p in no_activation_phrases), (
        "masked-read doc must state no Balance.ge activation in this task"
    )


# ---------------------------------------------------------------------------
# C) Allowed status fields: contract field set is correct
# ---------------------------------------------------------------------------

def test_allowed_status_fields_includes_required_fields():
    required = {
        "provider",
        "credential_type",
        "configured",
        "status",
        "masked_hint",
        "last_tested_at",
        "last_test_status",
        "last_used_at",
        "rotated_at",
        "revoked_at",
        "is_active",
        "message",
        "reason",
        "error_code",
    }
    missing = required - ALLOWED_STATUS_FIELDS
    assert not missing, f"ALLOWED_STATUS_FIELDS is missing required fields: {missing}"


def test_allowed_status_fields_does_not_contain_forbidden_fields():
    overlap = ALLOWED_STATUS_FIELDS & FORBIDDEN_STATUS_FIELDS
    assert not overlap, (
        f"ALLOWED_STATUS_FIELDS and FORBIDDEN_STATUS_FIELDS overlap: {overlap}"
    )


# ---------------------------------------------------------------------------
# D) Forbidden public/status fields: contract field set is complete
# ---------------------------------------------------------------------------

def test_forbidden_status_fields_includes_all_required():
    required_forbidden = {
        "api_key",
        "raw_api_key",
        "password",
        "app_password",
        "imap_password",
        "rsge_password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "webhook_secret",
        "totp_secret",
        "encrypted_value",
        "encrypted_secret",
        "decryption_key",
        "private_key",
        "client_secret",
        "authorization_header",
    }
    missing = required_forbidden - FORBIDDEN_STATUS_FIELDS
    assert not missing, f"FORBIDDEN_STATUS_FIELDS is missing required entries: {missing}"


# ---------------------------------------------------------------------------
# E) Sample safe response: must pass forbidden-field scan
# ---------------------------------------------------------------------------

SAMPLE_SAFE_BALANCE_STATUS = {
    "provider": "balance",
    "credential_type": "api_key",
    "configured": True,
    "status": "active",
    "masked_hint": "****7a3f",
    "last_tested_at": "2026-05-10T09:00:00Z",
    "last_test_status": "ok",
    "last_used_at": "2026-05-10T08:30:00Z",
    "rotated_at": None,
    "is_active": True,
}

SAMPLE_SAFE_NOT_CONFIGURED_STATUS = {
    "provider": "rsge",
    "credential_type": "password",
    "configured": False,
    "status": "not_configured",
    "masked_hint": None,
    "last_tested_at": None,
    "last_test_status": "not_tested",
    "last_used_at": None,
    "rotated_at": None,
    "is_active": False,
}

SAMPLE_SAFE_EMAIL_STATUS = {
    "provider": "email",
    "credential_type": "app_password",
    "configured": True,
    "status": "active",
    "masked_hint": "****9z2q",
    "last_tested_at": "2026-05-09T12:00:00Z",
    "last_test_status": "ok",
    "last_used_at": None,
    "rotated_at": None,
    "is_active": True,
}

SAMPLE_SAFE_TOTP_STATUS = {
    "provider": "totp",
    "credential_type": "totp_secret",
    "configured": True,
    "status": "active",
    "masked_hint": None,
    "is_active": True,
}


def test_sample_safe_balance_status_passes_scan():
    found = _scan_forbidden_fields(SAMPLE_SAFE_BALANCE_STATUS, FORBIDDEN_STATUS_FIELDS)
    assert not found, f"Safe balance status contains forbidden fields: {found}"


def test_sample_safe_not_configured_status_passes_scan():
    found = _scan_forbidden_fields(SAMPLE_SAFE_NOT_CONFIGURED_STATUS, FORBIDDEN_STATUS_FIELDS)
    assert not found, f"Not-configured status contains forbidden fields: {found}"


def test_sample_safe_email_status_passes_scan():
    found = _scan_forbidden_fields(SAMPLE_SAFE_EMAIL_STATUS, FORBIDDEN_STATUS_FIELDS)
    assert not found, f"Safe email status contains forbidden fields: {found}"


def test_sample_safe_totp_status_passes_scan():
    found = _scan_forbidden_fields(SAMPLE_SAFE_TOTP_STATUS, FORBIDDEN_STATUS_FIELDS)
    assert not found, f"Safe TOTP status contains forbidden fields: {found}"


def test_sample_safe_balance_status_configured_is_boolean():
    assert isinstance(SAMPLE_SAFE_BALANCE_STATUS["configured"], bool), (
        "configured must be a boolean"
    )


def test_sample_safe_balance_status_masked_hint_is_safe():
    hint = SAMPLE_SAFE_BALANCE_STATUS["masked_hint"]
    assert hint is None or isinstance(hint, str), "masked_hint must be str or None"
    if hint is not None:
        assert hint.startswith("****"), "masked_hint must start with ****"
        assert len(hint) <= 12, "masked_hint must not expose more than 4 chars after ****"


def test_sample_safe_responses_contain_no_raw_secret_values():
    raw_secrets = ["sk-live-abcdef123456", "myP@ssw0rd!", "BASE32TOTPSECRET", "wh_secret_xyz"]
    for sample in [SAMPLE_SAFE_BALANCE_STATUS, SAMPLE_SAFE_NOT_CONFIGURED_STATUS,
                   SAMPLE_SAFE_EMAIL_STATUS, SAMPLE_SAFE_TOTP_STATUS]:
        sample_str = str(sample)
        for raw in raw_secrets:
            assert raw not in sample_str, (
                f"Sample response must not contain raw secret value: {raw}"
            )


# ---------------------------------------------------------------------------
# F) Sample unsafe responses: scanner must catch forbidden fields
# ---------------------------------------------------------------------------

SAMPLE_UNSAFE_WITH_API_KEY = {
    "provider": "balance",
    "configured": True,
    "api_key": "sk-live-abcdef123456",
}

SAMPLE_UNSAFE_WITH_PASSWORD = {
    "provider": "rsge",
    "configured": True,
    "password": "myP@ssw0rd!",
}

SAMPLE_UNSAFE_WITH_TOKEN = {
    "provider": "email",
    "configured": True,
    "token": "oauth-token-xyz",
}

SAMPLE_UNSAFE_WITH_ENCRYPTED_VALUE = {
    "provider": "balance",
    "configured": True,
    "encrypted_value": "gAAAAA...base64blob",
}

SAMPLE_UNSAFE_WITH_WEBHOOK_SECRET = {
    "provider": "webhook",
    "configured": True,
    "webhook_secret": "wh_secret_live_abc123",
}

SAMPLE_UNSAFE_WITH_TOTP_SECRET = {
    "provider": "totp",
    "configured": True,
    "totp_secret": "JBSWY3DPEHPK3PXP",
}

SAMPLE_UNSAFE_WITH_CLIENT_SECRET = {
    "provider": "oauth",
    "configured": True,
    "client_secret": "oauth-client-secret-abc",
}


def test_scanner_catches_api_key():
    found = _scan_forbidden_fields(SAMPLE_UNSAFE_WITH_API_KEY, FORBIDDEN_STATUS_FIELDS)
    assert "api_key" in found, "scanner must catch api_key in unsafe response"


def test_scanner_catches_password():
    found = _scan_forbidden_fields(SAMPLE_UNSAFE_WITH_PASSWORD, FORBIDDEN_STATUS_FIELDS)
    assert "password" in found, "scanner must catch password in unsafe response"


def test_scanner_catches_token():
    found = _scan_forbidden_fields(SAMPLE_UNSAFE_WITH_TOKEN, FORBIDDEN_STATUS_FIELDS)
    assert "token" in found, "scanner must catch token in unsafe response"


def test_scanner_catches_encrypted_value():
    found = _scan_forbidden_fields(SAMPLE_UNSAFE_WITH_ENCRYPTED_VALUE, FORBIDDEN_STATUS_FIELDS)
    assert "encrypted_value" in found, "scanner must catch encrypted_value in unsafe response"


def test_scanner_catches_webhook_secret():
    found = _scan_forbidden_fields(SAMPLE_UNSAFE_WITH_WEBHOOK_SECRET, FORBIDDEN_STATUS_FIELDS)
    assert "webhook_secret" in found, "scanner must catch webhook_secret in unsafe response"


def test_scanner_catches_totp_secret():
    found = _scan_forbidden_fields(SAMPLE_UNSAFE_WITH_TOTP_SECRET, FORBIDDEN_STATUS_FIELDS)
    assert "totp_secret" in found, "scanner must catch totp_secret in unsafe response"


def test_scanner_catches_client_secret():
    found = _scan_forbidden_fields(SAMPLE_UNSAFE_WITH_CLIENT_SECRET, FORBIDDEN_STATUS_FIELDS)
    assert "client_secret" in found, "scanner must catch client_secret in unsafe response"


def test_is_safe_status_response_rejects_unsafe_responses():
    assert not _is_safe_status_response(SAMPLE_UNSAFE_WITH_API_KEY)
    assert not _is_safe_status_response(SAMPLE_UNSAFE_WITH_PASSWORD)
    assert not _is_safe_status_response(SAMPLE_UNSAFE_WITH_TOKEN)
    assert not _is_safe_status_response(SAMPLE_UNSAFE_WITH_ENCRYPTED_VALUE)
    assert not _is_safe_status_response(SAMPLE_UNSAFE_WITH_WEBHOOK_SECRET)
    assert not _is_safe_status_response(SAMPLE_UNSAFE_WITH_TOTP_SECRET)
    assert not _is_safe_status_response(SAMPLE_UNSAFE_WITH_CLIENT_SECRET)


def test_is_safe_status_response_accepts_safe_responses():
    assert _is_safe_status_response(SAMPLE_SAFE_BALANCE_STATUS)
    assert _is_safe_status_response(SAMPLE_SAFE_NOT_CONFIGURED_STATUS)
    assert _is_safe_status_response(SAMPLE_SAFE_EMAIL_STATUS)
    assert _is_safe_status_response(SAMPLE_SAFE_TOTP_STATUS)


# ---------------------------------------------------------------------------
# G) Nested payload scan: scanner must catch forbidden keys in nested structures
# ---------------------------------------------------------------------------

NESTED_UNSAFE_PAYLOAD = {
    "tenant_id": "acme",
    "credentials": {
        "balance": {
            "configured": True,
            "api_key": "sk-live-nested-secret",
        },
        "email": {
            "configured": True,
            "app_password": "nested-app-password",
        },
    },
    "connectors": [
        {"name": "balance", "token": "bearer-token-nested"},
        {"name": "totp", "totp_secret": "NESTED_TOTP_SECRET"},
    ],
}

NESTED_SAFE_PAYLOAD = {
    "tenant_id": "acme",
    "credentials": {
        "balance": {
            "configured": True,
            "masked_hint": "****4321",
            "status": "active",
        },
        "email": {
            "configured": True,
            "masked_hint": "****abcd",
            "status": "active",
        },
    },
    "connectors": [
        {"name": "balance", "status": "active"},
        {"name": "totp", "configured": True},
    ],
}


def test_nested_scanner_catches_api_key_in_nested_dict():
    found = _scan_forbidden_fields(NESTED_UNSAFE_PAYLOAD, FORBIDDEN_STATUS_FIELDS)
    assert "api_key" in found, "scanner must catch api_key in nested dict"


def test_nested_scanner_catches_app_password_in_nested_dict():
    found = _scan_forbidden_fields(NESTED_UNSAFE_PAYLOAD, FORBIDDEN_STATUS_FIELDS)
    assert "app_password" in found, "scanner must catch app_password in nested dict"


def test_nested_scanner_catches_token_in_nested_list():
    found = _scan_forbidden_fields(NESTED_UNSAFE_PAYLOAD, FORBIDDEN_STATUS_FIELDS)
    assert "token" in found, "scanner must catch token in nested list"


def test_nested_scanner_catches_totp_secret_in_nested_list():
    found = _scan_forbidden_fields(NESTED_UNSAFE_PAYLOAD, FORBIDDEN_STATUS_FIELDS)
    assert "totp_secret" in found, "scanner must catch totp_secret in nested list"


def test_nested_scanner_accepts_safe_nested_payload():
    found = _scan_forbidden_fields(NESTED_SAFE_PAYLOAD, FORBIDDEN_STATUS_FIELDS)
    assert not found, f"Safe nested payload should not trigger scanner: {found}"


# ---------------------------------------------------------------------------
# H) Text source scan: docs must explicitly forbid raw fields
# ---------------------------------------------------------------------------

def test_masked_doc_explicitly_forbids_api_key_in_public_responses():
    text = _masked_doc().lower()
    assert "api_key" in text, (
        "masked-read doc must explicitly list api_key as forbidden in public responses"
    )


def test_masked_doc_explicitly_forbids_password_in_public_responses():
    text = _masked_doc().lower()
    assert "password" in text, (
        "masked-read doc must explicitly list password as forbidden in public responses"
    )


def test_masked_doc_explicitly_forbids_totp_secret_in_public_responses():
    text = _masked_doc().lower()
    assert "totp_secret" in text, (
        "masked-read doc must explicitly list totp_secret as forbidden in public responses"
    )


def test_masked_doc_explicitly_forbids_encrypted_value_in_public_responses():
    text = _masked_doc().lower()
    assert "encrypted_value" in text, (
        "masked-read doc must explicitly list encrypted_value as forbidden in public responses"
    )


def test_masked_doc_explicitly_forbids_webhook_secret_in_public_responses():
    text = _masked_doc().lower()
    assert "webhook_secret" in text, (
        "masked-read doc must explicitly list webhook_secret as forbidden in public responses"
    )


def test_interface_doc_explicitly_forbids_raw_fields_in_status():
    text = _interface_doc().lower()
    required_forbidden_in_text = [
        "api_key",
        "password",
        "token",
        "secret",
        "encrypted_value",
        "totp_secret",
        "webhook_secret",
    ]
    for field in required_forbidden_in_text:
        assert field in text, (
            f"interface contract must explicitly list '{field}' as forbidden in status responses"
        )


def test_masked_doc_explicitly_covers_all_credential_types():
    text = _masked_doc().lower()
    credential_types = [
        "balance.ge",
        "email",
        "rs.ge",
        "1c",
        "webhook",
        "totp",
    ]
    for ctype in credential_types:
        assert ctype in text, (
            f"masked-read doc must cover credential type: {ctype}"
        )


# ---------------------------------------------------------------------------
# I) Active script safety: no executable DROP TABLE IF EXISTS users
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


# ---------------------------------------------------------------------------
# J) Balance.ge safety: docs confirm inactive and gates deferred
# ---------------------------------------------------------------------------

def test_masked_doc_balance_ge_activation_requires_all_gates():
    text = _masked_doc().lower()
    gate_phrases = [
        "balance-ge-activation-gate",
        "activation gate",
        "all 12 gates",
        "all gates",
    ]
    assert any(p in text for p in gate_phrases), (
        "masked-read doc must reference Balance.ge activation gate requirement"
    )


def test_masked_doc_balance_ge_all_gates_currently_not_met():
    text = _masked_doc()
    not_met_phrases = [
        "NOT MET",
        "not met",
        "currently NOT MET",
        "All gates are currently NOT MET",
    ]
    assert any(p in text for p in not_met_phrases), (
        "masked-read doc must state that all Balance.ge activation gates are currently NOT MET"
    )
