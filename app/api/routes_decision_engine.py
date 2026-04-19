"""
app/api/routes_decision_engine.py
Bridge Hub — Decision Engine: Hybrid Matching & AI Pipeline
All results are preview + pending_approval. No auto-approve.
"""
import json
import logging
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.authz import require_permission
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
from app.api.services.decision_engine import run_decision_pipeline

log = logging.getLogger(__name__)

router = APIRouter(prefix="/decision-engine", tags=["decision-engine"])


# ── Request Models ────────────────────────────────────────────────────────────

class InvoiceLine(BaseModel):
    description: str
    amount: float


class AnalyzeRequest(BaseModel):
    description: str
    amount: float
    partner: Optional[str] = None
    date: Optional[str] = None
    vat_note: Optional[str] = None
    debit_account: Optional[str] = None
    credit_account: Optional[str] = None
    candidates: Optional[list[dict]] = None


class BatchAnalyzeRequest(BaseModel):
    invoices: list[AnalyzeRequest]
    candidates: Optional[list[dict]] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/analyze")
def analyze_invoice(req: AnalyzeRequest, request: Request):
    """
    Submit a single invoice for hybrid matching + AI classification.
    Returns draft IDs + preview lines. Status always = pending_approval.
    """
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    invoice = req.model_dump(exclude={"candidates"})
    candidates = req.candidates or []

    try:
        result = run_decision_pipeline(invoice, candidates, tenant_id)
        return ok_response("Decision engine analysis complete", result)
    except Exception as e:
        log.error("analyze_invoice error: %s", e, exc_info=True)
        return error_response("Pipeline failed", "PIPELINE_ERROR", str(e))


@router.post("/analyze/batch")
def analyze_batch(req: BatchAnalyzeRequest, request: Request):
    """Analyze multiple invoices at once."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    candidates = req.candidates or []
    results = []

    for inv in req.invoices:
        invoice = inv.model_dump(exclude={"candidates"})
        inv_candidates = inv.candidates or candidates
        try:
            r = run_decision_pipeline(invoice, inv_candidates, tenant_id)
            results.append({"ok": True, "invoice": invoice.get("description"), **r})
        except Exception as e:
            results.append({
                "ok": False,
                "invoice": invoice.get("description"),
                "error": str(e),
            })

    total_drafts = sum(len(r.get("draft_ids") or []) for r in results)
    return ok_response(
        f"Batch complete: {len(results)} invoices → {total_drafts} drafts",
        {"results": results, "total_drafts": total_drafts},
    )


@router.get("/queue")
def get_de_queue(request: Request, limit: int = 50, offset: int = 0):
    """
    Return journal drafts created by the decision engine (source_type='decision_engine').
    Groups by engine_metadata.match_type and confidence.
    """
    require_permission(request, "approval:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(
                """
                SELECT id, date, description, amount, debit_account, credit_account,
                       account_code, confidence, status, partner,
                       autopilot_flag, engine_metadata, created_at
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND source_type = 'decision_engine'
                  AND status = 'pending_approval'
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (tenant_id, limit, offset),
            )
            rows = []
            for r in cur.fetchall():
                row = dict(r)
                if row.get("engine_metadata") and isinstance(row["engine_metadata"], str):
                    try:
                        row["engine_metadata"] = json.loads(row["engine_metadata"])
                    except Exception:
                        pass
                rows.append(row)

            cur.execute(
                """
                SELECT COUNT(*) as total
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND source_type = 'decision_engine'
                  AND status = 'pending_approval'
                """,
                (tenant_id,),
            )
            total = cur.fetchone()["total"]

        finally:
            cur.close()
            conn.close()

        return ok_response("Decision Engine queue", {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": rows,
        })

    except Exception as e:
        return error_response("Queue failed", "DE_QUEUE_ERROR", str(e))


@router.get("/stats")
def get_de_stats(request: Request):
    """Stats for decision engine drafts."""
    require_permission(request, "approval:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                    COUNT(CASE WHEN status = 'pending_approval' THEN 1 END) as pending,
                    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                    AVG(confidence) as avg_confidence,
                    SUM(amount) as total_amount
                FROM journal_drafts
                WHERE tenant_id = %s AND source_type = 'decision_engine'
                """,
                (tenant_id,),
            )
            row = dict(cur.fetchone())
        finally:
            cur.close()
            conn.close()

        return ok_response("Decision Engine stats", {
            "total": row["total"],
            "approved": row["approved"],
            "pending": row["pending"],
            "rejected": row["rejected"],
            "avg_confidence": round(float(row["avg_confidence"] or 0), 3),
            "total_amount": round(float(row["total_amount"] or 0), 2),
        })

    except Exception as e:
        return error_response("Stats failed", "DE_STATS_ERROR", str(e))


@router.post("/preview")
def preview_pipeline(req: AnalyzeRequest, request: Request):
    """
    Run the pipeline WITHOUT saving to DB — for preview/testing.
    Returns what drafts WOULD be created.
    """
    require_permission(request, "approval:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    invoice = req.model_dump(exclude={"candidates"})
    candidates = req.candidates or []

    try:
        from app.api.services.decision_engine.normalize import normalize_text, parse_amount, detect_vat_flag, normalize_partner
        from app.api.services.decision_engine.matcher import exact_match, partial_match

        vat_flag = detect_vat_flag(invoice.get("vat_note") or invoice.get("description") or "")
        amount_info = parse_amount(invoice.get("amount") or 0, vat_inclusive=vat_flag)

        norm_invoice = {
            **invoice,
            "amount": amount_info["net"] if vat_flag is not None else amount_info["gross"],
            "description_normalized": normalize_text(invoice.get("description") or ""),
            "partner_normalized": normalize_partner(invoice.get("partner") or ""),
        }

        match_result = exact_match(norm_invoice, candidates)
        if not match_result:
            match_result = partial_match(norm_invoice, candidates, tenant_id)

        return ok_response("Pipeline preview (no DB write)", {
            "match_type": match_result["match_type"],
            "confidence": match_result["confidence"],
            "autopilot_flag": match_result.get("autopilot_flag"),
            "amount_info": amount_info,
            "match_detail": match_result,
        })

    except Exception as e:
        log.error("preview_pipeline error: %s", e, exc_info=True)
        return error_response("Preview failed", "PREVIEW_ERROR", str(e))
