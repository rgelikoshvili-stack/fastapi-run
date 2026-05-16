"""
H29 - Synthetic Snapshot Comparator Contract.

Local contract prototypes for comparing H28-normalized snapshots. These helpers
are defined only in this test file and are not app/runtime implementations.

No DB, no network, no migrations, no fixture load, no runtime API calls.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
H29_DOC = ROOT / "docs" / "synthetic-snapshot-comparator-contract.md"
H28_DOC = ROOT / "docs" / "synthetic-snapshot-normalizer-contract.md"
H27_DOC = ROOT / "docs" / "synthetic-fixture-report-snapshot-comparison-plan.md"
FIXTURE = ROOT / "tests" / "fixtures" / "posted_ledger" / "synthetic_posted_ledger_fixture_pack.json"

REPORT_NAMES = [
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

MISMATCH_CODES = [
    "SNAPSHOT_SHAPE_MISMATCH",
    "REPORT_TOTAL_MISMATCH",
    "ROW_COUNT_MISMATCH",
    "ROW_VALUE_MISMATCH",
    "ROUNDING_ONLY_DIFFERENCE",
    "TENANT_LEAKAGE",
    "STATUS_POLICY_MISMATCH",
    "CORRECTION_REVERSAL_MISMATCH",
    "DRILLDOWN_LINK_MISSING",
    "EVIDENCE_LINK_MISSING",
    "CASHFLOW_CLASSIFICATION_MISMATCH",
    "VAT_CLASSIFICATION_MISMATCH",
    "PAYROLL_CLASSIFICATION_MISMATCH",
    "CURRENCY_MISMATCH",
    "PERIOD_MISMATCH",
    "REPORT_NAME_MISMATCH",
    "ROW_KEY_MISSING",
    "REQUIRED_TOTAL_MISSING",
    "REQUIRED_ROW_MISSING",
    "UNEXPECTED_ROW_PRESENT",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _money(value) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def classify_mismatch(code: str, *, field: str | None = None, difference=None) -> dict:
    critical = {
        "SNAPSHOT_SHAPE_MISMATCH",
        "TENANT_LEAKAGE",
        "STATUS_POLICY_MISMATCH",
        "CURRENCY_MISMATCH",
        "PERIOD_MISMATCH",
        "REPORT_NAME_MISMATCH",
        "ROW_KEY_MISSING",
        "REQUIRED_TOTAL_MISSING",
        "REQUIRED_ROW_MISSING",
    }
    high = {
        "REPORT_TOTAL_MISMATCH",
        "ROW_VALUE_MISMATCH",
        "CORRECTION_REVERSAL_MISMATCH",
        "DRILLDOWN_LINK_MISSING",
        "EVIDENCE_LINK_MISSING",
        "CASHFLOW_CLASSIFICATION_MISMATCH",
        "VAT_CLASSIFICATION_MISMATCH",
        "PAYROLL_CLASSIFICATION_MISMATCH",
    }
    if code == "ROUNDING_ONLY_DIFFERENCE":
        severity = "rounding_only"
    elif code in critical:
        severity = "critical"
    elif code in high:
        severity = "high"
    elif code in {"ROW_COUNT_MISMATCH", "UNEXPECTED_ROW_PRESENT"}:
        severity = "medium"
    else:
        severity = "low"
    return {"code": code, "severity": severity, "field": field, "difference": difference}


def _mismatch(code: str, *, report_name="Trial Balance", tenant_id="tenant_alpha",
              row_key=None, field=None, expected=None, actual=None, difference=None,
              tolerance="0.01", path="", message="") -> dict:
    meta = classify_mismatch(code, field=field, difference=difference)
    return {
        "code": code,
        "severity": meta["severity"],
        "report_name": report_name,
        "tenant_id": tenant_id,
        "row_key": row_key,
        "field": field,
        "expected_value": expected,
        "actual_value": actual,
        "difference": difference,
        "tolerance": tolerance,
        "path": path,
        "message": message or code,
        "evidence": {},
        "classification_notes": [],
    }


def compare_totals(left_totals: dict, right_totals: dict, *, tolerance: Decimal) -> list[dict]:
    mismatches = []
    for key in sorted(set(left_totals) | set(right_totals)):
        if key not in left_totals or key not in right_totals:
            mismatches.append(_mismatch(
                "REQUIRED_TOTAL_MISSING",
                field=key,
                expected=left_totals.get(key),
                actual=right_totals.get(key),
                path=f"totals.{key}",
            ))
            continue
        left = Decimal(str(left_totals[key]))
        right = Decimal(str(right_totals[key]))
        diff = abs(left - right)
        if diff == 0:
            continue
        sign_changed = (left < 0 < right) or (right < 0 < left)
        code = "REPORT_TOTAL_MISMATCH" if diff > tolerance or sign_changed else "ROUNDING_ONLY_DIFFERENCE"
        mismatches.append(_mismatch(
            code,
            field=key,
            expected=_money(left),
            actual=_money(right),
            difference=_money(diff),
            tolerance=_money(tolerance),
            path=f"totals.{key}",
        ))
    return mismatches


def _row_map(rows: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    mapped = {}
    mismatches = []
    for row in rows:
        key = row.get("row_key")
        if not key:
            mismatches.append(_mismatch("ROW_KEY_MISSING", row_key=None, path="rows[].row_key"))
            continue
        if key in mapped:
            mismatches.append(_mismatch("SNAPSHOT_SHAPE_MISMATCH", row_key=key, path=f"rows.{key}"))
            continue
        mapped[key] = row
    return mapped, mismatches


def compare_rows(left_rows: list[dict], right_rows: list[dict], *, report_name: str,
                 tolerance: Decimal) -> list[dict]:
    left_map, mismatches = _row_map(left_rows)
    right_map, right_shape = _row_map(right_rows)
    mismatches.extend(right_shape)
    for key in sorted(set(left_map) - set(right_map)):
        mismatches.append(_mismatch("REQUIRED_ROW_MISSING", report_name=report_name, row_key=key, path=f"rows.{key}"))
    for key in sorted(set(right_map) - set(left_map)):
        mismatches.append(_mismatch("UNEXPECTED_ROW_PRESENT", report_name=report_name, row_key=key, path=f"rows.{key}"))
    for key in sorted(set(left_map) & set(right_map)):
        left_values = left_map[key].get("values", {})
        right_values = right_map[key].get("values", {})
        for field in sorted(set(left_values) | set(right_values)):
            if field not in left_values or field not in right_values:
                mismatches.append(_mismatch("ROW_VALUE_MISMATCH", report_name=report_name, row_key=key, field=field))
                continue
            left = Decimal(str(left_values[field]))
            right = Decimal(str(right_values[field]))
            diff = abs(left - right)
            if diff == 0:
                continue
            code = "ROW_VALUE_MISMATCH" if diff > tolerance else "ROUNDING_ONLY_DIFFERENCE"
            mismatches.append(_mismatch(
                code,
                report_name=report_name,
                row_key=key,
                field=field,
                expected=_money(left),
                actual=_money(right),
                difference=_money(diff),
                tolerance=_money(tolerance),
                path=f"rows.{key}.values.{field}",
            ))
    return mismatches


def _sample_snapshot() -> dict:
    return {
        "report_name": "Trial Balance",
        "tenant_id": "tenant_alpha",
        "period": {"from": "2026-01-01", "to": "2026-01-31"},
        "currency": "GEL",
        "generated_from": "expected_fixture",
        "status_policy": {
            "included": ["posted", "correction"],
            "excluded": ["reversed", "voided", "draft", "pending_approval", "rejected"],
        },
        "totals": {"total_dr": "14480.00", "total_cr": "14480.00"},
        "rows": [
            {"row_key": "trial_balance|tenant_alpha|1010", "tenant_id": "tenant_alpha",
             "account_code": "1010", "values": {"net_balance": "4475.00"}},
            {"row_key": "trial_balance|tenant_alpha|4100", "tenant_id": "tenant_alpha",
             "account_code": "4100", "values": {"net_balance": "-1800.00"}},
        ],
        "metadata": {},
    }


def compare_snapshots(left: dict, right: dict, *, context: dict) -> dict:
    tolerance = Decimal(str(context.get("tolerance", "0.01")))
    mismatches = []
    for field, code in [
        ("tenant_id", "TENANT_LEAKAGE"),
        ("currency", "CURRENCY_MISMATCH"),
        ("report_name", "REPORT_NAME_MISMATCH"),
        ("period", "PERIOD_MISMATCH"),
        ("status_policy", "STATUS_POLICY_MISMATCH"),
    ]:
        if left.get(field) != right.get(field):
            mismatches.append(_mismatch(
                code,
                report_name=context["report_name"],
                tenant_id=context["tenant_id"],
                field=field,
                expected=left.get(field),
                actual=right.get(field),
                path=field,
            ))
    mismatches.extend(compare_totals(left.get("totals", {}), right.get("totals", {}), tolerance=tolerance))
    mismatches.extend(compare_rows(left.get("rows", []), right.get("rows", []), report_name=context["report_name"], tolerance=tolerance))
    summary = {"total_mismatches": len(mismatches), "critical": 0, "high": 0, "medium": 0, "low": 0, "rounding_only": 0}
    for item in mismatches:
        summary[item["severity"]] += 1
    return {
        "ok": summary["critical"] == summary["high"] == summary["medium"] == 0,
        "comparison_name": context["comparison_name"],
        "report_name": context["report_name"],
        "tenant_id": context["tenant_id"],
        "period": context["period"],
        "currency": context["currency"],
        "summary": summary,
        "mismatches": mismatches,
        "metadata": {},
    }


def _context() -> dict:
    return {
        "comparison_name": "expected_vs_current_trial_balance",
        "left_label": "expected_fixture",
        "right_label": "posted_ledger",
        "report_name": "Trial Balance",
        "tenant_id": "tenant_alpha",
        "period": {"from": "2026-01-01", "to": "2026-01-31"},
        "currency": "GEL",
        "tolerance": "0.01",
    }


def test_h29_doc_exists():
    assert H29_DOC.is_file()


def test_h29_non_action_statement_present():
    text = _read(H29_DOC)
    for phrase in [
        "H29 is docs/tests only",
        "H29 does not create DB",
        "H29 does not connect to DB",
        "H29 does not execute SQL",
        "H29 does not run migrations",
        "H29 does not load fixtures into DB",
        "H29 does not call runtime report APIs",
        "H29 does not modify runtime report behavior",
        "H29 does not implement app/runtime helpers",
        "H29 does not enable feature flags",
        "H29 does not activate Balance.ge",
    ]:
        assert phrase in text


def test_comparator_input_contract_documented():
    text = _read(H29_DOC)
    for term in ["Comparator Input Contract", "left", "right", "comparison_context", "tolerance"]:
        assert term in text


def test_comparator_output_contract_documented():
    text = _read(H29_DOC)
    for term in ["Comparator Output Contract", "ok", "summary", "mismatches", "rounding_only"]:
        assert term in text


def test_mismatch_item_shape_documented():
    text = _read(H29_DOC)
    for field in ["code", "severity", "row_key", "expected_value", "actual_value", "classification_notes"]:
        assert field in text


def test_severity_rules_documented():
    text = _read(H29_DOC)
    for severity in ["critical", "high", "medium", "low", "rounding_only"]:
        assert severity in text


def test_all_mismatch_codes_documented():
    text = _read(H29_DOC)
    for code in MISMATCH_CODES:
        assert code in text


def test_numeric_comparison_rules_documented():
    text = _read(H29_DOC)
    for phrase in ["Decimal only", "Default tolerance is `0.01` GEL", "No tolerance for sign mismatch", "Float comparisons are forbidden"]:
        assert phrase in text


def test_row_matching_rules_documented():
    text = _read(H29_DOC)
    for phrase in ["Match rows by `row_key` first", "REQUIRED_ROW_MISSING", "UNEXPECTED_ROW_PRESENT", "order-independent"]:
        assert phrase in text


def test_hard_fail_rules_documented():
    text = _read(H29_DOC)
    for phrase in ["tenant_id mismatch", "currency mismatch", "report_name mismatch", "status policy mismatch", "missing required totals"]:
        assert phrase in text


def test_report_by_report_comparator_rules_for_all_11_reports():
    text = _read(H29_DOC)
    for name in REPORT_NAMES:
        assert f"| {name} |" in text


def test_comparison_modes_documented():
    text = _read(H29_DOC)
    for mode in ["strict_accounting", "accountant_review", "smoke"]:
        assert mode in text


def test_future_helper_design_documented():
    text = _read(H29_DOC)
    for sig in ["compare_snapshots", "compare_totals", "compare_rows", "classify_mismatch"]:
        assert sig in text
    assert "H29 does not implement app/runtime helpers" in text


def test_accountant_review_output_documented():
    text = _read(H29_DOC)
    for phrase in ["affected accounts", "affected counterparties", "affected journal entries", "sign-off checkbox"]:
        assert phrase in text


def test_future_old_vs_new_comparator_flow_documented():
    text = _read(H29_DOC)
    for phrase in ["Normalize legacy/current output", "Compare normalized snapshots", "block production", "sign-off"]:
        assert phrase.lower() in text.lower()


def test_safety_rules_documented():
    text = _read(H29_DOC)
    for phrase in ["No DB in H29", "No runtime API calls", "No feature flag", "No Balance.ge", "No connector changes", "No UI/static changes"]:
        assert phrase in text


def test_local_compare_totals_detects_exact_match():
    assert compare_totals({"total_dr": "10.00"}, {"total_dr": "10.00"}, tolerance=Decimal("0.01")) == []


def test_local_compare_totals_classifies_rounding_only_difference():
    mismatches = compare_totals({"total_dr": "10.00"}, {"total_dr": "10.01"}, tolerance=Decimal("0.01"))
    assert mismatches[0]["code"] == "ROUNDING_ONLY_DIFFERENCE"
    assert mismatches[0]["severity"] == "rounding_only"


def test_local_compare_totals_classifies_total_mismatch_outside_tolerance():
    mismatches = compare_totals({"total_dr": "10.00"}, {"total_dr": "10.02"}, tolerance=Decimal("0.01"))
    assert mismatches[0]["code"] == "REPORT_TOTAL_MISMATCH"
    assert mismatches[0]["severity"] == "high"


def test_local_compare_rows_detects_missing_row():
    left = [{"row_key": "a", "values": {"net": "1.00"}}]
    assert compare_rows(left, [], report_name="Trial Balance", tolerance=Decimal("0.01"))[0]["code"] == "REQUIRED_ROW_MISSING"


def test_local_compare_rows_detects_unexpected_row():
    right = [{"row_key": "b", "values": {"net": "1.00"}}]
    assert compare_rows([], right, report_name="Trial Balance", tolerance=Decimal("0.01"))[0]["code"] == "UNEXPECTED_ROW_PRESENT"


def test_local_compare_rows_detects_row_value_mismatch():
    left = [{"row_key": "a", "values": {"net": "1.00"}}]
    right = [{"row_key": "a", "values": {"net": "1.20"}}]
    mismatch = compare_rows(left, right, report_name="Trial Balance", tolerance=Decimal("0.01"))[0]
    assert mismatch["code"] == "ROW_VALUE_MISMATCH"


def test_local_compare_rows_ignores_order_after_key_matching():
    left = [{"row_key": "a", "values": {"net": "1.00"}}, {"row_key": "b", "values": {"net": "2.00"}}]
    right = list(reversed(left))
    assert compare_rows(left, right, report_name="Trial Balance", tolerance=Decimal("0.01")) == []


def test_local_compare_snapshots_detects_tenant_mismatch_as_critical():
    right = deepcopy(_sample_snapshot())
    right["tenant_id"] = "tenant_beta"
    result = compare_snapshots(_sample_snapshot(), right, context=_context())
    assert any(m["code"] == "TENANT_LEAKAGE" and m["severity"] == "critical" for m in result["mismatches"])
    assert result["ok"] is False


def test_local_compare_snapshots_detects_currency_mismatch_as_critical():
    right = deepcopy(_sample_snapshot())
    right["currency"] = "USD"
    result = compare_snapshots(_sample_snapshot(), right, context=_context())
    assert any(m["code"] == "CURRENCY_MISMATCH" and m["severity"] == "critical" for m in result["mismatches"])


def test_local_compare_snapshots_detects_status_policy_mismatch_as_critical():
    right = deepcopy(_sample_snapshot())
    right["status_policy"]["included"] = ["posted"]
    result = compare_snapshots(_sample_snapshot(), right, context=_context())
    assert any(m["code"] == "STATUS_POLICY_MISMATCH" and m["severity"] == "critical" for m in result["mismatches"])


def test_fixture_expected_reports_are_comparable_inputs():
    assert H28_DOC.is_file()
    assert H27_DOC.is_file()
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reports = data["expected_reports"]["tenant_alpha"]
    expected_keys = {
        "trial_balance",
        "pl_summary",
        "pl_detail",
        "balance_sheet_summary",
        "balance_sheet_detail",
        "vat_register",
        "account_ledger",
        "counterparty_ledger",
        "payroll_ledger",
        "journal_entries_list",
        "cashflow",
    }
    assert expected_keys.issubset(reports)


def test_no_real_pii_or_tax_or_bank_patterns():
    combined = "\n".join([
        _read(H29_DOC),
        _read(Path(__file__)),
        FIXTURE.read_text(encoding="utf-8"),
    ])
    forbidden = [
        r"010[0-9]{8}",
        r"[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}",
        r"[0-9]{16}",
        r"GE[0-9A-Z]{20,}",
        r"Bank of " + "Georgia",
        "saqar" + "tvelos banki",
        "tib" + "isi",
        r"L" + r"td\.",
        "L" + "LC",
        r"In" + r"c\.",
        "Gm" + "bH",
        r"@gmail\.com",
        r"@yahoo\.com",
        r"@hotmail\.com",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, combined)


def test_no_db_or_network_imports_in_test_file():
    src = _read(Path(__file__))
    forbidden = [
        "psy" + "copg",
        "sql" + "alchemy",
        "req" + "uests",
        "ht" + "tpx",
        "sock" + "et",
    ]
    for token in forbidden:
        assert token not in src


def test_no_sql_or_subprocess_in_test_file():
    src = _read(Path(__file__)).replace("test_no_sql_or_subprocess_in_test_file", "")
    forbidden = [
        "INSERT" + " INTO",
        "DELETE" + " FROM",
        "CREATE" + " TABLE",
        "ALTER" + " TABLE",
        "DROP" + " TABLE",
    ]
    for token in forbidden:
        assert token not in src
    assert "sub" + "process" not in src


def test_next_task_h30_documented():
    text = _read(H29_DOC)
    assert "H30 - Accountant Review Report Contract / Snapshot Comparison Result UX Plan" in text
