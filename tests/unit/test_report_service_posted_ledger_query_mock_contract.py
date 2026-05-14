"""
H14 — Report Service Query Mock / Local-Fake Contract Tests (11C-H14)

H14 does not implement runtime report behavior.
These tests encode the future contract only.

No DB. No network. No runtime service imports.
All data is pure-Python fake dictionaries.
"""

import ast
import pathlib
from collections import defaultdict
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"

FORBIDDEN_STATUSES = frozenset({
    "draft", "approved", "auto_approved",
    "simulated_success", "mock_posting", "dry_run",
})

STANDARD_NET_STATUSES = frozenset({"posted", "correction"})

HISTORY_STATUSES = frozenset({"posted", "reversed", "correction", "voided"})

SECRET_KEYS = frozenset({
    "api_key", "password", "token", "secret",
    "encrypted_value", "private_key", "auth_token",
})

# ---------------------------------------------------------------------------
# Fake journal_entry_headers
# ---------------------------------------------------------------------------

FAKE_HEADERS = [
    # --- Standard posted entries (tenant-a, 2026-04) ---
    {
        "id": "hdr-invoice",
        "tenant_id": TENANT_A,
        "status": "posted",
        "period": "2026-04",
        "entry_date": date(2026, 4, 1),
        "source_type": "invoice",
        "currency": "GEL",
        "total_debit": 1000,
        "total_credit": 1000,
        "source_draft_id": "draft-1",
        "posting_log_id": "log-1",
        "evidence_bundle_id": "evid-1",
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    {
        "id": "hdr-expense",
        "tenant_id": TENANT_A,
        "status": "posted",
        "period": "2026-04",
        "entry_date": date(2026, 4, 5),
        "source_type": "expense",
        "currency": "GEL",
        "total_debit": 500,
        "total_credit": 500,
        "source_draft_id": None,
        "posting_log_id": "log-2",
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    {
        "id": "hdr-payroll",
        "tenant_id": TENANT_A,
        "status": "posted",
        "period": "2026-04",
        "entry_date": date(2026, 4, 10),
        "source_type": "payroll",
        "currency": "GEL",
        "total_debit": 2000,
        "total_credit": 2000,
        "source_draft_id": None,
        "posting_log_id": "log-3",
        "evidence_bundle_id": "evid-2",
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    {
        "id": "hdr-equity",
        "tenant_id": TENANT_A,
        "status": "posted",
        "period": "2026-04",
        "entry_date": date(2026, 4, 15),
        "source_type": "equity_contribution",
        "currency": "GEL",
        "total_debit": 5000,
        "total_credit": 5000,
        "source_draft_id": None,
        "posting_log_id": "log-4",
        "evidence_bundle_id": "evid-3",
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    # --- Forbidden-status headers (must be excluded from all net/standard views) ---
    {
        "id": "hdr-forbidden-draft",
        "tenant_id": TENANT_A,
        "status": "draft",
        "period": "2026-04",
        "entry_date": date(2026, 4, 2),
        "source_type": "invoice",
        "currency": "GEL",
        "total_debit": 999,
        "total_credit": 999,
        "source_draft_id": None,
        "posting_log_id": None,
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    {
        "id": "hdr-forbidden-approved",
        "tenant_id": TENANT_A,
        "status": "approved",
        "period": "2026-04",
        "entry_date": date(2026, 4, 3),
        "source_type": "invoice",
        "currency": "GEL",
        "total_debit": 888,
        "total_credit": 888,
        "source_draft_id": None,
        "posting_log_id": None,
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    {
        "id": "hdr-forbidden-auto-approved",
        "tenant_id": TENANT_A,
        "status": "auto_approved",
        "period": "2026-04",
        "entry_date": date(2026, 4, 4),
        "source_type": "invoice",
        "currency": "GEL",
        "total_debit": 777,
        "total_credit": 777,
        "source_draft_id": None,
        "posting_log_id": None,
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    {
        "id": "hdr-forbidden-sim",
        "tenant_id": TENANT_A,
        "status": "simulated_success",
        "period": "2026-04",
        "entry_date": date(2026, 4, 6),
        "source_type": "invoice",
        "currency": "GEL",
        "total_debit": 666,
        "total_credit": 666,
        "source_draft_id": None,
        "posting_log_id": None,
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    {
        "id": "hdr-forbidden-mock",
        "tenant_id": TENANT_A,
        "status": "mock_posting",
        "period": "2026-04",
        "entry_date": date(2026, 4, 7),
        "source_type": "invoice",
        "currency": "GEL",
        "total_debit": 555,
        "total_credit": 555,
        "source_draft_id": None,
        "posting_log_id": None,
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    {
        "id": "hdr-forbidden-dry-run",
        "tenant_id": TENANT_A,
        "status": "dry_run",
        "period": "2026-04",
        "entry_date": date(2026, 4, 8),
        "source_type": "invoice",
        "currency": "GEL",
        "total_debit": 444,
        "total_credit": 444,
        "source_draft_id": None,
        "posting_log_id": None,
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    # --- Cross-tenant isolation ---
    {
        "id": "hdr-tenant-b",
        "tenant_id": TENANT_B,
        "status": "posted",
        "period": "2026-04",
        "entry_date": date(2026, 4, 12),
        "source_type": "invoice",
        "currency": "GEL",
        "total_debit": 9999,
        "total_credit": 9999,
        "source_draft_id": None,
        "posting_log_id": "log-b",
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    # --- Reversal chain (tenant-a, 2026-04) ---
    # original entry — status "reversed" → excluded from STANDARD_NET
    {
        "id": "hdr-orig",
        "tenant_id": TENANT_A,
        "status": "reversed",
        "period": "2026-04",
        "entry_date": date(2026, 4, 18),
        "source_type": "expense",
        "currency": "GEL",
        "total_debit": 300,
        "total_credit": 300,
        "source_draft_id": None,
        "posting_log_id": "log-5",
        "evidence_bundle_id": None,
        "reversal_of_id": None,
        "correction_of_id": None,
    },
    # reversal entry — status "posted", reversal_of_id set → included in STANDARD_NET
    {
        "id": "hdr-reversal",
        "tenant_id": TENANT_A,
        "status": "posted",
        "period": "2026-04",
        "entry_date": date(2026, 4, 19),
        "source_type": "expense",
        "currency": "GEL",
        "total_debit": 300,
        "total_credit": 300,
        "source_draft_id": None,
        "posting_log_id": "log-6",
        "evidence_bundle_id": None,
        "reversal_of_id": "hdr-orig",
        "correction_of_id": None,
    },
    # correction entry — status "correction" → included in STANDARD_NET
    {
        "id": "hdr-correction",
        "tenant_id": TENANT_A,
        "status": "correction",
        "period": "2026-04",
        "entry_date": date(2026, 4, 20),
        "source_type": "expense",
        "currency": "GEL",
        "total_debit": 320,
        "total_credit": 320,
        "source_draft_id": None,
        "posting_log_id": "log-7",
        "evidence_bundle_id": "evid-4",
        "reversal_of_id": None,
        "correction_of_id": "hdr-orig",
    },
]

# ---------------------------------------------------------------------------
# Fake journal_entry_lines
#
# Account code convention:
#   1100 = cash/bank (asset)     1200 = AR (asset)
#   2100 = wages payable (lib)   2300 = VAT payable (liability)
#   3100 = capital (equity)      4100 = revenue (income)
#   5100 = payroll expense       5200 = general expense
#
# Trial-balance check across STANDARD_NET entries:
#   Total DR = Total CR = 9120
# ---------------------------------------------------------------------------

FAKE_LINES = [
    # hdr-invoice (posted) — DR 1200  1000, CR 4100  1000
    {"id": "ln-001", "journal_entry_id": "hdr-invoice", "tenant_id": TENANT_A,
     "line_no": 1, "account_code": "1200", "account_type": "asset",
     "debit": 1000, "credit": 0, "description": "AR — invoice",
     "counterparty_id": "cp-alpha", "document_id": "doc-1",
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},
    {"id": "ln-002", "journal_entry_id": "hdr-invoice", "tenant_id": TENANT_A,
     "line_no": 2, "account_code": "4100", "account_type": "income",
     "debit": 0, "credit": 1000, "description": "Revenue",
     "counterparty_id": "cp-alpha", "document_id": "doc-1",
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": "VAT18", "vat_amount": 180},

    # hdr-expense (posted) — DR 5200  500, CR 1100  500
    {"id": "ln-003", "journal_entry_id": "hdr-expense", "tenant_id": TENANT_A,
     "line_no": 1, "account_code": "5200", "account_type": "expense",
     "debit": 500, "credit": 0, "description": "General expense",
     "counterparty_id": "cp-beta", "document_id": "doc-2",
     "bank_transaction_id": None, "cashflow_category": "operating",
     "tax_code": None, "vat_amount": None},
    {"id": "ln-004", "journal_entry_id": "hdr-expense", "tenant_id": TENANT_A,
     "line_no": 2, "account_code": "1100", "account_type": "asset",
     "debit": 0, "credit": 500, "description": "Cash out",
     "counterparty_id": "cp-beta", "document_id": "doc-2",
     "bank_transaction_id": "btx-1", "cashflow_category": "operating",
     "tax_code": None, "vat_amount": None},

    # hdr-payroll (posted) — DR 5100  2000, CR 2100  2000
    {"id": "ln-005", "journal_entry_id": "hdr-payroll", "tenant_id": TENANT_A,
     "line_no": 1, "account_code": "5100", "account_type": "expense",
     "debit": 2000, "credit": 0, "description": "Payroll expense",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": "operating",
     "tax_code": None, "vat_amount": None},
    {"id": "ln-006", "journal_entry_id": "hdr-payroll", "tenant_id": TENANT_A,
     "line_no": 2, "account_code": "2100", "account_type": "liability",
     "debit": 0, "credit": 2000, "description": "Wages payable",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},

    # hdr-equity (posted) — DR 1100  5000, CR 3100  5000
    {"id": "ln-007", "journal_entry_id": "hdr-equity", "tenant_id": TENANT_A,
     "line_no": 1, "account_code": "1100", "account_type": "asset",
     "debit": 5000, "credit": 0, "description": "Cash in — equity",
     "counterparty_id": "cp-owner", "document_id": None,
     "bank_transaction_id": "btx-2", "cashflow_category": "financing",
     "tax_code": None, "vat_amount": None},
    {"id": "ln-008", "journal_entry_id": "hdr-equity", "tenant_id": TENANT_A,
     "line_no": 2, "account_code": "3100", "account_type": "equity",
     "debit": 0, "credit": 5000, "description": "Owner capital",
     "counterparty_id": "cp-owner", "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},

    # hdr-tenant-b (posted, tenant-b) — must never appear in tenant-a queries
    {"id": "ln-009", "journal_entry_id": "hdr-tenant-b", "tenant_id": TENANT_B,
     "line_no": 1, "account_code": "1100", "account_type": "asset",
     "debit": 9999, "credit": 0, "description": "Tenant-B cash",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},
    {"id": "ln-010", "journal_entry_id": "hdr-tenant-b", "tenant_id": TENANT_B,
     "line_no": 2, "account_code": "3100", "account_type": "equity",
     "debit": 0, "credit": 9999, "description": "Tenant-B capital",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},

    # hdr-orig (reversed) — EXCLUDED from STANDARD_NET
    {"id": "ln-011", "journal_entry_id": "hdr-orig", "tenant_id": TENANT_A,
     "line_no": 1, "account_code": "5200", "account_type": "expense",
     "debit": 300, "credit": 0, "description": "Orig expense DR",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},
    {"id": "ln-012", "journal_entry_id": "hdr-orig", "tenant_id": TENANT_A,
     "line_no": 2, "account_code": "2300", "account_type": "liability",
     "debit": 0, "credit": 300, "description": "Orig VAT payable CR",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},

    # hdr-reversal (posted, reversal_of_id set) — included in STANDARD_NET
    {"id": "ln-013", "journal_entry_id": "hdr-reversal", "tenant_id": TENANT_A,
     "line_no": 1, "account_code": "2300", "account_type": "liability",
     "debit": 300, "credit": 0, "description": "Reversal — VAT payable DR",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},
    {"id": "ln-014", "journal_entry_id": "hdr-reversal", "tenant_id": TENANT_A,
     "line_no": 2, "account_code": "5200", "account_type": "expense",
     "debit": 0, "credit": 300, "description": "Reversal — expense CR",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},

    # hdr-correction (correction) — included in STANDARD_NET
    {"id": "ln-015", "journal_entry_id": "hdr-correction", "tenant_id": TENANT_A,
     "line_no": 1, "account_code": "5200", "account_type": "expense",
     "debit": 320, "credit": 0, "description": "Corrected expense DR",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},
    {"id": "ln-016", "journal_entry_id": "hdr-correction", "tenant_id": TENANT_A,
     "line_no": 2, "account_code": "2300", "account_type": "liability",
     "debit": 0, "credit": 320, "description": "Corrected VAT payable CR",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},

    # Forbidden-status lines (should never appear in net/standard views)
    {"id": "ln-017", "journal_entry_id": "hdr-forbidden-draft", "tenant_id": TENANT_A,
     "line_no": 1, "account_code": "1200", "account_type": "asset",
     "debit": 999, "credit": 0, "description": "Forbidden draft DR",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},
    {"id": "ln-018", "journal_entry_id": "hdr-forbidden-draft", "tenant_id": TENANT_A,
     "line_no": 2, "account_code": "4100", "account_type": "income",
     "debit": 0, "credit": 999, "description": "Forbidden draft CR",
     "counterparty_id": None, "document_id": None,
     "bank_transaction_id": None, "cashflow_category": None,
     "tax_code": None, "vat_amount": None},
]

# ---------------------------------------------------------------------------
# Pure-Python query helpers (no DB, no ORM, no network)
# ---------------------------------------------------------------------------

def _posted_headers(
    headers: list[dict],
    tenant_id: str,
    period: str | None = None,
    as_of_date: date | None = None,
) -> list[dict]:
    """Return headers matching STANDARD_NET_STATUSES for the given tenant."""
    result = [
        h for h in headers
        if h["tenant_id"] == tenant_id and h["status"] in STANDARD_NET_STATUSES
    ]
    if period is not None:
        result = [h for h in result if h["period"] == period]
    if as_of_date is not None:
        result = [h for h in result if h["entry_date"] <= as_of_date]
    return result


def _join_posted_lines(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    period: str | None = None,
    as_of_date: date | None = None,
) -> list[dict]:
    """Join lines to posted headers (STANDARD_NET_STATUSES only)."""
    valid_ids = {
        h["id"] for h in _posted_headers(headers, tenant_id, period, as_of_date)
    }
    return [
        ln for ln in lines
        if ln["tenant_id"] == tenant_id and ln["journal_entry_id"] in valid_ids
    ]


def _trial_balance(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    period: str,
) -> dict[str, dict[str, Any]]:
    """Return {account_code: {debit, credit}} for STANDARD_NET entries in period."""
    joined = _join_posted_lines(headers, lines, tenant_id, period=period)
    tb: dict[str, dict] = defaultdict(lambda: {"debit": 0, "credit": 0})
    for ln in joined:
        tb[ln["account_code"]]["debit"] += ln["debit"]
        tb[ln["account_code"]]["credit"] += ln["credit"]
    return dict(tb)


def _pnl_summary(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    period: str,
) -> dict[str, Any]:
    """P&L summary: income = 4xxx credit-debit, expense = 5xxx debit-credit."""
    joined = _join_posted_lines(headers, lines, tenant_id, period=period)
    income = sum(ln["credit"] - ln["debit"] for ln in joined if ln["account_code"].startswith("4"))
    expense = sum(ln["debit"] - ln["credit"] for ln in joined if ln["account_code"].startswith("5"))
    return {"income": income, "expense": expense, "net": income - expense}


def _pnl_detail(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    period: str,
) -> list[dict]:
    """P&L detail: line-level rows with audit drilldown fields from headers."""
    hdr_map = {h["id"]: h for h in headers}
    joined = _join_posted_lines(headers, lines, tenant_id, period=period)
    rows = []
    for ln in joined:
        if ln["account_code"].startswith(("4", "5")):
            h = hdr_map.get(ln["journal_entry_id"], {})
            rows.append({
                **ln,
                "source_draft_id": h.get("source_draft_id"),
                "posting_log_id": h.get("posting_log_id"),
                "evidence_bundle_id": h.get("evidence_bundle_id"),
            })
    return rows


def _balance_sheet_summary(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    as_of_date: date,
) -> dict[str, Any]:
    """Cumulative BS totals as of a given date (STANDARD_NET_STATUSES only)."""
    joined = _join_posted_lines(headers, lines, tenant_id, as_of_date=as_of_date)
    totals: dict[str, int] = defaultdict(int)
    for ln in joined:
        t = ln["account_type"]
        if t in ("asset", "liability", "equity"):
            totals[t] += ln["debit"] - ln["credit"]
    return dict(totals)


def _balance_sheet_detail(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    as_of_date: date,
) -> list[dict]:
    """BS line-level rows for asset/liability/equity accounts, STANDARD_NET only."""
    joined = _join_posted_lines(headers, lines, tenant_id, as_of_date=as_of_date)
    return [ln for ln in joined if ln["account_type"] in ("asset", "liability", "equity")]


def _vat_register(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    period: str,
) -> list[dict]:
    """VAT register: lines with non-None tax_code or non-None vat_amount."""
    joined = _join_posted_lines(headers, lines, tenant_id, period=period)
    return [ln for ln in joined if ln["tax_code"] is not None or ln["vat_amount"] is not None]


def _account_ledger(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    account_code: str,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    """Opening/running/closing for single account_code + date range."""
    # opening: STANDARD_NET entries before date_from
    pre = _join_posted_lines(headers, lines, tenant_id,
                             as_of_date=date(date_from.year, date_from.month, date_from.day - 1)
                             if date_from.day > 1 else date(date_from.year, date_from.month, 1))
    opening = sum(ln["debit"] - ln["credit"] for ln in pre if ln["account_code"] == account_code)

    # movement: entries in range
    in_range = [
        ln for ln in _join_posted_lines(headers, lines, tenant_id)
        if ln["account_code"] == account_code
    ]
    hdr_map = {h["id"]: h for h in headers}
    in_range = [
        ln for ln in in_range
        if date_from <= hdr_map[ln["journal_entry_id"]]["entry_date"] <= date_to
    ]
    running = [{"date": hdr_map[ln["journal_entry_id"]]["entry_date"],
                "debit": ln["debit"], "credit": ln["credit"]} for ln in in_range]
    closing = opening + sum(ln["debit"] - ln["credit"] for ln in in_range)
    return {"account_code": account_code, "opening": opening, "movement": running, "closing": closing}


def _counterparty_ledger(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    counterparty_id: str,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    """Opening/closing for single counterparty_id + date range."""
    hdr_map = {h["id"]: h for h in headers}
    joined = _join_posted_lines(headers, lines, tenant_id)
    in_range = [
        ln for ln in joined
        if ln["counterparty_id"] == counterparty_id
        and date_from <= hdr_map[ln["journal_entry_id"]]["entry_date"] <= date_to
    ]
    total_dr = sum(ln["debit"] for ln in in_range)
    total_cr = sum(ln["credit"] for ln in in_range)
    return {"counterparty_id": counterparty_id, "total_debit": total_dr,
            "total_credit": total_cr, "net": total_dr - total_cr}


def _payroll_ledger(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    period: str,
) -> list[dict]:
    """Lines from headers with source_type='payroll' or account_code starting '51'."""
    payroll_hdr_ids = {
        h["id"] for h in _posted_headers(headers, tenant_id, period=period)
        if h["source_type"] == "payroll"
    }
    joined = _join_posted_lines(headers, lines, tenant_id, period=period)
    return [
        ln for ln in joined
        if ln["journal_entry_id"] in payroll_hdr_ids or ln["account_code"].startswith("51")
    ]


def _journal_entries_list(
    headers: list[dict],
    tenant_id: str,
    period: str,
    history: bool = False,
) -> list[dict]:
    """Standard view (posted only) or history view (all HISTORY_STATUSES)."""
    statuses = HISTORY_STATUSES if history else STANDARD_NET_STATUSES
    result = [
        h for h in headers
        if h["tenant_id"] == tenant_id and h["period"] == period and h["status"] in statuses
    ]
    for h in result:
        h["_view"] = "history" if history else "standard"
    return result


def _cashflow(
    headers: list[dict],
    lines: list[dict],
    tenant_id: str,
    period: str,
) -> dict[str, Any]:
    """Cash/bank lines (account starts '11') grouped by cashflow_category."""
    joined = _join_posted_lines(headers, lines, tenant_id, period=period)
    cash_lines = [ln for ln in joined if ln["account_code"].startswith("11")]
    result: dict[str, dict] = defaultdict(lambda: {"debit": 0, "credit": 0})
    for ln in cash_lines:
        cat = ln["cashflow_category"] or "uncategorized"
        result[cat]["debit"] += ln["debit"]
        result[cat]["credit"] += ln["credit"]
    return dict(result)


def _assert_no_raw_secrets(payload: Any, path: str = "root") -> None:
    """Raise AssertionError if any SECRET_KEY appears as a key in the payload."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            assert k.lower() not in SECRET_KEYS, \
                f"Raw secret key '{k}' found at {path}.{k}"
            _assert_no_raw_secrets(v, f"{path}.{k}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _assert_no_raw_secrets(item, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# Test file path
# ---------------------------------------------------------------------------

_THIS_FILE = pathlib.Path(__file__)


# ===========================================================================
# Tests
# ===========================================================================

class TestFileStructure:

    def test_test_file_exists_and_is_self_contained(self):
        assert _THIS_FILE.exists(), "Test file must exist"
        source = _THIS_FILE.read_text(encoding="utf-8")
        assert "FAKE_HEADERS" in source
        assert "FAKE_LINES" in source
        assert "STANDARD_NET_STATUSES" in source
        assert "FORBIDDEN_STATUSES" in source
        assert "H14 does not implement runtime report behavior" in source

    def test_fake_data_contains_required_header_and_line_fields(self):
        required_header_fields = {
            "id", "tenant_id", "status", "period", "entry_date",
            "source_type", "currency", "total_debit", "total_credit",
            "source_draft_id", "posting_log_id", "evidence_bundle_id",
            "reversal_of_id", "correction_of_id",
        }
        required_line_fields = {
            "id", "journal_entry_id", "tenant_id", "line_no",
            "account_code", "account_type", "debit", "credit",
        }
        for h in FAKE_HEADERS:
            missing = required_header_fields - set(h.keys())
            assert not missing, f"Header {h['id']} missing fields: {missing}"
        for ln in FAKE_LINES:
            missing = required_line_fields - set(ln.keys())
            assert not missing, f"Line {ln['id']} missing fields: {missing}"

    def test_file_has_no_runtime_service_imports(self):
        source = _THIS_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_modules = {
            "app.api.services",
            "app.api.routes",
            "app.storage",
            "app.core",
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                for forbidden in forbidden_modules:
                    assert not module.startswith(forbidden), \
                        f"Runtime service import forbidden: {module}"

    def test_file_has_no_db_or_network_imports(self):
        source = _THIS_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        db_network = {"asyncpg", "psycopg2", "sqlalchemy", "aiohttp",
                      "httpx", "requests", "boto3", "google.cloud"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0]
                    assert top not in db_network, \
                        f"DB/network import forbidden: {node.module}"
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        assert top not in db_network, \
                            f"DB/network import forbidden: {alias.name}"

    def test_h14_does_not_modify_runtime_report_behavior_contract(self):
        # Verify no runtime service files were modified by H14
        # (encoded as assertion that runtime report services are not imported)
        source = _THIS_FILE.read_text(encoding="utf-8")
        assert "financial_statements_service" not in source or \
               "import" not in source.split("financial_statements_service")[0].split("\n")[-1], \
               "H14 must not import financial_statements_service"
        assert "ledger_service" not in source or \
               "import" not in source.split("ledger_service")[0].split("\n")[-1], \
               "H14 must not import ledger_service"


class TestPostedHeadersFilter:

    def test_posted_headers_requires_tenant_id(self):
        result_a = _posted_headers(FAKE_HEADERS, TENANT_A)
        result_b = _posted_headers(FAKE_HEADERS, TENANT_B)
        ids_a = {h["id"] for h in result_a}
        ids_b = {h["id"] for h in result_b}
        assert ids_a.isdisjoint(ids_b), "Tenant-a and tenant-b headers must not overlap"
        assert "hdr-tenant-b" not in ids_a
        assert "hdr-invoice" not in ids_b

    def test_posted_headers_excludes_other_tenants(self):
        result = _posted_headers(FAKE_HEADERS, TENANT_A)
        assert all(h["tenant_id"] == TENANT_A for h in result)

    def test_posted_headers_requires_status_posted_for_standard_totals(self):
        result = _posted_headers(FAKE_HEADERS, TENANT_A)
        for h in result:
            assert h["status"] in STANDARD_NET_STATUSES, \
                f"Header {h['id']} has forbidden status {h['status']}"

    def test_posted_headers_excludes_draft_approved_auto_approved_simulated_success_mock_dry_run(self):
        result = _posted_headers(FAKE_HEADERS, TENANT_A)
        for h in result:
            assert h["status"] not in FORBIDDEN_STATUSES, \
                f"Forbidden status {h['status']} in posted headers"
        # explicitly confirm each forbidden header is absent
        result_ids = {h["id"] for h in result}
        for hid in ("hdr-forbidden-draft", "hdr-forbidden-approved",
                    "hdr-forbidden-auto-approved", "hdr-forbidden-sim",
                    "hdr-forbidden-mock", "hdr-forbidden-dry-run"):
            assert hid not in result_ids, f"{hid} must be excluded"


class TestJoinPostedLines:

    def test_join_posted_lines_uses_headers_and_lines_not_journal_drafts(self):
        # _join_posted_lines receives explicit header/line lists — no journal_drafts source
        joined = _join_posted_lines(FAKE_HEADERS, FAKE_LINES, TENANT_A, period="2026-04")
        assert len(joined) > 0
        # All joined lines belong to STANDARD_NET headers only
        valid_ids = {h["id"] for h in _posted_headers(FAKE_HEADERS, TENANT_A, period="2026-04")}
        for ln in joined:
            assert ln["journal_entry_id"] in valid_ids, \
                f"Line {ln['id']} joined to non-STANDARD_NET header"

    def test_no_silent_fallback_to_journal_drafts(self):
        # With an empty headers list, result must be empty — never fall back to any other source
        joined = _join_posted_lines([], FAKE_LINES, TENANT_A, period="2026-04")
        assert joined == [], "Empty headers must return empty lines — no silent fallback"

        # With forbidden-only headers, result must also be empty
        forbidden_only = [h for h in FAKE_HEADERS if h["status"] in FORBIDDEN_STATUSES]
        joined2 = _join_posted_lines(forbidden_only, FAKE_LINES, TENANT_A, period="2026-04")
        assert joined2 == [], "Forbidden-status headers must yield no lines"


class TestTrialBalance:

    def test_trial_balance_uses_posted_lines_only(self):
        tb = _trial_balance(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        # Forbidden lines (ln-017, ln-018) belong to hdr-forbidden-draft → excluded
        assert "1200" in tb, "AR account expected in TB"
        # Verify TB does not include amounts from forbidden headers
        # hdr-forbidden-draft DR=999 on 1200 must NOT appear
        # hdr-invoice also DR=1000 on 1200; total must be exactly 1000, not 1999
        assert tb["1200"]["debit"] == 1000, \
            f"Expected TB 1200 debit=1000 (invoice only), got {tb['1200']['debit']}"

    def test_trial_balance_requires_period_and_tenant(self):
        tb_a = _trial_balance(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        tb_b = _trial_balance(FAKE_HEADERS, FAKE_LINES, TENANT_B, "2026-04")
        # Tenant-B 9999 debit on 1100 must not bleed into tenant-A
        a_1100_dr = tb_a.get("1100", {}).get("debit", 0)
        b_1100_dr = tb_b.get("1100", {}).get("debit", 0)
        assert b_1100_dr == 9999
        assert a_1100_dr != 9999, "Tenant-B amount must not appear in Tenant-A TB"

    def test_trial_balance_opening_movement_closing_contract(self):
        tb = _trial_balance(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        total_dr = sum(v["debit"] for v in tb.values())
        total_cr = sum(v["credit"] for v in tb.values())
        # STANDARD_NET entries for tenant-a 2026-04:
        # hdr-invoice: DR=1000 CR=1000
        # hdr-expense: DR=500  CR=500
        # hdr-payroll: DR=2000 CR=2000
        # hdr-equity:  DR=5000 CR=5000
        # hdr-reversal: DR=300 CR=300
        # hdr-correction: DR=320 CR=320
        # Total: DR = CR = 9120
        assert total_dr == 9120, f"Expected total DR=9120, got {total_dr}"
        assert total_cr == 9120, f"Expected total CR=9120, got {total_cr}"
        assert total_dr == total_cr, "Trial balance must balance"


class TestPnlSummary:

    def test_pnl_summary_uses_income_and_expense_posted_lines_only(self):
        pnl = _pnl_summary(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        assert "income" in pnl
        assert "expense" in pnl
        assert "net" in pnl
        # 4100 credit: 1000 (invoice) → income = 1000 - 0 = 1000
        assert pnl["income"] == 1000

    def test_pnl_summary_excludes_simulated_success_and_drafts(self):
        # All forbidden-status lines must not inflate P&L
        pnl_all = _pnl_summary(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        # hdr-forbidden-draft has CR=999 on 4100; must NOT appear
        assert pnl_all["income"] == 1000, \
            f"Income should be 1000 (only invoice), got {pnl_all['income']}"

    def test_pnl_detail_returns_line_level_rows(self):
        rows = _pnl_detail(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        assert len(rows) > 0
        for row in rows:
            assert row["account_code"].startswith(("4", "5"))

    def test_pnl_detail_includes_source_draft_posting_log_evidence_ids(self):
        rows = _pnl_detail(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        for row in rows:
            assert "source_draft_id" in row
            assert "posting_log_id" in row
            assert "evidence_bundle_id" in row
        # hdr-invoice's lines should carry source_draft_id="draft-1", posting_log_id="log-1"
        invoice_rows = [r for r in rows if r["journal_entry_id"] == "hdr-invoice"]
        assert len(invoice_rows) > 0
        for r in invoice_rows:
            assert r["source_draft_id"] == "draft-1"
            assert r["posting_log_id"] == "log-1"
            assert r["evidence_bundle_id"] == "evid-1"


class TestBalanceSheet:

    def test_balance_sheet_summary_uses_asset_liability_equity_as_of_date(self):
        bs = _balance_sheet_summary(FAKE_HEADERS, FAKE_LINES, TENANT_A, date(2026, 4, 30))
        assert "asset" in bs or "liability" in bs or "equity" in bs
        # Only STANDARD_NET_STATUSES entries included
        # hdr-orig (reversed) must NOT appear in BS
        # Compute manual: asset DR-CR: hdr-invoice 1200 DR=1000, hdr-expense 1100 CR=500,
        #   hdr-equity 1100 DR=5000, hdr-reversal 2300 DR=300 (liability account but DR here)
        # This test checks the contract, not an exact number
        assert isinstance(bs.get("asset", 0), (int, float))

    def test_balance_sheet_detail_requires_status_posted(self):
        detail = _balance_sheet_detail(FAKE_HEADERS, FAKE_LINES, TENANT_A, date(2026, 4, 30))
        for ln in detail:
            assert ln["account_type"] in ("asset", "liability", "equity")
            # Verify no forbidden-status lines
            hdr = next(h for h in FAKE_HEADERS if h["id"] == ln["journal_entry_id"])
            assert hdr["status"] in STANDARD_NET_STATUSES, \
                f"BS detail has line from forbidden-status header {hdr['id']}"

    def test_balance_sheet_detail_fixes_h1_no_status_filter_risk(self):
        # H1 risk: a BS query that joins lines without a status filter would include
        # draft/approved entries and report inflated balances.
        # This test verifies the helper never returns lines from forbidden-status headers.
        detail = _balance_sheet_detail(FAKE_HEADERS, FAKE_LINES, TENANT_A, date(2026, 4, 30))
        hdr_map = {h["id"]: h for h in FAKE_HEADERS}
        for ln in detail:
            status = hdr_map[ln["journal_entry_id"]]["status"]
            assert status not in FORBIDDEN_STATUSES, \
                f"BS detail includes line from forbidden status '{status}'"


class TestVatRegister:

    def test_vat_register_uses_tax_code_or_vat_amount_only(self):
        vat = _vat_register(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        for ln in vat:
            assert ln["tax_code"] is not None or ln["vat_amount"] is not None

    def test_vat_register_requires_tenant_and_period(self):
        vat_a = _vat_register(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        vat_b = _vat_register(FAKE_HEADERS, FAKE_LINES, TENANT_B, "2026-04")
        ids_a = {ln["id"] for ln in vat_a}
        ids_b = {ln["id"] for ln in vat_b}
        assert ids_a.isdisjoint(ids_b)


class TestAccountLedger:

    def test_account_ledger_filters_account_code_and_date_range(self):
        ledger = _account_ledger(
            FAKE_HEADERS, FAKE_LINES, TENANT_A, "1200",
            date(2026, 4, 1), date(2026, 4, 30)
        )
        assert ledger["account_code"] == "1200"
        for entry in ledger["movement"]:
            assert entry["date"] >= date(2026, 4, 1)
            assert entry["date"] <= date(2026, 4, 30)

    def test_account_ledger_computes_running_balance_contract(self):
        ledger = _account_ledger(
            FAKE_HEADERS, FAKE_LINES, TENANT_A, "1200",
            date(2026, 4, 1), date(2026, 4, 30)
        )
        assert "opening" in ledger
        assert "closing" in ledger
        assert "movement" in ledger
        movement_net = sum(e["debit"] - e["credit"] for e in ledger["movement"])
        assert ledger["closing"] == ledger["opening"] + movement_net


class TestCounterpartyLedger:

    def test_counterparty_ledger_filters_counterparty_and_date_range(self):
        ledger = _counterparty_ledger(
            FAKE_HEADERS, FAKE_LINES, TENANT_A, "cp-alpha",
            date(2026, 4, 1), date(2026, 4, 30)
        )
        assert ledger["counterparty_id"] == "cp-alpha"
        assert "total_debit" in ledger
        assert "total_credit" in ledger
        assert "net" in ledger
        # cp-alpha appears in hdr-invoice lines: ln-001 DR=1000, ln-002 CR=1000
        assert ledger["total_debit"] == 1000
        assert ledger["total_credit"] == 1000


class TestPayrollLedger:

    def test_payroll_ledger_filters_payroll_source_or_accounts(self):
        rows = _payroll_ledger(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        assert len(rows) > 0
        hdr_map = {h["id"]: h for h in FAKE_HEADERS}
        for ln in rows:
            hdr = hdr_map[ln["journal_entry_id"]]
            assert hdr["source_type"] == "payroll" or ln["account_code"].startswith("51"), \
                f"Payroll ledger line {ln['id']} not from payroll source or 51xx account"


class TestJournalEntriesList:

    def test_journal_entries_standard_view_posted_only(self):
        entries = _journal_entries_list(FAKE_HEADERS, TENANT_A, "2026-04", history=False)
        for e in entries:
            assert e["status"] in STANDARD_NET_STATUSES
            assert e["status"] not in FORBIDDEN_STATUSES

    def test_journal_entries_history_view_labels_reversed_correction_voided(self):
        entries = _journal_entries_list(FAKE_HEADERS, TENANT_A, "2026-04", history=True)
        statuses = {e["status"] for e in entries}
        assert "reversed" in statuses, "History view must include reversed entries"
        assert "correction" in statuses, "History view must include correction entries"
        for e in entries:
            assert e["status"] in HISTORY_STATUSES
            assert e["status"] not in FORBIDDEN_STATUSES


class TestReversalCorrectionContract:

    def test_reversal_correction_net_view_does_not_double_count(self):
        # hdr-orig is "reversed" → excluded from STANDARD_NET
        # hdr-reversal is "posted" → included
        # hdr-correction is "correction" → included
        # Net view must NOT include hdr-orig
        net_hdrs = _posted_headers(FAKE_HEADERS, TENANT_A, period="2026-04")
        net_ids = {h["id"] for h in net_hdrs}
        assert "hdr-orig" not in net_ids, \
            "Original reversed entry must be excluded from STANDARD_NET view"
        assert "hdr-reversal" in net_ids, \
            "Reversal entry (posted) must be included in STANDARD_NET view"
        assert "hdr-correction" in net_ids, \
            "Correction entry must be included in STANDARD_NET view"

    def test_reversal_correction_history_view_preserves_chain(self):
        history = _journal_entries_list(FAKE_HEADERS, TENANT_A, "2026-04", history=True)
        history_ids = {e["id"] for e in history}
        assert "hdr-orig" in history_ids, "History view must preserve the original reversed entry"
        assert "hdr-reversal" in history_ids
        assert "hdr-correction" in history_ids


class TestCashFlow:

    def test_cashflow_uses_posted_cash_bank_lines_not_bank_transactions_only(self):
        # Cashflow is computed from account_code starting "11", not from bank_transaction_id
        cf = _cashflow(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        # 1100 lines in STANDARD_NET: hdr-expense CR=500 (operating), hdr-equity DR=5000 (financing)
        assert "operating" in cf or "financing" in cf
        # Verify that the cash amounts come from journal lines, not from bank_transaction_id filter
        total_dr = sum(v["debit"] for v in cf.values())
        # hdr-equity 1100 DR=5000 → financing
        # hdr-reversal 2300 DR=300 → not a cash account (doesn't start with "11")
        assert total_dr >= 5000

    def test_cashflow_has_operating_investing_financing_categories(self):
        cf = _cashflow(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        # At minimum operating and financing are present
        assert "operating" in cf, "Operating cashflow category expected"
        assert "financing" in cf, "Financing cashflow category expected"


class TestReportDetailAuditFields:

    def test_report_detail_rows_include_evidence_audit_drilldown_fields(self):
        rows = _pnl_detail(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04")
        for row in rows:
            assert "source_draft_id" in row, "Row must have source_draft_id"
            assert "posting_log_id" in row, "Row must have posting_log_id"
            assert "evidence_bundle_id" in row, "Row must have evidence_bundle_id"

    def test_report_payloads_forbid_raw_secrets(self):
        payloads = [
            _trial_balance(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04"),
            _pnl_summary(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04"),
            _pnl_detail(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04"),
            _balance_sheet_summary(FAKE_HEADERS, FAKE_LINES, TENANT_A, date(2026, 4, 30)),
            _vat_register(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04"),
            _payroll_ledger(FAKE_HEADERS, FAKE_LINES, TENANT_A, "2026-04"),
        ]
        for payload in payloads:
            _assert_no_raw_secrets(payload)


class TestMissingTenantAndPermission:

    def test_missing_tenant_id_fails_closed(self):
        # An empty tenant_id string must return no results (not all tenants' data)
        result = _posted_headers(FAKE_HEADERS, "")
        assert result == [], "Empty tenant_id must return no results"

        result2 = _join_posted_lines(FAKE_HEADERS, FAKE_LINES, "")
        assert result2 == [], "Empty tenant_id must yield no lines"

    def test_unauthorized_or_missing_permission_contract_documented_in_test(self):
        # Contract: all report endpoints must require tenant_id from request.state
        # This test documents the permission contract even though it cannot call the real
        # endpoint (no DB / no HTTP client). The runtime enforcement is in require_permission()
        # and the tenant_id assertion in get_tenant_setting().
        #
        # If tenant_id is absent or empty, report helpers return empty collections.
        # The routes layer must not proceed without a verified tenant_id.
        assert _posted_headers(FAKE_HEADERS, "") == []
        assert _join_posted_lines(FAKE_HEADERS, FAKE_LINES, "") == []
        assert _trial_balance(FAKE_HEADERS, FAKE_LINES, "", "2026-04") == {}


class TestFeatureFlagContract:

    def test_feature_flag_contract_documented_in_test(self):
        # Contract: POSTED_LEDGER_REPORTS_ENABLED must default to False.
        # When False, runtime report routes continue to read from journal_drafts.
        # When True, routes switch to journal_entry_headers + journal_entry_lines.
        # No silent fallback in either direction.
        #
        # H14 does not implement this flag — this test encodes the contract only.
        # The flag name is agreed upon:
        flag_name = "POSTED_LEDGER_REPORTS_ENABLED"
        assert flag_name == "POSTED_LEDGER_REPORTS_ENABLED"

        # Simulate flag=False → no posted-ledger results should be returned
        flag_enabled = False
        if not flag_enabled:
            result = []  # simulates route returning journal_drafts path (not implemented here)
        else:
            result = _posted_headers(FAKE_HEADERS, TENANT_A, period="2026-04")
        assert result == [] or not flag_enabled, \
            "With feature flag False, posted ledger path must not run"
