"""app/api/services/payroll_rsge_workflow_service.py — RS.ge Payroll Workflow (Task 12D).

Manages the RS.ge PAYG declaration workflow:
  draft → submitted → accepted | rejected

Also generates bank transfer instructions for:
  - Net salary payments to employees
  - PIT (personal income tax) to RS.ge treasury
  - PAYG (pension fund contribution) to Pension Agency
  - Employer pension contribution to Pension Agency

Submission records are stored in payroll_submissions table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.db import get_conn, _q

# RS.ge treasury account (Georgian Revenue Service)
RSGE_TREASURY_ACCOUNT = "GE60TB0000000000000001"
PENSION_AGENCY_ACCOUNT = "GE40TB0000000000000002"

SUBMISSION_STATUSES = {"draft", "submitted", "accepted", "rejected"}


# ---------------------------------------------------------------------------
# DDL (run once at startup via migrations)
# ---------------------------------------------------------------------------
PAYROLL_SUBMISSIONS_DDL = """
CREATE TABLE IF NOT EXISTS payroll_submissions (
    id             SERIAL PRIMARY KEY,
    tenant_id      TEXT        NOT NULL,
    run_id         INTEGER     NOT NULL,
    period         TEXT        NOT NULL,
    status         TEXT        NOT NULL DEFAULT 'draft'
                              CHECK (status IN ('draft','submitted','accepted','rejected')),
    xml_content    TEXT,
    submission_ref TEXT,
    submitted_at   TIMESTAMPTZ,
    resolved_at    TIMESTAMPTZ,
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, run_id)
);
CREATE INDEX IF NOT EXISTS idx_payroll_submissions_tenant
    ON payroll_submissions (tenant_id, period);
"""


# ---------------------------------------------------------------------------
# Transfer instruction builder (pure — no DB access)
# ---------------------------------------------------------------------------

def build_transfer_instructions(
    payroll: dict,
    tenant_iban: str = "",
    period: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of bank transfer instructions for a finalised payroll run.

    Each instruction has:
        type        — "salary" | "pit" | "payg" | "employer_pension"
        recipient   — name of recipient
        iban        — destination IBAN
        amount      — GEL amount
        reference   — payment reference string
        currency    — "GEL"
    """
    period_label = period or payroll.get("period", "")
    instructions: list[dict[str, Any]] = []

    totals = payroll.get("totals", {})

    # Individual net salary payments
    for emp in payroll.get("employees", []):
        net = round(float(emp.get("net_salary", 0)), 2)
        if net > 0:
            instructions.append({
                "type": "salary",
                "recipient": emp.get("employee_name", "Employee"),
                "iban": emp.get("iban", ""),
                "amount": net,
                "reference": f"Salary {period_label} / {emp.get('employee_name', '')}",
                "currency": "GEL",
            })

    # PIT to RS.ge
    pit = round(float(totals.get("pit", 0)), 2)
    if pit > 0:
        instructions.append({
            "type": "pit",
            "recipient": "Revenue Service of Georgia (RS.ge)",
            "iban": RSGE_TREASURY_ACCOUNT,
            "amount": pit,
            "reference": f"PIT {period_label}",
            "currency": "GEL",
        })

    # PAYG (employee pension) to Pension Agency
    payg = round(float(totals.get("payg", 0)), 2)
    if payg > 0:
        instructions.append({
            "type": "payg",
            "recipient": "Pension Agency of Georgia",
            "iban": PENSION_AGENCY_ACCOUNT,
            "amount": payg,
            "reference": f"Employee pension {period_label}",
            "currency": "GEL",
        })

    # Employer pension contribution
    employer_pension = round(float(totals.get("employer_pension", 0)), 2)
    if employer_pension > 0:
        instructions.append({
            "type": "employer_pension",
            "recipient": "Pension Agency of Georgia",
            "iban": PENSION_AGENCY_ACCOUNT,
            "amount": employer_pension,
            "reference": f"Employer pension {period_label}",
            "currency": "GEL",
        })

    return instructions


def transfer_summary(instructions: list[dict]) -> dict[str, Any]:
    """Aggregate transfer instructions into a payment summary."""
    total = round(sum(i["amount"] for i in instructions), 2)
    by_type: dict[str, float] = {}
    for ins in instructions:
        by_type[ins["type"]] = round(by_type.get(ins["type"], 0.0) + ins["amount"], 2)
    return {
        "total_amount": total,
        "instruction_count": len(instructions),
        "by_type": by_type,
        "currency": "GEL",
    }


# ---------------------------------------------------------------------------
# Async workflow functions
# ---------------------------------------------------------------------------

async def upsert_submission(
    tenant_id: str,
    run_id: int,
    period: str,
    xml_content: str,
) -> dict[str, Any]:
    """Create or return existing submission record in 'draft' status."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                INSERT INTO payroll_submissions
                    (tenant_id, run_id, period, xml_content, status)
                VALUES ($1, $2, $3, $4, 'draft')
                ON CONFLICT (tenant_id, run_id)
                DO UPDATE SET
                    xml_content = EXCLUDED.xml_content,
                    updated_at  = NOW()
                RETURNING id, tenant_id, run_id, period, status,
                          submission_ref, submitted_at, resolved_at, created_at, updated_at
            """),
            tenant_id, run_id, period, xml_content,
        )
    return dict(row)


async def submit_declaration(
    tenant_id: str,
    run_id: int,
    submission_ref: str | None = None,
) -> dict[str, Any]:
    """Advance submission from 'draft' to 'submitted'.

    Returns the updated submission record.
    Raises ValueError if already submitted/accepted/rejected.
    """
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                UPDATE payroll_submissions
                SET status         = 'submitted',
                    submitted_at   = NOW(),
                    submission_ref = COALESCE($3, submission_ref),
                    updated_at     = NOW()
                WHERE tenant_id = $1 AND run_id = $2 AND status = 'draft'
                RETURNING id, tenant_id, run_id, period, status,
                          submission_ref, submitted_at, resolved_at, created_at, updated_at
            """),
            tenant_id, run_id, submission_ref,
        )
    if row is None:
        raise ValueError("SUBMISSION_NOT_FOUND_OR_ALREADY_SUBMITTED")
    return dict(row)


async def resolve_submission(
    tenant_id: str,
    run_id: int,
    outcome: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Advance submission to 'accepted' or 'rejected'.

    *outcome* must be 'accepted' or 'rejected'.
    """
    if outcome not in ("accepted", "rejected"):
        raise ValueError("INVALID_OUTCOME")
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                UPDATE payroll_submissions
                SET status      = $3,
                    resolved_at = NOW(),
                    notes       = COALESCE($4, notes),
                    updated_at  = NOW()
                WHERE tenant_id = $1 AND run_id = $2 AND status = 'submitted'
                RETURNING id, tenant_id, run_id, period, status,
                          submission_ref, submitted_at, resolved_at, created_at, updated_at
            """),
            tenant_id, run_id, outcome, notes,
        )
    if row is None:
        raise ValueError("SUBMISSION_NOT_FOUND_OR_NOT_SUBMITTED")
    return dict(row)


async def get_submission(tenant_id: str, run_id: int) -> dict[str, Any] | None:
    """Return the submission record for a payroll run, or None."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                SELECT id, tenant_id, run_id, period, status,
                       submission_ref, submitted_at, resolved_at, notes, created_at, updated_at
                FROM payroll_submissions
                WHERE tenant_id = $1 AND run_id = $2
            """),
            tenant_id, run_id,
        )
    return dict(row) if row else None


async def list_submissions(
    tenant_id: str,
    period: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List submission records for a tenant, optionally filtered."""
    async with get_conn() as conn:
        params: list = [tenant_id]
        where = ["tenant_id = $1"]
        if period:
            params.append(period)
            where.append(f"period = ${len(params)}")
        if status:
            params.append(status)
            where.append(f"status = ${len(params)}")
        rows = await conn.fetch(
            f"""
            SELECT id, tenant_id, run_id, period, status,
                   submission_ref, submitted_at, resolved_at, created_at
            FROM payroll_submissions
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            """,
            *params,
        )
    return [dict(r) for r in rows]
