"""app/api/services/evidence_workbench_service.py — Document Evidence Workbench (Task 13).

Query layer on top of evidence_bundles:
  - list_bundles_for_draft   — evidence attached to one journal draft
  - list_drafts_without_evidence — audit gap finder
  - get_evidence_summary     — coverage score for a draft
  - link_document_to_draft   — manually attach a document to a draft
"""
from __future__ import annotations

from typing import Any

from app.api.db import get_conn, _q


async def list_bundles_for_draft(
    tenant_id: str,
    draft_id: int,
) -> list[dict[str, Any]]:
    """Return all evidence bundles linked to *draft_id*."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("""
                SELECT id, tenant_id, source_type, source_id, document_id,
                       journal_draft_id, confidence, status,
                       ai_reasoning, extracted_fields, risk_flags,
                       created_at, updated_at
                FROM evidence_bundles
                WHERE tenant_id = $1 AND journal_draft_id = $2
                ORDER BY created_at DESC
            """),
            tenant_id, draft_id,
        )
    return [dict(r) for r in rows]


async def list_drafts_without_evidence(
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return posted/approved journal drafts that have no evidence bundle.

    These are the 'audit gaps' — transactions without supporting documents.
    """
    async with get_conn() as conn:
        total = await conn.fetchval(
            _q("""
                SELECT COUNT(*)
                FROM journal_drafts jd
                WHERE jd.tenant_id = $1
                  AND jd.status IN ('posted', 'approved', 'awaiting_cfo')
                  AND NOT EXISTS (
                      SELECT 1 FROM evidence_bundles eb
                      WHERE eb.tenant_id = jd.tenant_id
                        AND eb.journal_draft_id = jd.id
                  )
            """),
            tenant_id,
        )
        rows = await conn.fetch(
            _q("""
                SELECT jd.id, jd.description, jd.amount, jd.status,
                       jd.created_at, jd.partner, jd.source_document_id
                FROM journal_drafts jd
                WHERE jd.tenant_id = $1
                  AND jd.status IN ('posted', 'approved', 'awaiting_cfo')
                  AND NOT EXISTS (
                      SELECT 1 FROM evidence_bundles eb
                      WHERE eb.tenant_id = jd.tenant_id
                        AND eb.journal_draft_id = jd.id
                  )
                ORDER BY jd.created_at DESC
                LIMIT $2 OFFSET $3
            """),
            tenant_id, limit, offset,
        )
    return {
        "drafts": [dict(r) for r in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


async def get_evidence_summary(
    tenant_id: str,
    draft_id: int,
) -> dict[str, Any]:
    """Return a coverage summary and quality score for *draft_id*.

    Score:
        0   — no evidence at all
        0.5 — evidence exists but low confidence (< 0.6)
        1.0 — evidence with confidence ≥ 0.6
    """
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                SELECT
                    COUNT(*)                              AS bundle_count,
                    COALESCE(MAX(confidence), 0)          AS max_confidence,
                    COALESCE(AVG(confidence), 0)          AS avg_confidence,
                    COUNT(*) FILTER (WHERE document_id IS NOT NULL)
                                                          AS with_document,
                    COUNT(*) FILTER (WHERE ai_reasoning IS NOT NULL
                                       AND ai_reasoning::text != '{}')
                                                          AS with_ai_reasoning
                FROM evidence_bundles
                WHERE tenant_id = $1 AND journal_draft_id = $2
            """),
            tenant_id, draft_id,
        )

    bundle_count = int(row["bundle_count"])
    max_conf = float(row["max_confidence"])

    if bundle_count == 0:
        score = 0.0
        coverage = "none"
    elif max_conf >= 0.6:
        score = 1.0
        coverage = "full"
    else:
        score = 0.5
        coverage = "partial"

    return {
        "draft_id": draft_id,
        "bundle_count": bundle_count,
        "max_confidence": round(max_conf, 4),
        "avg_confidence": round(float(row["avg_confidence"]), 4),
        "with_document": int(row["with_document"]),
        "with_ai_reasoning": int(row["with_ai_reasoning"]),
        "coverage_score": score,
        "coverage": coverage,
    }


async def link_document_to_draft(
    tenant_id: str,
    draft_id: int,
    document_id: int,
    created_by: str = "system",
) -> dict[str, Any]:
    """Manually attach a document to a journal draft by creating an evidence bundle.

    Returns the new bundle record.
    Raises ValueError if the draft or document doesn't exist for this tenant.
    """
    async with get_conn() as conn:
        draft = await conn.fetchrow(
            _q("SELECT id FROM journal_drafts WHERE id = $1 AND tenant_id = $2"),
            draft_id, tenant_id,
        )
        if not draft:
            raise ValueError("DRAFT_NOT_FOUND")

        doc = await conn.fetchrow(
            _q("SELECT id FROM documents WHERE id = $1 AND tenant_id = $2"),
            document_id, tenant_id,
        )
        if not doc:
            raise ValueError("DOCUMENT_NOT_FOUND")

        existing = await conn.fetchrow(
            _q("""
                SELECT id FROM evidence_bundles
                WHERE tenant_id = $1 AND journal_draft_id = $2 AND document_id = $3
            """),
            tenant_id, draft_id, document_id,
        )
        if existing:
            raise ValueError("ALREADY_LINKED")

        row = await conn.fetchrow(
            _q("""
                INSERT INTO evidence_bundles
                    (tenant_id, source_type, source_id, document_id,
                     journal_draft_id, status, created_by, updated_by)
                VALUES ($1, 'manual_link', $2, $3, $4, 'verified', $5, $5)
                RETURNING id, tenant_id, source_type, document_id,
                          journal_draft_id, status, created_at
            """),
            tenant_id, str(document_id), document_id, draft_id, created_by,
        )
    return dict(row)
