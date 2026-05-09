import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "auth-tenant-schema-contract.md"
MANIFEST = ROOT / "tests" / "fixtures" / "schema_manifest.json"


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def _manifest_records() -> list[dict]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("tables", [])
    return data


def test_auth_tenant_contract_exists_and_covers_required_objects():
    assert DOC.exists()
    text = _doc_text()
    required = [
        "users",
        "tenants",
        "tenant_settings",
        "password_reset_tokens",
        "user roles",
        "user permissions",
        "tenant membership",
        "TOTP",
        "users.totp_secret",
        "trial_ends_at",
        "subscription",
        "audit and security metadata",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_tenant_isolation():
    text = _doc_text()
    required = [
        "Tenant isolation is a hard boundary",
        "Tenant-owned tables must include `tenant_id`",
        "All tenant-scoped queries must filter by `tenant_id`",
        "Cross-tenant access must be forbidden by default",
        "Global or admin-only tables must be explicitly documented as global",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_safe_auth_password_reset_and_totp():
    text = _doc_text()
    required = [
        "Password hashes must never be exposed",
        "`password_reset_tokens` must use hashed, expiring, single-use tokens",
        "token hash, not raw token",
        "TOTP fields such as `users.totp_secret` must be protected or encrypted at rest",
        "TOTP secret must never be returned unmasked after setup",
        "Disabled, suspended, locked, or deleted users must not authenticate",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_rbac_permissions_and_audited_admin_actions():
    text = _doc_text()
    required = [
        "Role and permission behavior must be explicit",
        "Approval actions must require approval permissions",
        "Posting actions must require posting permissions",
        "Reporting actions must require reporting permissions",
        "Admin, tenant, security, credential, and billing actions must require elevated permissions",
        "Least privilege must be the default",
        "Admin actions must be audited",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_tenant_lifecycle_and_subscription_enforcement():
    text = _doc_text()
    required = [
        "`active`",
        "`trial`",
        "`suspended`",
        "`expired`",
        "`inactive`",
        "`trial_ends_at` and subscription state must be enforced before commercial pilot",
        "Suspended or expired tenants must not execute mutating accounting actions",
        "Suspended or expired tenants must not execute connector actions",
        "Read-only access policy for suspended or expired tenants must be explicit",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_audit_metadata_rate_limits_and_secret_non_exposure():
    text = _doc_text()
    required = [
        "Auth and security-sensitive events must be auditable",
        "failed login",
        "password reset request",
        "TOTP setup",
        "role changes",
        "tenant status changes",
        "subscription or trial changes",
        "actor",
        "tenant",
        "timestamp",
        "Login, reset, token refresh, TOTP, and credential-adjacent endpoints must be rate limited",
        "API responses must not return",
        "password hashes",
        "reset tokens",
        "TOTP secrets",
        "raw credentials",
        "connector secrets",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_forbids_destructive_migrations_db_mutation_and_balance_activation():
    text = _doc_text()
    required = [
        "no destructive migrations",
        "no `DROP TABLE`",
        "no `TRUNCATE`",
        "no destructive `ALTER`",
        "no production DB mutation during planning/contract tasks",
        "Runtime DDL removal must wait",
        "Balance.ge live activation is still deferred",
        "Production database is not touched by this task",
    ]
    for phrase in required:
        assert phrase in text


def test_schema_manifest_tracks_key_auth_tenant_tables_as_risky_or_planned():
    records = {row["table_name"]: row for row in _manifest_records()}
    required_tables = [
        "users",
        "tenants",
        "tenant_settings",
        "password_reset_tokens",
        "tenant_secrets",
    ]
    for table in required_tables:
        assert table in records
        row = records[table]
        assert row["migration_coverage"] in {"none", "partial"}
        if table in {"users", "tenants", "password_reset_tokens", "tenant_secrets"}:
            assert row["risk"] in {"high", "critical"}
        else:
            assert row["risk"] in {"medium", "high", "critical"}
        action = row["recommended_next_action"].lower()
        assert any(
            token in action
            for token in (
                "auth",
                "tenant",
                "password",
                "token",
                "credential",
                "security",
                "migration",
                "contract",
                "canonical",
                "review",
            )
        )


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
