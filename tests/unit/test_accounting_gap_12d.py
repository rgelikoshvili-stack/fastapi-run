"""tests/unit/test_accounting_gap_12d.py — Task 12D: Payroll RS.ge Workflow.

Covers:
  1. build_transfer_instructions — salary, PIT, PAYG, employer pension
  2. transfer_summary aggregation
  3. Async: upsert_submission, submit_declaration, resolve_submission, get_submission
  4. Invalid transitions (already submitted, invalid outcome)
  5. payroll_submissions DDL in migrations_tables
  6. Service importable with correct exports
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared test payroll fixture
# ---------------------------------------------------------------------------
def _payroll(period="2026-01"):
    return {
        "period": period,
        "employees": [
            {"employee_name": "ნინო მამიაშვილი", "net_salary": 780.0, "iban": "GE29TB0000000000000001"},
            {"employee_name": "გიორგი ბერიძე",  "net_salary": 940.0, "iban": "GE29TB0000000000000002"},
        ],
        "totals": {
            "gross": 2000.0,
            "payg": 40.0,
            "pit": 400.0,
            "employer_pension": 40.0,
            "net": 1720.0,
        },
    }


# ---------------------------------------------------------------------------
# 1. build_transfer_instructions
# ---------------------------------------------------------------------------
class TestBuildTransferInstructions:
    def test_returns_list(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        result = build_transfer_instructions(_payroll())
        assert isinstance(result, list)

    def test_includes_salary_entries_per_employee(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        result = build_transfer_instructions(_payroll())
        salary = [i for i in result if i["type"] == "salary"]
        assert len(salary) == 2

    def test_salary_amounts_match_net(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        result = build_transfer_instructions(_payroll())
        salary = sorted([i for i in result if i["type"] == "salary"], key=lambda x: x["amount"])
        assert salary[0]["amount"] == 780.0
        assert salary[1]["amount"] == 940.0

    def test_pit_entry_exists(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        result = build_transfer_instructions(_payroll())
        pit = [i for i in result if i["type"] == "pit"]
        assert len(pit) == 1
        assert pit[0]["amount"] == 400.0

    def test_pit_goes_to_rsge(self):
        from app.api.services.payroll_rsge_workflow_service import (
            build_transfer_instructions, RSGE_TREASURY_ACCOUNT
        )
        result = build_transfer_instructions(_payroll())
        pit = next(i for i in result if i["type"] == "pit")
        assert pit["iban"] == RSGE_TREASURY_ACCOUNT

    def test_payg_entry_exists(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        result = build_transfer_instructions(_payroll())
        payg = [i for i in result if i["type"] == "payg"]
        assert len(payg) == 1
        assert payg[0]["amount"] == 40.0

    def test_employer_pension_entry_exists(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        result = build_transfer_instructions(_payroll())
        ep = [i for i in result if i["type"] == "employer_pension"]
        assert len(ep) == 1
        assert ep[0]["amount"] == 40.0

    def test_all_currency_gel(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        result = build_transfer_instructions(_payroll())
        assert all(i["currency"] == "GEL" for i in result)

    def test_period_in_references(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        result = build_transfer_instructions(_payroll(), period="2026-01")
        refs = [i["reference"] for i in result]
        assert any("2026-01" in r for r in refs)

    def test_empty_employees_no_salary_instructions(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions
        p = _payroll()
        p["employees"] = []
        result = build_transfer_instructions(p)
        salary = [i for i in result if i["type"] == "salary"]
        assert salary == []


# ---------------------------------------------------------------------------
# 2. transfer_summary
# ---------------------------------------------------------------------------
class TestTransferSummary:
    def test_total_amount(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions, transfer_summary
        instrs = build_transfer_instructions(_payroll())
        s = transfer_summary(instrs)
        # 780 + 940 + 400 + 40 + 40 = 2200
        assert s["total_amount"] == 2200.0

    def test_instruction_count(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions, transfer_summary
        instrs = build_transfer_instructions(_payroll())
        s = transfer_summary(instrs)
        assert s["instruction_count"] == 5

    def test_by_type_keys(self):
        from app.api.services.payroll_rsge_workflow_service import build_transfer_instructions, transfer_summary
        instrs = build_transfer_instructions(_payroll())
        s = transfer_summary(instrs)
        assert "salary" in s["by_type"]
        assert "pit" in s["by_type"]
        assert "payg" in s["by_type"]
        assert "employer_pension" in s["by_type"]


# ---------------------------------------------------------------------------
# 3. Async workflow functions (mocked DB)
# ---------------------------------------------------------------------------

def _mock_ctx(row):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=row)
    mock_conn.fetch    = AsyncMock(return_value=[row] if row else [])
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__  = AsyncMock(return_value=False)
    return mock_ctx


class TestAsyncWorkflow:
    @pytest.mark.asyncio
    async def test_upsert_submission_returns_dict(self):
        from app.api.services.payroll_rsge_workflow_service import upsert_submission
        row = {"id": 1, "tenant_id": "t1", "run_id": 5, "period": "2026-01",
               "status": "draft", "submission_ref": None, "submitted_at": None,
               "resolved_at": None, "created_at": "2026-01-01", "updated_at": "2026-01-01"}
        with patch("app.api.services.payroll_rsge_workflow_service.get_conn",
                   return_value=_mock_ctx(row)):
            result = await upsert_submission("t1", 5, "2026-01", "<xml/>")
        assert result["status"] == "draft"
        assert result["run_id"] == 5

    @pytest.mark.asyncio
    async def test_submit_declaration_advances_status(self):
        from app.api.services.payroll_rsge_workflow_service import submit_declaration
        row = {"id": 1, "tenant_id": "t1", "run_id": 5, "period": "2026-01",
               "status": "submitted", "submission_ref": "REF-001", "submitted_at": "2026-01-31",
               "resolved_at": None, "created_at": "2026-01-01", "updated_at": "2026-01-31"}
        with patch("app.api.services.payroll_rsge_workflow_service.get_conn",
                   return_value=_mock_ctx(row)):
            result = await submit_declaration("t1", 5, "REF-001")
        assert result["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_submit_declaration_raises_if_not_found(self):
        from app.api.services.payroll_rsge_workflow_service import submit_declaration
        with patch("app.api.services.payroll_rsge_workflow_service.get_conn",
                   return_value=_mock_ctx(None)):
            with pytest.raises(ValueError, match="SUBMISSION_NOT_FOUND_OR_ALREADY_SUBMITTED"):
                await submit_declaration("t1", 99)

    @pytest.mark.asyncio
    async def test_resolve_submission_accepted(self):
        from app.api.services.payroll_rsge_workflow_service import resolve_submission
        row = {"id": 1, "tenant_id": "t1", "run_id": 5, "period": "2026-01",
               "status": "accepted", "submission_ref": "REF-001", "submitted_at": "2026-01-31",
               "resolved_at": "2026-02-01", "created_at": "2026-01-01", "updated_at": "2026-02-01"}
        with patch("app.api.services.payroll_rsge_workflow_service.get_conn",
                   return_value=_mock_ctx(row)):
            result = await resolve_submission("t1", 5, "accepted")
        assert result["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_resolve_submission_invalid_outcome(self):
        from app.api.services.payroll_rsge_workflow_service import resolve_submission
        with pytest.raises(ValueError, match="INVALID_OUTCOME"):
            await resolve_submission("t1", 5, "pending")

    @pytest.mark.asyncio
    async def test_get_submission_returns_none_when_missing(self):
        from app.api.services.payroll_rsge_workflow_service import get_submission
        with patch("app.api.services.payroll_rsge_workflow_service.get_conn",
                   return_value=_mock_ctx(None)):
            result = await get_submission("t1", 999)
        assert result is None


# ---------------------------------------------------------------------------
# 4. DDL presence
# ---------------------------------------------------------------------------
class TestPayrollSubmissionsDDL:
    def test_migration_has_payroll_submissions(self):
        import pathlib
        src = pathlib.Path("app/startup/migrations_tables.py").read_text(encoding="utf-8")
        assert "payroll_submissions" in src
        assert "submitted_at" in src
        assert "submission_ref" in src

    def test_migration_has_status_check_constraint(self):
        import pathlib
        src = pathlib.Path("app/startup/migrations_tables.py").read_text(encoding="utf-8")
        assert "draft" in src
        assert "submitted" in src
        assert "accepted" in src
        assert "rejected" in src


# ---------------------------------------------------------------------------
# 5. Service importable
# ---------------------------------------------------------------------------
class TestServiceImportable:
    def test_module_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.payroll_rsge_workflow_service")
        assert hasattr(mod, "build_transfer_instructions")
        assert hasattr(mod, "transfer_summary")
        assert hasattr(mod, "upsert_submission")
        assert hasattr(mod, "submit_declaration")
        assert hasattr(mod, "resolve_submission")
        assert hasattr(mod, "get_submission")
        assert hasattr(mod, "list_submissions")

    def test_submission_statuses_defined(self):
        from app.api.services.payroll_rsge_workflow_service import SUBMISSION_STATUSES
        assert {"draft", "submitted", "accepted", "rejected"} == SUBMISSION_STATUSES
