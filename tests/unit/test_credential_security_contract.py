import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "credential-security-schema-contract.md"
MANIFEST = ROOT / "tests" / "fixtures" / "schema_manifest.json"


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def _manifest_records() -> list[dict]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("tables", [])
    return data


def test_credential_security_contract_exists_and_covers_required_objects():
    assert DOC.exists()
    text = _doc_text()
    required = [
        "tenant_secrets",
        "tenant_email_credentials",
        "tenant_balance_credentials",
        "tenant_rsge_credentials",
        "webhooks",
        "webhook_deliveries",
        "users.totp_secret",
        "password_reset_tokens",
        "connector API keys",
        "email app passwords",
        "RS.ge passwords",
        "webhook secrets",
        "TOTP secrets",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_encryption_masking_and_no_plaintext_exposure():
    text = _doc_text().lower()
    required = [
        "never expose plaintext secrets",
        "encrypted-at-rest",
        "masked reads",
        "must not return raw api keys",
        "must not return plaintext secret material",
        "do not log decrypted values",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_rotation_tenant_isolation_and_audit_metadata():
    text = _doc_text()
    required = [
        "created_at",
        "updated_at",
        "rotated_at",
        "last_used_at",
        "revoked_at",
        "is_active",
        "tenant_id",
        "unique tenant/key constraint",
        "created_by",
        "updated_by",
        "last_tested_at",
        "last_test_status",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_covers_password_reset_totp_webhook_and_connector_rules():
    text = _doc_text()
    required = [
        "hashed tokens",
        "expiry",
        "single-use",
        "TOTP secret may be shown only during initial setup",
        "TOTP secret must never be returned unmasked after setup",
        "`webhook_deliveries` must not store webhook secret values",
        "Status endpoints return configured/not_configured/demo/sandbox/dry_run/live_ready only",
        "Live connector activation is forbidden in this task",
        "Balance.ge live posting remains deferred",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_forbids_db_mutation_and_requires_additive_future_migrations():
    text = _doc_text()
    required = [
        "no production DB mutation during planning/contract tasks",
        "CREATE TABLE IF NOT EXISTS",
        "CREATE INDEX IF NOT EXISTS",
        "ADD COLUMN IF NOT EXISTS",
        "no destructive migrations",
        "no `DROP TABLE`",
        "no `TRUNCATE`",
        "Runtime DDL removal must wait",
    ]
    for phrase in required:
        assert phrase in text


def test_schema_manifest_tracks_credential_security_tables_as_risky_or_planned():
    records = {row["table_name"]: row for row in _manifest_records()}
    required_tables = [
        "tenant_secrets",
        "tenant_email_credentials",
        "tenant_balance_credentials",
        "webhooks",
        "webhook_deliveries",
        "password_reset_tokens",
        "users",
    ]
    for table in required_tables:
        assert table in records
        row = records[table]
        if table == "webhook_deliveries":
            assert row["risk"] in {"medium", "high", "critical"}
        else:
            assert row["risk"] in {"high", "critical"}
        assert row["migration_coverage"] in {"none", "partial"}
        action = row["recommended_next_action"].lower()
        assert any(token in action for token in ("credential", "security", "auth", "10e", "migration", "contract", "harden", "review"))


def test_active_scripts_do_not_execute_drop_table_users():
    scripts_dir = ROOT / "scripts"
    pattern = re.compile(r"^\s*DROP\s+TABLE\s+IF\s+EXISTS\s+users\b", re.IGNORECASE | re.MULTILINE)
    offenders = []
    for path in scripts_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        active_lines = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith(("#", "--"))
        )
        if pattern.search(active_lines):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
