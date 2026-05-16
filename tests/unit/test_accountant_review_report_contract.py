"""
H30 - Accountant Review Report Contract.

Local contract prototypes for turning H29 comparison output into an
accountant-facing review report. These helpers are defined only in this test
file and are not app/runtime or UI implementations.

No DB, no network, no migrations, no fixture load, no runtime API calls.
"""
from __future__ import annotations

import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
H30_DOC = ROOT / "docs" / "accountant-review-report-contract.md"
H29_DOC = ROOT / "docs" / "synthetic-snapshot-comparator-contract.md"

RECOMMENDED_ACTIONS = [
    "ACCEPT_ROUNDING_DIFFERENCE",
    "REVIEW_ACCOUNT_MAPPING",
    "REVIEW_STATUS_POLICY",
    "REVIEW_TENANT_FILTER",
    "REVIEW_CORRECTION_REVERSAL_CHAIN",
    "REVIEW_EVIDENCE_LINKS",
    "REVIEW_COUNTERPARTY_MAPPING",
    "REVIEW_CASHFLOW_CLASSIFICATION",
    "REVIEW_VAT_CLASSIFICATION",
    "REVIEW_PAYROLL_CLASSIFICATION",
    "BLOCK_PRODUCTION_SWITCH",
    "REQUEST_ENGINEERING_FIX",
    "REQUEST_ACCOUNTANT_SIGN_OFF",
]

SUMMARY_FIELDS = [
    "total_reports_compared",
    "reports_passed",
    "reports_failed",
    "reports_blocked",
    "total_mismatches",
    "critical_count",
    "high_count",
    "medium_count",
    "low_count",
    "rounding_only_count",
    "affected_accounts_count",
    "affected_counterparties_count",
    "affected_journal_entries_count",
    "missing_evidence_count",
    "tenant_leakage_detected",
    "status_policy_errors",
    "correction_reversal_errors",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _mismatch(code: str, severity: str, *, report_name="Trial Balance", row_key="row_1",
              account_code=None, counterparty_id=None, journal_entry_id=None,
              evidence_bundle_id=None, source_draft_id=None, posting_log_id=None) -> dict:
    evidence = {
        "account_code": account_code,
        "counterparty_id": counterparty_id,
        "journal_entry_id": journal_entry_id,
        "evidence_bundle_id": evidence_bundle_id,
        "source_draft_id": source_draft_id,
        "posting_log_id": posting_log_id,
    }
    return {
        "code": code,
        "severity": severity,
        "report_name": report_name,
        "tenant_id": "tenant_alpha",
        "row_key": row_key,
        "field": "total_dr",
        "expected_value": "10.00",
        "actual_value": "11.00",
        "difference": "1.00",
        "tolerance": "0.01",
        "path": "totals.total_dr",
        "message": code,
        "evidence": {k: v for k, v in evidence.items() if v is not None},
        "classification_notes": [],
    }


def _comparison_result(mismatches: list[dict]) -> dict:
    summary = {"total_mismatches": len(mismatches), "critical": 0, "high": 0, "medium": 0, "low": 0, "rounding_only": 0}
    for item in mismatches:
        summary[item["severity"]] += 1
    return {
        "ok": not any(item["severity"] in {"critical", "high", "medium"} for item in mismatches),
        "comparison_name": "expected_vs_posted_trial_balance",
        "report_name": "Trial Balance",
        "tenant_id": "tenant_alpha",
        "period": {"from": "2026-01-01", "to": "2026-01-31"},
        "currency": "GEL",
        "summary": summary,
        "mismatches": mismatches,
        "metadata": {},
    }


def _status_for_mismatches(mismatches: list[dict]) -> str:
    codes = {item["code"] for item in mismatches}
    severities = {item["severity"] for item in mismatches}
    hard_fail_codes = {
        "TENANT_LEAKAGE",
        "STATUS_POLICY_MISMATCH",
        "CORRECTION_REVERSAL_MISMATCH",
        "EVIDENCE_LINK_MISSING",
        "DRILLDOWN_LINK_MISSING",
    }
    if not mismatches:
        return "passed"
    if "critical" in severities or codes & hard_fail_codes:
        return "blocked"
    if "high" in severities or "medium" in severities or "low" in severities:
        return "failed"
    return "passed_with_rounding"


def _recommended_actions(mismatches: list[dict]) -> list[str]:
    actions = set()
    for item in mismatches:
        code = item["code"]
        if item["severity"] == "critical":
            actions.add("BLOCK_PRODUCTION_SWITCH")
        if code == "TENANT_LEAKAGE":
            actions.update({"REVIEW_TENANT_FILTER", "BLOCK_PRODUCTION_SWITCH"})
        elif code == "STATUS_POLICY_MISMATCH":
            actions.update({"REVIEW_STATUS_POLICY", "BLOCK_PRODUCTION_SWITCH"})
        elif code == "CORRECTION_REVERSAL_MISMATCH":
            actions.update({"REVIEW_CORRECTION_REVERSAL_CHAIN", "BLOCK_PRODUCTION_SWITCH"})
        elif code in {"EVIDENCE_LINK_MISSING", "DRILLDOWN_LINK_MISSING"}:
            actions.update({"REVIEW_EVIDENCE_LINKS", "REQUEST_ENGINEERING_FIX"})
        elif code == "ROUNDING_ONLY_DIFFERENCE":
            actions.update({"ACCEPT_ROUNDING_DIFFERENCE", "REQUEST_ACCOUNTANT_SIGN_OFF"})
        else:
            actions.add("REQUEST_ENGINEERING_FIX")
    return sorted(actions)


def _affected_entities(mismatches: list[dict]) -> dict:
    entity_fields = {
        "accounts": "account_code",
        "counterparties": "counterparty_id",
        "journal_entries": "journal_entry_id",
        "evidence_bundles": "evidence_bundle_id",
        "source_drafts": "source_draft_id",
        "posting_logs": "posting_log_id",
        "reports": "report_name",
    }
    grouped = {name: {} for name in entity_fields}
    severity_rank = {"rounding_only": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    for item in mismatches:
        for group_name, field in entity_fields.items():
            value = item["report_name"] if field == "report_name" else item.get("evidence", {}).get(field)
            if not value:
                continue
            current = grouped[group_name].setdefault(value, {
                "id": value,
                "count": 0,
                "max_severity": item["severity"],
                "related_mismatch_codes": set(),
                "related_reports": set(),
            })
            current["count"] += 1
            if severity_rank[item["severity"]] > severity_rank[current["max_severity"]]:
                current["max_severity"] = item["severity"]
            current["related_mismatch_codes"].add(item["code"])
            current["related_reports"].add(item["report_name"])
    result = {}
    for group_name, values in grouped.items():
        result[group_name] = [
            {
                **entry,
                "related_mismatch_codes": sorted(entry["related_mismatch_codes"]),
                "related_reports": sorted(entry["related_reports"]),
            }
            for entry in values.values()
        ]
    result["ledger_lines"] = []
    return result


def _review_report(comparison_results: list[dict], *, rounding_signed_off=False) -> dict:
    mismatches = [item for result in comparison_results for item in result["mismatches"]]
    status = _status_for_mismatches(mismatches)
    production_switch_allowed = status == "passed" or (status == "passed_with_rounding" and rounding_signed_off)
    affected = _affected_entities(mismatches)
    counts = defaultdict(int)
    for item in mismatches:
        counts[item["severity"]] += 1
    summary = {
        "total_reports_compared": len(comparison_results),
        "reports_passed": sum(1 for result in comparison_results if _status_for_mismatches(result["mismatches"]) == "passed"),
        "reports_failed": sum(1 for result in comparison_results if _status_for_mismatches(result["mismatches"]) == "failed"),
        "reports_blocked": sum(1 for result in comparison_results if _status_for_mismatches(result["mismatches"]) == "blocked"),
        "total_mismatches": len(mismatches),
        "critical_count": counts["critical"],
        "high_count": counts["high"],
        "medium_count": counts["medium"],
        "low_count": counts["low"],
        "rounding_only_count": counts["rounding_only"],
        "affected_accounts_count": len(affected["accounts"]),
        "affected_counterparties_count": len(affected["counterparties"]),
        "affected_journal_entries_count": len(affected["journal_entries"]),
        "missing_evidence_count": sum(1 for item in mismatches if item["code"] in {"EVIDENCE_LINK_MISSING", "DRILLDOWN_LINK_MISSING"}),
        "tenant_leakage_detected": any(item["code"] == "TENANT_LEAKAGE" for item in mismatches),
        "status_policy_errors": sum(1 for item in mismatches if item["code"] == "STATUS_POLICY_MISMATCH"),
        "correction_reversal_errors": sum(1 for item in mismatches if item["code"] == "CORRECTION_REVERSAL_MISMATCH"),
    }
    return {
        "review_id": "review_synthetic_001",
        "comparison_name": "expected_vs_posted_all_reports",
        "generated_at": "2026-05-16T00:00:00Z",
        "generated_by": "Bridge Hub",
        "environment": "nonproduction",
        "tenant_id": "tenant_alpha",
        "period": {"from": "2026-01-01", "to": "2026-01-31"},
        "currency": "GEL",
        "overall_status": status,
        "production_switch_allowed": production_switch_allowed,
        "summary": summary,
        "report_results": comparison_results,
        "mismatch_groups": {},
        "affected_entities": affected,
        "evidence_links": affected["evidence_bundles"],
        "recommended_actions": _recommended_actions(mismatches),
        "sign_off": {
            "accountant_reviewed": False,
            "rounding_differences_accepted": rounding_signed_off,
            "critical_mismatches_absent": summary["critical_count"] == 0,
            "high_mismatches_resolved": summary["high_count"] == 0,
            "evidence_reviewed": summary["missing_evidence_count"] == 0,
            "production_switch_recommended": production_switch_allowed,
        },
        "audit": {"git_sha": "synthetic", "feature_flag_state": "off"},
    }


def test_h30_doc_exists():
    assert H30_DOC.is_file()


def test_h30_non_action_statement_present():
    text = _read(H30_DOC)
    for phrase in [
        "H30 is docs/tests only",
        "H30 does not create DB",
        "H30 does not connect to DB",
        "H30 does not execute SQL",
        "H30 does not run migrations",
        "H30 does not load fixtures into DB",
        "H30 does not call runtime report APIs",
        "H30 does not modify runtime report behavior",
        "H30 does not implement UI/static",
        "H30 does not implement app/runtime helpers",
        "H30 does not enable feature flags",
        "H30 does not activate Balance.ge",
    ]:
        assert phrase in text


def test_accountant_review_json_contract_documented():
    text = _read(H30_DOC)
    for field in ["Accountant Review Report JSON Contract", "review_id", "overall_status", "production_switch_allowed", "report_results"]:
        assert field in text


def test_overall_status_rules_documented():
    text = _read(H30_DOC)
    for status in ["passed", "passed_with_rounding", "blocked", "failed"]:
        assert status in text


def test_summary_section_documented():
    text = _read(H30_DOC)
    for field in SUMMARY_FIELDS:
        assert field in text


def test_report_result_shape_documented():
    text = _read(H30_DOC)
    for field in ["report_name", "comparison_result", "severity_counts", "totals_summary", "sign_off_required"]:
        assert field in text


def test_mismatch_grouping_rules_documented():
    text = _read(H30_DOC)
    for field in ["severity", "mismatch code", "account_code", "journal_entry_id", "correction/reversal chain"]:
        assert field in text


def test_affected_entities_section_documented():
    text = _read(H30_DOC)
    for entity in ["accounts", "counterparties", "journal_entries", "ledger_lines", "evidence_bundles", "reports"]:
        assert entity in text


def test_evidence_drilldown_presentation_documented():
    text = _read(H30_DOC)
    for field in ["evidence_bundle_id", "posting_log_id", "source_draft_id", "journal_entry_id", "ledger_line_id"]:
        assert field in text


def test_recommended_action_categories_documented():
    text = _read(H30_DOC)
    for action in RECOMMENDED_ACTIONS:
        assert action in text


def test_sign_off_contract_documented():
    text = _read(H30_DOC)
    for field in ["signer_name", "signer_id", "signed_at", "accepted_rounding_differences", "production_switch_recommendation"]:
        assert field in text


def test_audit_metadata_documented():
    text = _read(H30_DOC)
    for field in ["comparison_run_id", "source_snapshot_ids", "normalized_snapshot_ids", "comparator_version", "rollback_plan_reference"]:
        assert field in text


def test_markdown_table_layout_documented():
    text = _read(H30_DOC)
    for phrase in ["Executive summary", "Gate status", "Report-by-report status table", "Critical/high mismatch table", "Audit footer"]:
        assert phrase in text


def test_production_switch_gate_rules_documented():
    text = _read(H30_DOC)
    for phrase in ["never allow production switch with critical mismatches", "tenant leakage", "feature flag must remain OFF", "gates G1-G10"]:
        assert phrase in text


def test_sample_review_outcomes_documented():
    text = _read(H30_DOC)
    for phrase in ["Clean pass", "Passed with rounding", "Blocked by tenant leakage", "Failed by report total mismatch", "Blocked by missing evidence"]:
        assert phrase in text


def test_future_ui_ux_plan_documented():
    text = _read(H30_DOC)
    for phrase in ["Future UI/UX Plan", "dashboard card summary", "filter by severity/report/account/counterparty", "export JSON/CSV/PDF"]:
        assert phrase in text


def test_safety_rules_documented():
    text = _read(H30_DOC)
    for phrase in ["No DB in H30", "No runtime API calls", "No UI/static implementation", "No feature flag", "No Balance.ge"]:
        assert phrase in text


def test_local_review_status_passed_when_no_mismatches():
    review = _review_report([_comparison_result([])])
    assert review["overall_status"] == "passed"
    assert review["production_switch_allowed"] is True


def test_local_review_status_passed_with_rounding_only():
    review = _review_report([_comparison_result([_mismatch("ROUNDING_ONLY_DIFFERENCE", "rounding_only")])])
    assert review["overall_status"] == "passed_with_rounding"
    assert "REQUEST_ACCOUNTANT_SIGN_OFF" in review["recommended_actions"]


def test_local_review_status_blocked_on_critical_mismatch():
    review = _review_report([_comparison_result([_mismatch("TENANT_LEAKAGE", "critical")])])
    assert review["overall_status"] == "blocked"


def test_local_review_status_failed_on_high_mismatch():
    review = _review_report([_comparison_result([_mismatch("REPORT_TOTAL_MISMATCH", "high")])])
    assert review["overall_status"] == "failed"


def test_local_production_switch_false_with_critical_mismatch():
    review = _review_report([_comparison_result([_mismatch("TENANT_LEAKAGE", "critical")])], rounding_signed_off=True)
    assert review["production_switch_allowed"] is False


def test_local_production_switch_false_with_missing_evidence():
    review = _review_report([_comparison_result([_mismatch("EVIDENCE_LINK_MISSING", "high")])], rounding_signed_off=True)
    assert review["overall_status"] == "blocked"
    assert review["production_switch_allowed"] is False


def test_local_recommended_actions_include_block_switch_for_critical():
    review = _review_report([_comparison_result([_mismatch("TENANT_LEAKAGE", "critical")])])
    assert "BLOCK_PRODUCTION_SWITCH" in review["recommended_actions"]
    assert "REVIEW_TENANT_FILTER" in review["recommended_actions"]


def test_local_review_summary_counts_by_severity():
    mismatches = [
        _mismatch("TENANT_LEAKAGE", "critical"),
        _mismatch("REPORT_TOTAL_MISMATCH", "high"),
        _mismatch("ROW_COUNT_MISMATCH", "medium"),
        _mismatch("ROUNDING_ONLY_DIFFERENCE", "rounding_only"),
    ]
    summary = _review_report([_comparison_result(mismatches)])["summary"]
    assert summary["critical_count"] == 1
    assert summary["high_count"] == 1
    assert summary["medium_count"] == 1
    assert summary["rounding_only_count"] == 1


def test_local_affected_entities_grouping():
    mismatch = _mismatch(
        "ROW_VALUE_MISMATCH",
        "high",
        account_code="1010",
        counterparty_id="counterparty_alpha",
        journal_entry_id="je_001",
        evidence_bundle_id="evidence_001",
    )
    affected = _review_report([_comparison_result([mismatch])])["affected_entities"]
    assert affected["accounts"][0]["id"] == "1010"
    assert affected["counterparties"][0]["id"] == "counterparty_alpha"
    assert affected["journal_entries"][0]["id"] == "je_001"
    assert affected["evidence_bundles"][0]["id"] == "evidence_001"


def test_no_real_pii_or_tax_or_bank_patterns():
    combined = "\n".join([_read(H30_DOC), _read(Path(__file__)), _read(H29_DOC)])
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


def test_next_task_h31_documented():
    assert "H31 - Production Switch Gate Contract / Feature Flag Approval Checklist" in _read(H30_DOC)
