"""
Bridge Hub — AI Chat Service
app/api/services/ai_chat_service.py

როლი:
- file -> process_document -> draft
- text -> KB / local rules / vector / memory / LLM
- "გატარე" / "post" -> draft creation
- direct OpenAI call ❌
- unified llm_service ✅

Architecture:
- bridge_hub_knowledge.py = source of truth
- accounting_rules.py = posting engine
- posting_service.py = draft / posting execution
"""

import os
import re
import tempfile
from typing import Optional, List, Dict, Any

from app.api.services.accounting_engine import process_document
from app.api.services.llm_service import classify as llm_classify
from app.api.services.llm_service import generate_preview
from app.api.services.chat_context_service import build_chat_context, format_context_for_prompt

try:
    from app.api.services.llm_service import chat_with_claude, chat_with_claude_structured
    CLAUDE_CHAT_AVAILABLE = True
except ImportError:
    CLAUDE_CHAT_AVAILABLE = False

from app.api.services.posting_service import create_journal_draft

try:
    from app.api.services.ai_orchestrator_service import orchestrate as _orchestrate
    _ORCHESTRATOR_AVAILABLE = True
except ImportError:
    _ORCHESTRATOR_AVAILABLE = False


# ─────────────────────────────────────────────────────────────
# Knowledge Base
# ─────────────────────────────────────────────────────────────
try:
    from bridge_hub_knowledge import (
        calculate_vat,
        calculate_payroll,
        calculate_cit,
        calculate_depreciation,
        classify_transaction,
        search_knowledge,
        learn_new_rule,
        get_context_for_llm,
        get_stats,
        CHART_OF_ACCOUNTS,
        build_journal_from_text,
    )
    KB_LOADED = True
except ImportError:
    KB_LOADED = False
    CHART_OF_ACCOUNTS = {}


# ─────────────────────────────────────────────────────────────
# Vector DB
# ─────────────────────────────────────────────────────────────
_vector_db_available = False
try:
    from bridge_hub_vector_db import (
        hybrid_search,
        learn_from_correction,
        get_vector_stats,
        index_files,
        get_context_for_llm_hybrid,
    )
    _vector_db_available = True
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────
# Accounting Rules
# ─────────────────────────────────────────────────────────────
try:
    from app.api.services.accounting_rules import (
        build_vat_posting,
        build_vat_posting_from_net,
        build_dividend_posting,
        build_payroll_posting,
        build_payroll_from_net_posting,
        format_gel,
    )
    ACCT_RULES_LOADED = True
except ImportError:
    ACCT_RULES_LOADED = False

    def format_gel(a):
        return f"{a:,.2f}₾"


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _extract_amount(text: str) -> Optional[float]:
    normalized = text.lower().replace("₾", " ₾ ").replace("ლარი", " ლარი ")
    m = re.search(r"(\d+(?:[.,]\d+)?)", normalized)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _contains_any(text: str, words: List[str]) -> bool:
    return any(w in text for w in words)


def _format_sources(results) -> List[str]:
    return [f"{r.get('category', 'kb')}: {r.get('source', 'unknown')}" for r in results]


def _create_draft_from_result(result: dict, tenant_id: str, source_document_id: Optional[int] = None) -> dict:
    lines = result.get("lines", []) or []
    if not isinstance(lines, list) or not lines:
        raise ValueError("draft lines are missing")

    description = str(result.get("description") or "AI Draft").strip() or "AI Draft"
    partner = str(result.get("partner") or "Unknown").strip() or "Unknown"
    currency = str(result.get("currency") or "GEL").strip() or "GEL"
    draft_date = result.get("date")

    return create_journal_draft(
        description=description,
        lines=lines,
        tenant_id=tenant_id,
        partner=partner,
        date=draft_date,
        currency=currency,
        source_document_id=source_document_id,
    )


def _build_memory_context(message: str, tenant_id: str) -> Dict[str, Any]:
    """
    Memory / learned rules first.
    იყენებს bridge_hub_knowledge.classify_transaction()-ს როგორც
    learned rules / patterns / memory წყაროს.
    """
    if not KB_LOADED:
        return {
            "matched": False,
            "account_code": None,
            "confidence": 0.0,
            "reasoning": "",
            "source": "kb_unavailable",
        }

    try:
        result = classify_transaction(message, tenant_id)
        account_code = result.get("account") or result.get("account_code")
        confidence = float(result.get("confidence", 0.0))
        source = result.get("source", "memory")
        reason = result.get("reason") or result.get("reasoning") or result.get("matched_on") or ""

        return {
            "matched": bool(account_code),
            "account_code": account_code,
            "confidence": confidence,
            "reasoning": reason,
            "source": source,
        }
    except Exception as e:
        return {
            "matched": False,
            "account_code": None,
            "confidence": 0.0,
            "reasoning": f"memory error: {str(e)}",
            "source": "memory_error",
        }


def _local_answer(message: str) -> Optional[str]:
    if not KB_LOADED:
        return None

    msg = message.lower()

    if _contains_any(msg, ["დივიდენდი", "dividend"]):
        amount = _extract_amount(msg)
        if amount is None:
            return None

        if ACCT_RULES_LOADED:
            d = build_dividend_posting(amount)
            return (
                f"📊 **დივიდენდის 2-ეტაპიანი გატარება — {format_gel(amount)}**\n\n"
                f"**ეტაპი 1 — დარიცხვა:**\n```\n{d['step1']['human_readable']}\n```\n\n"
                f"**ეტაპი 2 — გადახდა + CIT:**\n```\n{d['step2']['human_readable']}\n```"
            )

        r = calculate_cit(amount)
        return (
            f"📊 **CIT გაანგარიშება — {format_gel(amount)}**\n\n"
            f"📒 **გატარება:**\n```\n{r['journal']}\n```"
        )

    if _contains_any(msg, ["cit", "მოგება", "profit"]) and "დივიდენდი" not in msg:
        amount = _extract_amount(msg)
        if amount is None:
            return None

        r = calculate_cit(amount)
        return (
            f"📊 **CIT გაანგარიშება — {format_gel(amount)}**\n\n"
            f"| | |\n|---|---|\n"
            f"| განაწილებული მოგება | **{format_gel(r['distributed_profit'])}** |\n"
            f"| CIT (15%) | **{format_gel(r['cit'])}** |\n"
            f"| **ნეტო** | **{format_gel(r['net_dividend'])}** |"
        )

    if _contains_any(msg, ["ხელფასი", "salary", "payroll", "pit", "payg", "ხელზე"]):
        amount = _extract_amount(msg)
        if amount is None:
            return None

        mode = "net" if "ხელზე" in msg else "gross"

        if ACCT_RULES_LOADED:
            if mode == "net":
                p = build_payroll_from_net_posting(amount)
            else:
                p = build_payroll_posting(amount)

            return (
                f"👤 **ხელფასის გაანგარიშება — {format_gel(amount)}**\n\n"
                f"| | |\n|---|---|\n"
                f"| დათვლილი ბრუტო | **{format_gel(p['gross_salary'])}** |\n"
                f"| PIT (20%) | **{format_gel(p['pit'])}** |\n"
                f"| PAYG თანამშრომელი (2%) | **{format_gel(p['employee_pension'])}** |\n"
                f"| PAYG დამსაქმებელი (2%) | **{format_gel(p['employer_pension'])}** |\n"
                f"| **ნეტო** | **{format_gel(p['net_salary'])}** |\n"
                f"| **ჯამური ხარჯი** | **{format_gel(p['total_employer_cost'])}** |"
            )

        r = calculate_payroll(amount, mode=mode)
        return (
            f"👤 **ხელფასის გაანგარიშება — {format_gel(amount)}**\n\n"
            f"| | |\n|---|---|\n"
            f"| დათვლილი ბრუტო | **{format_gel(r['gross'])}** |\n"
            f"| PIT (20%) | **{format_gel(r['pit'])}** |\n"
            f"| PAYG თანამშრომელი (2%) | **{format_gel(r['payg_employee'])}** |\n"
            f"| **ნეტო** | **{format_gel(r['net'])}** |"
        )

    if _contains_any(msg, ["vat", "დღგ", "ამოიღე", "გამოყავი"]):
        amount = _extract_amount(msg)
        if amount is None:
            return None

        inclusive = not _contains_any(msg, ["გარეშე", "without", "exclusive"])
        payment_status = "unpaid" if _contains_any(msg, ["ინვოისი", "invoice", "unpaid", "მოთხოვნა"]) else "paid"

        if ACCT_RULES_LOADED:
            if inclusive:
                p = build_vat_posting(amount, payment_status=payment_status)
            else:
                p = build_vat_posting_from_net(amount, payment_status=payment_status)

            return (
                f"💰 **VAT გაანგარიშება — {format_gel(amount)}**\n\n"
                f"| | |\n|---|---|\n"
                f"| ნეტო | **{format_gel(p['net'])}** |\n"
                f"| დღგ | **{format_gel(p['vat'])}** |\n"
                f"| ბრუტო | **{format_gel(p['gross'])}** |"
            )

        r = calculate_vat(amount, inclusive=inclusive)
        return (
            f"💰 **VAT გაანგარიშება — {format_gel(amount)}**\n\n"
            f"| | |\n|---|---|\n"
            f"| ნეტო | **{format_gel(r['net'])}** |\n"
            f"| დღგ | **{format_gel(r['vat'])}** |\n"
            f"| ბრუტო | **{format_gel(r['gross'])}** |"
        )

    return None


def _append_memory_to_context(context: str, memory_result: Dict[str, Any]) -> str:
    if not memory_result.get("matched"):
        return context or ""

    memory_block = (
        "\n\n[Memory Match]\n"
        f"Account Code: {memory_result.get('account_code')}\n"
        f"Confidence: {memory_result.get('confidence')}\n"
        f"Source: {memory_result.get('source')}\n"
        f"Reasoning: {memory_result.get('reasoning') or '-'}\n"
    )

    return (context or "") + memory_block


def _extract_draft_id_from_message(message: str) -> Optional[int]:
    """Extract draft/invoice ID mentioned in natural language. e.g. '#1130', 'draft 1130'."""
    import re
    m = re.search(r"(?:draft|invoice|დრაფტ|ინვოის|#)\s*#?(\d+)", message, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# ─────────────────────────────────────────────────────────────
# MAIN CHAT HANDLER
# ─────────────────────────────────────────────────────────────
async def _process_single_file(file, tenant_id: str, session_id: Optional[str]) -> Dict[str, Any]:
    """Process one uploaded file → extract data, create draft if lines found."""
    import base64
    suffix = os.path.splitext(file.filename or "")[1] or ".bin"
    raw_bytes = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw_bytes)
        temp_path = tmp.name

    # Inline preview for images
    preview_html = None
    img_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    if suffix.lower() in img_exts:
        b64 = base64.b64encode(raw_bytes).decode()
        mime = "image/jpeg" if suffix.lower() in (".jpg", ".jpeg") else f"image/{suffix[1:].lower()}"
        preview_html = f'<img src="data:{mime};base64,{b64}" style="max-width:100%;max-height:260px;border-radius:8px;margin-top:8px"/>'

    try:
        result = process_document(temp_path)
    except Exception as e:
        return {
            "filename": file.filename,
            "answer": f"⚠️ {file.filename}: დამუშავების შეცდომა — {e}",
            "preview_html": preview_html,
            "draft_id": None,
        }
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

    # Save file to processed_documents so eye-button can retrieve it later
    doc_id: Optional[int] = None
    try:
        import hashlib, json as _json
        from app.api.db import get_db as _get_db
        _mime = (
            "application/pdf" if suffix.lower() == ".pdf"
            else f"image/{suffix[1:].lower()}" if suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
            else "application/octet-stream"
        )
        _hash = hashlib.sha256(raw_bytes).hexdigest()
        _conn = _get_db()
        _cur = _conn.cursor()
        try:
            _cur.execute(
                "SELECT id FROM processed_documents WHERE tenant_id = %s AND file_hash = %s LIMIT 1",
                (tenant_id, _hash),
            )
            _existing = _cur.fetchone()
            if _existing:
                doc_id = _existing[0]
            else:
                _cur.execute(
                    """INSERT INTO processed_documents
                       (tenant_id, file_hash, file_name, file_size_bytes, mime_type,
                        extraction_method, raw_text, extracted_data, file_content)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (tenant_id, _hash, file.filename, len(raw_bytes), _mime,
                     "ai_chat", (result.get("text") or "")[:10000],
                     _json.dumps(result), raw_bytes),
                )
                doc_id = _cur.fetchone()[0]
            _conn.commit()
        finally:
            _cur.close(); _conn.close()
    except Exception as _de:
        log.warning("processed_documents save failed (non-fatal): %s", _de)

    if result.get("lines"):
        try:
            draft = _create_draft_from_result(result, tenant_id, source_document_id=doc_id)
            draft_id = draft.get("id")
        except Exception:
            draft_id = None
    else:
        draft_id = None

    # Build human-readable summary from result
    desc = result.get("description") or result.get("message") or file.filename
    amount = result.get("amount") or result.get("total") or 0
    partner = result.get("partner") or result.get("vendor") or ""
    inv_number = result.get("invoice_number") or result.get("number") or ""
    _dt = result.get("document_type") or result.get("type") or ""
    doc_type = _dt if _dt and _dt.lower() not in ("unknown", "none", "") else "დოკუმენტი"
    date = result.get("date") or ""
    lines = result.get("lines") or []

    parts = [f"📄 **{file.filename}** — {doc_type}"]
    if inv_number:
        parts.append(f"📋 ინვოისი: `{inv_number}`")
    if partner:
        parts.append(f"🏢 პარტნიორი: **{partner}**")
    if amount:
        parts.append(f"💰 თანხა: **{format_gel(float(amount))}**")
    if date:
        parts.append(f"📅 თარიღი: {date}")
    if lines:
        parts.append(f"\n**Dr/Cr გატარება:**")
        for ln in lines[:4]:
            parts.append(f"  Dr {ln.get('account_code','')} / Cr — {ln.get('label','')} {format_gel(float(ln.get('debit') or ln.get('amount') or 0))}")
    if draft_id:
        parts.append(f"\n✅ Draft შეიქმნა — **ID #{draft_id}**")

    return {
        "filename": file.filename,
        "answer": "\n".join(parts),
        "preview_html": preview_html,
        "draft_id": draft_id,
        "confidence": float(result.get("confidence", 0.90)),
    }


async def handle_ai_chat(
    message: str,
    session_id: Optional[str] = None,
    tenant_id: str = "global",
    use_vector_search: bool = True,
    file=None,
    files: Optional[List] = None,
    role: Optional[str] = None,
    draft_id: Optional[int] = None,
) -> Dict[str, Any]:
    message = (message or "").strip()

    # ── Multi-file path ───────────────────────────────────────
    if files and len(files) > 1:
        results = []
        for f in files:
            r = await _process_single_file(f, tenant_id, session_id)
            results.append(r)

        # Build combined answer
        combined_parts = [f"📁 **{len(files)} ფაილი დამუშავდა:**\n"]
        for r in results:
            combined_parts.append(r["answer"])
            combined_parts.append("")  # blank line between files

        # Collect any preview_html (first image only for now)
        preview_html = next((r["preview_html"] for r in results if r.get("preview_html")), None)
        draft_ids = [r["draft_id"] for r in results if r.get("draft_id")]

        answer = "\n".join(combined_parts)
        if preview_html:
            answer = f"__PREVIEW_HTML__{preview_html}__END_PREVIEW__\n" + answer

        return {
            "answer": answer,
            "sources": ["multi_document"],
            "confidence": sum(r.get("confidence", 0.9) for r in results) / len(results),
            "search_method": "multi_document_analysis",
            "session_id": session_id,
            "suggested_actions": [
                {"action": "view_draft", "label": f"✅ Draft #{did}", "route": "/static/approval.html", "method": "GET", "params": {"draft_id": did}}
                for did in draft_ids
            ],
        }

    if file:
        r = await _process_single_file(file, tenant_id, session_id)
        answer = r["answer"]
        if r.get("preview_html"):
            answer = f"__PREVIEW_HTML__{r['preview_html']}__END_PREVIEW__\n" + answer
        return {
            "answer": answer,
            "sources": ["document"],
            "confidence": r.get("confidence", 0.90),
            "search_method": "document_analysis",
            "session_id": session_id,
            "suggested_actions": [
                {"action": "view_draft", "label": f"✅ Draft #{r['draft_id']} გახსნა",
                 "route": "/static/approval.html", "method": "GET",
                 "params": {"draft_id": r["draft_id"]}}
            ] if r.get("draft_id") else [],
        }

    if message and ("გატარე" in message.lower() or "post" in message.lower()):
        try:
            if not KB_LOADED:
                return {
                    "answer": "⚠️ Knowledge Base არ არის ჩატვირთული",
                    "sources": ["accounting_engine"],
                    "confidence": 0.30,
                    "search_method": "auto_posting",
                    "session_id": session_id,
                }

            result = build_journal_from_text(message)

            if result.get("lines"):
                draft = _create_draft_from_result(result, tenant_id)
                return {
                    "answer": (
                        f"{result.get('message', 'გატარება მომზადდა')}\n\n"
                        f"🧾 Draft შეიქმნა ✅\n"
                        f"📌 ID: {draft.get('id')}"
                    ),
                    "sources": ["accounting_engine"],
                    "confidence": float(result.get("confidence", 0.95)),
                    "search_method": "auto_posting",
                    "session_id": session_id,
                }

            return {
                "answer": result.get("message", "ვერ დამუშავდა"),
                "sources": ["accounting_engine"],
                "confidence": 0.70,
                "search_method": "auto_posting",
                "session_id": session_id,
            }

        except Exception as e:
            return {
                "answer": f"⚠️ შეცდომა: {str(e)}",
                "sources": ["accounting_engine"],
                "confidence": 0.30,
                "search_method": "auto_posting",
                "session_id": session_id,
            }

    # If draft_id not provided via Form, try to extract from message text
    if draft_id is None:
        draft_id = _extract_draft_id_from_message(message)

    # _local_answer only for pure tax calculations (no draft_id, no DB-related question)
    _db_question_keywords = [
        "დრაფტ", "draft", "ინვოის", "invoice", "approval", "დამტკიც",
        "პარტნიორ", "partner", "ანგარიშ", "account", "გადარიცხვ",
        "ტრანზაქცი", "transaction", "status", "pending", "queue",
        "bank", "ბანკ", "balance", "ბალანს", "report", "ანგარიშგებ",
        "audit", "history", "ისტორი", "#",
    ]
    _is_db_question = (
        draft_id is not None
        or any(kw in message.lower() for kw in _db_question_keywords)
    )

    if KB_LOADED and not _is_db_question:
        local = _local_answer(message)
        if local:
            return {
                "answer": local,
                "sources": ["kb"],
                "confidence": 0.98,
                "search_method": "local_rules",
                "session_id": session_id,
            }

    # ── KB / vector context (lightweight, no DB) ──────────────
    kb_context = ""
    sources: List[str] = []

    if use_vector_search and _vector_db_available:
        try:
            kb_context = get_context_for_llm_hybrid(message, max_chars=4000)
            sources = ["ChromaDB + KB"]
        except Exception:
            pass

    if not kb_context and KB_LOADED:
        kb_context = get_context_for_llm(message, max_chars=3000)
        results = search_knowledge(message, top_k=5)
        sources = _format_sources(results)

    memory_result = _build_memory_context(message, tenant_id)
    kb_context = _append_memory_to_context(kb_context, memory_result)

    # ── Orchestrator path (Claude + tools + DB context) ───────
    if _ORCHESTRATOR_AVAILABLE:
        return await _orchestrate(
            message=message,
            session_id=session_id,
            tenant_id=tenant_id,
            role=role,
            draft_id=draft_id,
            kb_context=kb_context,
            sources=sources,
            memory_result=memory_result,
        )

    # ── Fallback: direct Claude (no orchestrator) ─────────────
    db_ctx = build_chat_context(tenant_id=tenant_id, message=message, draft_id=draft_id)

    if draft_id is not None and db_ctx.get("not_found"):
        return {
            "answer": f"სისტემაში ვერ ვიპოვე draft #{draft_id}. შეიძლება სხვა tenant-ს ეკუთვნოდეს ან წაშლილი იყოს.",
            "sources": ["db"],
            "confidence": 1.0,
            "search_method": "db_lookup",
            "session_id": session_id,
        }

    db_prompt = format_context_for_prompt(db_ctx)
    context = (db_prompt + ("\n\n" + kb_context if kb_context else "")) if db_prompt else kb_context

    if CLAUDE_CHAT_AVAILABLE:
        claude_result = chat_with_claude_structured(
            message, context=context, tenant_id=tenant_id, role=role, session_id=session_id
        )
        claude_answer = claude_result.get("answer")
        if claude_answer:
            return {
                "answer": claude_answer,
                "suggested_actions": claude_result.get("suggested_actions", []),
                "sources": sources + ["claude:sonnet"],
                "confidence": 0.92,
                "search_method": "claude_chat",
                "session_id": session_id,
            }

    # GPT fallback
    llm_result = llm_classify(
        description=message,
        context={"context": context, **{k: memory_result.get(k) for k in ("account_code", "confidence", "reasoning")}},
        tenant_id=tenant_id,
    )

    preview = generate_preview(
        {"account_dr": llm_result.get("account_code"), "account_cr": "", "amount": _extract_amount(message) or 0.0, "description": llm_result.get("reasoning") or message},
        tenant_id=tenant_id,
    )

    return {
        "answer": preview or llm_result.get("reasoning") or "დამუშავდა",
        "sources": sources + [f"llm:{llm_result.get('source', 'gateway')}"],
        "confidence": float(llm_result.get("confidence", 0.70)),
        "search_method": "memory_plus_llm",
        "session_id": session_id,
    }


# ─────────────────────────────────────────────────────────────
# SUPPORT FUNCTIONS FOR routes_ai_chat.py
# ─────────────────────────────────────────────────────────────
def get_ai_system_stats():
    result = {
        "kb_loaded": KB_LOADED,
        "vector_db_available": _vector_db_available,
        "accounting_rules_loaded": ACCT_RULES_LOADED,
    }
    if KB_LOADED:
        result["knowledge_base"] = get_stats()
    return result


def run_ai_search(q: str, top_k: int = 5, use_vector: bool = True):
    if use_vector and _vector_db_available:
        try:
            return {"query": q, "results": hybrid_search(q, top_k), "method": "hybrid"}
        except Exception:
            pass

    if KB_LOADED:
        return {"query": q, "results": search_knowledge(q, top_k), "method": "keyword"}

    return {"query": q, "results": [], "method": "unavailable"}


def run_vat_calc(request):
    payment_status = getattr(request, "payment_status", "paid") or "paid"
    inclusive = bool(getattr(request, "inclusive", True))
    service_type = getattr(request, "service_type", "standard") or "standard"

    if ACCT_RULES_LOADED:
        if inclusive:
            return build_vat_posting(
                request.amount,
                payment_status=payment_status,
            )
        return build_vat_posting_from_net(
            request.amount,
            payment_status=payment_status,
        )

    if not KB_LOADED:
        return {"error": "KB not loaded"}

    return calculate_vat(request.amount, inclusive, service_type)


def run_dividend_calc(request):
    if ACCT_RULES_LOADED:
        return build_dividend_posting(request.gross_amount, request.cit_rate)

    if not KB_LOADED:
        return {"error": "KB not loaded"}

    return calculate_cit(request.gross_amount)


def run_payroll_calc(request):
    if ACCT_RULES_LOADED:
        mode = request.mode or "gross"
        if mode == "net":
            return build_payroll_from_net_posting(
                request.gross,
                employee_pension_rate=0.02 if getattr(request, "include_employee_payg", True) else 0.0,
                employer_pension_rate=0.02 if getattr(request, "include_employee_payg", True) else 0.0,
            )
        return build_payroll_posting(
            request.gross,
            employee_pension_rate=0.02 if getattr(request, "include_employee_payg", True) else 0.0,
            employer_pension_rate=0.02 if getattr(request, "include_employee_payg", True) else 0.0,
        )

    if not KB_LOADED:
        return {"error": "KB not loaded"}

    return calculate_payroll(
        request.gross,
        request.include_employee_payg,
        request.mode or "gross",
    )


def run_cit_calc(request):
    if not KB_LOADED:
        return {"error": "KB not loaded"}

    return calculate_cit(request.distributed_profit)


def run_depreciation_calc(request):
    if not KB_LOADED:
        return {"error": "KB not loaded"}

    return calculate_depreciation(
        request.cost,
        request.residual,
        request.useful_life_years,
        request.method,
    )


def run_classify_tx(request):
    if not KB_LOADED:
        return {"error": "KB not loaded"}

    from app.api.services.classification_explanation_service import build_explanation
    result = classify_transaction(request.description, request.tenant_id)
    enriched = build_explanation(result)
    return {
        **enriched,
        "account_type": CHART_OF_ACCOUNTS.get(
            result.get("account") or result.get("account_code"),
            {}
        ).get("type", "unknown"),
    }


def run_learn_rule(request):
    if not KB_LOADED:
        return {"status": "error", "message": "KB not loaded"}

    results = {
        "python_rules": learn_new_rule(
            request.pattern,
            request.account,
            request.tenant_id,
            request.note,
        )
    }

    if request.use_vector and _vector_db_available:
        try:
            results["vector_db"] = learn_from_correction(
                request.pattern,
                request.account,
                tenant_id=request.tenant_id,
                note=request.note,
            )
        except Exception as e:
            results["vector_db"] = {"status": "error", "error": str(e)}

    account_name = CHART_OF_ACCOUNTS.get(request.account, {}).get("name", request.account)

    return {
        "status": "learned",
        "message": f"✅ ვისწავლე: '{request.pattern}' → {request.account} ({account_name})",
        "stored_in": list(results.keys()),
    }


def run_index_files(request):
    if not _vector_db_available:
        return {"status": "error", "detail": "ChromaDB არ არის"}

    stats = index_files(request.files_dir, request.force_reindex)
    return {"status": "success", **stats}


def run_vector_stats():
    if not _vector_db_available:
        return {"available": False}

    try:
        return {"available": True, **get_vector_stats()}
    except Exception as e:
        return {"available": True, "error": str(e)}