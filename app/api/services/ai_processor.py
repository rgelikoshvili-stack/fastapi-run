"""app/api/services/ai_processor.py
Bridge Hub — AI Processor (STEP 1.3)
Claude (primary) → Gemini (fallback). Analyzes a document and saves a draft.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.api.services.ai_context_builder import build_ai_context

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
შენ ხარ Bridge Hub-ის ბუღალტრული AI.
გაანალიზე დოკუმენტი და დააბრუნე ᲛᲮᲝᲚᲝᲓ JSON ობიექტი.

ველები:
- document_type: "tax_invoice" | "waybill" | "receipt" | "bank_statement" | "other"
- account_dr: 4-ნიშნა Dr ანგარიშის კოდი (COA-დან)
- account_cr: 4-ნიშნა Cr ანგარიშის კოდი (COA-დან)
- amount: რიცხვი (GEL)
- vat_amount: დღგ-ს თანხა (0 თუ არ გამოიყენება)
- net_amount: თანხა დღგ-ს გარეშე
- partner: კონტრაგენტის სახელი
- description: მოკლე ქართული აღწერა
- confidence: 0.0–1.0
- reasoning: მოკლე ახსნა ქართულად (max 100 სიმბოლო)
- balance_payload: {"debit_account": ..., "credit_account": ..., "amount": ..., "description": ...}

COA, tax_rules და vendor_patterns კონტექსტში მოცემულია.
"""


def _get_db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not configured")
    return psycopg2.connect(url)


def _get_document(tenant_id: str, doc_id: int) -> Optional[dict]:
    try:
        conn = _get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM documents WHERE id = %s AND tenant_id = %s",
                (doc_id, tenant_id),
            )
            row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        log.error("_get_document failed: %s", e)
        return None


def _save_draft(tenant_id: str, ai_output: dict, source_doc_id: Optional[int] = None) -> int:
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO journal_drafts
                    (tenant_id, description, account_dr, account_cr, amount,
                     status, confidence_score, review_required, engine_metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tenant_id,
                    ai_output.get("description", ""),
                    ai_output.get("account_dr"),
                    ai_output.get("account_cr"),
                    ai_output.get("amount", 0),
                    "pending_human_review",
                    ai_output.get("confidence", 0.5),
                    True,
                    json.dumps({
                        "ai_output": ai_output,
                        "source_doc_id": source_doc_id,
                        "ai_model": ai_output.get("_model", "unknown"),
                    }, ensure_ascii=False),
                    datetime.now(timezone.utc),
                ),
            )
            draft_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return draft_id
    except Exception:
        conn.close()
        raise


async def _claude_analyze(text: str, context: dict) -> dict:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=api_key)

    context_str = json.dumps({
        "chart_of_accounts": context.get("chart_of_accounts", {}),
        "tax_rules": context.get("tax_rules", {}),
        "vendor_patterns": context.get("vendor_patterns", [])[:20],
    }, ensure_ascii=False)

    user_text = f"კონტექსტი:\n{context_str}\n\nდოკუმენტი:\n{text[:6000]}"

    resp = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1000,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_text}],
    )
    raw = (resp.content[0].text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw)
    result["_model"] = "claude-3-5-sonnet-20241022"
    return result


async def _gemini_analyze(text: str, context: dict) -> dict:
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    client = genai.Client(api_key=api_key)

    context_str = json.dumps({
        "tax_rules": context.get("tax_rules", {}),
        "vendor_patterns": context.get("vendor_patterns", [])[:10],
    }, ensure_ascii=False)

    prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"კონტექსტი:\n{context_str}\n\n"
        f"დოკუმენტი:\n{text[:4000]}\n\n"
        f"დააბრუნე მხოლოდ JSON:"
    )

    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = resp.text.strip().replace("```json", "").replace("```", "")
    result = json.loads(raw)
    result["_model"] = "gemini-2.5-flash"
    return result


def _validate_ai_response(result: dict) -> bool:
    required = {"account_dr", "account_cr", "amount", "description"}
    if not required.issubset(result.keys()):
        return False
    if not str(result.get("account_dr", "")).isdigit():
        return False
    if not str(result.get("account_cr", "")).isdigit():
        return False
    try:
        float(result["amount"])
    except (TypeError, ValueError):
        return False
    return True


async def ai_process_document(
    tenant_id: str,
    doc_id: int,
    doc_text: Optional[str] = None,
) -> dict:
    """
    Main entry point.
    Accepts either a doc_id (fetches from DB) or doc_text directly.
    Returns {"draft_id": int, "model": str, "confidence": float}.
    """
    if doc_text is None:
        doc = _get_document(tenant_id, doc_id)
        if not doc:
            return {"ok": False, "error": f"document {doc_id} not found"}
        doc_text = doc.get("raw_text") or doc.get("extracted_text") or ""

    if not doc_text or len(doc_text) < 20:
        return {"ok": False, "error": "document text too short for AI analysis"}

    context = build_ai_context(tenant_id)

    result = None
    try:
        result = await _claude_analyze(doc_text, context)
    except Exception as e:
        log.warning("Claude failed (%s), trying Gemini…", e)
        try:
            result = await _gemini_analyze(doc_text, context)
        except Exception as e2:
            log.error("Gemini also failed: %s", e2)
            return {"ok": False, "error": f"all LLMs failed: {e2}"}

    if not _validate_ai_response(result):
        return {"ok": False, "error": "AI response failed validation", "raw": result}

    draft_id = _save_draft(tenant_id, result, source_doc_id=doc_id)

    # Notify connected approval UI clients
    _ws_notify_new_draft(tenant_id, draft_id, result)

    return {
        "ok": True,
        "draft_id": draft_id,
        "model": result.get("_model", "unknown"),
        "confidence": result.get("confidence", 0.5),
        "status": "pending_human_review",
    }


def _ws_notify_new_draft(tenant_id: str, draft_id: int, ai_result: dict):
    """Fire-and-forget WS push to approval UI when AI creates a new draft."""
    try:
        import asyncio
        from app.api.routes_notifications_ws import manager
        from datetime import datetime
        msg = {
            "type": "new_draft",
            "draft_id": draft_id,
            "status": "pending_human_review",
            "description": ai_result.get("description", ""),
            "amount": ai_result.get("amount", 0),
            "confidence": ai_result.get("confidence", 0),
            "model": ai_result.get("_model", "unknown"),
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(manager.send_to_tenant(tenant_id, msg))
        except RuntimeError:
            pass
    except Exception as e:
        log.debug("_ws_notify_new_draft: %s", e)
