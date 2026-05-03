"""app/api/routes_reconciliation.py — Bank reconciliation with smart auto-matching."""
import logging
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.response_utils import ok_response, error_response, http_error
from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_conn, _q, get_db
from app.api.services.reconciliation_service import (
    reconcile_bank_statement, apply_reconciliation,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


class BankTransaction(BaseModel):
    id: Optional[str] = None
    description: str
    amount: float
    transaction_date: str        # YYYY-MM-DD
    reference: Optional[str] = None
    currency: str = "GEL"


class ReconcileRequest(BaseModel):
    transactions: List[BankTransaction]
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class ApplyMatchRequest(BaseModel):
    matches: List[dict]  # [{draft_id, bank_txn_id}]


@router.post("/run")
def run_reconciliation(body: ReconcileRequest, request: Request):
    """
    Smart bank reconciliation — matches bank transactions against journal drafts.
    Returns auto-matched, suggested, and unmatched items.
    """
    require_permission(request, "bank:process")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    txns = [t.dict() for t in body.transactions]
    date_from = date.fromisoformat(body.date_from) if body.date_from else None
    date_to = date.fromisoformat(body.date_to) if body.date_to else None

    conn = get_db()
    try:
        result = reconcile_bank_statement(conn, tenant_id, txns, date_from, date_to)
    except Exception as e:
        conn.close()
        return error_response("Reconciliation failed", "RECON_ERROR", str(e))
    finally:
        conn.close()

    return ok_response("Reconciliation complete", result)


@router.post("/apply")
def apply_matches(body: ApplyMatchRequest, request: Request):
    """Confirm and persist reconciliation matches."""
    require_permission(request, "bank:process")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conn = get_db()
    try:
        count = apply_reconciliation(conn, tenant_id, body.matches)
    except Exception as e:
        conn.close()
        return error_response("Apply failed", "APPLY_ERROR", str(e))
    finally:
        conn.close()

    return ok_response(f"Applied {count} matches", {"updated": count})


@router.get("/status")
async def reconciliation_status(request: Request):
    require_permission(request, "bank:process")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q("""
                SELECT
                    COUNT(*) FILTER (WHERE reconciled = TRUE)  AS reconciled_count,
                    COUNT(*) FILTER (WHERE reconciled IS NULL OR reconciled = FALSE) AS unreconciled_count
                FROM journal_drafts WHERE tenant_id = %s
            """), tenant_id)
        stats = {"reconciled": row["reconciled_count"] or 0, "unreconciled": row["unreconciled_count"] or 0} if row else {}
    except Exception:
        stats = {}

    return ok_response("Reconciliation status", {"ready": True, **stats})


@router.get("/history")
async def reconciliation_history(request: Request):
    require_permission(request, "bank:process")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT status, COUNT(*) AS cnt,
                       MIN(created_at) AS first, MAX(created_at) AS last
                FROM journal_drafts WHERE tenant_id = %s
                GROUP BY status ORDER BY cnt DESC
            """), tenant_id)]
        for r in rows:
            for f in ("first", "last"):
                if r.get(f):
                    r[f] = r[f].isoformat()
    except Exception as e:
        log.warning("reconciliation history failed: %s", e)
        rows = []

    return ok_response("Reconciliation history", {"summary": rows})
