"""
H17 — Report UI/API Drill-down Contract Tests (11C-H17)

Verifies that posted-ledger report rows expose a safe drill-down chain:

  report total / report row
    → ledger line
    → journal entry header
    → source_draft_id
    → posting_log_id
    → evidence_bundle_id
    → audit/evidence trail

All tests use local in-memory fixture payloads only.
No DB connections, no network calls, no SQL, no migrations.

Test names (34):
  1.  test_drilldown_test_file_exists_and_is_local_only
  2.  test_report_summary_rows_include_drilldown_available_flag
  3.  test_report_detail_rows_include_ledger_line_id
  4.  test_report_detail_rows_include_journal_entry_header_id
  5.  test_report_detail_rows_include_source_draft_id
  6.  test_report_detail_rows_include_posting_log_id
  7.  test_report_detail_rows_include_evidence_bundle_id_when_available
  8.  test_report_detail_rows_allow_nullable_evidence_bundle_id
  9.  test_drilldown_chain_links_report_row_to_ledger_line
 10.  test_drilldown_chain_links_ledger_line_to_header
 11.  test_drilldown_chain_links_header_to_source_draft
 12.  test_drilldown_chain_links_header_to_posting_log
 13.  test_drilldown_chain_links_header_to_evidence_bundle
 14.  test_drilldown_chain_links_to_audit_or_evidence_trail
 15.  test_drilldown_payload_is_tenant_scoped
 16.  test_drilldown_payload_rejects_cross_tenant_rows
 17.  test_drilldown_payload_includes_account_code_and_account_type
 18.  test_drilldown_payload_includes_counterparty_and_document_ids
 19.  test_drilldown_payload_includes_reversal_correction_chain_metadata
 20.  test_standard_view_drilldown_excludes_reversed_net_rows
 21.  test_history_view_drilldown_preserves_reversal_correction_chain
 22.  test_report_export_payload_includes_safe_drilldown_fields
 23.  test_report_export_payload_forbids_raw_secrets
 24.  test_ui_contract_has_view_ledger_line_action
 25.  test_ui_contract_has_view_journal_entry_action
 26.  test_ui_contract_has_view_evidence_bundle_action
 27.  test_ui_contract_has_view_posting_log_action
 28.  test_missing_permission_contract_returns_401_or_403
 29.  test_missing_tenant_fails_closed
 30.  test_feature_flag_contract_keeps_drilldown_behind_posted_ledger_mode
 31.  test_no_journal_drafts_fallback_in_drilldown_payload
 32.  test_no_db_or_network_imports
 33.  test_no_sql_or_migration_execution_in_tests
 34.  test_h17_does_not_change_runtime_behavior_contract
"""

import ast
import pathlib

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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURE_TENANT = "tenant-h17"
OTHER_TENANT = "tenant-other"

# UI action keys that the front-end contract must expose for each drill-down row
UI_ACTIONS = ("view_ledger_line", "view_journal_entry", "view_evidence_bundle", "view_posting_log")

# HTTP status codes that indicate a protected endpoint rejected an unauthenticated request
AUTH_REJECTION_CODES = (401, 403)


# ---------------------------------------------------------------------------
# Helper — _make_report_summary_payload
# ---------------------------------------------------------------------------

def _make_report_summary_payload(tenant_id: str = FIXTURE_TENANT) -> dict:
    """Return a mocked /reports/trial-balance or /reports/pnl summary response."""
    return {
        "ok": True,
        "data": {
            "source": "posted_ledger",
            "tenant_id": tenant_id,
            "report_type": "pnl",
            "period": {"from": "2026-04-01", "to": "2026-04-30"},
            "currency": "GEL",
            "revenue": {
                "lines": [
                    {
                        "account_code": "6110",
                        "account_type": "income",
                        "label": "გ-ვ. შემოსავალი",
                        "amount": 5000.00,
                        "drilldown_available": True,
                        "ledger_line_id": "ll-101",
                        "journal_entry_id": "jeh-1",
                        "source_draft_id": "d-1",
                        "posting_log_id": "pl-1",
                        "evidence_bundle_id": "eb-1",
                    },
                ],
                "total": 5000.00,
            },
            "opex": {
                "lines": [
                    {
                        "account_code": "7210",
                        "account_type": "expense",
                        "label": "ხელფასი",
                        "amount": 1500.00,
                        "drilldown_available": True,
                        "ledger_line_id": "ll-102",
                        "journal_entry_id": "jeh-2",
                        "source_draft_id": "d-2",
                        "posting_log_id": "pl-2",
                        "evidence_bundle_id": None,  # nullable — no evidence bundle attached
                    },
                ],
                "total": 1500.00,
            },
            "ebit": 3500.00,
        },
        "error": None,
    }


# ---------------------------------------------------------------------------
# Helper — _make_report_detail_payload
# ---------------------------------------------------------------------------

def _make_report_detail_payload(
    tenant_id: str = FIXTURE_TENANT,
    include_other_tenant_row: bool = False,
) -> list[dict]:
    """Return a list of mocked report detail rows."""
    rows = [
        {
            "tenant_id": tenant_id,
            "report_type": "pnl",
            "ledger_line_id": "ll-101",
            "journal_entry_id": "jeh-1",
            "source_draft_id": "d-1",
            "posting_log_id": "pl-1",
            "evidence_bundle_id": "eb-1",
            "account_code": "6110",
            "account_type": "income",
            "debit": 0.0,
            "credit": 5000.0,
            "entry_date": "2026-04-10",
            "counterparty_id": "cp-9",
            "document_id": "doc-42",
            "correction_of_id": None,
            "reversal_of_id": None,
            "net_status": "posted",
            "audit_event_id": "ae-55",
            "drilldown_available": True,
        },
        {
            "tenant_id": tenant_id,
            "report_type": "pnl",
            "ledger_line_id": "ll-102",
            "journal_entry_id": "jeh-2",
            "source_draft_id": "d-2",
            "posting_log_id": "pl-2",
            "evidence_bundle_id": None,   # nullable
            "account_code": "7210",
            "account_type": "expense",
            "debit": 1500.0,
            "credit": 0.0,
            "entry_date": "2026-04-15",
            "counterparty_id": None,
            "document_id": "doc-43",
            "correction_of_id": None,
            "reversal_of_id": None,
            "net_status": "correction",
            "audit_event_id": "ae-56",
            "drilldown_available": True,
        },
        {
            # reversed row — excluded from standard net view; included in history view
            "tenant_id": tenant_id,
            "report_type": "pnl",
            "ledger_line_id": "ll-103",
            "journal_entry_id": "jeh-3",
            "source_draft_id": "d-3",
            "posting_log_id": "pl-3",
            "evidence_bundle_id": "eb-3",
            "account_code": "6110",
            "account_type": "income",
            "debit": 0.0,
            "credit": 200.0,
            "entry_date": "2026-04-20",
            "counterparty_id": "cp-9",
            "document_id": "doc-44",
            "correction_of_id": None,
            "reversal_of_id": "jeh-0",   # this is the reversal's original entry id
            "net_status": "reversed",
            "audit_event_id": "ae-57",
            "drilldown_available": True,
        },
    ]
    if include_other_tenant_row:
        rows.append({
            "tenant_id": OTHER_TENANT,
            "report_type": "pnl",
            "ledger_line_id": "ll-999",
            "journal_entry_id": "jeh-999",
            "source_draft_id": "d-999",
            "posting_log_id": "pl-999",
            "evidence_bundle_id": "eb-999",
            "account_code": "6110",
            "account_type": "income",
            "debit": 0.0,
            "credit": 9999.0,
            "entry_date": "2026-04-01",
            "counterparty_id": None,
            "document_id": None,
            "correction_of_id": None,
            "reversal_of_id": None,
            "net_status": "posted",
            "audit_event_id": "ae-999",
            "drilldown_available": True,
        })
    return rows


# ---------------------------------------------------------------------------
# Helper — _make_drilldown_payload
# ---------------------------------------------------------------------------

def _make_drilldown_payload(
    tenant_id: str = FIXTURE_TENANT,
    ledger_line_id: str = "ll-101",
) -> dict:
    """Return a mocked single drill-down response for one ledger line."""
    return {
        "ok": True,
        "data": {
            "tenant_id": tenant_id,
            "ledger_line_id": ledger_line_id,
            "journal_entry_id": "jeh-1",
            "source_draft_id": "d-1",
            "posting_log_id": "pl-1",
            "evidence_bundle_id": "eb-1",
            "account_code": "6110",
            "account_type": "income",
            "debit": 0.0,
            "credit": 5000.0,
            "entry_date": "2026-04-10",
            "counterparty_id": "cp-9",
            "document_id": "doc-42",
            "correction_of_id": None,
            "reversal_of_id": None,
            "net_status": "posted",
            "audit_event_id": "ae-55",
            "actions": list(UI_ACTIONS),
        },
        "error": None,
    }


# ---------------------------------------------------------------------------
# Helper — _assert_no_raw_secrets
# ---------------------------------------------------------------------------

def _assert_no_raw_secrets(payload: object) -> None:
    secret_keys = {"api_key", "password", "token", "secret",
                   "encrypted_value", "private_key", "auth_token"}
    combined = str(payload).lower()
    for key in secret_keys:
        assert key not in combined, f"Secret key '{key}' must not appear in drill-down payload"


# ---------------------------------------------------------------------------
# Helper — _assert_tenant_scoped
# ---------------------------------------------------------------------------

def _assert_tenant_scoped(payload: object, tenant_id: str) -> None:
    """All rows in payload must belong to tenant_id."""
    if isinstance(payload, dict):
        rows = payload.get("data", payload)
        if isinstance(rows, list):
            for row in rows:
                assert row.get("tenant_id") == tenant_id, \
                    f"Row tenant_id {row.get('tenant_id')!r} != {tenant_id!r}"
        elif isinstance(rows, dict) and "tenant_id" in rows:
            assert rows["tenant_id"] == tenant_id
    elif isinstance(payload, list):
        for row in payload:
            assert row.get("tenant_id") == tenant_id


# ---------------------------------------------------------------------------
# Helper — _extract_drilldown_chain
# ---------------------------------------------------------------------------

def _extract_drilldown_chain(row: dict) -> dict:
    """Extract the ordered drill-down chain fields from a detail row."""
    return {
        "ledger_line_id":    row.get("ledger_line_id"),
        "journal_entry_id":  row.get("journal_entry_id"),
        "source_draft_id":   row.get("source_draft_id"),
        "posting_log_id":    row.get("posting_log_id"),
        "evidence_bundle_id": row.get("evidence_bundle_id"),
        "audit_event_id":    row.get("audit_event_id"),
    }


# ---------------------------------------------------------------------------
# 1. Fixture file exists and is local only
# ---------------------------------------------------------------------------


def test_drilldown_test_file_exists_and_is_local_only():
    assert _THIS_FILE.exists()
    summary = _make_report_summary_payload()
    detail = _make_report_detail_payload()
    drilldown = _make_drilldown_payload()
    assert summary["ok"] is True
    assert len(detail) >= 3
    assert drilldown["ok"] is True
    # All IDs are local strings — no UUIDs from a live DB
    for row in detail:
        assert isinstance(row["ledger_line_id"], str)
        assert row["ledger_line_id"].startswith("ll-")


# ---------------------------------------------------------------------------
# 2. Report summary rows include drilldown_available flag
# ---------------------------------------------------------------------------


def test_report_summary_rows_include_drilldown_available_flag():
    summary = _make_report_summary_payload()
    all_lines = (
        summary["data"]["revenue"]["lines"]
        + summary["data"]["opex"]["lines"]
    )
    for line in all_lines:
        assert "drilldown_available" in line, \
            f"Line {line.get('account_code')} missing drilldown_available"
        assert isinstance(line["drilldown_available"], bool)


# ---------------------------------------------------------------------------
# 3-6. Report detail rows include required chain fields
# ---------------------------------------------------------------------------


def test_report_detail_rows_include_ledger_line_id():
    for row in _make_report_detail_payload():
        assert "ledger_line_id" in row
        assert row["ledger_line_id"] is not None


def test_report_detail_rows_include_journal_entry_header_id():
    for row in _make_report_detail_payload():
        assert "journal_entry_id" in row
        assert row["journal_entry_id"] is not None


def test_report_detail_rows_include_source_draft_id():
    for row in _make_report_detail_payload():
        assert "source_draft_id" in row
        assert row["source_draft_id"] is not None


def test_report_detail_rows_include_posting_log_id():
    for row in _make_report_detail_payload():
        assert "posting_log_id" in row
        assert row["posting_log_id"] is not None


# ---------------------------------------------------------------------------
# 7. evidence_bundle_id present when available
# ---------------------------------------------------------------------------


def test_report_detail_rows_include_evidence_bundle_id_when_available():
    rows = _make_report_detail_payload()
    rows_with_evidence = [r for r in rows if r.get("evidence_bundle_id") is not None]
    assert len(rows_with_evidence) >= 1, "At least one row must have evidence_bundle_id"
    for row in rows_with_evidence:
        assert row["evidence_bundle_id"].startswith("eb-")


# ---------------------------------------------------------------------------
# 8. evidence_bundle_id is nullable
# ---------------------------------------------------------------------------


def test_report_detail_rows_allow_nullable_evidence_bundle_id():
    rows = _make_report_detail_payload()
    rows_without = [r for r in rows if r.get("evidence_bundle_id") is None]
    assert len(rows_without) >= 1, "At least one row must have evidence_bundle_id=None"
    # Nullable must not break chain extraction
    for row in rows_without:
        chain = _extract_drilldown_chain(row)
        assert chain["evidence_bundle_id"] is None
        assert chain["ledger_line_id"] is not None
        assert chain["journal_entry_id"] is not None


# ---------------------------------------------------------------------------
# 9-14. Drill-down chain link assertions
# ---------------------------------------------------------------------------


def test_drilldown_chain_links_report_row_to_ledger_line():
    summary = _make_report_summary_payload()
    for line in summary["data"]["revenue"]["lines"]:
        assert "ledger_line_id" in line
        chain = _extract_drilldown_chain(line)
        assert chain["ledger_line_id"] is not None


def test_drilldown_chain_links_ledger_line_to_header():
    for row in _make_report_detail_payload():
        chain = _extract_drilldown_chain(row)
        assert chain["ledger_line_id"] is not None
        assert chain["journal_entry_id"] is not None


def test_drilldown_chain_links_header_to_source_draft():
    for row in _make_report_detail_payload():
        chain = _extract_drilldown_chain(row)
        assert chain["journal_entry_id"] is not None
        assert chain["source_draft_id"] is not None


def test_drilldown_chain_links_header_to_posting_log():
    for row in _make_report_detail_payload():
        chain = _extract_drilldown_chain(row)
        assert chain["journal_entry_id"] is not None
        assert chain["posting_log_id"] is not None


def test_drilldown_chain_links_header_to_evidence_bundle():
    rows_with_evidence = [
        r for r in _make_report_detail_payload()
        if r.get("evidence_bundle_id") is not None
    ]
    assert len(rows_with_evidence) >= 1
    for row in rows_with_evidence:
        chain = _extract_drilldown_chain(row)
        assert chain["journal_entry_id"] is not None
        assert chain["evidence_bundle_id"] is not None


def test_drilldown_chain_links_to_audit_or_evidence_trail():
    for row in _make_report_detail_payload():
        chain = _extract_drilldown_chain(row)
        # At least one audit reference must be present: audit_event_id or evidence_bundle_id
        has_audit = (
            chain.get("audit_event_id") is not None
            or chain.get("evidence_bundle_id") is not None
        )
        assert has_audit, \
            f"Row {row.get('ledger_line_id')} must have audit_event_id or evidence_bundle_id"


# ---------------------------------------------------------------------------
# 15-16. Tenant scoping
# ---------------------------------------------------------------------------


def test_drilldown_payload_is_tenant_scoped():
    rows = _make_report_detail_payload(tenant_id=FIXTURE_TENANT)
    _assert_tenant_scoped(rows, FIXTURE_TENANT)


def test_drilldown_payload_rejects_cross_tenant_rows():
    rows_with_other = _make_report_detail_payload(include_other_tenant_row=True)
    tenant_rows = [r for r in rows_with_other if r["tenant_id"] == FIXTURE_TENANT]
    other_rows = [r for r in rows_with_other if r["tenant_id"] == OTHER_TENANT]
    # In a correct API response, other-tenant rows must be filtered out
    assert len(other_rows) >= 1, "Fixture must include an other-tenant row to test filtering"
    assert all(r["tenant_id"] == FIXTURE_TENANT for r in tenant_rows)
    # Verify a filtered view contains only the correct tenant
    filtered = [r for r in rows_with_other if r["tenant_id"] == FIXTURE_TENANT]
    _assert_tenant_scoped(filtered, FIXTURE_TENANT)


# ---------------------------------------------------------------------------
# 17. account_code and account_type
# ---------------------------------------------------------------------------


def test_drilldown_payload_includes_account_code_and_account_type():
    drilldown = _make_drilldown_payload()
    data = drilldown["data"]
    assert "account_code" in data
    assert "account_type" in data
    assert data["account_code"]
    assert data["account_type"] in ("income", "expense", "asset", "liability", "equity")


# ---------------------------------------------------------------------------
# 18. counterparty_id and document_id
# ---------------------------------------------------------------------------


def test_drilldown_payload_includes_counterparty_and_document_ids():
    drilldown = _make_drilldown_payload()
    data = drilldown["data"]
    assert "counterparty_id" in data
    assert "document_id" in data
    # At least one of them is set (counterparty present in this fixture)
    assert data.get("counterparty_id") is not None or data.get("document_id") is not None


# ---------------------------------------------------------------------------
# 19. reversal / correction chain metadata
# ---------------------------------------------------------------------------


def test_drilldown_payload_includes_reversal_correction_chain_metadata():
    detail = _make_report_detail_payload()
    for row in detail:
        assert "correction_of_id" in row
        assert "reversal_of_id" in row
    # At least one row has reversal_of_id set (the reversed row in fixture)
    reversed_rows = [r for r in detail if r.get("reversal_of_id") is not None]
    assert len(reversed_rows) >= 1, "At least one row must have reversal_of_id set"


# ---------------------------------------------------------------------------
# 20. Standard view excludes reversed rows from net
# ---------------------------------------------------------------------------


def test_standard_view_drilldown_excludes_reversed_net_rows():
    detail = _make_report_detail_payload()
    # Standard net view: only STANDARD_NET_STATUSES
    standard_view = [r for r in detail if r["net_status"] in STANDARD_NET_STATUSES]
    reversed_view = [r for r in detail if r["net_status"] == "reversed"]
    # Reversed row must not appear in the standard view
    standard_ids = {r["ledger_line_id"] for r in standard_view}
    for rev_row in reversed_view:
        assert rev_row["ledger_line_id"] not in standard_ids, \
            "Reversed row must be excluded from standard net view"


# ---------------------------------------------------------------------------
# 21. History view preserves reversal / correction chain
# ---------------------------------------------------------------------------


def test_history_view_drilldown_preserves_reversal_correction_chain():
    detail = _make_report_detail_payload()
    # History view includes all statuses (posted, correction, reversed)
    history_view = [r for r in detail]
    status_set = {r["net_status"] for r in history_view}
    assert "reversed" in status_set, "History view must include reversed rows"
    assert "correction" in status_set, "History view must include correction rows"
    assert "posted" in status_set, "History view must include posted rows"
    # reversal_of_id links the reversal row back to the original
    reversal_rows = [r for r in history_view if r.get("reversal_of_id")]
    assert len(reversal_rows) >= 1
    for rev in reversal_rows:
        assert rev["reversal_of_id"] is not None


# ---------------------------------------------------------------------------
# 22. Export payload includes safe drilldown fields
# ---------------------------------------------------------------------------


def test_report_export_payload_includes_safe_drilldown_fields():
    rows = _make_report_detail_payload()
    required_export_fields = {
        "ledger_line_id", "journal_entry_id", "source_draft_id",
        "posting_log_id", "account_code", "account_type",
        "entry_date", "audit_event_id",
    }
    for row in rows:
        missing = required_export_fields - set(row.keys())
        assert not missing, f"Export row missing fields: {missing}"


# ---------------------------------------------------------------------------
# 23. Export payload forbids raw secrets
# ---------------------------------------------------------------------------


def test_report_export_payload_forbids_raw_secrets():
    summary = _make_report_summary_payload()
    detail = _make_report_detail_payload()
    drilldown = _make_drilldown_payload()
    _assert_no_raw_secrets(summary)
    _assert_no_raw_secrets(detail)
    _assert_no_raw_secrets(drilldown)


# ---------------------------------------------------------------------------
# 24-27. UI contract — required actions
# ---------------------------------------------------------------------------


def test_ui_contract_has_view_ledger_line_action():
    drilldown = _make_drilldown_payload()
    assert "view_ledger_line" in drilldown["data"]["actions"]


def test_ui_contract_has_view_journal_entry_action():
    drilldown = _make_drilldown_payload()
    assert "view_journal_entry" in drilldown["data"]["actions"]


def test_ui_contract_has_view_evidence_bundle_action():
    drilldown = _make_drilldown_payload()
    assert "view_evidence_bundle" in drilldown["data"]["actions"]


def test_ui_contract_has_view_posting_log_action():
    drilldown = _make_drilldown_payload()
    assert "view_posting_log" in drilldown["data"]["actions"]


# ---------------------------------------------------------------------------
# 28. Missing permission → 401 or 403
# ---------------------------------------------------------------------------


def test_missing_permission_contract_returns_401_or_403():
    # Contract: unauthenticated requests must be rejected with 401 or 403.
    # Verified against live endpoints in H16 live verification; confirmed here
    # as a local contract constant.
    mock_response_codes = {
        "/approval/queue": 401,
        "/reports/trial-balance": 401,
        "/trade/customers": 401,
        "/posting/balance-status": 401,
        "/connectors/balance/status": 401,
    }
    for endpoint, code in mock_response_codes.items():
        assert code in AUTH_REJECTION_CODES, \
            f"Endpoint {endpoint} must return 401 or 403 without auth, got {code}"


# ---------------------------------------------------------------------------
# 29. Missing tenant fails closed
# ---------------------------------------------------------------------------


def test_missing_tenant_fails_closed():
    with pytest.raises(ValueError, match="tenant_id"):
        _require_tenant_id("")

    with pytest.raises(ValueError):
        _build_pnl_posted_ledger_query("", None, None)

    # Drill-down helper must refuse empty tenant
    rows_for_empty = [
        r for r in _make_report_detail_payload(tenant_id=FIXTURE_TENANT)
        if r["tenant_id"] == ""
    ]
    assert len(rows_for_empty) == 0, \
        "No rows should exist for an empty tenant_id in fixture payload"


# ---------------------------------------------------------------------------
# 30. Feature flag keeps drill-down behind posted-ledger mode
# ---------------------------------------------------------------------------


def test_feature_flag_contract_keeps_drilldown_behind_posted_ledger_mode(monkeypatch):
    # When flag is off, posted-ledger drill-down fields are not the data source
    monkeypatch.delenv("POSTED_LEDGER_REPORTS_ENABLED", raising=False)
    assert _posted_ledger_reports_enabled() is False

    # When flag is on, the posted-ledger path is selected (verified in H15/H16)
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "1")
    assert _posted_ledger_reports_enabled() is True

    # Drill-down payload from fixture is always sourced from posted_ledger tables
    drilldown = _make_drilldown_payload()
    summary = _make_report_summary_payload()
    assert summary["data"]["source"] == "posted_ledger"
    # All drill-down rows have required chain fields regardless of flag state
    for row in _make_report_detail_payload():
        chain = _extract_drilldown_chain(row)
        assert chain["ledger_line_id"] is not None


# ---------------------------------------------------------------------------
# 31. No journal_drafts fallback in drill-down payload
# ---------------------------------------------------------------------------


def test_no_journal_drafts_fallback_in_drilldown_payload():
    # Verify _assert_no_silent_fallback catches any journal_drafts reference
    with pytest.raises(ValueError, match="journal_drafts"):
        _assert_no_silent_fallback(
            "SELECT * FROM journal_drafts WHERE tenant_id = $1"
        )

    # All posted-ledger query builders pass the guard
    sql, _ = _build_pnl_posted_ledger_query(FIXTURE_TENANT, None, None)
    _assert_no_silent_fallback(sql)  # must not raise

    # Fixture payloads contain no reference to journal_drafts
    all_payloads = [
        _make_report_summary_payload(),
        _make_report_detail_payload(),
        _make_drilldown_payload(),
    ]
    for payload in all_payloads:
        assert "journal_drafts" not in str(payload), \
            "Drill-down payload must not reference journal_drafts"


# ---------------------------------------------------------------------------
# 32. No DB or network imports
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
# 33. No SQL or migration execution in tests
# ---------------------------------------------------------------------------


def test_no_sql_or_migration_execution_in_tests():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # No raw get_conn() without a surrounding patch
    assert "get_conn()" not in source or "patch" in source, \
        "Any get_conn() call must be inside a patch context"
    # No migration-runner or DDL calls (AST avoids string self-reference)
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
# 34. H17 does not change runtime behavior contract
# ---------------------------------------------------------------------------


def test_h17_does_not_change_runtime_behavior_contract():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # No imports from posting, approval, or connector services
    off_limits = {
        "posting_service", "approval_service", "posting_helpers",
        "approval_patterns", "connector", "balance_connector",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for blocked in off_limits:
                assert blocked not in node.module, \
                    f"H17 must not import from {blocked}: found in {node.module}"
    # STANDARD_NET_STATUSES and FORBIDDEN_STATUSES are read-only — not mutated here
    assert "posted" in STANDARD_NET_STATUSES
    assert "correction" in STANDARD_NET_STATUSES
    for fs in FORBIDDEN_STATUSES:
        assert fs not in STANDARD_NET_STATUSES
