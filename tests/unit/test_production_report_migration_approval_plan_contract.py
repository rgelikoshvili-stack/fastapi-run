"""
11C-H19 — Production Report Migration Approval Plan Contract Tests

Verifies the documentation completeness and planning contract for the
production migration from journal_drafts to posted-ledger reports.

No DB, no network, no Cloud Run mutation, no SQL, no migrations.
All assertions are documentation and in-memory contract checks only.
"""

import ast
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PLAN_DOC = pathlib.Path(__file__).parents[2] / "docs" / "production-report-migration-approval-plan.md"
_THIS_FILE = pathlib.Path(__file__)

# ---------------------------------------------------------------------------
# Constants — mirrored from the plan doc
# ---------------------------------------------------------------------------

_REQUIRED_SECTIONS = [
    "## 1. Purpose",
    "## 2. Safety Scope",
    "## 3. Production Non-Action Statement",
    "## 4. H1–H18 Completion Chain",
    "## 5. Report Types in Scope",
    "## 6. Old vs New Report Path Comparison",
    "## 7. Approval Gates",
    "## 8. Go / No-Go Checklist",
    "## 9. Production Enablement Command",
    "## 10. Monitoring Plan",
    "## 11. Rollback Plan",
    "## 12. Security and Compliance Requirements",
    "## 13. Non-goals",
    "## 14. Verification Plan",
    "## 15. Test Results",
    "## 16. Next Step",
]

_REQUIRED_APPROVAL_GATES = [
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G7",
    "G8",
]

_REQUIRED_REPORT_TYPES = [
    "profit_and_loss",
    "balance_sheet",
    "cash_flow",
    "trial_balance",
    "accounts_payable_aging",
    "accounts_receivable_aging",
    "general_ledger",
    "tax_summary",
    "payroll_summary",
    "budget_vs_actual",
    "audit_trail",
]

_H_CHAIN = [f"H{i}" for i in range(1, 19)]  # H1 through H18

_PRODUCTION_FLAG = "POSTED_LEDGER_REPORTS_ENABLED"

_FORBIDDEN_STATUSES = frozenset(
    {"draft", "approved", "auto_approved", "simulated_success", "mock_posting", "dry_run"}
)
_STANDARD_NET_STATUSES = ("posted", "correction")

_REQUIRED_SAFETY_CONSTRAINTS = [
    "No production Cloud Run config changes",
    "No production DB access",
    "No SQL execution",
    "No migration execution",
    "No Balance.ge activation",
    "No credentials changed",
    "No connector behavior changed",
    "No infrastructure changed",
    "No posting behavior changed",
    "No approval logic changed",
    "No UI/static files changed",
]

_ROLLBACK_STEPS_KEYWORDS = [
    "Unset",
    "Restart",
    "health",
    "incident",
    "re-enable",
]

_MONITORING_SIGNALS = [
    "POSTED_LEDGER_UNAVAILABLE",
    "5xx",
    "p95",
    "tenant isolation",
    "posted_ledger",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    assert _PLAN_DOC.exists(), f"Plan doc missing: {_PLAN_DOC}"
    return _PLAN_DOC.read_text(encoding="utf-8")


def _make_approval_gate_payload(gate_id: str, satisfied: bool) -> dict:
    return {
        "gate_id": gate_id,
        "satisfied": satisfied,
        "evidence": f"PR merged and live-verified for gate {gate_id}" if satisfied else None,
    }


def _all_gates_satisfied(gates: list[dict]) -> bool:
    return all(g["satisfied"] for g in gates)


def _make_go_nogo_decision(gates: list[dict]) -> dict:
    passed = _all_gates_satisfied(gates)
    return {
        "decision": "go" if passed else "no-go",
        "gates_passed": sum(1 for g in gates if g["satisfied"]),
        "gates_total": len(gates),
        "production_flag_enabled": False,  # never enabled by H19
    }


def _make_report_comparison_row(report_type: str) -> dict:
    return {
        "report_type": report_type,
        "legacy_source": "journal_drafts",
        "new_source": "journal_entry_headers",
        "standard_net_statuses": list(_STANDARD_NET_STATUSES),
        "reversed_excluded": True,
    }


def _assert_no_production_flag_enabled(runtime_state: dict) -> None:
    assert not runtime_state.get("production_flag_enabled"), (
        f"{_PRODUCTION_FLAG} must never be enabled in H19"
    )


# ---------------------------------------------------------------------------
# Tests 1–5: Doc existence and section completeness
# ---------------------------------------------------------------------------


def test_plan_doc_exists():
    assert _PLAN_DOC.exists(), f"Missing: {_PLAN_DOC}"


def test_plan_doc_has_all_16_sections():
    text = _doc_text()
    for section in _REQUIRED_SECTIONS:
        assert section in text, f"Missing section: {section!r}"


def test_plan_doc_section_count_is_16():
    text = _doc_text()
    h2_sections = [line.strip() for line in text.splitlines() if line.startswith("## ")]
    assert len(h2_sections) == 16, f"Expected 16 sections, found {len(h2_sections)}: {h2_sections}"


def test_plan_doc_title_matches():
    text = _doc_text()
    assert "# Bridge Hub — Production Report Migration Approval Plan" in text


def test_plan_doc_is_not_empty():
    text = _doc_text()
    assert len(text.strip()) > 500, "Plan doc suspiciously short"


# ---------------------------------------------------------------------------
# Tests 6–8: Production non-action statement
# ---------------------------------------------------------------------------


def test_production_non_action_statement_present():
    text = _doc_text()
    assert "## 3. Production Non-Action Statement" in text
    assert "does not" in text.lower() or "does **not**" in text


def test_future_production_switch_marked_not_executed_in_h19():
    text = _doc_text()
    assert "deferred to a future task" in text or "future task" in text
    # H19 must not claim to execute the production switch
    assert "H19 executes" not in text
    # Non-goals section must list "switch production" as a non-goal
    nongoals_start = text.find("## 13. Non-goals")
    nongoals_end = text.find("\n## ", nongoals_start + 1)
    nongoals_section = text[nongoals_start:nongoals_end].lower()
    assert "switch production" in nongoals_section


def test_production_flag_remains_off_in_safety_scope():
    text = _doc_text()
    assert _PRODUCTION_FLAG in text
    # Safety scope table must state flag remains OFF
    assert "remains OFF" in text


# ---------------------------------------------------------------------------
# Tests 9–11: H1–H18 completion chain
# ---------------------------------------------------------------------------


def test_h1_through_h18_chain_all_present():
    text = _doc_text()
    for task in _H_CHAIN:
        assert task in text, f"Missing task {task} in H1–H18 chain"


def test_h1_through_h18_chain_has_18_entries():
    text = _doc_text()
    found = set()
    for task in _H_CHAIN:
        if task in text:
            found.add(task)
    assert len(found) == 18, f"Expected 18 tasks in chain, found {len(found)}: {found}"


def test_all_chain_tasks_marked_required():
    text = _doc_text()
    # Each H-task row in the chain table should have 'required'
    chain_section_start = text.find("## 4. H1–H18 Completion Chain")
    chain_section_end = text.find("\n## ", chain_section_start + 1)
    chain_section = text[chain_section_start:chain_section_end]
    required_count = chain_section.count("required")
    assert required_count >= 18, f"Expected ≥18 'required' entries in chain, found {required_count}"


# ---------------------------------------------------------------------------
# Tests 12–14: Approval gates
# ---------------------------------------------------------------------------


def test_approval_gates_section_present():
    text = _doc_text()
    assert "## 7. Approval Gates" in text


def test_approval_gates_include_all_required_gates():
    text = _doc_text()
    for gate in _REQUIRED_APPROVAL_GATES:
        assert gate in text, f"Missing approval gate: {gate}"


def test_approval_gate_count_is_8():
    text = _doc_text()
    gate_matches = re.findall(r"\bG\d+\b", text)
    unique_gates = {g for g in gate_matches if g in {f"G{i}" for i in range(1, 9)}}
    assert len(unique_gates) == 8, f"Expected 8 gates (G1–G8), found {len(unique_gates)}: {unique_gates}"


# ---------------------------------------------------------------------------
# Tests 15–17: Report types in scope
# ---------------------------------------------------------------------------


def test_report_types_section_present():
    text = _doc_text()
    assert "## 5. Report Types in Scope" in text


def test_old_vs_new_comparison_lists_all_official_reports():
    text = _doc_text()
    for report_type in _REQUIRED_REPORT_TYPES:
        assert report_type in text, f"Missing report type: {report_type}"


def test_report_type_count_is_11():
    text = _doc_text()
    found = [rt for rt in _REQUIRED_REPORT_TYPES if rt in text]
    assert len(found) == 11, f"Expected 11 report types, found {len(found)}: {found}"


# ---------------------------------------------------------------------------
# Tests 18–20: Go / no-go logic (in-memory)
# ---------------------------------------------------------------------------


def test_go_nogo_all_gates_pass_produces_go():
    gates = [_make_approval_gate_payload(g, satisfied=True) for g in _REQUIRED_APPROVAL_GATES]
    decision = _make_go_nogo_decision(gates)
    assert decision["decision"] == "go"
    assert decision["gates_passed"] == 8


def test_go_nogo_any_gate_failing_produces_no_go():
    gates = [_make_approval_gate_payload(g, satisfied=True) for g in _REQUIRED_APPROVAL_GATES]
    gates[4]["satisfied"] = False  # G5 fails
    decision = _make_go_nogo_decision(gates)
    assert decision["decision"] == "no-go"
    assert decision["gates_passed"] == 7


def test_go_nogo_production_flag_never_enabled_in_h19():
    gates = [_make_approval_gate_payload(g, satisfied=True) for g in _REQUIRED_APPROVAL_GATES]
    decision = _make_go_nogo_decision(gates)
    _assert_no_production_flag_enabled(decision)


# ---------------------------------------------------------------------------
# Tests 21–23: Report comparison payload (in-memory)
# ---------------------------------------------------------------------------


def test_report_comparison_row_has_correct_legacy_source():
    row = _make_report_comparison_row("profit_and_loss")
    assert row["legacy_source"] == "journal_drafts"


def test_report_comparison_row_has_correct_new_source():
    row = _make_report_comparison_row("balance_sheet")
    assert row["new_source"] == "journal_entry_headers"


def test_report_comparison_row_reversed_excluded():
    row = _make_report_comparison_row("cash_flow")
    assert row["reversed_excluded"] is True
    assert "correction" in row["standard_net_statuses"]
    assert "posted" in row["standard_net_statuses"]


# ---------------------------------------------------------------------------
# Tests 24–26: Rollback and monitoring plan in doc
# ---------------------------------------------------------------------------


def test_rollback_plan_section_present():
    text = _doc_text()
    assert "## 11. Rollback Plan" in text


def test_rollback_plan_contains_required_keywords():
    text = _doc_text()
    rollback_start = text.find("## 11. Rollback Plan")
    rollback_end = text.find("\n## ", rollback_start + 1)
    rollback_section = text[rollback_start:rollback_end]
    for kw in _ROLLBACK_STEPS_KEYWORDS:
        assert kw.lower() in rollback_section.lower(), (
            f"Rollback plan missing keyword: {kw!r}"
        )


def test_monitoring_plan_contains_required_signals():
    text = _doc_text()
    monitoring_start = text.find("## 10. Monitoring Plan")
    monitoring_end = text.find("\n## ", monitoring_start + 1)
    monitoring_section = text[monitoring_start:monitoring_end]
    for signal in _MONITORING_SIGNALS:
        assert signal.lower() in monitoring_section.lower(), (
            f"Monitoring plan missing signal: {signal!r}"
        )


# ---------------------------------------------------------------------------
# Tests 27–28: AST-based self-referential safety checks
# ---------------------------------------------------------------------------


def test_no_db_or_network_imports_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {
        "asyncpg",
        "psycopg2",
        "sqlalchemy",
        "httpx",
        "requests",
        "aiohttp",
        "urllib",
        "socket",
        "startup.migrations",
        "app.startup",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_modules, (
                    f"Forbidden import in test file: {alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden_modules, (
                f"Forbidden import-from in test file: {node.module!r}"
            )
            for mod in forbidden_modules:
                assert not node.module.startswith(mod + "."), (
                    f"Forbidden import-from prefix in test file: {node.module!r}"
                )


def test_no_gcloud_or_infra_mutation_commands_in_test_file():
    source = _THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Check no os.system or subprocess calls that could mutate infra
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            elif isinstance(node.func, ast.Name):
                fname = node.func.id
            else:
                fname = ""
            assert fname not in ("system", "popen", "run", "check_call", "check_output", "Popen"), (
                f"Forbidden subprocess/os call in test file: {fname!r}"
            )
        # Check for infra command strings as constants
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for infra_tool in ("gcloud", "kubectl", "terraform", "helm"):
                if node.value.startswith(infra_tool + " ") and "deploy" in node.value:
                    raise AssertionError(
                        f"Forbidden infra deploy command constant in test file: {node.value!r}"
                    )


# ---------------------------------------------------------------------------
# Test 29: Safety constraints in doc
# ---------------------------------------------------------------------------


def test_safety_scope_contains_all_required_constraints():
    text = _doc_text()
    safety_start = text.find("## 2. Safety Scope")
    safety_end = text.find("\n## ", safety_start + 1)
    safety_section = text[safety_start:safety_end]
    for constraint in _REQUIRED_SAFETY_CONSTRAINTS:
        assert constraint in safety_section, (
            f"Safety scope missing constraint: {constraint!r}"
        )
