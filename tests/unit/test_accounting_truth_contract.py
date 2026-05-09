import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "accounting-truth-schema-contract.md"
MANIFEST = ROOT / "tests" / "fixtures" / "schema_manifest.json"


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def _manifest_records() -> list[dict]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("tables", [])
    return data


def test_accounting_truth_contract_exists_and_covers_required_objects():
    assert DOC.exists()
    text = _doc_text()
    required = [
        "journal_drafts",
        "draft_comments",
        "journal_entries",
        "posting_logs",
        "audit_events",
        "approval_history",
        "period_locks",
        "journal_lines",
        "posting_queue",
        "bank_reconciliations",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_approval_first_and_forbids_ai_direct_posting():
    text = _doc_text()
    required = [
        "approval-first",
        "AI may create draft proposals only",
        "AI must not post directly",
        "Posting requires an approved draft",
        "Corrections must preserve history",
        "must not write directly to posted ledger truth",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_posted_only_ledger_truth():
    text = _doc_text()
    required = [
        "Posted-Only Ledger Truth",
        "Reports must use posted `journal_entries`",
        "Drafts must not appear in final ledger reports unless clearly marked",
        "Trial balance must distinguish draft turnover from posted turnover",
        "Income statement must distinguish draft results from posted results",
        "Balance sheet must distinguish draft balances from posted balances",
        "VAT reports must distinguish draft VAT exposure from posted VAT truth",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_immutability_idempotency_tenant_and_period_controls():
    text = _doc_text()
    required = [
        "Posted `journal_entries` must not be edited in place",
        "reversal and replacement entries",
        "Posting must be idempotent",
        "Duplicate posting attempts must be rejected or return the existing result safely",
        "Tenant-owned accounting truth tables must include `tenant_id`",
        "All reporting queries must be tenant-scoped",
        "Posting into locked periods must be blocked",
        "Backdated entries require explicit policy and audit trail",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_requires_evidence_audit_and_secret_safe_posting_logs():
    text = _doc_text()
    required = [
        "Every posted entry should be traceable to source evidence",
        "An evidence bundle is required before any Balance.ge or ERP write pilot",
        "who approved or rejected",
        "reviewer notes",
        "Posting logs are audit evidence",
        "must not store plaintext credentials",
        "AI decision explanation",
    ]
    for phrase in required:
        assert phrase in text


def test_contract_forbids_destructive_migrations_db_mutation_and_balance_activation():
    text = _doc_text()
    required = [
        "no `DROP TABLE`",
        "no `TRUNCATE`",
        "no data-destructive `DELETE`",
        "no data-rewriting `UPDATE` migration without a separate reviewed data plan",
        "no production DB mutation during planning/contract tasks",
        "Runtime DDL removal must wait",
        "Balance.ge live activation is still deferred",
        "Production database is not touched by this task",
    ]
    for phrase in required:
        assert phrase in text


def test_schema_manifest_tracks_key_accounting_truth_tables_as_risky_or_planned():
    records = {row["table_name"]: row for row in _manifest_records()}
    required_tables = [
        "journal_drafts",
        "draft_comments",
        "journal_entries",
        "posting_logs",
        "audit_events",
        "period_locks",
        "bank_reconciliations",
    ]
    for table in required_tables:
        assert table in records
        row = records[table]
        assert row["migration_coverage"] in {"none", "partial"}
        if table in {"journal_drafts", "journal_entries", "posting_logs", "bank_reconciliations"}:
            assert row["risk"] in {"high", "critical"}
        else:
            assert row["risk"] in {"medium", "high", "critical"}
        action = row["recommended_next_action"].lower()
        assert any(
            token in action
            for token in (
                "draft",
                "ledger",
                "posting",
                "audit",
                "period",
                "reconciliation",
                "migration",
                "schema",
                "canonical",
                "normalize",
            )
        )


def test_active_scripts_do_not_execute_drop_table_users():
    scripts_dir = ROOT / "scripts"
    pattern = re.compile(r"^\s*DROP\s+TABLE\s+IF\s+EXISTS\s+users\b", re.IGNORECASE | re.MULTILINE)
    offenders = []
    for path in scripts_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        active_lines = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith(("#", "--"))
        )
        if pattern.search(active_lines):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
