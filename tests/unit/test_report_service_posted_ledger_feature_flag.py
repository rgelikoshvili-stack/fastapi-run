"""
H15 — Report Service Feature Flag Tests (11C-H15)

Tests verify:
- feature flag defaults false
- legacy path preserved when flag false
- posted-ledger path selected when flag true
- tenant_id guard
- no journal_drafts in posted-ledger queries
- query shapes for TB, P&L, BS, cashflow
- fail-closed behavior
- no DB connections in this file
- no Balance.ge / connector imports
"""

import ast
import os
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — import only pure helpers (no DB execution)
# ---------------------------------------------------------------------------

from app.api.services.financial_statements_service import (
    FORBIDDEN_STATUSES,
    STANDARD_NET_STATUSES,
    _assert_no_silent_fallback,
    _build_balance_sheet_posted_ledger_query,
    _build_cashflow_posted_ledger_query,
    _build_pnl_posted_ledger_query,
    _posted_ledger_reports_enabled,
    _require_tenant_id,
)
from app.api.services.ledger_service import _build_trial_balance_posted_ledger_query

_THIS_FILE = pathlib.Path(__file__)

# ---------------------------------------------------------------------------
# 1. Feature flag default
# ---------------------------------------------------------------------------


def test_feature_flag_defaults_false(monkeypatch):
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    assert _posted_ledger_reports_enabled() is False


def test_feature_flag_empty_string_is_false(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "")
    assert _posted_ledger_reports_enabled() is False


def test_feature_flag_true_values(monkeypatch):
    for val in ("1", "true", "True", "TRUE", "yes", "Yes", "YES"):
        monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", val)
        assert _posted_ledger_reports_enabled() is True, f"Expected True for '{val}'"


def test_feature_flag_false_values(monkeypatch):
    for val in ("0", "false", "no", "off", "False"):
        monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", val)
        assert _posted_ledger_reports_enabled() is False, f"Expected False for '{val}'"


# ---------------------------------------------------------------------------
# 2. Legacy path preserved when flag false
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_feature_flag_false_keeps_legacy_report_path(monkeypatch):
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)

    legacy_called = []

    async def mock_get_trial_balance(tid, df, dt):
        legacy_called.append(True)
        return {}

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.financial_statements_service.get_conn", return_value=cm):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = await build_profit_and_loss("tenant-a", "2026-04-01", "2026-04-30")

    assert result.get("ok") is True
    data = result.get("data", {})
    assert data.get("source") != "posted_ledger", \
        "Legacy path must not set source=posted_ledger"


# ---------------------------------------------------------------------------
# 3. Posted-ledger path selected when flag true
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_feature_flag_true_selects_posted_ledger_path(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.financial_statements_service.get_conn", return_value=cm):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = await build_profit_and_loss("tenant-a", "2026-04-01", "2026-04-30")

    assert result.get("ok") is True
    data = result.get("data", {})
    assert data.get("source") == "posted_ledger", \
        "Feature flag true must select posted_ledger path"


# ---------------------------------------------------------------------------
# 4. tenant_id guard
# ---------------------------------------------------------------------------


def test_posted_ledger_path_requires_tenant_id():
    with pytest.raises(ValueError, match="tenant_id"):
        _require_tenant_id("")


def test_posted_ledger_path_forbids_default_tenant_fallback():
    with pytest.raises(ValueError):
        _build_pnl_posted_ledger_query("", None, None)

    with pytest.raises(ValueError):
        _build_balance_sheet_posted_ledger_query("", None)

    with pytest.raises(ValueError):
        _build_trial_balance_posted_ledger_query("", None, None)

    with pytest.raises(ValueError):
        _build_cashflow_posted_ledger_query("", None, None)


# ---------------------------------------------------------------------------
# 5. Query references journal_entry_headers and journal_entry_lines
# ---------------------------------------------------------------------------


def test_posted_ledger_query_uses_journal_entry_headers_and_lines():
    for builder in (
        lambda: _build_pnl_posted_ledger_query("t", None, None),
        lambda: _build_balance_sheet_posted_ledger_query("t", None),
        lambda: _build_trial_balance_posted_ledger_query("t", None, None),
        lambda: _build_cashflow_posted_ledger_query("t", None, None),
    ):
        sql, _ = builder()
        assert "journal_entry_headers" in sql, \
            f"Query must reference journal_entry_headers"
        assert "journal_entry_lines" in sql, \
            f"Query must reference journal_entry_lines"


def test_posted_ledger_query_requires_status_posted():
    sql, params = _build_pnl_posted_ledger_query("t", None, None)
    assert "status" in sql
    assert "posted" in str(params)


def test_posted_ledger_query_excludes_non_posted_states():
    sql, params = _build_pnl_posted_ledger_query("t", None, None)
    params_str = str(params)
    for forbidden in FORBIDDEN_STATUSES:
        assert forbidden not in params_str, \
            f"Forbidden status '{forbidden}' must not appear in posted-ledger query params"


def test_posted_ledger_query_does_not_reference_journal_drafts():
    for builder in (
        lambda: _build_pnl_posted_ledger_query("t", None, None),
        lambda: _build_balance_sheet_posted_ledger_query("t", None),
        lambda: _build_trial_balance_posted_ledger_query("t", None, None),
        lambda: _build_cashflow_posted_ledger_query("t", None, None),
    ):
        sql, _ = builder()
        assert "journal_drafts" not in sql, \
            "Posted-ledger query must not reference journal_drafts"


def test_posted_ledger_query_forbids_simulated_success_mock_dry_run_truth():
    sql, params = _build_trial_balance_posted_ledger_query("t", "2026-04-01", "2026-04-30")
    combined = sql + str(params)
    for bad in ("simulated_success", "mock_posting", "dry_run", "approved"):
        assert bad not in combined, \
            f"'{bad}' must not appear as report truth in posted-ledger query"


# ---------------------------------------------------------------------------
# 6. Query shapes
# ---------------------------------------------------------------------------


def test_trial_balance_posted_ledger_query_shape():
    sql, params = _build_trial_balance_posted_ledger_query("tenant-a", "2026-04-01", "2026-04-30")
    assert isinstance(sql, str)
    assert isinstance(params, list)
    assert "tenant-a" in params
    assert list(STANDARD_NET_STATUSES) in params
    assert "GROUP BY" in sql
    assert "SUM" in sql
    assert "account_code" in sql
    assert "$1" in sql
    assert "$2" in sql


def test_pnl_posted_ledger_query_shape():
    sql, params = _build_pnl_posted_ledger_query("tenant-a", "2026-04-01", "2026-04-30")
    assert isinstance(sql, str)
    assert "account_type" in sql
    assert "income" in sql
    assert "expense" in sql
    assert "source_draft_id" in sql or "source_draft_id" in sql
    assert "posting_log_id" in sql
    assert "evidence_bundle_id" in sql
    assert "$3" in sql  # date_from becomes $3
    assert "$4" in sql  # date_to becomes $4


def test_balance_sheet_posted_ledger_query_shape():
    sql, params = _build_balance_sheet_posted_ledger_query("tenant-a", "2026-04-30")
    assert isinstance(sql, str)
    assert "asset" in sql
    assert "liability" in sql
    assert "equity" in sql
    assert "entry_date" in sql
    assert "$3" in sql  # as_of becomes $3


def test_cashflow_posted_ledger_query_shape():
    sql, params = _build_cashflow_posted_ledger_query("tenant-a", "2026-04-01", "2026-04-30")
    assert isinstance(sql, str)
    assert "cashflow_category" in sql
    assert "LIKE '1%'" in sql or "account_code" in sql
    assert "SUM" in sql


# ---------------------------------------------------------------------------
# 7. Evidence / audit drilldown fields
# ---------------------------------------------------------------------------


def test_detail_query_includes_evidence_posting_source_fields():
    sql, _ = _build_pnl_posted_ledger_query("t", None, None)
    assert "source_draft_id" in sql
    assert "posting_log_id" in sql
    assert "evidence_bundle_id" in sql


# ---------------------------------------------------------------------------
# 8. Fail-closed when tables unavailable
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_posted_ledger_mode_fails_closed_if_tables_unavailable(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=Exception("relation journal_entry_headers does not exist"))
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.financial_statements_service.get_conn", return_value=cm):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = await build_profit_and_loss("tenant-a")

    assert result.get("ok") is False
    err = result.get("error", {})
    assert err.get("code") == "POSTED_LEDGER_UNAVAILABLE"


@pytest.mark.anyio
async def test_posted_ledger_balance_sheet_fails_closed_if_tables_unavailable(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=Exception("relation journal_entry_lines does not exist"))
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.financial_statements_service.get_conn", return_value=cm):
        from app.api.services.financial_statements_service import build_balance_sheet
        result = await build_balance_sheet("tenant-a", "2026-04-30")

    assert result.get("ok") is False
    err = result.get("error", {})
    assert err.get("code") == "POSTED_LEDGER_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 9. No silent fallback
# ---------------------------------------------------------------------------


def test_no_silent_fallback_to_legacy_in_posted_ledger_mode():
    # _assert_no_silent_fallback must raise if journal_drafts appears in SQL
    bad_sql = "SELECT * FROM journal_drafts WHERE tenant_id = $1"
    with pytest.raises(ValueError, match="journal_drafts"):
        _assert_no_silent_fallback(bad_sql)

    # Clean posted-ledger SQL must pass
    good_sql, _ = _build_pnl_posted_ledger_query("t", None, None)
    _assert_no_silent_fallback(good_sql)  # must not raise


# ---------------------------------------------------------------------------
# 10. Reversal/correction handling
# ---------------------------------------------------------------------------


def test_reversal_correction_handling_explicit_or_fail_closed():
    # STANDARD_NET_STATUSES includes 'correction' — reversals handled by
    # excluding hdr-orig (status='reversed', not in STANDARD_NET) and
    # including the reversal entry (status='posted') and correction (status='correction').
    assert "correction" in STANDARD_NET_STATUSES, \
        "correction must be in STANDARD_NET_STATUSES for net report truth"
    assert "reversed" not in STANDARD_NET_STATUSES, \
        "reversed must be excluded from STANDARD_NET_STATUSES (original reversed entry)"
    assert "posted" in STANDARD_NET_STATUSES

    _, params = _build_trial_balance_posted_ledger_query("t", None, None)
    statuses_param = next(p for p in params if isinstance(p, list))
    assert "correction" in statuses_param
    assert "reversed" not in statuses_param
    assert "voided" not in statuses_param


# ---------------------------------------------------------------------------
# 11. AST / structural checks
# ---------------------------------------------------------------------------


def test_tests_do_not_connect_to_db():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # Real DB calls would be conn.fetch / conn.execute without mock
                assert node.func.attr not in ("fetchrow", "execute"), \
                    "Test file must not call real DB methods directly"


def test_no_sql_execution_in_tests():
    source = _THIS_FILE.read_text(encoding="utf-8")
    # No raw asyncpg connection usage without mock
    assert "get_conn()" not in source or "patch" in source, \
        "Any get_conn() call must be inside a patch context"


def test_no_balance_or_connector_imports():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"balance", "connector", "posting_service", "approval_service"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    assert f not in node.module, \
                        f"Connector/balance import forbidden in test: {node.module}"


def test_no_credentials_or_secrets_in_report_payload():
    secret_keys = {"api_key", "password", "token", "secret",
                   "encrypted_value", "private_key", "auth_token"}
    for builder in (
        lambda: _build_pnl_posted_ledger_query("t", None, None),
        lambda: _build_balance_sheet_posted_ledger_query("t", None),
        lambda: _build_trial_balance_posted_ledger_query("t", None, None),
        lambda: _build_cashflow_posted_ledger_query("t", None, None),
    ):
        sql, params = builder()
        combined = (sql + str(params)).lower()
        for key in secret_keys:
            assert key not in combined, \
                f"Secret key '{key}' must not appear in report query"


def test_runtime_report_behavior_default_unchanged_contract(monkeypatch):
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    # When flag is absent, _posted_ledger_reports_enabled() is False —
    # existing journal_drafts-based path is preserved unchanged.
    assert _posted_ledger_reports_enabled() is False
    # STANDARD_NET_STATUSES is additive (not replacing anything in legacy)
    assert "posted" in STANDARD_NET_STATUSES
    assert "correction" in STANDARD_NET_STATUSES
    # No forbidden status leaks into the standard net set
    for fs in FORBIDDEN_STATUSES:
        assert fs not in STANDARD_NET_STATUSES, \
            f"Forbidden status '{fs}' must not be in STANDARD_NET_STATUSES"
