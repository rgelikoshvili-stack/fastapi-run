"""app/api/services/bank_format_detector.py

Sprint 3B — Bank export format auto-detection.
Detects TBC, BOG (Bank of Georgia), or UNKNOWN from filename + content.
No network calls, no credentials.
"""
from __future__ import annotations

import re

# Keyword sets for each bank — checked in content and filename
_TBC_MARKERS = frozenset([
    "tbcbank", "tbc bank", "mygemini", "tbc_", "_tbc",
    "tbcgroup", "joint stock company tbc bank",
])
_BOG_MARKERS = frozenset([
    "bankofgeorgia", "bank of georgia", "bog_", "_bog",
    "joint stock company bank of georgia", "jsck bank of georgia",
])

_KNOWN_CURRENCIES = {"gel", "usd", "eur", "gbp"}


def detect_bank(filename: str, content: bytes) -> str:
    """Return 'TBC', 'BOG', or 'UNKNOWN'."""
    name = filename.lower()
    for m in _TBC_MARKERS:
        if m in name:
            return "TBC"
    for m in _BOG_MARKERS:
        if m in name:
            return "BOG"

    # Scan first 4 KB of content
    snippet = content[:4096].decode("utf-8", errors="replace").lower()
    for m in _TBC_MARKERS:
        if m in snippet:
            return "TBC"
    for m in _BOG_MARKERS:
        if m in snippet:
            return "BOG"

    # Column-header heuristics for TBC XLSX/CSV
    # TBC: "ოპ. თარიღი", "ვალ. თარიღი", "გასული", "შემოსული"
    if "ოპ. თარიღი" in snippet or "ვალ. თარიღი" in snippet:
        return "TBC"
    # BOG: "გადახდის თარიღი", "ვალუტა", "თანხა", specific BOG pattern
    if "გადახდის თარიღი" in snippet:
        return "BOG"

    return "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# Column-name maps for TBC and BOG (mapped to our internal field names)
# ─────────────────────────────────────────────────────────────────────────────

# TBC exports (CSV/XLSX) — column name variants
TBC_COL_MAP = {
    "date": [
        "ოპ. თარიღი", "operation date", "oper. date", "op. date",
        "date", "transaction date", "valuedate", "value date",
    ],
    "description": [
        "დეტალები", "details", "description", "narrative",
        "operation description", "designation",
    ],
    "paid_out": [
        "გასული", "debit", "paid out", "withdrawal",
        "withdrawalamt", "expense", "debit amount",
    ],
    "paid_in": [
        "შემოსული", "credit", "paid in", "deposit",
        "depositamt", "income", "credit amount",
    ],
    "balance": [
        "ნაშთი", "balance", "account balance", "closing balance",
        "balance after",
    ],
    "currency": [
        "ვალუტა", "currency", "ccy",
    ],
    "transaction_ref": [
        "reference no", "reference", "ref no", "doc no",
        "document no", "transaction id", "txn id", "order no",
    ],
    "partner": [
        "მიმღები / გამგზავნი", "counterparty", "partner", "beneficiary",
        "payer", "correspondent",
    ],
    "operation_code": [
        "ოპ. კოდი", "operation code", "operation type", "txn type",
        "transaction type",
    ],
}

# BOG exports (CSV/XLSX)
BOG_COL_MAP = {
    "date": [
        "თარიღი", "date", "transaction date", "value date",
        "გადახდის თარიღი",
    ],
    "description": [
        "დანიშნულება", "description", "details", "purpose",
        "payment details", "narrative",
    ],
    "paid_out": [
        "გასული", "debit", "paid out", "withdrawal",
        "debit amount", "გადახდა",
    ],
    "paid_in": [
        "შემოსული", "credit", "paid in", "receipt",
        "credit amount", "ჩარიცხვა",
    ],
    "balance": [
        "ნაშთი", "balance", "closing balance",
    ],
    "currency": [
        "ვალუტა", "currency", "ccy",
    ],
    "transaction_ref": [
        "დოკ. ნომ.", "document number", "reference", "ref", "doc no",
        "transaction reference",
    ],
    "partner": [
        "კონტრაჰენტი", "counterparty", "partner", "correspondent",
        "sender/receiver",
    ],
    "operation_code": [
        "ოპ. კოდი", "operation code",
    ],
}

GENERIC_COL_MAP = {
    "date": ["date", "Date", "transaction_date", "value_date"],
    "description": ["description", "Description", "details", "Details", "narrative"],
    "paid_out": ["paid_out", "debit", "Debit", "withdrawal", "WithdrawalAmt"],
    "paid_in": ["paid_in", "credit", "Credit", "deposit", "DepositAmt"],
    "balance": ["balance", "Balance", "closing_balance"],
    "currency": ["currency", "Currency", "ccy"],
    "transaction_ref": ["transaction_id", "reference", "ref_no", "doc_no", "RefNo"],
    "partner": ["partner", "Partner", "counterparty", "Counterparty"],
    "operation_code": ["operation_code", "OperationCode", "txn_type"],
}


def get_col_map(bank: str) -> dict:
    if bank == "TBC":
        return TBC_COL_MAP
    if bank == "BOG":
        return BOG_COL_MAP
    return GENERIC_COL_MAP


def extract_partner_from_description(description: str | None) -> str | None:
    """Try to extract partner/counterparty name from a bank description string.

    Georgian bank descriptions often contain: "Transfer to: Company Name LLC"
    or "From: Company Name, details: ..."
    """
    if not description:
        return None
    desc = description.strip()
    # Georgian patterns
    patterns = [
        r"(?:მიმღები|გამგზავნი|beneficiary|counterparty|from|to)[:\s]+([^\,;/\n]{3,60})",
        r"(?:transfer to|payment to|საბანკო გადარიცხვა)[:\s]+([^\,;/\n]{3,60})",
    ]
    for pat in patterns:
        m = re.search(pat, desc, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if len(candidate) >= 3:
                return candidate[:120]
    return None
