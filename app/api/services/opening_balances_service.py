"""app/api/services/opening_balances_service.py — Opening Balances (Task 12A).

Opening balances represent the beginning trial balance for a tenant at the
start of an accounting period (typically the first day of the fiscal year).
They feed into the Trial Balance, Balance Sheet, and Ledger reports as the
starting point before any transactions are recorded.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.api.db import get_conn, _q


async def upsert_opening_balance(
    tenant_id: str,
    account_code: str,
    account_name: str,
    debit: Decimal,
    credit: Decimal,
    as_of_date: date,
    created_by: str,
) -> dict[str, Any]:
    """Insert or replace the opening balance for one account on a given date."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                INSERT INTO opening_balances
                    (tenant_id, account_code, account_name, debit, credit, as_of_date, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (tenant_id, account_code, as_of_date)
                DO UPDATE SET
                    account_name = EXCLUDED.account_name,
                    debit        = EXCLUDED.debit,
                    credit       = EXCLUDED.credit,
                    created_by   = EXCLUDED.created_by,
                    updated_at   = NOW()
                RETURNING id, tenant_id, account_code, account_name,
                          debit, credit, as_of_date, created_by, created_at, updated_at
            """),
            tenant_id, account_code, account_name,
            str(debit), str(credit), as_of_date, created_by,
        )
    return _row_to_dict(dict(row))


async def list_opening_balances(
    tenant_id: str,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Return all opening balances for a tenant, optionally filtered by date."""
    async with get_conn() as conn:
        if as_of_date:
            rows = await conn.fetch(
                _q("""
                    SELECT id, tenant_id, account_code, account_name,
                           debit, credit, as_of_date, created_by, created_at, updated_at
                    FROM opening_balances
                    WHERE tenant_id = $1 AND as_of_date = $2
                    ORDER BY account_code
                """),
                tenant_id, as_of_date,
            )
        else:
            rows = await conn.fetch(
                _q("""
                    SELECT id, tenant_id, account_code, account_name,
                           debit, credit, as_of_date, created_by, created_at, updated_at
                    FROM opening_balances
                    WHERE tenant_id = $1
                    ORDER BY as_of_date DESC, account_code
                """),
                tenant_id,
            )
    return [_row_to_dict(dict(r)) for r in rows]


async def delete_opening_balance(
    tenant_id: str,
    account_code: str,
    as_of_date: date,
) -> bool:
    """Delete one opening balance row. Returns True if a row was deleted."""
    async with get_conn() as conn:
        result = await conn.execute(
            _q("""
                DELETE FROM opening_balances
                WHERE tenant_id = $1 AND account_code = $2 AND as_of_date = $3
            """),
            tenant_id, account_code, as_of_date,
        )
    return result.endswith("1")


async def get_opening_balance_totals(
    tenant_id: str,
    as_of_date: date,
) -> dict[str, Any]:
    """Return debit/credit totals and balance check for a given date."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                SELECT
                    COUNT(*)                       AS row_count,
                    COALESCE(SUM(debit::numeric), 0)  AS total_debit,
                    COALESCE(SUM(credit::numeric), 0) AS total_credit
                FROM opening_balances
                WHERE tenant_id = $1 AND as_of_date = $2
            """),
            tenant_id, as_of_date,
        )
    total_debit = float(row["total_debit"])
    total_credit = float(row["total_credit"])
    return {
        "as_of_date": as_of_date.isoformat(),
        "row_count": int(row["row_count"]),
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balanced": abs(total_debit - total_credit) < 0.005,
        "difference": round(abs(total_debit - total_credit), 2),
    }


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    for k in ("debit", "credit"):
        if k in row:
            row[k] = round(float(row[k]), 2)
    for k in ("as_of_date", "created_at", "updated_at"):
        if k in row and row[k] is not None:
            row[k] = str(row[k])
    return row
