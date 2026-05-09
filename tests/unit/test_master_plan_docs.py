from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read_doc(name: str) -> str:
    return (ROOT / "docs" / name).read_text(encoding="utf-8")


def test_master_plan_docs_exist():
    expected = [
        "bridge-hub-ai-chief-accountant-master-plan.md",
        "bridge-hub-pilot-v1-scope.md",
        "bridge-hub-target-architecture.md",
    ]
    for name in expected:
        assert (ROOT / "docs" / name).exists()


def test_master_plan_contains_required_product_positioning_and_phases():
    text = _read_doc("bridge-hub-ai-chief-accountant-master-plan.md")
    required = [
        "AI Chief Accountant",
        "Financial Controller",
        "approval-first",
        "Input Layer",
        "Canonical Layer",
        "AI Reasoning Layer",
        "Control Layer",
        "Human Approval Layer",
        "Execution Layer",
        "Phase 1 - Trust Foundation",
        "Phase 2 - AI Document + Bank Brain",
        "Phase 3 - Balance.ge First Connector Pilot",
        "Phase 4 - Approval Cockpit 2.0",
        "Phase 5 - Monthly Close Cockpit",
        "Phase 6 - Multi-ERP Expansion",
        "Phase 7 - Commercial SaaS",
    ]
    for phrase in required:
        assert phrase in text


def test_master_plan_explicitly_forbids_unsafe_automation():
    text = _read_doc("bridge-hub-ai-chief-accountant-master-plan.md")
    required = [
        "Do not allow AI direct posting without approval",
        "Do not replace Balance.ge, ORIS, or 1C as a full ERP yet",
        "Do not remove runtime DDL before migrations and tests are complete",
        "0 unauthorized postings",
        "100% approval-before-execute",
        "0 plaintext secret exposure",
    ]
    for phrase in required:
        assert phrase in text


def test_pilot_scope_defines_go_no_go_and_fallback():
    text = _read_doc("bridge-hub-pilot-v1-scope.md")
    required = [
        "Pilot Target User",
        "Pilot Workflow",
        "In-Scope Features",
        "Out-of-Scope Features",
        "Required Credentials",
        "Required Test Data",
        "Acceptance Criteria",
        "Go / No-Go Checklist",
        "Rollback Plan",
        "Manual Fallback Workflow",
    ]
    for phrase in required:
        assert phrase in text


def test_target_architecture_documents_control_boundaries():
    text = _read_doc("bridge-hub-target-architecture.md")
    required = [
        "Text Architecture Diagram",
        "Canonical Object Flow",
        "AI Role Flow",
        "Approval-First Flow",
        "Connector Adapter Standard",
        "Audit / Logging Standard",
        "Security Boundaries",
        "Production Readiness Gates",
        "No direct posting from AI",
        "No RS.ge submission without approval",
    ]
    for phrase in required:
        assert phrase in text
