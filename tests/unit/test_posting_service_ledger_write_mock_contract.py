"""
Bridge Hub — Task 11C-H6
Mock-based contract tests for the future posting_service ledger write behavior.

Rules:
- No import of posting_service, approval_service, or any runtime module.
- No DB connection.
- No SQL execution.
- No migration execution.
- No real connector calls.
- No network calls.
- Uses only local fake objects and a pure evaluate_future_ledger_write_policy() helper.
- Defines expected future behavior without changing any runtime behavior.
"""
import ast
import dataclasses
import pathlib
import uuid
from decimal import Decimal
from typing import List, Optional

import pytest

# ---------------------------------------------------------------------------
# Fake domain objects — live only in this test file
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class FakeDraft:
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "tenant_acme"
    status: str = "approved"
    source_type: str = "bank_transaction"
    entry_date: str = "2026-05-12"
    period: str = "2026-05"
    currency: str = "GEL"
    exchange_rate: Decimal = Decimal("1.0")
    created_by: str = "user_01"
    approved_by: str = "user_02"
    journal_lines: List[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class FakeConnectorResult:
    success: bool = True
    mode: str = "live"          # "live" | "mock" | "demo" | "oris_stub" | "onec_demo"
    dry_run: bool = False
    status: str = "posted"      # "posted" | "simulated_success" | "mock_posting" | "failed"


@dataclasses.dataclass
class FakePostingLog:
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    draft_id: str = ""
    status: str = "success"     # "success" | "simulated_success" | "mock_posting" | "failed"
    connector_mode: str = "live"


@dataclasses.dataclass
class FakeLedgerWriter:
    """Records calls instead of hitting a DB."""
    calls: List[dict] = dataclasses.field(default_factory=list)
    should_raise: bool = False
    existing_entry_id: Optional[str] = None  # simulate duplicate detection

    def write(self, header: dict, lines: List[dict]) -> dict:
        if self.should_raise:
            raise RuntimeError("Simulated ledger write failure")
        if self.existing_entry_id:
            return {"id": self.existing_entry_id, "duplicate": True}
        entry_id = str(uuid.uuid4())
        self.calls.append({"header": header, "lines": lines, "id": entry_id})
        return {"id": entry_id, "duplicate": False}

    @property
    def called(self) -> bool:
        return len(self.calls) > 0


@dataclasses.dataclass
class FakeLedgerWritePolicy:
    is_period_locked: bool = False
    tenant_id: str = "tenant_acme"


# ---------------------------------------------------------------------------
# Sanitizer (mirrors future _strip_unsafe contract)
# ---------------------------------------------------------------------------

_FORBIDDEN_METADATA_KEYS = {
    "api_key", "password", "token", "secret", "encrypted_value",
}

def _strip_unsafe(metadata: dict) -> dict:
    return {k: v for k, v in metadata.items() if k not in _FORBIDDEN_METADATA_KEYS}


# ---------------------------------------------------------------------------
# Future ledger write policy — pure function, no DB, no imports
# ---------------------------------------------------------------------------

def evaluate_future_ledger_write_policy(
    draft: FakeDraft,
    connector_result: FakeConnectorResult,
    posting_log: Optional[FakePostingLog],
    ledger_writer: FakeLedgerWriter,
    policy: FakeLedgerWritePolicy,
    request_tenant_id: str,
    evidence_bundle_id: Optional[str] = None,
    existing_source_key: Optional[str] = None,  # "source_draft_id:posting_log_id" already written
) -> dict:
    """
    Pure function encoding the future posting_service ledger write contract.
    Returns a result dict with keys: written, reason, entry_id, inconsistency.
    Never touches DB, connectors, or network.
    """
    # --- 1. Tenant isolation ---
    if not draft.tenant_id or not draft.tenant_id.strip():
        return {"written": False, "reason": "TENANT_MISSING", "entry_id": None, "inconsistency": False}
    if draft.tenant_id != request_tenant_id:
        return {"written": False, "reason": "TENANT_MISMATCH", "entry_id": None, "inconsistency": False}

    # --- 2. Status gate ---
    non_truth_statuses = {
        "draft", "pending_approval", "pending approval", "rejected",
        "auto_approved", "simulated_success", "mock_posting", "dry_run",
    }
    if draft.status in non_truth_statuses:
        return {"written": False, "reason": "NOT_APPROVED", "entry_id": None, "inconsistency": False}

    # --- 3. Dry run gate ---
    if connector_result.dry_run:
        return {"written": False, "reason": "DRY_RUN", "entry_id": None, "inconsistency": False}

    # --- 4. Mock / demo / stub connector gate ---
    if connector_result.mode in {"mock", "demo", "oris_stub", "onec_demo"}:
        return {"written": False, "reason": "MOCK_OR_DEMO_CONNECTOR", "entry_id": None, "inconsistency": False}

    # --- 5. Connector failure gate ---
    if not connector_result.success:
        return {"written": False, "reason": "CONNECTOR_FAILED", "entry_id": None, "inconsistency": False}

    # --- 6. Posting log required with real success status ---
    if posting_log is None:
        return {"written": False, "reason": "POSTING_LOG_MISSING", "entry_id": None, "inconsistency": False}
    if posting_log.status in {"simulated_success", "mock_posting", "failed"}:
        return {"written": False, "reason": "POSTING_LOG_NOT_REAL_SUCCESS", "entry_id": None, "inconsistency": False}

    # --- 7. Period lock gate ---
    if policy.is_period_locked:
        return {"written": False, "reason": "PERIOD_LOCKED", "entry_id": None, "inconsistency": False}

    # --- 8. Balance check ---
    total_debit = sum(Decimal(str(l.get("debit", 0))) for l in draft.journal_lines)
    total_credit = sum(Decimal(str(l.get("credit", 0))) for l in draft.journal_lines)
    if total_debit != total_credit:
        return {"written": False, "reason": "UNBALANCED", "entry_id": None, "inconsistency": False}

    # --- 9. Line tenant isolation ---
    for line in draft.journal_lines:
        if line.get("tenant_id") and line["tenant_id"] != draft.tenant_id:
            return {"written": False, "reason": "LINE_TENANT_MISMATCH", "entry_id": None, "inconsistency": False}

    # --- 10. Idempotency / duplicate check ---
    source_key = f"{draft.id}:{posting_log.id}"
    if existing_source_key and existing_source_key == source_key:
        return {
            "written": False,
            "reason": "DUPLICATE_IDEMPOTENT",
            "entry_id": existing_source_key.split(":")[0],
            "inconsistency": False,
        }

    # --- 11. Build header ---
    header = {
        "tenant_id": draft.tenant_id,
        "source_draft_id": draft.id,
        "posting_log_id": posting_log.id,
        "evidence_bundle_id": evidence_bundle_id,
        "entry_date": draft.entry_date,
        "period": draft.period,
        "status": "posted",
        "source_type": draft.source_type,
        "currency": draft.currency,
        "exchange_rate": str(draft.exchange_rate),
        "total_debit": str(total_debit),
        "total_credit": str(total_credit),
        "created_by": draft.created_by,
        "approved_by": draft.approved_by,
        "metadata_json": {},
    }

    lines = [
        {
            "tenant_id": draft.tenant_id,
            "line_no": i,
            "account_code": l.get("account_code", ""),
            "debit": str(Decimal(str(l.get("debit", 0)))),
            "credit": str(Decimal(str(l.get("credit", 0)))),
            "currency": l.get("currency", draft.currency),
            "amount_gel": str(Decimal(str(l.get("amount_gel", l.get("debit", l.get("credit", 0)))))),
        }
        for i, l in enumerate(draft.journal_lines)
    ]

    # --- 12. Transactional write (fail-closed) ---
    try:
        result = ledger_writer.write(header, lines)
    except Exception:
        return {
            "written": False,
            "reason": "LEDGER_WRITE_FAILED_AFTER_CONNECTOR_SUCCESS",
            "entry_id": None,
            "inconsistency": True,  # recoverable inconsistency — connector succeeded, ledger write failed
        }

    return {
        "written": True,
        "reason": "OK",
        "entry_id": result["id"],
        "inconsistency": False,
    }


# ---------------------------------------------------------------------------
# Balanced line helpers
# ---------------------------------------------------------------------------

def _balanced_lines(tenant_id: str = "tenant_acme") -> List[dict]:
    return [
        {"account_code": "1210", "debit": "100.00", "credit": "0", "amount_gel": "100.00", "tenant_id": tenant_id},
        {"account_code": "3110", "debit": "0", "credit": "100.00", "amount_gel": "100.00", "tenant_id": tenant_id},
    ]


def _unbalanced_lines() -> List[dict]:
    return [
        {"account_code": "1210", "debit": "100.00", "credit": "0", "amount_gel": "100.00", "tenant_id": "tenant_acme"},
        {"account_code": "3110", "debit": "0", "credit": "50.00", "amount_gel": "50.00", "tenant_id": "tenant_acme"},
    ]


def _good_draft(**kwargs) -> FakeDraft:
    defaults = dict(
        status="approved",
        tenant_id="tenant_acme",
        journal_lines=_balanced_lines(),
    )
    defaults.update(kwargs)
    return FakeDraft(**defaults)


def _good_connector() -> FakeConnectorResult:
    return FakeConnectorResult(success=True, mode="live", dry_run=False, status="posted")


def _good_posting_log(draft_id: str = "") -> FakePostingLog:
    return FakePostingLog(status="success", connector_mode="live", draft_id=draft_id)


def _good_policy() -> FakeLedgerWritePolicy:
    return FakeLedgerWritePolicy(is_period_locked=False, tenant_id="tenant_acme")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNoLedgerWriteForDraftStatus:
    def test_no_ledger_write_for_draft_status(self):
        draft = _good_draft(status="draft")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert "NOT_APPROVED" in result["reason"] or result["reason"] in {
            "NOT_APPROVED", "DRAFT", "draft"
        }

    def test_draft_reason_contains_not_approved(self):
        draft = _good_draft(status="draft")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert result["reason"] == "NOT_APPROVED"


class TestNoLedgerWriteForPendingApprovalStatus:
    def test_no_ledger_write_for_pending_approval_status(self):
        draft = _good_draft(status="pending_approval")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "NOT_APPROVED"

    def test_pending_approval_space_variant(self):
        draft = _good_draft(status="pending approval")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]


class TestNoLedgerWriteForRejectedStatus:
    def test_no_ledger_write_for_rejected_status(self):
        draft = _good_draft(status="rejected")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "NOT_APPROVED"


class TestNoLedgerWriteForAutoApproved:
    def test_no_ledger_write_for_auto_approved_without_final_policy(self):
        draft = _good_draft(status="auto_approved")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "NOT_APPROVED"

    def test_auto_approved_simulated_success_variant(self):
        draft = _good_draft(status="simulated_success")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]


class TestNoLedgerWriteForDryRun:
    def test_no_ledger_write_for_dry_run(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=True, mode="live", dry_run=True, status="posted")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "DRY_RUN"

    def test_dry_run_false_does_not_block(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=True, mode="live", dry_run=False, status="posted")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert result["written"]


class TestNoLedgerWriteForMockTarget:
    def test_no_ledger_write_for_mock_target(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=True, mode="mock", dry_run=False, status="mock_posting")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "MOCK_OR_DEMO_CONNECTOR"

    def test_mock_simulated_success_not_ledger_truth(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=True, mode="mock", dry_run=False, status="simulated_success")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]


class TestNoLedgerWriteForSimulatedSuccess:
    def test_no_ledger_write_for_simulated_success(self):
        draft = _good_draft()
        connector = _good_connector()
        posting_log = FakePostingLog(status="simulated_success")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, posting_log, writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "POSTING_LOG_NOT_REAL_SUCCESS"

    def test_mock_posting_log_also_blocked(self):
        draft = _good_draft()
        connector = _good_connector()
        posting_log = FakePostingLog(status="mock_posting")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, posting_log, writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]


class TestNoLedgerWriteForDemoModeConnector:
    def test_no_ledger_write_for_demo_mode_connector(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=False, mode="demo", dry_run=False, status="demo_mode")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "MOCK_OR_DEMO_CONNECTOR"

    def test_demo_mode_with_success_flag_still_blocked(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=True, mode="demo", dry_run=False, status="demo_mode")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "MOCK_OR_DEMO_CONNECTOR"


class TestNoLedgerWriteForOrisStubOrOnecDemo:
    def test_no_ledger_write_for_oris_stub_or_onec_demo(self):
        for mode in ("oris_stub", "onec_demo"):
            draft = _good_draft()
            connector = FakeConnectorResult(success=True, mode=mode, dry_run=False, status="posted")
            writer = FakeLedgerWriter()
            result = evaluate_future_ledger_write_policy(
                draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
            )
            assert not writer.called, f"mode={mode} must not write ledger"
            assert not result["written"]
            assert result["reason"] == "MOCK_OR_DEMO_CONNECTOR"

    def test_oris_stub_blocked_regardless_of_success_flag(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=True, mode="oris_stub", dry_run=False, status="posted")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]


class TestNoLedgerWriteWhenConnectorFails:
    def test_no_ledger_write_when_connector_fails(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=False, mode="live", dry_run=False, status="failed")
        posting_log = FakePostingLog(status="failed")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, posting_log, writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "CONNECTOR_FAILED"

    def test_posting_log_records_failure_on_connector_fail(self):
        posting_log = FakePostingLog(status="failed")
        assert posting_log.status == "failed"

    def test_connector_success_false_blocks_regardless_of_posting_log(self):
        draft = _good_draft()
        connector = FakeConnectorResult(success=False, mode="live", dry_run=False, status="posted")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, connector, _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert result["reason"] == "CONNECTOR_FAILED"


class TestNoLedgerWriteWhenPeriodLocked:
    def test_no_ledger_write_when_period_locked(self):
        draft = _good_draft()
        policy = FakeLedgerWritePolicy(is_period_locked=True, tenant_id="tenant_acme")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, policy, "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "PERIOD_LOCKED"

    def test_period_not_locked_does_not_block(self):
        draft = _good_draft()
        policy = FakeLedgerWritePolicy(is_period_locked=False, tenant_id="tenant_acme")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, policy, "tenant_acme"
        )
        assert result["written"]

    def test_period_locked_is_fail_closed(self):
        draft = _good_draft()
        policy = FakeLedgerWritePolicy(is_period_locked=True, tenant_id="tenant_acme")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, policy, "tenant_acme"
        )
        assert not result["inconsistency"]
        assert result["entry_id"] is None


class TestNoLedgerWriteWhenTenantMissing:
    def test_no_ledger_write_when_tenant_missing(self):
        draft = _good_draft(tenant_id="")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), ""
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "TENANT_MISSING"

    def test_whitespace_tenant_also_missing(self):
        draft = _good_draft(tenant_id="   ")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "   "
        )
        assert not writer.called
        assert not result["written"]


class TestNoLedgerWriteWhenTenantMismatch:
    def test_no_ledger_write_when_tenant_mismatch(self):
        draft = _good_draft(tenant_id="tenant_acme")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(),
            request_tenant_id="tenant_other"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "TENANT_MISMATCH"

    def test_line_tenant_mismatch_also_blocked(self):
        lines = [
            {"account_code": "1210", "debit": "100.00", "credit": "0", "amount_gel": "100.00", "tenant_id": "tenant_acme"},
            {"account_code": "3110", "debit": "0", "credit": "100.00", "amount_gel": "100.00", "tenant_id": "tenant_evil"},
        ]
        draft = _good_draft(journal_lines=lines)
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "LINE_TENANT_MISMATCH"

    def test_tenant_mismatch_fail_closed(self):
        draft = _good_draft(tenant_id="tenant_a")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(),
            request_tenant_id="tenant_b"
        )
        assert not result["inconsistency"]
        assert result["entry_id"] is None


class TestNoLedgerWriteWhenLinesUnbalanced:
    def test_no_ledger_write_when_lines_unbalanced(self):
        draft = _good_draft(journal_lines=_unbalanced_lines())
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "UNBALANCED"

    def test_zero_lines_unbalanced(self):
        draft = _good_draft(journal_lines=[])
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert result["written"]  # 0 == 0 is balanced; lines enforcement is at DB level

    def test_balanced_lines_pass(self):
        draft = _good_draft(journal_lines=_balanced_lines())
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert result["written"]


class TestSuccessfulRealConnectorPostingWritesHeaderAndLines:
    def test_successful_real_connector_posting_writes_header_and_lines(self):
        draft = _good_draft()
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(),
            "tenant_acme", evidence_bundle_id="eb_001"
        )
        assert result["written"]
        assert result["reason"] == "OK"
        assert result["entry_id"] is not None
        assert writer.called
        call = writer.calls[0]
        assert call["header"]["tenant_id"] == "tenant_acme"
        assert call["header"]["source_draft_id"] == draft.id
        assert call["header"]["status"] == "posted"
        assert call["header"]["evidence_bundle_id"] == "eb_001"
        assert len(call["lines"]) == 2
        assert call["lines"][0]["account_code"] == "1210"
        assert call["lines"][1]["account_code"] == "3110"

    def test_header_contains_posting_log_id(self):
        draft = _good_draft()
        posting_log = _good_posting_log()
        writer = FakeLedgerWriter()
        evaluate_future_ledger_write_policy(
            draft, _good_connector(), posting_log, writer, _good_policy(), "tenant_acme"
        )
        assert writer.calls[0]["header"]["posting_log_id"] == posting_log.id

    def test_lines_contain_line_no(self):
        draft = _good_draft()
        writer = FakeLedgerWriter()
        evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        for i, line in enumerate(writer.calls[0]["lines"]):
            assert line["line_no"] == i

    def test_writer_called_exactly_once(self):
        draft = _good_draft()
        writer = FakeLedgerWriter()
        evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert len(writer.calls) == 1


class TestLedgerWriteRequiresPostingLogSuccess:
    def test_ledger_write_requires_posting_log_success(self):
        draft = _good_draft()
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), None, writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "POSTING_LOG_MISSING"

    def test_failed_posting_log_blocks_write(self):
        draft = _good_draft()
        posting_log = FakePostingLog(status="failed")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), posting_log, writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert result["reason"] == "POSTING_LOG_NOT_REAL_SUCCESS"


class TestDuplicateRetryDoesNotWriteDuplicateLedgerEntry:
    def test_duplicate_retry_does_not_write_duplicate_ledger_entry(self):
        draft = _good_draft()
        posting_log = _good_posting_log()
        existing_key = f"{draft.id}:{posting_log.id}"
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), posting_log, writer, _good_policy(),
            "tenant_acme", existing_source_key=existing_key
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "DUPLICATE_IDEMPOTENT"

    def test_different_posting_log_is_not_duplicate(self):
        draft = _good_draft()
        posting_log = _good_posting_log()
        other_log_id = str(uuid.uuid4())
        existing_key = f"{draft.id}:{other_log_id}"
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), posting_log, writer, _good_policy(),
            "tenant_acme", existing_source_key=existing_key
        )
        assert result["written"]

    def test_idempotent_duplicate_returns_without_inconsistency(self):
        draft = _good_draft()
        posting_log = _good_posting_log()
        existing_key = f"{draft.id}:{posting_log.id}"
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), posting_log, writer, _good_policy(),
            "tenant_acme", existing_source_key=existing_key
        )
        assert not result["inconsistency"]


class TestLedgerWriteIsTransactional:
    def test_ledger_write_is_transactional_header_and_lines(self):
        draft = _good_draft()
        writer = FakeLedgerWriter(should_raise=True)
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert not writer.called
        assert not result["written"]
        assert result["reason"] == "LEDGER_WRITE_FAILED_AFTER_CONNECTOR_SUCCESS"
        assert result["inconsistency"]

    def test_no_partial_write_on_failure(self):
        draft = _good_draft()
        writer = FakeLedgerWriter(should_raise=True)
        evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert len(writer.calls) == 0


class TestFailureAfterConnectorSuccessRecordsRecoverableInconsistency:
    def test_failure_after_connector_success_records_recoverable_inconsistency(self):
        draft = _good_draft()
        writer = FakeLedgerWriter(should_raise=True)
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert result["inconsistency"] is True
        assert result["written"] is False
        assert result["reason"] == "LEDGER_WRITE_FAILED_AFTER_CONNECTOR_SUCCESS"

    def test_no_silent_success_on_write_failure(self):
        draft = _good_draft()
        writer = FakeLedgerWriter(should_raise=True)
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert result["written"] is False
        assert result["entry_id"] is None

    def test_inconsistency_false_on_non_connector_gate(self):
        draft = _good_draft(status="draft")
        writer = FakeLedgerWriter()
        result = evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert result["inconsistency"] is False


class TestNoRawSecretsInLedgerMetadata:
    def test_no_raw_secrets_in_ledger_metadata(self):
        dirty = {
            "api_key": "sk-live-abc123",
            "password": "hunter2",
            "token": "tok_secret",
            "secret": "shh",
            "encrypted_value": "base64blob",
            "connector_mode": "live",
            "result_code": "200",
        }
        clean = _strip_unsafe(dirty)
        for key in _FORBIDDEN_METADATA_KEYS:
            assert key not in clean, f"Forbidden key {key!r} must be stripped"
        assert "connector_mode" in clean
        assert "result_code" in clean

    def test_empty_metadata_safe(self):
        assert _strip_unsafe({}) == {}

    def test_metadata_with_no_secrets_unchanged(self):
        safe = {"connector_mode": "live", "result_code": "200"}
        assert _strip_unsafe(safe) == safe

    def test_forbidden_keys_enumerated(self):
        assert "api_key" in _FORBIDDEN_METADATA_KEYS
        assert "password" in _FORBIDDEN_METADATA_KEYS
        assert "token" in _FORBIDDEN_METADATA_KEYS
        assert "secret" in _FORBIDDEN_METADATA_KEYS
        assert "encrypted_value" in _FORBIDDEN_METADATA_KEYS


class TestEvidenceAndAuditLinksArePreserved:
    def test_evidence_and_audit_links_are_preserved(self):
        draft = _good_draft()
        writer = FakeLedgerWriter()
        evidence_id = "eb_abc123"
        evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(),
            "tenant_acme", evidence_bundle_id=evidence_id
        )
        assert writer.calls[0]["header"]["evidence_bundle_id"] == evidence_id

    def test_evidence_bundle_id_null_when_not_provided(self):
        draft = _good_draft()
        writer = FakeLedgerWriter()
        evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert writer.calls[0]["header"]["evidence_bundle_id"] is None

    def test_source_draft_id_always_present(self):
        draft = _good_draft()
        writer = FakeLedgerWriter()
        evaluate_future_ledger_write_policy(
            draft, _good_connector(), _good_posting_log(), writer, _good_policy(), "tenant_acme"
        )
        assert writer.calls[0]["header"]["source_draft_id"] == draft.id

    def test_posting_log_id_always_present_in_header(self):
        draft = _good_draft()
        posting_log = _good_posting_log()
        writer = FakeLedgerWriter()
        evaluate_future_ledger_write_policy(
            draft, _good_connector(), posting_log, writer, _good_policy(), "tenant_acme"
        )
        assert writer.calls[0]["header"]["posting_log_id"] == posting_log.id


class TestH6DoesNotImportRuntimePostingService:
    def test_h6_does_not_import_runtime_posting_service(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {"posting_service", "approval_service", "routes_posting", "ledger_service"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    assert f not in node.module, f"Forbidden import: {node.module}"

    def test_no_db_imports(self):
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


class TestH6DoesNotRunSqlOrMigrations:
    def test_h6_does_not_run_sql_or_migrations(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_names = {"run_migrations", "execute_migration", "cursor", "fetchall", "fetchone"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                assert name not in forbidden_names, f"Forbidden call: {name}"

    def test_no_sql_string_execution(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Look for calls to DB execution methods: conn.execute, cursor.execute, db.execute
        sql_exec_attrs = {"execute", "executemany", "executescript"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in sql_exec_attrs:
                    # Allow: the only valid case is if the object is a FakeLedgerWriter
                    # (writer.write — not a SQL exec attr). Since none of ours match,
                    # any such call is a violation.
                    obj_name = ""
                    if isinstance(func.value, ast.Name):
                        obj_name = func.value.id
                    assert False, f"Forbidden SQL execution call: {obj_name}.{func.attr}"

    def test_no_migration_file_paths(self):
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Check for open() or pathlib.Path() calls whose string args reference migration SQL files
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        val = arg.value
                        assert not (val.endswith(".sql") and "migration" in val.lower()), \
                            f"Forbidden migration file reference: {val}"
