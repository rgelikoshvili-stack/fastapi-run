"""
Bridge Hub — Task 11C-H8
Mock-based contract tests for future report query behavior against posted ledger tables.

Rules:
- No import of financial_statements_service, ledger_service, or routes_reports.
- No DB connection.
- No SQL execution.
- No migration execution.
- No network calls.
- Uses only local fake query builder objects and pure helper functions.
- Describes future query contract, not current runtime behavior.
"""
import ast
import dataclasses
import pathlib
from typing import List, Optional

import pytest

# ---------------------------------------------------------------------------
# Fake query building objects — live only in this test file
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class FakeReportQuery:
    """Represents the structure of a future posted-ledger report query."""
    source_tables: List[str]        # e.g. ["journal_entry_headers", "journal_entry_lines"]
    filters: dict                   # e.g. {"tenant_id": "t1", "status": "posted", ...}
    account_classes: List[str]      # e.g. ["income", "expense"]
    group_by: List[str]
    include_statuses: List[str]     # statuses accepted by this query
    exclude_statuses: List[str]     # statuses explicitly excluded
    cumulative: bool = False        # True for balance sheet (as-of-date)
    period_only: bool = False       # True for P&L (not cumulative)
    opening_balance: bool = False   # True when query supports opening balance logic


@dataclasses.dataclass
class FakePostedLedgerQueryBuilder:
    """Accumulates query parameters that will be passed to a future DB layer."""
    _tables: List[str] = dataclasses.field(default_factory=list)
    _filters: dict = dataclasses.field(default_factory=dict)
    _account_classes: List[str] = dataclasses.field(default_factory=list)
    _include_statuses: List[str] = dataclasses.field(default_factory=list)
    _exclude_statuses: List[str] = dataclasses.field(default_factory=list)
    _group_by: List[str] = dataclasses.field(default_factory=list)
    _cumulative: bool = False
    _period_only: bool = False
    _opening_balance: bool = False

    def from_tables(self, *tables: str) -> "FakePostedLedgerQueryBuilder":
        self._tables = list(tables)
        return self

    def where(self, **kwargs) -> "FakePostedLedgerQueryBuilder":
        self._filters.update(kwargs)
        return self

    def with_account_classes(self, *classes: str) -> "FakePostedLedgerQueryBuilder":
        self._account_classes = list(classes)
        return self

    def include_status(self, *statuses: str) -> "FakePostedLedgerQueryBuilder":
        self._include_statuses = list(statuses)
        return self

    def exclude_status(self, *statuses: str) -> "FakePostedLedgerQueryBuilder":
        self._exclude_statuses = list(statuses)
        return self

    def group_by(self, *cols: str) -> "FakePostedLedgerQueryBuilder":
        self._group_by = list(cols)
        return self

    def as_cumulative(self) -> "FakePostedLedgerQueryBuilder":
        self._cumulative = True
        return self

    def as_period_only(self) -> "FakePostedLedgerQueryBuilder":
        self._period_only = True
        return self

    def with_opening_balance(self) -> "FakePostedLedgerQueryBuilder":
        self._opening_balance = True
        return self

    def build(self) -> FakeReportQuery:
        return FakeReportQuery(
            source_tables=self._tables,
            filters=self._filters,
            account_classes=self._account_classes,
            group_by=self._group_by,
            include_statuses=self._include_statuses,
            exclude_statuses=self._exclude_statuses,
            cumulative=self._cumulative,
            period_only=self._period_only,
            opening_balance=self._opening_balance,
        )


# ---------------------------------------------------------------------------
# Future query builder helpers — pure functions, no DB, no imports
# ---------------------------------------------------------------------------

_NON_TRUTH_STATUSES = [
    "draft", "pending_approval", "approved", "rejected", "auto_approved",
    "simulated_success", "mock_posting", "dry_run",
]

_POSTED_STATUS = "posted"
_CORRECTION_STATUS = "correction"
_REVERSED_STATUS = "reversed"
_VOIDED_STATUS = "voided"

_LEDGER_TABLES = ["journal_entry_headers", "journal_entry_lines"]
_DRAFT_TABLE = "journal_drafts"


def build_trial_balance_query(
    tenant_id: str,
    period: str,
    include_opening_balance: bool = True,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, period=period, status=_POSTED_STATUS)
    b.include_status(_POSTED_STATUS, _CORRECTION_STATUS)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    b.group_by("account_code", "currency", "period")
    if include_opening_balance:
        b.with_opening_balance()
    return b.build()


def build_pnl_query(
    tenant_id: str,
    period: str,
    detail: bool = False,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, period=period, status=_POSTED_STATUS)
    b.with_account_classes("income", "expense")
    b.include_status(_POSTED_STATUS, _CORRECTION_STATUS)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    b.as_period_only()
    if not detail:
        b.group_by("account_code", "currency")
    return b.build()


def build_balance_sheet_query(
    tenant_id: str,
    as_of_date: str,
    detail: bool = False,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, as_of_date=as_of_date, status=_POSTED_STATUS)
    b.with_account_classes("asset", "liability", "equity")
    b.include_status(_POSTED_STATUS, _CORRECTION_STATUS)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    b.as_cumulative()
    if not detail:
        b.group_by("account_code", "currency")
    return b.build()


def build_vat_register_query(
    tenant_id: str,
    period: str,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, period=period, status=_POSTED_STATUS,
            has_tax_code=True)
    b.include_status(_POSTED_STATUS)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    return b.build()


def build_account_ledger_query(
    tenant_id: str,
    account_code: str,
    date_from: str,
    date_to: str,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, account_code=account_code,
            date_from=date_from, date_to=date_to, status=_POSTED_STATUS)
    b.include_status(_POSTED_STATUS, _CORRECTION_STATUS)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    b.with_opening_balance()
    return b.build()


def build_counterparty_ledger_query(
    tenant_id: str,
    counterparty_id: str,
    period: str,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, counterparty_id=counterparty_id,
            period=period, status=_POSTED_STATUS)
    b.include_status(_POSTED_STATUS, _CORRECTION_STATUS)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    return b.build()


def build_payroll_ledger_query(
    tenant_id: str,
    period: str,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, period=period, status=_POSTED_STATUS,
            source_type="payroll")
    b.include_status(_POSTED_STATUS)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    return b.build()


def build_journal_entries_query(
    tenant_id: str,
    period: str,
    include_history: bool = False,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, period=period)
    statuses = [_POSTED_STATUS, _CORRECTION_STATUS]
    if include_history:
        statuses.append(_REVERSED_STATUS)
    b.include_status(*statuses)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    return b.build()


def build_cashflow_query(
    tenant_id: str,
    period: str,
) -> FakeReportQuery:
    b = FakePostedLedgerQueryBuilder()
    b.from_tables(*_LEDGER_TABLES)
    b.where(tenant_id=tenant_id, period=period, status=_POSTED_STATUS)
    b.with_account_classes("cash", "bank")
    b.include_status(_POSTED_STATUS)
    b.exclude_status(_VOIDED_STATUS, *_NON_TRUTH_STATUSES)
    b.as_period_only()
    return b.build()


# ---------------------------------------------------------------------------
# Helpers for test assertions
# ---------------------------------------------------------------------------

def _all_queries() -> List[FakeReportQuery]:
    return [
        build_trial_balance_query("t1", "2026-05"),
        build_pnl_query("t1", "2026-05"),
        build_pnl_query("t1", "2026-05", detail=True),
        build_balance_sheet_query("t1", "2026-05-31"),
        build_balance_sheet_query("t1", "2026-05-31", detail=True),
        build_vat_register_query("t1", "2026-05"),
        build_account_ledger_query("t1", "1210", "2026-05-01", "2026-05-31"),
        build_counterparty_ledger_query("t1", "cp_001", "2026-05"),
        build_payroll_ledger_query("t1", "2026-05"),
        build_journal_entries_query("t1", "2026-05"),
        build_cashflow_query("t1", "2026-05"),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTrialBalanceUsesPostedLedgerTables:
    def test_trial_balance_uses_posted_ledger_tables(self):
        q = build_trial_balance_query("tenant_acme", "2026-05")
        assert "journal_entry_headers" in q.source_tables
        assert "journal_entry_lines" in q.source_tables

    def test_trial_balance_does_not_reference_journal_drafts(self):
        q = build_trial_balance_query("tenant_acme", "2026-05")
        assert _DRAFT_TABLE not in q.source_tables

    def test_trial_balance_filters_status_posted(self):
        q = build_trial_balance_query("tenant_acme", "2026-05")
        assert q.filters.get("status") == "posted"

    def test_trial_balance_filters_tenant_id(self):
        q = build_trial_balance_query("tenant_acme", "2026-05")
        assert q.filters.get("tenant_id") == "tenant_acme"

    def test_trial_balance_filters_period(self):
        q = build_trial_balance_query("tenant_acme", "2026-05")
        assert q.filters.get("period") == "2026-05"

    def test_trial_balance_supports_opening_balance(self):
        q = build_trial_balance_query("tenant_acme", "2026-05", include_opening_balance=True)
        assert q.opening_balance is True

    def test_trial_balance_excludes_non_truth_statuses(self):
        q = build_trial_balance_query("tenant_acme", "2026-05")
        for status in _NON_TRUTH_STATUSES:
            assert status in q.exclude_statuses

    def test_trial_balance_excludes_voided(self):
        q = build_trial_balance_query("tenant_acme", "2026-05")
        assert _VOIDED_STATUS in q.exclude_statuses


class TestPnlSummaryUsesPostedIncomeAndExpenseLines:
    def test_pnl_summary_uses_posted_income_and_expense_lines(self):
        q = build_pnl_query("tenant_acme", "2026-05")
        assert "income" in q.account_classes
        assert "expense" in q.account_classes

    def test_pnl_summary_source_is_posted_ledger(self):
        q = build_pnl_query("tenant_acme", "2026-05")
        assert "journal_entry_headers" in q.source_tables
        assert "journal_entry_lines" in q.source_tables
        assert _DRAFT_TABLE not in q.source_tables

    def test_pnl_summary_tenant_filter(self):
        q = build_pnl_query("tenant_acme", "2026-05")
        assert q.filters.get("tenant_id") == "tenant_acme"

    def test_pnl_summary_period_filter(self):
        q = build_pnl_query("tenant_acme", "2026-05")
        assert q.filters.get("period") == "2026-05"

    def test_pnl_excludes_simulated_success_and_draft(self):
        q = build_pnl_query("tenant_acme", "2026-05")
        assert "simulated_success" in q.exclude_statuses
        assert "draft" in q.exclude_statuses

    def test_pnl_is_period_only(self):
        q = build_pnl_query("tenant_acme", "2026-05")
        assert q.period_only is True


class TestPnlDetailNeverUsesSimulatedSuccess:
    def test_pnl_detail_never_uses_simulated_success(self):
        q = build_pnl_query("tenant_acme", "2026-05", detail=True)
        assert "simulated_success" not in q.include_statuses
        assert "simulated_success" in q.exclude_statuses

    def test_pnl_detail_source_is_posted_lines_only(self):
        q = build_pnl_query("tenant_acme", "2026-05", detail=True)
        assert _POSTED_STATUS in q.include_statuses
        assert _DRAFT_TABLE not in q.source_tables

    def test_pnl_detail_excludes_all_non_truth_states(self):
        q = build_pnl_query("tenant_acme", "2026-05", detail=True)
        for bad in ["draft", "auto_approved", "mock_posting", "dry_run"]:
            assert bad in q.exclude_statuses


class TestBalanceSheetSummaryUsesPostedAssetLiabilityEquityLines:
    def test_balance_sheet_summary_uses_posted_asset_liability_equity_lines(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31")
        assert "asset" in q.account_classes
        assert "liability" in q.account_classes
        assert "equity" in q.account_classes

    def test_balance_sheet_source_is_posted_ledger(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31")
        assert "journal_entry_headers" in q.source_tables
        assert _DRAFT_TABLE not in q.source_tables

    def test_balance_sheet_is_cumulative(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31")
        assert q.cumulative is True

    def test_balance_sheet_tenant_filter(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31")
        assert q.filters.get("tenant_id") == "tenant_acme"

    def test_balance_sheet_as_of_date_filter(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31")
        assert q.filters.get("as_of_date") == "2026-05-31"


class TestBalanceSheetDetailRequiresStatusPostedAndTenantFilter:
    def test_balance_sheet_detail_requires_status_posted_and_tenant_filter(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31", detail=True)
        assert q.filters.get("status") == _POSTED_STATUS
        assert q.filters.get("tenant_id") == "tenant_acme"

    def test_balance_sheet_detail_does_not_return_all_drafts(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31", detail=True)
        assert "draft" in q.exclude_statuses
        assert _DRAFT_TABLE not in q.source_tables

    def test_balance_sheet_detail_requires_as_of_date(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31", detail=True)
        assert "as_of_date" in q.filters


class TestVatRegisterUsesPostedTaxLines:
    def test_vat_register_uses_posted_tax_lines(self):
        q = build_vat_register_query("tenant_acme", "2026-05")
        assert "journal_entry_lines" in q.source_tables
        assert q.filters.get("has_tax_code") is True

    def test_vat_register_status_posted(self):
        q = build_vat_register_query("tenant_acme", "2026-05")
        assert q.filters.get("status") == _POSTED_STATUS

    def test_vat_register_tenant_and_period_filter(self):
        q = build_vat_register_query("tenant_acme", "2026-05")
        assert q.filters.get("tenant_id") == "tenant_acme"
        assert q.filters.get("period") == "2026-05"

    def test_vat_register_excludes_non_posted_states(self):
        q = build_vat_register_query("tenant_acme", "2026-05")
        assert "simulated_success" in q.exclude_statuses
        assert "draft" in q.exclude_statuses


class TestAccountLedgerUsesPostedLinesByAccountCode:
    def test_account_ledger_uses_posted_lines_by_account_code(self):
        q = build_account_ledger_query("tenant_acme", "1210", "2026-05-01", "2026-05-31")
        assert q.filters.get("account_code") == "1210"
        assert "journal_entry_lines" in q.source_tables

    def test_account_ledger_tenant_id_required(self):
        q = build_account_ledger_query("tenant_acme", "1210", "2026-05-01", "2026-05-31")
        assert q.filters.get("tenant_id") == "tenant_acme"

    def test_account_ledger_date_range_required(self):
        q = build_account_ledger_query("tenant_acme", "1210", "2026-05-01", "2026-05-31")
        assert q.filters.get("date_from") == "2026-05-01"
        assert q.filters.get("date_to") == "2026-05-31"

    def test_account_ledger_opening_closing_movement(self):
        q = build_account_ledger_query("tenant_acme", "1210", "2026-05-01", "2026-05-31")
        assert q.opening_balance is True

    def test_account_ledger_excludes_drafts(self):
        q = build_account_ledger_query("tenant_acme", "1210", "2026-05-01", "2026-05-31")
        assert "draft" in q.exclude_statuses
        assert _DRAFT_TABLE not in q.source_tables


class TestCounterpartyLedgerUsesPostedLinesByCounterpartyId:
    def test_counterparty_ledger_uses_posted_lines_by_counterparty_id(self):
        q = build_counterparty_ledger_query("tenant_acme", "cp_001", "2026-05")
        assert q.filters.get("counterparty_id") == "cp_001"
        assert "journal_entry_lines" in q.source_tables

    def test_counterparty_ledger_tenant_id_required(self):
        q = build_counterparty_ledger_query("tenant_acme", "cp_001", "2026-05")
        assert q.filters.get("tenant_id") == "tenant_acme"

    def test_counterparty_ledger_date_or_period_required(self):
        q = build_counterparty_ledger_query("tenant_acme", "cp_001", "2026-05")
        assert q.filters.get("period") == "2026-05"

    def test_counterparty_ledger_excludes_non_truth(self):
        q = build_counterparty_ledger_query("tenant_acme", "cp_001", "2026-05")
        assert "draft" in q.exclude_statuses
        assert "simulated_success" in q.exclude_statuses


class TestPayrollLedgerUsesPostedPayrollSourceOrPayrollAccounts:
    def test_payroll_ledger_uses_posted_payroll_source_or_payroll_accounts(self):
        q = build_payroll_ledger_query("tenant_acme", "2026-05")
        assert q.filters.get("source_type") == "payroll"
        assert "journal_entry_lines" in q.source_tables

    def test_payroll_ledger_tenant_and_period_required(self):
        q = build_payroll_ledger_query("tenant_acme", "2026-05")
        assert q.filters.get("tenant_id") == "tenant_acme"
        assert q.filters.get("period") == "2026-05"

    def test_payroll_ledger_status_posted(self):
        q = build_payroll_ledger_query("tenant_acme", "2026-05")
        assert q.filters.get("status") == _POSTED_STATUS

    def test_payroll_ledger_excludes_non_truth(self):
        q = build_payroll_ledger_query("tenant_acme", "2026-05")
        assert "simulated_success" in q.exclude_statuses


class TestJournalEntriesListUsesHeadersAndLines:
    def test_journal_entries_list_uses_headers_and_lines(self):
        q = build_journal_entries_query("tenant_acme", "2026-05")
        assert "journal_entry_headers" in q.source_tables
        assert "journal_entry_lines" in q.source_tables

    def test_journal_entries_standard_includes_posted_and_correction(self):
        q = build_journal_entries_query("tenant_acme", "2026-05")
        assert _POSTED_STATUS in q.include_statuses
        assert _CORRECTION_STATUS in q.include_statuses

    def test_journal_entries_history_includes_reversed(self):
        q = build_journal_entries_query("tenant_acme", "2026-05", include_history=True)
        assert _REVERSED_STATUS in q.include_statuses

    def test_journal_entries_standard_excludes_draft_approved_simulated(self):
        q = build_journal_entries_query("tenant_acme", "2026-05")
        for bad in ["draft", "approved", "auto_approved", "simulated_success"]:
            assert bad in q.exclude_statuses

    def test_journal_entries_tenant_and_period_required(self):
        q = build_journal_entries_query("tenant_acme", "2026-05")
        assert q.filters.get("tenant_id") == "tenant_acme"
        assert q.filters.get("period") == "2026-05"


class TestCashflowUsesLedgerLinkedCashBankLines:
    def test_cashflow_uses_cash_bank_posted_lines_or_ledger_linked_bank_transactions(self):
        q = build_cashflow_query("tenant_acme", "2026-05")
        assert "cash" in q.account_classes or "bank" in q.account_classes
        assert "journal_entry_lines" in q.source_tables

    def test_cashflow_not_bank_transactions_only_without_ledger_linkage(self):
        q = build_cashflow_query("tenant_acme", "2026-05")
        assert "journal_entry_headers" in q.source_tables
        assert "journal_entry_lines" in q.source_tables

    def test_cashflow_tenant_and_period_filter(self):
        q = build_cashflow_query("tenant_acme", "2026-05")
        assert q.filters.get("tenant_id") == "tenant_acme"
        assert q.filters.get("period") == "2026-05"

    def test_cashflow_period_only(self):
        q = build_cashflow_query("tenant_acme", "2026-05")
        assert q.period_only is True

    def test_cashflow_excludes_non_posted(self):
        q = build_cashflow_query("tenant_acme", "2026-05")
        assert "draft" in q.exclude_statuses
        assert "simulated_success" in q.exclude_statuses


class TestAllOfficialReportQueriesRequireTenantId:
    def test_all_official_report_queries_require_tenant_id(self):
        for q in _all_queries():
            assert "tenant_id" in q.filters, \
                f"tenant_id missing in query for tables {q.source_tables}"

    def test_no_query_falls_back_to_default_tenant(self):
        for q in _all_queries():
            assert q.filters.get("tenant_id") != "default", \
                "Query must not silently use 'default' tenant"

    def test_all_queries_have_non_empty_tenant_id(self):
        for q in _all_queries():
            assert q.filters.get("tenant_id"), \
                "tenant_id must be non-empty in all queries"


class TestAllOfficialReportQueriesRequirePeriodOrDateFilter:
    def test_all_official_report_queries_require_period_or_date_filter(self):
        for q in _all_queries():
            has_period = "period" in q.filters
            has_date = "date_from" in q.filters or "as_of_date" in q.filters
            assert has_period or has_date, \
                f"period or date filter missing in query for tables {q.source_tables}"

    def test_balance_sheet_uses_as_of_date(self):
        q = build_balance_sheet_query("tenant_acme", "2026-05-31")
        assert "as_of_date" in q.filters

    def test_pnl_uses_period(self):
        q = build_pnl_query("tenant_acme", "2026-05")
        assert "period" in q.filters


class TestAllOfficialReportQueriesRequireStatusPostedForStandardTotals:
    def test_all_official_report_queries_require_status_posted_for_standard_totals(self):
        standard_queries = [
            build_trial_balance_query("t1", "2026-05"),
            build_pnl_query("t1", "2026-05"),
            build_balance_sheet_query("t1", "2026-05-31"),
            build_vat_register_query("t1", "2026-05"),
            build_account_ledger_query("t1", "1210", "2026-05-01", "2026-05-31"),
            build_payroll_ledger_query("t1", "2026-05"),
            build_cashflow_query("t1", "2026-05"),
        ]
        for q in standard_queries:
            assert q.filters.get("status") == _POSTED_STATUS, \
                f"Standard report query must filter status='posted', got: {q.filters.get('status')}"

    def test_special_audit_history_may_include_reversed(self):
        q = build_journal_entries_query("t1", "2026-05", include_history=True)
        assert _REVERSED_STATUS in q.include_statuses

    def test_special_audit_mode_still_excludes_non_truth_statuses(self):
        q = build_journal_entries_query("t1", "2026-05", include_history=True)
        for bad in ["draft", "simulated_success", "auto_approved"]:
            assert bad in q.exclude_statuses


class TestReversedEntriesExcludedFromStandardNetTotals:
    def test_reversed_entries_excluded_from_standard_net_totals(self):
        net_reports = [
            build_trial_balance_query("t1", "2026-05"),
            build_pnl_query("t1", "2026-05"),
            build_balance_sheet_query("t1", "2026-05-31"),
        ]
        for q in net_reports:
            assert _REVERSED_STATUS not in q.include_statuses or \
                   _REVERSED_STATUS in q.exclude_statuses, \
                   f"Reversed must not appear in net totals for {q.source_tables}"

    def test_reversal_history_only_in_audit_mode(self):
        standard = build_journal_entries_query("t1", "2026-05", include_history=False)
        audit = build_journal_entries_query("t1", "2026-05", include_history=True)
        assert _REVERSED_STATUS not in standard.include_statuses
        assert _REVERSED_STATUS in audit.include_statuses


class TestCorrectionEntriesHandledWithoutDoubleCounting:
    def test_correction_entries_handled_without_double_counting(self):
        q = build_trial_balance_query("t1", "2026-05")
        assert _CORRECTION_STATUS in q.include_statuses

    def test_correction_included_in_net_view(self):
        for q in [
            build_pnl_query("t1", "2026-05"),
            build_trial_balance_query("t1", "2026-05"),
        ]:
            assert _CORRECTION_STATUS in q.include_statuses

    def test_correction_not_added_to_non_truth_exclude_list(self):
        q = build_trial_balance_query("t1", "2026-05")
        assert _CORRECTION_STATUS not in q.exclude_statuses


class TestVoidedEntriesExcludedFromAllOfficialTotals:
    def test_voided_entries_excluded_from_all_official_totals(self):
        for q in _all_queries():
            assert _VOIDED_STATUS in q.exclude_statuses, \
                f"voided must be excluded in all queries, missing in {q.source_tables}"

    def test_voided_not_in_include_statuses(self):
        for q in _all_queries():
            assert _VOIDED_STATUS not in q.include_statuses


class TestOpeningBalanceQueryUsesPriorPostedLines:
    def test_opening_balance_query_uses_prior_posted_lines(self):
        q = build_trial_balance_query("t1", "2026-05", include_opening_balance=True)
        assert q.opening_balance is True
        assert "journal_entry_headers" in q.source_tables

    def test_opening_balance_not_from_drafts(self):
        q = build_trial_balance_query("t1", "2026-05", include_opening_balance=True)
        assert _DRAFT_TABLE not in q.source_tables

    def test_account_ledger_also_uses_opening_balance(self):
        q = build_account_ledger_query("t1", "1210", "2026-05-01", "2026-05-31")
        assert q.opening_balance is True


class TestBalanceSheetAsOfDateIsCumulative:
    def test_balance_sheet_as_of_date_is_cumulative(self):
        q = build_balance_sheet_query("t1", "2026-05-31")
        assert q.cumulative is True

    def test_balance_sheet_is_not_period_only(self):
        q = build_balance_sheet_query("t1", "2026-05-31")
        assert q.period_only is False

    def test_balance_sheet_includes_lines_up_to_as_of_date(self):
        q = build_balance_sheet_query("t1", "2026-05-31")
        assert q.filters.get("as_of_date") == "2026-05-31"
        assert q.cumulative is True


class TestPnlIsPeriodOnly:
    def test_pnl_is_period_only(self):
        q = build_pnl_query("t1", "2026-05")
        assert q.period_only is True

    def test_pnl_is_not_cumulative(self):
        q = build_pnl_query("t1", "2026-05")
        assert q.cumulative is False

    def test_pnl_includes_only_selected_period_range(self):
        q = build_pnl_query("t1", "2026-05")
        assert q.filters.get("period") == "2026-05"
        assert q.period_only is True


class TestQueryContractRejectsJournalDraftsSource:
    def test_query_contract_rejects_journal_drafts_source(self):
        for q in _all_queries():
            assert _DRAFT_TABLE not in q.source_tables, \
                f"journal_drafts must not be a source table in official reports"

    def test_no_query_has_journal_drafts_as_primary_source(self):
        for q in _all_queries():
            if q.source_tables:
                assert q.source_tables[0] != _DRAFT_TABLE

    def test_all_queries_use_ledger_tables(self):
        for q in _all_queries():
            assert "journal_entry_headers" in q.source_tables or \
                   "journal_entry_lines" in q.source_tables


class TestQueryContractRejectsApprovedAutoApprovedMockDryRun:
    def test_query_contract_rejects_approved_auto_approved_mock_dry_run(self):
        bad_statuses = ["approved", "auto_approved", "mock_posting", "dry_run"]
        for q in _all_queries():
            for bad in bad_statuses:
                assert bad not in q.include_statuses, \
                    f"Status '{bad}' must not be in include_statuses for official reports"

    def test_simulated_success_not_accepted_as_report_source(self):
        for q in _all_queries():
            assert "simulated_success" not in q.include_statuses

    def test_all_non_truth_statuses_excluded(self):
        for q in _all_queries():
            for bad in _NON_TRUTH_STATUSES:
                assert bad in q.exclude_statuses, \
                    f"Status '{bad}' must be in exclude_statuses"


class TestH8DoesNotImportRuntimeReportServices:
    def test_h8_does_not_import_runtime_report_services(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {
            "financial_statements_service",
            "ledger_service",
            "routes_reports",
            "posting_service",
            "approval_service",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    assert f not in node.module, f"Forbidden import: {node.module}"

    def test_no_app_runtime_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_prefixes = {"app.api", "app.core", "app.knowledge"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden_prefixes:
                    assert not node.module.startswith(prefix), \
                        f"Forbidden runtime import: {node.module}"


class TestH8DoesNotRunSqlOrConnectToDb:
    def test_h8_does_not_run_sql_or_connect_to_db(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_db = {"psycopg2", "asyncpg", "sqlalchemy", "databases"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                for alias in getattr(node, "names", []):
                    name = alias.name or ""
                    for f in forbidden_db:
                        assert not name.startswith(f), f"Forbidden DB import: {name}"
                        assert not mod.startswith(f), f"Forbidden DB import from: {mod}"

    def test_no_network_imports(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_net = {"requests", "httpx", "urllib", "aiohttp"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                for alias in getattr(node, "names", []):
                    name = alias.name or ""
                    for f in forbidden_net:
                        assert not name.startswith(f), f"Forbidden net import: {name}"
                        assert not mod.startswith(f), f"Forbidden net import from: {mod}"

    def test_no_sql_execution_calls(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        sql_exec_attrs = {"execute", "executemany", "executescript", "fetchall", "fetchone"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in sql_exec_attrs:
                    obj_name = ""
                    if isinstance(func.value, ast.Name):
                        obj_name = func.value.id
                    assert False, f"Forbidden SQL execution call: {obj_name}.{func.attr}"

    def test_no_migration_file_references(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        val = arg.value
                        assert not (val.endswith(".sql") and "migration" in val.lower()), \
                            f"Forbidden migration file reference: {val}"
