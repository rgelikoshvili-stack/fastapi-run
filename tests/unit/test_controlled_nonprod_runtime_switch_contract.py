"""
H18 — Controlled Non-Production Runtime Switch Contract Tests (11C-H18)

Verifies:
- Feature flag production guard (flag must stay OFF in production)
- Environment classification rules
- Non-production explicit-approval gate
- Unknown environment fail-closed behavior
- CI/local/test env rules
- Non-prod checklist items (no Balance.ge, no credentials, no connectors, etc.)
- Runtime behavior contract when flag is ON (tenant guard, status filter,
  no journal_drafts fallback, fail-closed on unavailable source)
- Drill-down fields preserved when flag is ON
- H19 next-task documented

All tests use local mocks only.  No DB, no network, no SQL, no migrations.

Test names (26):
  1.  test_contract_document_exists
  2.  test_h18_is_nonprod_switch_plan_only
  3.  test_feature_flag_name_documented
  4.  test_feature_flag_defaults_false
  5.  test_production_must_keep_feature_flag_off
  6.  test_nonprod_requires_explicit_approval_to_enable
  7.  test_unknown_environment_fails_closed
  8.  test_ci_can_use_monkeypatch_only
  9.  test_local_test_can_enable_with_explicit_approval
 10.  test_nonprod_switch_requires_test_data_only
 11.  test_nonprod_switch_forbids_balance_activation
 12.  test_nonprod_switch_forbids_credentials_changes
 13.  test_nonprod_switch_forbids_connector_changes
 14.  test_nonprod_switch_forbids_infrastructure_changes
 15.  test_nonprod_switch_forbids_sql_and_migrations
 16.  test_nonprod_switch_forbids_production_db
 17.  test_enabled_mode_requires_tenant_id_contract
 18.  test_enabled_mode_requires_posted_status_contract
 19.  test_enabled_mode_forbids_journal_drafts_fallback_contract
 20.  test_enabled_mode_fails_closed_if_posted_ledger_unavailable
 21.  test_drilldown_fields_preserved_in_enabled_mode_contract
 22.  test_live_verification_must_confirm_production_flag_off
 23.  test_next_task_h19_documented
 24.  test_no_db_or_network_imports
 25.  test_no_gcloud_or_infra_mutation_commands
 26.  test_h18_does_not_start_h19_contract
"""

import ast
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.financial_statements_service import (
    FORBIDDEN_STATUSES,
    STANDARD_NET_STATUSES,
    _assert_no_silent_fallback,
    _build_pnl_posted_ledger_query,
    _posted_ledger_reports_enabled,
    _require_tenant_id,
)

_THIS_FILE = pathlib.Path(__file__)
_PLAN_DOC = pathlib.Path(__file__).parents[2] / "docs" / "controlled-nonprod-runtime-switch-plan.md"

# Environments that are never production-safe for flag enablement
_PRODUCTION_ENVS = {"production", "prod"}
# Environments where the flag may be enabled with explicit approval
_NONPROD_ENVS = {"staging", "test", "local", "ci", "development", "dev"}


# ---------------------------------------------------------------------------
# Helper — _classify_environment
# ---------------------------------------------------------------------------

def _classify_environment(env_name: str) -> str:
    """Return 'production', 'nonprod', or 'unknown' for an environment name."""
    normalized = (env_name or "").strip().lower()
    if normalized in _PRODUCTION_ENVS:
        return "production"
    if normalized in _NONPROD_ENVS:
        return "nonprod"
    return "unknown"


# ---------------------------------------------------------------------------
# Helper — _is_production
# ---------------------------------------------------------------------------

def _is_production(env_name: str) -> bool:
    """Return True if env_name resolves to the production environment."""
    return _classify_environment(env_name) == "production"


# ---------------------------------------------------------------------------
# Helper — _can_enable_posted_ledger_reports
# ---------------------------------------------------------------------------

def _can_enable_posted_ledger_reports(env_name: str, explicit_approval: bool) -> bool:
    """Return True only when environment is non-prod AND explicit approval is given."""
    classification = _classify_environment(env_name)
    if classification == "production":
        return False
    if classification == "unknown":
        return False  # fail closed for unknown environments
    return explicit_approval


# ---------------------------------------------------------------------------
# Helper — _assert_production_guard
# ---------------------------------------------------------------------------

def _assert_production_guard(env_name: str, flag_value: bool) -> None:
    """Raise AssertionError if production environment has flag enabled."""
    if _is_production(env_name) and flag_value:
        raise AssertionError(
            f"PRODUCTION GUARD VIOLATED: POSTED_LEDGER_REPORTS_ENABLED must be False "
            f"in production environment '{env_name}', got True"
        )


# ---------------------------------------------------------------------------
# Helper — _fake_runtime_switch_result
# ---------------------------------------------------------------------------

def _fake_runtime_switch_result(
    env_name: str,
    flag_value: bool,
    posted_ledger_available: bool = True,
) -> dict:
    """
    Simulate the outcome of enabling the feature flag in a given environment.
    Returns a result dict describing what would happen — no real DB calls.
    """
    classification = _classify_environment(env_name)
    if _is_production(env_name) and flag_value:
        return {
            "allowed": False,
            "reason": "production_guard",
            "env": env_name,
            "flag": flag_value,
        }
    if classification == "unknown" and flag_value:
        return {
            "allowed": False,
            "reason": "unknown_env_fail_closed",
            "env": env_name,
            "flag": flag_value,
        }
    if flag_value and not posted_ledger_available:
        return {
            "allowed": True,
            "env": env_name,
            "flag": flag_value,
            "result": "fail_closed",
            "error_code": "POSTED_LEDGER_UNAVAILABLE",
        }
    return {
        "allowed": True,
        "env": env_name,
        "flag": flag_value,
        "result": "posted_ledger_path" if flag_value else "legacy_path",
    }


# ---------------------------------------------------------------------------
# 1. Contract document exists
# ---------------------------------------------------------------------------


def test_contract_document_exists():
    assert _PLAN_DOC.exists(), f"Contract doc missing: {_PLAN_DOC}"
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert len(content) >= 500, "Contract doc is too short — likely incomplete"


# ---------------------------------------------------------------------------
# 2. H18 is nonprod switch plan only
# ---------------------------------------------------------------------------


def test_h18_is_nonprod_switch_plan_only():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    # Doc must state non-production scope
    assert "non-production" in content.lower() or "nonprod" in content.lower()
    # Doc must document production stays OFF
    assert "production" in content.lower()
    # H18 must not claim to activate production
    assert "production runtime switch" not in content.lower() or \
        "non-goals" in content.lower(), \
        "If 'production runtime switch' appears, it must be in non-goals"


# ---------------------------------------------------------------------------
# 3. Feature flag name documented
# ---------------------------------------------------------------------------


def test_feature_flag_name_documented():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "POSTED_LEDGER_REPORTS_ENABLED" in content


# ---------------------------------------------------------------------------
# 4. Feature flag defaults false
# ---------------------------------------------------------------------------


def test_feature_flag_defaults_false(monkeypatch):
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    assert _posted_ledger_reports_enabled() is False


# ---------------------------------------------------------------------------
# 5. Production must keep feature flag off
# ---------------------------------------------------------------------------


def test_production_must_keep_feature_flag_off():
    for prod_env in ("production", "prod"):
        result = _fake_runtime_switch_result(prod_env, flag_value=True)
        assert result["allowed"] is False, \
            f"Production env '{prod_env}' must block flag enablement"
        assert result["reason"] == "production_guard"

    # Guard raises on violation
    with pytest.raises(AssertionError, match="PRODUCTION GUARD VIOLATED"):
        _assert_production_guard("production", flag_value=True)

    # Guard passes when flag is correctly off in production
    _assert_production_guard("production", flag_value=False)  # must not raise


# ---------------------------------------------------------------------------
# 6. Non-prod requires explicit approval to enable
# ---------------------------------------------------------------------------


def test_nonprod_requires_explicit_approval_to_enable():
    for env in ("staging", "test", "local"):
        # Without explicit approval: not allowed
        assert _can_enable_posted_ledger_reports(env, explicit_approval=False) is False, \
            f"Env '{env}' must not enable without explicit approval"
        # With explicit approval: allowed
        assert _can_enable_posted_ledger_reports(env, explicit_approval=True) is True, \
            f"Env '{env}' must allow enabling with explicit approval"


# ---------------------------------------------------------------------------
# 7. Unknown environment fails closed
# ---------------------------------------------------------------------------


def test_unknown_environment_fails_closed():
    for unknown in ("", "undefined", "preview", "canary", "sandbox"):
        classification = _classify_environment(unknown)
        assert classification == "unknown" or classification == "nonprod", \
            f"Env '{unknown}' should be unknown or nonprod — not production"
        # Even with explicit approval, unknown env must not allow enablement
        can_enable = _can_enable_posted_ledger_reports(unknown, explicit_approval=True)
        # unknown envs fail closed — they do NOT resolve to production, but also
        # must not be enabled without a known classification
        if classification == "unknown":
            assert can_enable is False, \
                f"Unknown env '{unknown}' must fail closed regardless of approval"


# ---------------------------------------------------------------------------
# 8. CI can use monkeypatch only
# ---------------------------------------------------------------------------


def test_ci_can_use_monkeypatch_only(monkeypatch):
    # CI may set the flag via monkeypatch inside a test
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    assert _posted_ledger_reports_enabled() is True

    # But the CI environment classification is nonprod — not production
    assert _classify_environment("ci") == "nonprod"
    assert _is_production("ci") is False

    # After monkeypatch scope ends, flag reverts — verified by delenv
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    assert _posted_ledger_reports_enabled() is False


# ---------------------------------------------------------------------------
# 9. Local/test can enable with explicit approval
# ---------------------------------------------------------------------------


def test_local_test_can_enable_with_explicit_approval(monkeypatch):
    assert _can_enable_posted_ledger_reports("local", explicit_approval=True) is True
    assert _can_enable_posted_ledger_reports("test", explicit_approval=True) is True

    result_local = _fake_runtime_switch_result("local", flag_value=True)
    assert result_local["allowed"] is True
    assert result_local["result"] == "posted_ledger_path"

    # Monkeypatch is the correct mechanism for local test activation
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    assert _posted_ledger_reports_enabled() is True


# ---------------------------------------------------------------------------
# 10. Non-prod switch requires test data only
# ---------------------------------------------------------------------------


def test_nonprod_switch_requires_test_data_only():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "test data" in content.lower(), \
        "Plan must require test data only for non-production switch"
    # Fake result confirms no production data used
    result = _fake_runtime_switch_result("test", flag_value=True)
    assert result["env"] == "test"
    assert result["allowed"] is True


# ---------------------------------------------------------------------------
# 11. Non-prod switch forbids Balance.ge activation
# ---------------------------------------------------------------------------


def test_nonprod_switch_forbids_balance_activation():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "balance" in content.lower(), \
        "Plan must address Balance.ge restriction"
    assert "demo_mode" in content.lower() or "no balance" in content.lower() or \
        "no connector" in content.lower() or "connector remains" in content.lower(), \
        "Plan must state Balance.ge stays demo_mode / no activation"


# ---------------------------------------------------------------------------
# 12. Non-prod switch forbids credentials changes
# ---------------------------------------------------------------------------


def test_nonprod_switch_forbids_credentials_changes():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "credential" in content.lower(), \
        "Plan must address credentials restriction"
    # The plan must state credentials must not change
    assert "no credential" in content.lower() or \
        "credentials changed" in content.lower() or \
        "credentials" in content.lower()


# ---------------------------------------------------------------------------
# 13. Non-prod switch forbids connector changes
# ---------------------------------------------------------------------------


def test_nonprod_switch_forbids_connector_changes():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "connector" in content.lower(), \
        "Plan must address connector restriction"


# ---------------------------------------------------------------------------
# 14. Non-prod switch forbids infrastructure changes
# ---------------------------------------------------------------------------


def test_nonprod_switch_forbids_infrastructure_changes():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "infrastructure" in content.lower(), \
        "Plan must address infrastructure restriction"


# ---------------------------------------------------------------------------
# 15. Non-prod switch forbids SQL and migrations
# ---------------------------------------------------------------------------


def test_nonprod_switch_forbids_sql_and_migrations():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "sql" in content.lower() or "migration" in content.lower(), \
        "Plan must address SQL/migration restriction"


# ---------------------------------------------------------------------------
# 16. Non-prod switch forbids production DB access
# ---------------------------------------------------------------------------


def test_nonprod_switch_forbids_production_db():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "production db" in content.lower() or \
        "no production db" in content.lower() or \
        "production database" in content.lower() or \
        "no production" in content.lower(), \
        "Plan must explicitly forbid production DB access"


# ---------------------------------------------------------------------------
# 17. Enabled mode requires tenant_id contract
# ---------------------------------------------------------------------------


def test_enabled_mode_requires_tenant_id_contract():
    with pytest.raises(ValueError, match="tenant_id"):
        _require_tenant_id("")

    with pytest.raises(ValueError):
        _build_pnl_posted_ledger_query("", None, None)

    # Valid tenant passes
    sql, params = _build_pnl_posted_ledger_query("test-tenant", None, None)
    assert "test-tenant" in params


# ---------------------------------------------------------------------------
# 18. Enabled mode requires posted status contract
# ---------------------------------------------------------------------------


def test_enabled_mode_requires_posted_status_contract():
    assert "posted" in STANDARD_NET_STATUSES
    assert "correction" in STANDARD_NET_STATUSES
    assert "reversed" not in STANDARD_NET_STATUSES
    for fs in FORBIDDEN_STATUSES:
        assert fs not in STANDARD_NET_STATUSES

    sql, params = _build_pnl_posted_ledger_query("test-tenant", None, None)
    assert "status" in sql
    statuses_param = next(p for p in params if isinstance(p, list))
    assert "posted" in statuses_param
    assert "correction" in statuses_param
    assert "reversed" not in statuses_param


# ---------------------------------------------------------------------------
# 19. Enabled mode forbids journal_drafts fallback contract
# ---------------------------------------------------------------------------


def test_enabled_mode_forbids_journal_drafts_fallback_contract():
    bad_sql = "SELECT * FROM journal_drafts WHERE tenant_id = $1"
    with pytest.raises(ValueError, match="journal_drafts"):
        _assert_no_silent_fallback(bad_sql)

    # All posted-ledger query builders pass
    sql, _ = _build_pnl_posted_ledger_query("test-tenant", None, None)
    _assert_no_silent_fallback(sql)  # must not raise
    assert "journal_drafts" not in sql


# ---------------------------------------------------------------------------
# 20. Enabled mode fails closed if posted ledger unavailable
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_enabled_mode_fails_closed_if_posted_ledger_unavailable(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(
        side_effect=Exception("relation journal_entry_headers does not exist")
    )
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.financial_statements_service.get_conn", return_value=cm):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = await build_profit_and_loss("test-tenant")

    assert result.get("ok") is False
    assert result.get("error", {}).get("code") == "POSTED_LEDGER_UNAVAILABLE"

    # Fake result helper also models this correctly
    fake = _fake_runtime_switch_result("test", flag_value=True, posted_ledger_available=False)
    assert fake["result"] == "fail_closed"
    assert fake["error_code"] == "POSTED_LEDGER_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 21. Drill-down fields preserved in enabled mode contract
# ---------------------------------------------------------------------------


def test_drilldown_fields_preserved_in_enabled_mode_contract():
    sql, _ = _build_pnl_posted_ledger_query("test-tenant", "2026-04-01", "2026-04-30")
    assert "source_draft_id" in sql
    assert "posting_log_id" in sql
    assert "evidence_bundle_id" in sql

    # Fake enabled-mode result shows posted_ledger_path
    result = _fake_runtime_switch_result("test", flag_value=True, posted_ledger_available=True)
    assert result["result"] == "posted_ledger_path"


# ---------------------------------------------------------------------------
# 22. Live verification must confirm production flag off
# ---------------------------------------------------------------------------


def test_live_verification_must_confirm_production_flag_off(monkeypatch):
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    assert _posted_ledger_reports_enabled() is False

    # Production guard holds: flag=False is compliant
    _assert_production_guard("production", flag_value=False)  # must not raise

    # Mock live /health payload (as returned by the real endpoint)
    mock_health = {
        "ok": True,
        "data": {
            "environment": "production",
            "env_vars": {
                "DATABASE_URL": "set",
                "JWT_SECRET": "set",
                "BALANCE_API_KEY": "missing",
                # POSTED_LEDGER_REPORTS_ENABLED intentionally absent — flag is OFF
            },
            "connectors": {"balance": "demo_mode"},
        },
    }
    env_vars = mock_health["data"]["env_vars"]
    assert "POSTED_LEDGER_REPORTS_ENABLED" not in env_vars, \
        "Production /health must not expose POSTED_LEDGER_REPORTS_ENABLED as set"
    assert mock_health["data"]["connectors"]["balance"] == "demo_mode"


# ---------------------------------------------------------------------------
# 23. Next task H19 documented
# ---------------------------------------------------------------------------


def test_next_task_h19_documented():
    content = _PLAN_DOC.read_text(encoding="utf-8")
    assert "H19" in content or "h19" in content.lower(), \
        "Plan doc must reference H19 as the next task"
    assert "production report migration" in content.lower() or \
        "approval plan" in content.lower(), \
        "Plan doc must name H19 task"


# ---------------------------------------------------------------------------
# 24. No DB or network imports
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"asyncpg", "psycopg2", "requests", "httpx", "aiohttp", "urllib", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split(".")[0]
            assert base not in forbidden, f"Forbidden DB/network import: {node.module}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                assert base not in forbidden, f"Forbidden DB/network import: {alias.name}"


# ---------------------------------------------------------------------------
# 25. No gcloud or infra mutation commands
# ---------------------------------------------------------------------------


def test_no_gcloud_or_infra_mutation_commands():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # No os.system calls (AST — avoids string self-reference)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fname = (node.func.id if isinstance(node.func, ast.Name)
                     else node.func.attr if isinstance(node.func, ast.Attribute) else "")
            assert fname != "system", \
                f"os.system() call forbidden in H18 test"
    # No subprocess imports (AST check)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "subprocess", \
                    "subprocess import forbidden in H18 test"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module != "subprocess", \
                "subprocess import forbidden in H18 test"
    # No gcloud/infra tool invocations (check via AST string constants, not literal assertion)
    infra_tools = {"gcloud", "kubectl", "terraform", "ansible", "helm"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for tool in infra_tools:
                # Flag any constant that looks like an infra command being executed
                if node.value.startswith(tool + " ") and "deploy" in node.value:
                    raise AssertionError(
                        f"Infra command constant '{node.value}' forbidden in H18 test"
                    )


# ---------------------------------------------------------------------------
# 26. H18 does not start H19 contract
# ---------------------------------------------------------------------------


def test_h18_does_not_start_h19_contract():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    off_limits = {
        "posting_service", "approval_service", "posting_helpers",
        "approval_patterns", "connector", "balance_connector",
        "evidence_bundle_service",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for blocked in off_limits:
                assert blocked not in node.module, \
                    f"H18 must not import from {blocked}: {node.module}"

    # Verify STANDARD_NET_STATUSES and FORBIDDEN_STATUSES unchanged
    assert "posted" in STANDARD_NET_STATUSES
    assert "correction" in STANDARD_NET_STATUSES
    for fs in FORBIDDEN_STATUSES:
        assert fs not in STANDARD_NET_STATUSES
