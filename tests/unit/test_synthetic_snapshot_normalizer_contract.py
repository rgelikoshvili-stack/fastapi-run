"""
H28 — Synthetic Snapshot Normalizer Contract.

Local contract prototypes for canonical_money, canonical_row_key, and
normalize_report_snapshot.  These helpers are defined here only — they are
NOT imported from or added to any app module.

No DB, no SQL, no migrations, no fixture load, no runtime API calls.
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


# ---------------------------------------------------------------------------
# Local prototype helpers (contract only — not production implementations)
# ---------------------------------------------------------------------------

REPORT_NAME_MAPPING = {
    "trial_balance": "Trial Balance",
    "pl_summary": "P&L Summary",
    "pl_detail": "P&L Detail",
    "balance_sheet_summary": "Balance Sheet Summary",
    "balance_sheet_detail": "Balance Sheet Detail",
    "vat_register": "VAT Register",
    "account_ledger": "Account Ledger",
    "counterparty_ledger": "Counterparty Ledger",
    "payroll_ledger": "Payroll Ledger",
    "journal_entries_list": "Journal Entries List",
    "cashflow": "Cashflow",
}

STANDARD_STATUS_POLICY = {
    "included": ["posted", "correction"],
    "excluded": ["reversed", "voided", "draft", "pending_approval", "rejected"],
}


def canonical_money(value) -> str:
    """Convert any money value to a canonical 2-decimal-place string."""
    if value is None:
        return "0.00"
    try:
        d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return str(d)
    except (InvalidOperation, ValueError):
        raise ValueError(
            f"NORMALIZATION_MONEY_PARSE_ERROR: cannot parse money value {value!r}"
        )


def canonical_row_key(row: dict, *, report_name: str) -> str:
    """Derive a stable row key using the priority hierarchy from Section 7."""
    # Priority 1 — ledger_line_id
    if row.get("ledger_line_id"):
        return f"{report_name}|{row['ledger_line_id']}"
    # Priority 2 — journal_entry_id
    if row.get("journal_entry_id"):
        return f"{report_name}|{row['journal_entry_id']}"
    # Priority 3 — counterparty_id
    if row.get("counterparty_id"):
        return f"{report_name}|{row['counterparty_id']}"
    # Priority 4 — account_code
    if row.get("account_code"):
        tenant = row.get("tenant_id", "")
        return f"{report_name}|{tenant}|{row['account_code']}"
    # Priority 5 — period
    if row.get("period"):
        tenant = row.get("tenant_id", "")
        return f"{report_name}|{tenant}|{row['period']}"
    # Fallback composite
    parts = [
        str(row.get(k, ""))
        for k in ("tenant_id", "account_code", "counterparty_id", "journal_entry_id", "ledger_line_id", "period")
        if row.get(k)
    ]
    key = "|".join([report_name] + parts)
    if not key.replace(report_name, "").strip("|"):
        raise ValueError(
            f"NORMALIZATION_UNSTABLE_ROW_KEY: cannot derive stable key from row {row!r}"
        )
    return key


def normalize_report_snapshot(
    raw: dict,
    *,
    source: str,
    report_name: str,
    tenant_id: str,
) -> dict:
    """Produce a canonical normalized snapshot dict from a raw report output."""
    if not tenant_id:
        raise ValueError("NORMALIZATION_TENANT_MISSING: tenant_id is required")

    canonical_name = REPORT_NAME_MAPPING.get(report_name)
    if not canonical_name:
        raise ValueError(
            f"NORMALIZATION_UNKNOWN_REPORT: {report_name!r} is not a known report key"
        )

    currency = raw.get("currency", "GEL")
    if currency != "GEL":
        raise ValueError(
            f"NORMALIZATION_CURRENCY_MISMATCH: expected GEL, got {currency!r}"
        )

    status_policy = raw.get("status_policy")
    if not status_policy or "included" not in status_policy or "excluded" not in status_policy:
        raise ValueError(
            "NORMALIZATION_STATUS_POLICY_MISSING: status_policy with included/excluded is required"
        )

    raw_totals = {
        k: v for k, v in raw.items()
        if isinstance(v, (int, float, str, Decimal)) and not k.startswith("_") and k not in (
            "report_name", "tenant_id", "currency", "generated_from",
            "period", "status_policy", "rows", "metadata",
        )
    }
    if not raw_totals:
        raise ValueError(
            "NORMALIZATION_REQUIRED_FIELD_MISSING: totals must not be empty"
        )

    normalized_totals = {}
    for k, v in raw_totals.items():
        try:
            normalized_totals[k] = canonical_money(v)
        except ValueError:
            raise ValueError(
                f"NORMALIZATION_MONEY_PARSE_ERROR: field {k!r} value {v!r} cannot be parsed"
            )

    rows = raw.get("rows") or []
    metadata = raw.get("metadata") or {}
    period = raw.get("period", {})

    return {
        "report_name": canonical_name,
        "tenant_id": tenant_id,
        "period": period,
        "currency": "GEL",
        "generated_from": source,
        "status_policy": status_policy,
        "totals": normalized_totals,
        "rows": rows,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Minimal raw snapshot helpers used by multiple tests
# ---------------------------------------------------------------------------

def _minimal_raw(report_key: str, totals: dict | None = None) -> dict:
    """Build a minimal valid raw snapshot for normalization tests."""
    t = totals or {"total_dr": "14480.00", "total_cr": "14480.00"}
    snap = {
        "currency": "GEL",
        "status_policy": {
            "included": ["posted", "correction"],
            "excluded": ["reversed", "voided", "draft", "pending_approval", "rejected"],
        },
        "rows": [],
        "metadata": {},
        "period": {"from": "2026-01-01", "to": "2026-01-31"},
    }
    snap.update(t)
    return snap


# ===========================================================================
# 1. REPORT_NAME_MAPPING contract
# ===========================================================================

def test_report_name_mapping_has_11_entries():
    assert len(REPORT_NAME_MAPPING) == 11


def test_report_name_mapping_all_snake_case_keys():
    for key in REPORT_NAME_MAPPING:
        assert key == key.lower(), f"Key {key!r} must be lowercase snake_case"
        assert " " not in key, f"Key {key!r} must not contain spaces"


def test_report_name_mapping_canonical_names():
    expected = {
        "trial_balance": "Trial Balance",
        "pl_summary": "P&L Summary",
        "pl_detail": "P&L Detail",
        "balance_sheet_summary": "Balance Sheet Summary",
        "balance_sheet_detail": "Balance Sheet Detail",
        "vat_register": "VAT Register",
        "account_ledger": "Account Ledger",
        "counterparty_ledger": "Counterparty Ledger",
        "payroll_ledger": "Payroll Ledger",
        "journal_entries_list": "Journal Entries List",
        "cashflow": "Cashflow",
    }
    assert REPORT_NAME_MAPPING == expected


def test_report_name_mapping_no_pl_summary_space_trap():
    # "pl_summary".replace("_"," ") -> "pl summary" — must NOT equal canonical name
    auto = "pl_summary".replace("_", " ")
    assert auto != REPORT_NAME_MAPPING["pl_summary"], (
        "Canonical P&L Summary must differ from naive replace"
    )


# ===========================================================================
# 2. canonical_money contract
# ===========================================================================

def test_canonical_money_int():
    assert canonical_money(1300) == "1300.00"


def test_canonical_money_float():
    assert canonical_money(1300.0) == "1300.00"


def test_canonical_money_str():
    assert canonical_money("1300.00") == "1300.00"


def test_canonical_money_none_returns_zero():
    assert canonical_money(None) == "0.00"


def test_canonical_money_negative():
    assert canonical_money(-1225) == "-1225.00"


def test_canonical_money_rounding():
    assert canonical_money("0.005") == "0.01"


def test_canonical_money_unparseable_raises():
    import pytest
    with pytest.raises(ValueError, match="NORMALIZATION_MONEY_PARSE_ERROR"):
        canonical_money("abc")


def test_canonical_money_two_decimal_places():
    result = canonical_money(14480)
    assert result.count(".") == 1
    assert len(result.split(".")[1]) == 2


def test_canonical_money_decimal_input():
    assert canonical_money(Decimal("4475.00")) == "4475.00"


# ===========================================================================
# 3. canonical_row_key priority hierarchy
# ===========================================================================

def test_row_key_priority_ledger_line_id():
    row = {"ledger_line_id": "LL001", "account_code": "1010", "journal_entry_id": "H007"}
    key = canonical_row_key(row, report_name="account_ledger")
    assert "LL001" in key


def test_row_key_priority_journal_entry_id_over_account():
    row = {"journal_entry_id": "H001", "account_code": "1010"}
    key = canonical_row_key(row, report_name="journal_entries_list")
    assert "H001" in key
    # ledger_line_id absent → journal_entry_id wins over account_code
    assert "1010" not in key or "H001" in key


def test_row_key_priority_counterparty_id():
    row = {"counterparty_id": "SYN-CUST-0001"}
    key = canonical_row_key(row, report_name="counterparty_ledger")
    assert "SYN-CUST-0001" in key


def test_row_key_priority_account_code():
    row = {"account_code": "1200", "tenant_id": "tenant_alpha"}
    key = canonical_row_key(row, report_name="trial_balance")
    assert "1200" in key
    assert "tenant_alpha" in key


def test_row_key_priority_period():
    row = {"period": "2026-01", "tenant_id": "tenant_alpha"}
    key = canonical_row_key(row, report_name="payroll_ledger")
    assert "2026-01" in key


def test_row_key_empty_row_raises():
    import pytest
    with pytest.raises(ValueError, match="NORMALIZATION_UNSTABLE_ROW_KEY"):
        canonical_row_key({}, report_name="trial_balance")


def test_row_key_is_deterministic():
    row = {"account_code": "1010", "tenant_id": "tenant_alpha"}
    k1 = canonical_row_key(row, report_name="trial_balance")
    k2 = canonical_row_key(row, report_name="trial_balance")
    assert k1 == k2


# ===========================================================================
# 4. normalize_report_snapshot contract
# ===========================================================================

def test_normalize_missing_tenant_raises():
    import pytest
    raw = _minimal_raw("trial_balance")
    with pytest.raises(ValueError, match="NORMALIZATION_TENANT_MISSING"):
        normalize_report_snapshot(raw, source="expected_fixture", report_name="trial_balance", tenant_id="")


def test_normalize_unknown_report_raises():
    import pytest
    raw = _minimal_raw("trial_balance")
    with pytest.raises(ValueError, match="NORMALIZATION_UNKNOWN_REPORT"):
        normalize_report_snapshot(raw, source="expected_fixture", report_name="unknown_report", tenant_id="tenant_alpha")


def test_normalize_currency_mismatch_raises():
    import pytest
    raw = _minimal_raw("trial_balance")
    raw["currency"] = "USD"
    with pytest.raises(ValueError, match="NORMALIZATION_CURRENCY_MISMATCH"):
        normalize_report_snapshot(raw, source="expected_fixture", report_name="trial_balance", tenant_id="tenant_alpha")


def test_normalize_status_policy_missing_raises():
    import pytest
    raw = _minimal_raw("trial_balance")
    del raw["status_policy"]
    with pytest.raises(ValueError, match="NORMALIZATION_STATUS_POLICY_MISSING"):
        normalize_report_snapshot(raw, source="expected_fixture", report_name="trial_balance", tenant_id="tenant_alpha")


def test_normalize_empty_totals_raises():
    import pytest
    raw = {
        "currency": "GEL",
        "status_policy": STANDARD_STATUS_POLICY,
        "rows": [],
        "metadata": {},
        "period": {"from": "2026-01-01", "to": "2026-01-31"},
    }
    with pytest.raises(ValueError, match="NORMALIZATION_REQUIRED_FIELD_MISSING"):
        normalize_report_snapshot(raw, source="expected_fixture", report_name="trial_balance", tenant_id="tenant_alpha")


def test_normalize_trial_balance_shape():
    raw = _minimal_raw("trial_balance")
    result = normalize_report_snapshot(
        raw, source="expected_fixture", report_name="trial_balance", tenant_id="tenant_alpha"
    )
    assert result["report_name"] == "Trial Balance"
    assert result["tenant_id"] == "tenant_alpha"
    assert result["currency"] == "GEL"
    assert result["generated_from"] == "expected_fixture"
    assert "included" in result["status_policy"]
    assert "excluded" in result["status_policy"]
    assert "totals" in result
    assert "rows" in result
    assert "metadata" in result


def test_normalize_pl_summary_canonical_name():
    raw = _minimal_raw("pl_summary", totals={"total_income": "2300.00", "total_expense": "3525.00", "net_profit_loss": "-1225.00"})
    result = normalize_report_snapshot(
        raw, source="expected_fixture", report_name="pl_summary", tenant_id="tenant_alpha"
    )
    assert result["report_name"] == "P&L Summary"


def test_normalize_money_values_are_canonical_strings():
    raw = _minimal_raw("trial_balance", totals={"total_dr": 14480, "total_cr": 14480.0})
    result = normalize_report_snapshot(
        raw, source="expected_fixture", report_name="trial_balance", tenant_id="tenant_alpha"
    )
    assert result["totals"]["total_dr"] == "14480.00"
    assert result["totals"]["total_cr"] == "14480.00"


def test_normalize_rows_none_becomes_empty_list():
    raw = _minimal_raw("trial_balance")
    raw["rows"] = None
    result = normalize_report_snapshot(
        raw, source="expected_fixture", report_name="trial_balance", tenant_id="tenant_alpha"
    )
    assert result["rows"] == []


def test_normalize_metadata_none_becomes_empty_dict():
    raw = _minimal_raw("trial_balance")
    raw["metadata"] = None
    result = normalize_report_snapshot(
        raw, source="expected_fixture", report_name="trial_balance", tenant_id="tenant_alpha"
    )
    assert result["metadata"] == {}


# ===========================================================================
# 5. Doc contract assertions
# ===========================================================================

def test_doc_exists():
    import os
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs",
        "synthetic-snapshot-normalizer-contract.md",
    )
    assert os.path.isfile(doc_path), "H28 doc must exist"


def test_doc_has_normalization_error_codes():
    import os
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs",
        "synthetic-snapshot-normalizer-contract.md",
    )
    with open(doc_path, encoding="utf-8") as f:
        text = f.read()
    codes = [
        "NORMALIZATION_REQUIRED_FIELD_MISSING",
        "NORMALIZATION_MONEY_PARSE_ERROR",
        "NORMALIZATION_DATE_PARSE_ERROR",
        "NORMALIZATION_UNSTABLE_ROW_KEY",
        "NORMALIZATION_TENANT_MISSING",
        "NORMALIZATION_CURRENCY_MISMATCH",
        "NORMALIZATION_STATUS_POLICY_MISSING",
        "NORMALIZATION_DRILLDOWN_LINK_MISSING",
        "NORMALIZATION_EVIDENCE_LINK_MISSING",
        "NORMALIZATION_UNKNOWN_REPORT",
    ]
    for code in codes:
        assert code in text, f"Doc must define error code {code}"


def test_doc_has_all_11_report_names_in_mapping_section():
    import os
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs",
        "synthetic-snapshot-normalizer-contract.md",
    )
    with open(doc_path, encoding="utf-8") as f:
    	text = f.read()
    canonical_names = [
        "Trial Balance",
        "P&L Summary",
        "P&L Detail",
        "Balance Sheet Summary",
        "Balance Sheet Detail",
        "VAT Register",
        "Account Ledger",
        "Counterparty Ledger",
        "Payroll Ledger",
        "Journal Entries List",
        "Cashflow",
    ]
    for name in canonical_names:
        assert name in text, f"Doc must contain canonical report name {name!r}"


def test_doc_has_four_helper_signatures():
    import os
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs",
        "synthetic-snapshot-normalizer-contract.md",
    )
    with open(doc_path, encoding="utf-8") as f:
        text = f.read()
    signatures = [
        "normalize_report_snapshot",
        "normalize_report_rows",
        "canonical_money",
        "canonical_row_key",
    ]
    for sig in signatures:
        assert sig in text, f"Doc must define future helper signature {sig!r}"


def test_doc_states_no_app_code_modified():
    import os
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs",
        "synthetic-snapshot-normalizer-contract.md",
    )
    with open(doc_path, encoding="utf-8") as f:
        text = f.read().lower().replace("**", "").replace("*", "")
    assert "not implemented in app code" in text or "does not implement runtime helpers in app code" in text


def test_standard_status_policy_has_included_and_excluded():
    assert "included" in STANDARD_STATUS_POLICY
    assert "excluded" in STANDARD_STATUS_POLICY
    assert "posted" in STANDARD_STATUS_POLICY["included"]
    assert "correction" in STANDARD_STATUS_POLICY["included"]
    assert "reversed" in STANDARD_STATUS_POLICY["excluded"]
    assert "voided" in STANDARD_STATUS_POLICY["excluded"]
    assert "draft" in STANDARD_STATUS_POLICY["excluded"]
