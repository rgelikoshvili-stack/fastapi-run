"""
decision_engine/pipeline.py
Main Decision Engine Pipeline:
Ingest → Normalize → Exact Match → Partial Match → Residual → Gemini Validate → Draft
"""
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

import psycopg2
import psycopg2.extras

from app.api.db import get_db
from .normalize import normalize_text, parse_amount, detect_vat_flag, normalize_partner
from .matcher import exact_match, partial_match
from .residual import classify_residual, gemini_validate

log = logging.getLogger(__name__)


def _build_journal_lines(match_result: dict, invoice: dict, tenant_id: str) -> list[dict]:
    """Convert match result into journal entry lines."""
    lines = []

    if match_result["match_type"] == "exact":
        cand = match_result["matched_candidate"]
        lines.append({
            "description": invoice.get("description") or cand.get("description") or "",
            "amount": invoice.get("amount") or cand.get("amount"),
            "debit_account": invoice.get("debit_account") or "1110",
            "credit_account": invoice.get("credit_account") or cand.get("account_code") or "2110",
            "account_code": cand.get("account_code") or invoice.get("account_code") or "2110",
            "confidence": match_result["confidence"],
            "match_type": "exact",
            "explanation": f"Exact match: {cand.get('description','?')}",
        })
        return lines

    # Partial match — build one line per matched pair + residual line
    for ml in match_result.get("lines") or []:
        cand = ml.get("matched_candidate")
        account = (cand.get("account_code") if cand else None) or "2110"
        lines.append({
            "description": ml["line_description"],
            "amount": ml["line_amount"],
            "debit_account": "1110",
            "credit_account": account,
            "account_code": account,
            "confidence": min(match_result["confidence"], ml.get("similarity_score", 0.5) + 0.2),
            "match_type": "partial",
            "explanation": (
                f"Matched: {cand.get('description','?')} (sim={ml.get('similarity_score',0):.0%})"
                if cand else f"Unmatched line: {ml['line_description']}"
            ),
        })

    # Residual line
    residual = match_result.get("residual", 0.0)
    if match_result.get("residual_significant") and abs(residual) >= 5.0:
        residual_cls = classify_residual(
            description=invoice.get("description") or "",
            amount=abs(residual),
            context={
                "matched_description": ", ".join(l["line_description"] for l in match_result.get("lines", [])),
                "partner": invoice.get("partner") or "",
                "invoice_total": invoice.get("amount"),
            },
            tenant_id=tenant_id,
        )
        lines.append({
            "description": f"Residual: {invoice.get('description') or ''}",
            "amount": abs(residual),
            "debit_account": "1110" if residual < 0 else "7990",
            "credit_account": residual_cls["account_code"],
            "account_code": residual_cls["account_code"],
            "confidence": residual_cls["confidence"],
            "match_type": "residual",
            "explanation": residual_cls["explanation"],
            "model_used": residual_cls.get("model_used"),
        })

    return lines


def _needs_gemini(match_result: dict, lines: list[dict]) -> bool:
    residual_pct = 0.0
    invoice_amt = match_result.get("_invoice_amount", 0)
    residual = abs(match_result.get("residual", 0))
    if invoice_amt and invoice_amt > 0:
        residual_pct = residual / invoice_amt

    has_partner_mismatch = match_result.get("confidence", 1.0) < 0.80
    return (
        residual_pct > 0.20
        or has_partner_mismatch
        or any(l.get("confidence", 1.0) < 0.80 for l in lines)
    )


def _invoice_fingerprint(invoice: dict, tenant_id: str) -> str:
    """Stable fingerprint for deduplication: tenant+description+amount+date."""
    import hashlib
    desc = (invoice.get("description") or "").strip().lower()
    amount = str(round(float(invoice.get("amount") or 0), 2))
    date = str(invoice.get("date") or "")
    partner = (invoice.get("partner") or "").strip().lower()
    raw = f"{tenant_id}|{desc}|{amount}|{date}|{partner}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _save_drafts(lines: list[dict], invoice: dict, match_result: dict, tenant_id: str) -> list[int]:
    """
    Persist journal draft lines to DB. Returns list of created draft IDs.
    Raises on DB error so callers can surface the failure.
    """
    created_ids = []
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        fingerprint = _invoice_fingerprint(invoice, tenant_id)

        # Idempotency: skip if drafts with this fingerprint already exist
        cur.execute(
            """
            SELECT id FROM journal_drafts
            WHERE tenant_id = %s
              AND source_type = 'decision_engine'
              AND engine_metadata->>'invoice_fingerprint' = %s
            LIMIT 1
            """,
            (tenant_id, fingerprint),
        )
        if cur.fetchone():
            log.info("_save_drafts: fingerprint %s already exists — skipping duplicate", fingerprint)
            cur.close()
            conn.close()
            return []

        engine_meta = {
            "match_type": match_result.get("match_type"),
            "confidence": match_result.get("confidence"),
            "autopilot_flag": match_result.get("autopilot_flag"),
            "line_count": len(lines),
            "residual": match_result.get("residual"),
            "scores": match_result.get("scores"),
            "invoice_fingerprint": fingerprint,
            "fallback_used": any(l.get("model_used") == "fallback" for l in lines),
        }

        for line in lines:
            cur.execute(
                """
                INSERT INTO journal_drafts
                    (tenant_id, date, description, amount,
                     debit_account, credit_account, account_code,
                     confidence, status, source_type, partner,
                     autopilot_flag, engine_metadata, created_at, updated_at)
                VALUES
                    (%s, %s, %s, %s,
                     %s, %s, %s,
                     %s, 'pending_approval', 'decision_engine', %s,
                     %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (
                    tenant_id,
                    invoice.get("date") or datetime.now().date(),
                    line["description"],
                    line["amount"],
                    line.get("debit_account") or "1110",
                    line.get("credit_account") or "2110",
                    line.get("account_code") or "2110",
                    round(line.get("confidence") or 0.5, 4),
                    invoice.get("partner") or "",
                    match_result.get("autopilot_flag") or "needs_review",
                    json.dumps({
                        **engine_meta,
                        "line_explanation": line.get("explanation") or "",
                        "line_match_type": line.get("match_type") or "",
                        "model_used": line.get("model_used"),
                    }),
                ),
            )
            row = cur.fetchone()
            if row:
                created_ids.append(row["id"])

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return created_ids


def run_decision_pipeline(
    invoice: dict,
    candidates: list[dict],
    tenant_id: str = "default",
) -> dict:
    """
    Full pipeline:
    Ingest → Normalize → Exact Match → Partial Match → Residual → Gemini → Draft

    invoice keys: description, amount, partner, date, debit_account, credit_account
    candidates keys: description, amount, partner, date, account_code
    """
    # ── Normalize ────────────────────────────────────────────────────────────
    vat_flag = detect_vat_flag(invoice.get("vat_note") or invoice.get("description") or "")
    amount_info = parse_amount(invoice.get("amount") or 0, vat_inclusive=vat_flag)

    norm_invoice = {
        **invoice,
        "amount": amount_info["net"] if vat_flag is not None else amount_info["gross"],
        "_amount_info": amount_info,
        "description_normalized": normalize_text(invoice.get("description") or ""),
        "partner_normalized": normalize_partner(invoice.get("partner") or ""),
    }

    # ── Exact Match ──────────────────────────────────────────────────────────
    match_result = exact_match(norm_invoice, candidates)

    if match_result:
        lines = _build_journal_lines(match_result, norm_invoice, tenant_id)
    else:
        # ── Partial Match ────────────────────────────────────────────────────
        match_result = partial_match(norm_invoice, candidates, tenant_id)
        match_result["_invoice_amount"] = float(Decimal(str(norm_invoice["amount"])))
        lines = _build_journal_lines(match_result, norm_invoice, tenant_id)

    # ── Gemini Validation (cost-safe: only when needed) ──────────────────────
    gemini_result = {"ok": True, "issues": [], "model_used": "skipped"}
    if _needs_gemini(match_result, lines):
        gemini_result = gemini_validate(lines, {
            "explanation": f"match_type={match_result['match_type']}",
            "partner": norm_invoice.get("partner") or "",
        })

    # If Gemini flags issues, downgrade all lines to manual_review
    if not gemini_result.get("ok"):
        for line in lines:
            line["confidence"] = min(line.get("confidence", 0.5), 0.65)
        if match_result.get("autopilot_flag") == "ready_for_approval":
            match_result["autopilot_flag"] = "needs_review"

    # ── Save to DB ────────────────────────────────────────────────────────────
    # _save_drafts raises on DB error — let it propagate to the route handler
    draft_ids = _save_drafts(lines, norm_invoice, match_result, tenant_id)
    skipped_duplicate = len(draft_ids) == 0 and len(lines) > 0

    return {
        "ok": True,
        "match_type": match_result["match_type"],
        "confidence": match_result["confidence"],
        "autopilot_flag": match_result.get("autopilot_flag"),
        "draft_ids": draft_ids,
        "lines": lines,
        "residual": match_result.get("residual"),
        "gemini_validation": gemini_result,
        "amount_info": amount_info,
        "status": "pending_approval",
        "skipped_duplicate": skipped_duplicate,
        "message": (
            "Duplicate skipped — drafts already exist for this invoice"
            if skipped_duplicate else
            f"{'Exact' if match_result['match_type'] == 'exact' else 'Partial'} match — "
            f"{len(draft_ids)} draft(s) created for approval"
        ),
    }
