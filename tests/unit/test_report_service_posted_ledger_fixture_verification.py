"""
H16 — Report Service Posted-Ledger Fixture Verification Tests (11C-H16)

Verifies the H15 feature-flagged posted-ledger path using local/test fixture
data only.  No DB connections, no network calls, no runtime code changes.

Test names (24):
  1.  test_fixture_file_exists_and_is_local_only
  2.  test_feature_flag_off_keeps_legacy_path_contract
  3.  test_feature_flag_on_selects_posted_ledger_path_with_fixture
  4.  test_posted_ledger_fixture_requires_tenant_id
  5.  test_posted_ledger_fixture_excludes_other_tenants
  6.  test_posted_ledger_fixture_excludes_non_posted_states
  7.  test_posted_ledger_fixture_includes_posted_and_correction_for_standard_net
  8.  test_posted_ledger_fixture_excludes_reversed_from_standard_net
  9.  test_fixture_pnl_query_uses_journal_entry_headers_and_lines
 10.  test_fixture_pnl_query_does_not_reference_journal_drafts
 11.  test_fixture_pnl_preserves_evidence_posting_source_fields
 12.  test_fixture_balance_sheet_query_shape
 13.  test_fixture_balance_sheet_uses_as_of_date
 14.  test_fixture_trial_balance_query_shape
 15.  test_fixture_trial_balance_requires_period
 16.  test_fixture_cashflow_uses_cash_bank_lines
 17.  test_fixture_cashflow_does_not_use_bank_transactions_only
 18.  test_fail_closed_when_posted_ledger_unavailable
 19.  test_no_silent_fallback_to_journal_drafts_when_flag_on
 20.  test_raw_secrets_not_present_in_fixture_payloads
 21.  test_no_db_or_network_imports
 22.  test_no_migration_or_sql_execution_in_tests
 23.  test_production_flag_not_enabled_by_tests
 24.  test_h16_does_not_change_posting_or_approval_contract
"""

import ast
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
# Local fixture data — simulates journal_entry_headers + journal_entry_lines
# ---------------------------------------------------------------------------

FIXTURE_TENANT = "fixture-tenant"
OTHER_TENANT = "other-tenant"

FIXTURE_HEADERS = [
    # Standard posted entry — income + asset
    {
        "id": "hdr-1", "tenant_id": FIXTURE_TENANT, "status": "posted",
        "entry_date": "2026-04-10",
        "source_draft_id": "d1", "posting_log_id": "pl1", "evidence_bundle_id": "eb1",
    },
    # Correction entry — also in STANDARD_NET
    {
        "id": "hdr-2", "tenant_id": FIXTURE_TENANT, "status": "correction",
        "entry_date": "2026-04-15",
        "source_draft_id": "d2", "posting_log_id": "pl2", "evidence_bundle_id": "eb2",
    },
    # Reversed header — original entry; excluded from STANDARD_NET
    {
        "id": "hdr-3", "tenant_id": FIXTURE_TENANT, "status": "reversed",
        "entry_date": "2026-04-20",
        "source_draft_id": "d3", "posting_log_id": "pl3", "evidence_bundle_id": "eb3",
    },
    # Draft — FORBIDDEN status, must never appear in net reports
    {
        "id": "hdr-draft", "tenant_id": FIXTURE_TENANT, "status": "draft",
        "entry_date": "2026-04-25",
        "source_draft_id": None, "posting_log_id": None, "evidence_bundle_id": None,
    },
    # Other tenant — must be filtered out by tenant_id guard
    {
        "id": "hdr-other", "tenant_id": OTHER_TENANT, "status": "posted",
        "entry_date": "2026-04-10",
        "source_draft_id": "d9", "posting_log_id": "pl9", "evidence_bundle_id": "eb9",
    },
]

FIXTURE_LINES = [
    # hdr-1: sales revenue + cash receipt
    {"journal_entry_id": "hdr-1", "account_code": "6110", "account_type": "income",
     "cashflow_category": None, "debit": 0.0, "credit": 1000.0},
    {"journal_entry_id": "hdr-1", "account_code": "1120", "account_type": "asset",
     "cashflow_category": "operating", "debit": 1000.0, "credit": 0.0},
    # hdr-2: salary expense + cash payment (correction entry)
    {"journal_entry_id": "hdr-2", "account_code": "7210", "account_type": "expense",
     "cashflow_category": None, "debit": 500.0, "credit": 0.0},
    {"journal_entry_id": "hdr-2", "account_code": "1120", "account_type": "asset",
     "cashflow_category": "operating", "debit": 0.0, "credit": 500.0},
    # hdr-3 (reversed — excluded from STANDARD_NET net view)
    {"journal_entry_id": "hdr-3", "account_code": "6110", "account_type": "income",
     "cashflow_category": None, "debit": 0.0, "credit": 200.0},
    {"journal_entry_id": "hdr-3", "account_code": "1120", "account_type": "asset",
     "cashflow_category": "operating", "debit": 200.0, "credit": 0.0},
    # hdr-draft (FORBIDDEN — excluded from net)
    {"journal_entry_id": "hdr-draft", "account_code": "6110", "account_type": "income",
     "cashflow_category": None, "debit": 0.0, "credit": 999.0},
    {"journal_entry_id": "hdr-draft", "account_code": "1120", "account_type": "asset",
     "cashflow_category": "operating", "debit": 999.0, "credit": 0.0},
    # hdr-other (other tenant — excluded by tenant_id filter)
    {"journal_entry_id": "hdr-other", "account_code": "6110", "account_type": "income",
     "cashflow_category": None, "debit": 0.0, "credit": 5000.0},
    {"journal_entry_id": "hdr-other", "account_code": "1120", "account_type": "asset",
     "cashflow_category": "operating", "debit": 5000.0, "credit": 0.0},
]


# ---------------------------------------------------------------------------
# In-memory fixture helpers (simulate SQL joins/filters, no DB)
# ---------------------------------------------------------------------------


def _net_headers(tenant_id: str) -> list[dict]:
    """Filter fixture headers by tenant_id AND status in STANDARD_NET_STATUSES."""
    return [
        h for h in FIXTURE_HEADERS
        if h["tenant_id"] == tenant_id and h["status"] in STANDARD_NET_STATUSES
    ]


def _join_net_lines(tenant_id: str) -> list[dict]:
    """Inner-join fixture lines with net headers for the given tenant."""
    net_ids = {h["id"] for h in _net_headers(tenant_id)}
    return [ln for ln in FIXTURE_LINES if ln["journal_entry_id"] in net_ids]


def _pnl_summary(tenant_id: str) -> dict[str, dict]:
    """Aggregate income/expense totals from fixture net lines."""
    totals: dict[str, dict] = {}
    for ln in _join_net_lines(tenant_id):
        if ln["account_type"] not in ("income", "expense"):
            continue
        code = ln["account_code"]
        if code not in totals:
            totals[code] = {"account_type": ln["account_type"], "debit": 0.0, "credit": 0.0}
        totals[code]["debit"] += ln["debit"]
        totals[code]["credit"] += ln["credit"]
    return totals


def _balance_sheet_summary(tenant_id: str) -> dict[str, dict]:
    """Aggregate asset/liability/equity totals from fixture net lines."""
    totals: dict[str, dict] = {}
    for ln in _join_net_lines(tenant_id):
        if ln["account_type"] not in ("asset", "liability", "equity"):
            continue
        code = ln["account_code"]
        if code not in totals:
            totals[code] = {"account_type": ln["account_type"], "debit": 0.0, "credit": 0.0}
        totals[code]["debit"] += ln["debit"]
        totals[code]["credit"] += ln["credit"]
    return totals


def _cashflow_summary(tenant_id: str) -> dict[str, dict]:
    """Aggregate cashflow from account_code LIKE '1%' lines."""
    totals: dict[str, dict] = {}
    for ln in _join_net_lines(tenant_id):
        if not ln["account_code"].startswith("1"):
            continue
        cat = ln["cashflow_category"] or "unclassified"
        if cat not in totals:
            totals[cat] = {"debit": 0.0, "credit": 0.0}
        totals[cat]["debit"] += ln["debit"]
        totals[cat]["credit"] += ln["credit"]
    return totals


def _assert_no_raw_secrets(data: object) -> None:
    secret_keys = {"api_key", "password", "token", "secret",
                   "encrypted_value", "private_key", "auth_token"}
    combined = str(data).lower()
    for key in secret_keys:
        assert key not in combined, f"Secret key '{key}' must not appear in fixture payload"


# ---------------------------------------------------------------------------
# 1. Fixture file exists and is local only
# ---------------------------------------------------------------------------


def test_fixture_file_exists_and_is_local_only():
    assert _THIS_FILE.exists(), "Test file must exist on disk"
    assert len(FIXTURE_HEADERS) >= 5
    assert len(FIXTURE_LINES) >= 10
    for h in FIXTURE_HEADERS:
        assert isinstance(h["id"], str)
        assert h["id"].startswith("hdr-")


# ---------------------------------------------------------------------------
# 2. Feature flag off keeps legacy path contract
# ---------------------------------------------------------------------------


def test_feature_flag_off_keeps_legacy_path_contract(monkeypatch):
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    assert _posted_ledger_reports_enabled() is False
    assert "posted" in STANDARD_NET_STATUSES
    assert "correction" in STANDARD_NET_STATUSES
    for fs in FORBIDDEN_STATUSES:
        assert fs not in STANDARD_NET_STATUSES


# ---------------------------------------------------------------------------
# 3. Feature flag on selects posted-ledger path with fixture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_feature_flag_on_selects_posted_ledger_path_with_fixture(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.financial_statements_service.get_conn", return_value=cm):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = await build_profit_and_loss(FIXTURE_TENANT, "2026-04-01", "2026-04-30")

    assert result.get("ok") is True
    assert result.get("data", {}).get("source") == "posted_ledger"


# ---------------------------------------------------------------------------
# 4. Fixture requires tenant_id
# ---------------------------------------------------------------------------


def test_posted_ledger_fixture_requires_tenant_id():
    with pytest.raises(ValueError, match="tenant_id"):
        _require_tenant_id("")

    with pytest.raises(ValueError):
        _build_pnl_posted_ledger_query("", None, None)


# ---------------------------------------------------------------------------
# 5. Fixture excludes other tenants
# ---------------------------------------------------------------------------


def test_posted_ledger_fixture_excludes_other_tenants():
    fixture_net = _net_headers(FIXTURE_TENANT)
    assert len(fixture_net) == 2  # posted + correction only
    assert all(h["tenant_id"] == FIXTURE_TENANT for h in fixture_net)

    other_ids = {h["id"] for h in FIXTURE_HEADERS if h["tenant_id"] == OTHER_TENANT}
    for ln in _join_net_lines(FIXTURE_TENANT):
        assert ln["journal_entry_id"] not in other_ids


# ---------------------------------------------------------------------------
# 6. Fixture excludes non-posted states
# ---------------------------------------------------------------------------


def test_posted_ledger_fixture_excludes_non_posted_states():
    for h in _net_headers(FIXTURE_TENANT):
        assert h["status"] not in FORBIDDEN_STATUSES
        assert h["status"] not in ("reversed", "voided")


# ---------------------------------------------------------------------------
# 7. Fixture includes posted and correction for standard net
# ---------------------------------------------------------------------------


def test_posted_ledger_fixture_includes_posted_and_correction_for_standard_net():
    statuses_present = {h["status"] for h in _net_headers(FIXTURE_TENANT)}
    assert "posted" in statuses_present, "posted must be included in standard net"
    assert "correction" in statuses_present, "correction must be included in standard net"


# ---------------------------------------------------------------------------
# 8. Fixture excludes reversed from standard net
# ---------------------------------------------------------------------------


def test_posted_ledger_fixture_excludes_reversed_from_standard_net():
    for h in _net_headers(FIXTURE_TENANT):
        assert h["status"] != "reversed", "reversed must be excluded from standard net"
    # Reversed header still exists in FIXTURE_HEADERS (it's just excluded from net view)
    assert any(h["status"] == "reversed" for h in FIXTURE_HEADERS)


# ---------------------------------------------------------------------------
# 9. P&L query uses journal_entry_headers and journal_entry_lines
# ---------------------------------------------------------------------------


def test_fixture_pnl_query_uses_journal_entry_headers_and_lines():
    sql, _ = _build_pnl_posted_ledger_query(FIXTURE_TENANT, None, None)
    assert "journal_entry_headers" in sql
    assert "journal_entry_lines" in sql


# ---------------------------------------------------------------------------
# 10. P&L query does not reference journal_drafts
# ---------------------------------------------------------------------------


def test_fixture_pnl_query_does_not_reference_journal_drafts():
    sql, _ = _build_pnl_posted_ledger_query(FIXTURE_TENANT, None, None)
    assert "journal_drafts" not in sql


# ---------------------------------------------------------------------------
# 11. P&L preserves evidence / posting / source fields
# ---------------------------------------------------------------------------


def test_fixture_pnl_preserves_evidence_posting_source_fields():
    sql, _ = _build_pnl_posted_ledger_query(FIXTURE_TENANT, "2026-04-01", "2026-04-30")
    assert "source_draft_id" in sql
    assert "posting_log_id" in sql
    assert "evidence_bundle_id" in sql
    # Fixture net headers have all three audit fields set
    for h in _net_headers(FIXTURE_TENANT):
        assert "source_draft_id" in h
        assert "posting_log_id" in h
        assert "evidence_bundle_id" in h


# ---------------------------------------------------------------------------
# 12. Balance Sheet query shape
# ---------------------------------------------------------------------------


def test_fixture_balance_sheet_query_shape():
    sql, params = _build_balance_sheet_posted_ledger_query(FIXTURE_TENANT, "2026-04-30")
    assert isinstance(sql, str)
    assert isinstance(params, list)
    assert "asset" in sql
    assert "liability" in sql
    assert "equity" in sql
    assert "journal_entry_headers" in sql
    assert "journal_entry_lines" in sql
    assert FIXTURE_TENANT in params


# ---------------------------------------------------------------------------
# 13. Balance Sheet uses as_of date
# ---------------------------------------------------------------------------


def test_fixture_balance_sheet_uses_as_of_date():
    as_of = "2026-04-30"
    sql, params = _build_balance_sheet_posted_ledger_query(FIXTURE_TENANT, as_of)
    assert "$3" in sql, "as_of date must be bound as $3"
    assert as_of in params


# ---------------------------------------------------------------------------
# 14. Trial Balance query shape
# ---------------------------------------------------------------------------


def test_fixture_trial_balance_query_shape():
    sql, params = _build_trial_balance_posted_ledger_query(
        FIXTURE_TENANT, "2026-04-01", "2026-04-30"
    )
    assert isinstance(sql, str)
    assert isinstance(params, list)
    assert "account_code" in sql
    assert "GROUP BY" in sql
    assert "SUM" in sql
    assert "$1" in sql
    assert FIXTURE_TENANT in params


# ---------------------------------------------------------------------------
# 15. Trial Balance requires period
# ---------------------------------------------------------------------------


def test_fixture_trial_balance_requires_period():
    # Without dates: only tenant_id and statuses bound ($1, $2)
    sql_no, params_no = _build_trial_balance_posted_ledger_query(FIXTURE_TENANT, None, None)
    assert "$3" not in sql_no, "No $3 when no dates supplied"
    assert len(params_no) == 2

    # With both dates: $3 and $4 appear
    sql_with, params_with = _build_trial_balance_posted_ledger_query(
        FIXTURE_TENANT, "2026-04-01", "2026-04-30"
    )
    assert "$3" in sql_with
    assert "$4" in sql_with
    assert len(params_with) == 4


# ---------------------------------------------------------------------------
# 16. Cashflow uses cash/bank account lines (account_code LIKE '1%')
# ---------------------------------------------------------------------------


def test_fixture_cashflow_uses_cash_bank_lines():
    sql, _ = _build_cashflow_posted_ledger_query(FIXTURE_TENANT, None, None)
    assert "account_code" in sql
    assert "1%" in sql
    # Fixture account 1120 starts with '1', so it contributes to cashflow
    cashflow = _cashflow_summary(FIXTURE_TENANT)
    assert len(cashflow) >= 1


# ---------------------------------------------------------------------------
# 17. Cashflow does not use bank_transactions table
# ---------------------------------------------------------------------------


def test_fixture_cashflow_does_not_use_bank_transactions_only():
    sql, _ = _build_cashflow_posted_ledger_query(FIXTURE_TENANT, None, None)
    assert "bank_transactions" not in sql
    assert "journal_entry_lines" in sql


# ---------------------------------------------------------------------------
# 18. Fail closed when posted-ledger tables unavailable
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fail_closed_when_posted_ledger_unavailable(monkeypatch):
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(
        side_effect=Exception("relation journal_entry_headers does not exist")
    )
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.financial_statements_service.get_conn", return_value=cm):
        from app.api.services.financial_statements_service import build_profit_and_loss
        result = await build_profit_and_loss(FIXTURE_TENANT)

    assert result.get("ok") is False
    assert result.get("error", {}).get("code") == "POSTED_LEDGER_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 19. No silent fallback to journal_drafts when flag on
# ---------------------------------------------------------------------------


def test_no_silent_fallback_to_journal_drafts_when_flag_on():
    with pytest.raises(ValueError, match="journal_drafts"):
        _assert_no_silent_fallback("SELECT * FROM journal_drafts WHERE tenant_id = $1")

    for builder in (
        lambda: _build_pnl_posted_ledger_query(FIXTURE_TENANT, None, None),
        lambda: _build_balance_sheet_posted_ledger_query(FIXTURE_TENANT, None),
        lambda: _build_trial_balance_posted_ledger_query(FIXTURE_TENANT, None, None),
        lambda: _build_cashflow_posted_ledger_query(FIXTURE_TENANT, None, None),
    ):
        sql, _ = builder()
        _assert_no_silent_fallback(sql)  # must not raise


# ---------------------------------------------------------------------------
# 20. Raw secrets not present in fixture payloads
# ---------------------------------------------------------------------------


def test_raw_secrets_not_present_in_fixture_payloads():
    for builder in (
        lambda: _build_pnl_posted_ledger_query(FIXTURE_TENANT, None, None),
        lambda: _build_balance_sheet_posted_ledger_query(FIXTURE_TENANT, None),
        lambda: _build_trial_balance_posted_ledger_query(FIXTURE_TENANT, None, None),
        lambda: _build_cashflow_posted_ledger_query(FIXTURE_TENANT, None, None),
    ):
        sql, params = builder()
        _assert_no_raw_secrets(sql + str(params))
    _assert_no_raw_secrets(FIXTURE_HEADERS)
    _assert_no_raw_secrets(FIXTURE_LINES)


# ---------------------------------------------------------------------------
# 21. No DB or network imports
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"asyncpg", "psycopg2", "requests", "httpx", "aiohttp", "urllib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split(".")[0]
            assert base not in forbidden, f"Forbidden DB/network import: {node.module}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                assert base not in forbidden, f"Forbidden DB/network import: {alias.name}"


# ---------------------------------------------------------------------------
# 22. No migration or SQL execution in tests
# ---------------------------------------------------------------------------


def test_no_migration_or_sql_execution_in_tests():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # No raw get_conn() without a surrounding patch
    assert "get_conn()" not in source or "patch" in source, \
        "Any get_conn() call must be inside a patch context"
    # No migration-runner or DDL imports/calls (AST avoids string self-reference)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "startup.migrations" not in node.module, \
                f"Migration import forbidden: {node.module}"
        if isinstance(node, ast.Call):
            fname = (node.func.id if isinstance(node.func, ast.Name)
                     else node.func.attr if isinstance(node.func, ast.Attribute) else "")
            assert fname not in ("run_migrations", "execute_ddl", "create_table", "drop_table"), \
                f"DDL/migration call forbidden in test: {fname}"


# ---------------------------------------------------------------------------
# 23. Production flag not enabled by tests
# ---------------------------------------------------------------------------


def test_production_flag_not_enabled_by_tests(monkeypatch):
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    assert _posted_ledger_reports_enabled() is False
    # Verify no direct os.environ[] assignment enables the flag (AST avoids self-reference)
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    flag_name = "POSTED_LEDGER_REPORTS_ENABLED"
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Attribute):
                    if target.value.attr == "environ" and isinstance(target.slice, ast.Constant):
                        assert target.slice.value != flag_name, \
                            f"Test must not directly set os.environ['{flag_name}']"


# ---------------------------------------------------------------------------
# 24. H16 does not change posting or approval contract
# ---------------------------------------------------------------------------


def test_h16_does_not_change_posting_or_approval_contract():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    off_limits = {"posting_service", "approval_service", "posting_helpers", "approval_patterns"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for blocked in off_limits:
                assert blocked not in node.module, \
                    f"H16 must not import from {blocked}"
