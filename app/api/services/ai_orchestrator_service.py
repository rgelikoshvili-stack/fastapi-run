"""
app/api/services/ai_orchestrator_service.py
Bridge Hub — AI Chat Orchestrator

Thin coordinator:
  message → intent → context → tool selection → LLM → response

handle_ai_chat() delegates here.
Never executes mutations — only preview/read.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Tool registry
# ─────────────────────────────────────────────────────────────
try:
    from app.api.services.ai_tool_registry import run_tool, TOOL_NAMES
    _TOOLS_AVAILABLE = True
except ImportError:
    _TOOLS_AVAILABLE = False
    TOOL_NAMES = []

# ─────────────────────────────────────────────────────────────
# Context builder
# ─────────────────────────────────────────────────────────────
from app.api.services.chat_context_service import build_chat_context, format_context_for_prompt

# ─────────────────────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────────────────────
from app.api.services.llm_service import chat_with_claude_structured

# ─────────────────────────────────────────────────────────────
# Intent → tool mapping
# ─────────────────────────────────────────────────────────────
_INTENT_TOOL_MAP: Dict[str, List[str]] = {
    "approval":      ["show_pending_tasks", "show_risks"],
    "bank":          ["financial_summary", "get_bank_transactions", "get_payment_status"],
    "reports":       ["financial_summary", "tax_summary"],
    "tax":           ["tax_summary"],
    "invoices":      ["search_documents", "get_payment_status"],
    "documents":     ["search_documents"],
    "waybills":      ["search_documents"],
    "tax_invoices":  ["search_documents"],
    "decisions":     ["show_risks", "show_pending_tasks"],
    "audit":         ["search_documents"],
}

_DRAFT_TOOLS = ["explain_draft", "prepare_approval_preview"]


_INVOICE_NUMBER_RE = re.compile(
    r"\b([A-Z]{2,10}[-_/][A-Z0-9][A-Z0-9/_-]{2,})\b",
    re.IGNORECASE,
)


def _select_tools(message: str, draft_id: Optional[int], intents: set) -> List[str]:
    """Pick relevant tool names based on intents + draft_id."""
    selected: List[str] = []
    msg = message.lower()

    if draft_id:
        selected.extend(_DRAFT_TOOLS)

    for intent in intents:
        for t in _INTENT_TOOL_MAP.get(intent, []):
            if t not in selected:
                selected.append(t)

    if any(k in msg for k in ("unreconciled", "შეუსაბამ", "ვერ დაემთხვ", "გადახდა ვერ", "ტრანზაქცია ვერ")):
        if "get_bank_transactions" not in selected:
            selected.append("get_bank_transactions")

    if any(k in msg for k in ("payment", "paid", "გადახდ", "გადასარიცხ", "მოვიდა თანხა", "ინვოისზე")):
        if "get_payment_status" not in selected:
            selected.append("get_payment_status")
        if "get_bank_transactions" not in selected:
            selected.append("get_bank_transactions")

    return selected[:6]  # cap at 6 tools per turn


def _extract_tool_params(message: str, draft_id: Optional[int]) -> dict:
    """Extract lightweight tool params from a chat message."""
    params = {"draft_id": draft_id} if draft_id else {}
    msg = message.strip()
    lower = msg.lower()

    match = _INVOICE_NUMBER_RE.search(msg)
    if match:
        params["invoice_number"] = match.group(1).strip(" .,:;")

    if any(k in lower for k in ("unreconciled", "შეუსაბამ", "ვერ დაემთხვ", "გადახდა ვერ", "ტრანზაქცია ვერ")):
        params["unreconciled_only"] = True

    return params


async def _run_selected_tools(
    tool_names: List[str],
    params: dict,
    tenant_id: str,
) -> Dict[str, Any]:
    """Run tools, collect results, never raise."""
    results: Dict[str, Any] = {}
    if not _TOOLS_AVAILABLE:
        return results

    for name in tool_names:
        try:
            result = await run_tool(name, params, tenant_id)
            if result and not result.get("error"):
                results[name] = result
        except Exception as e:
            log.debug("tool %s failed: %s", name, e)

    return results


def _format_tool_results(tool_results: Dict[str, Any]) -> str:
    """Convert tool results to a readable context block for Claude."""
    if not tool_results:
        return ""

    lines = ["\n[AI Tool Results]"]
    for tool_name, result in tool_results.items():
        lines.append(f"\n-- {tool_name} --")
        preview = result.get("preview", {})
        if isinstance(preview, dict):
            for k, v in preview.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(preview, (str, int, float)):
            lines.append(f"  {preview}")

        for key in (
            "payment_status",
            "expected_amount",
            "paid_amount",
            "count",
            "unreconciled_in_results",
            "filters_applied",
        ):
            if key in result:
                lines.append(f"  {key}: {result[key]}")

        for key in ("transactions", "matched_bank_transactions", "matched_journal_drafts"):
            items = result.get(key)
            if isinstance(items, list):
                lines.append(f"  {key}: {items[:5]}")

        if result.get("approval_required"):
            confirm_url = result.get("confirm_url", "")
            lines.append(f"  [requires_approval] confirm_url: {confirm_url}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

async def orchestrate(
    message: str,
    session_id: Optional[str],
    tenant_id: str,
    role: Optional[str],
    draft_id: Optional[int],
    kb_context: str = "",
    sources: Optional[List[str]] = None,
    memory_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Central coordinator.

    1. Build DB context (chat_context_service)
    2. Run relevant tools (ai_tool_registry)
    3. Compose full prompt context
    4. Call Claude (chat_with_claude_structured)
    5. Return {answer, suggested_actions, sources, confidence, session_id}
    """
    sources = sources or []
    memory_result = memory_result or {}

    # 1. DB context (async asyncpg)
    db_ctx = await build_chat_context(tenant_id=tenant_id, message=message, draft_id=draft_id)

    if draft_id is not None and db_ctx.get("not_found"):
        return {
            "answer": f"სისტემაში ვერ ვიპოვე draft #{draft_id}. შეიძლება სხვა tenant-ს ეკუთვნოდეს ან წაშლილი იყოს.",
            "sources": ["db"],
            "confidence": 1.0,
            "search_method": "db_lookup",
            "session_id": session_id,
            "suggested_actions": [],
        }

    db_prompt = format_context_for_prompt(db_ctx)

    # 2. Tool selection + execution
    intents: set = set(db_ctx.get("intents", []))
    tool_params = _extract_tool_params(message, draft_id)
    tool_names = _select_tools(message, draft_id, intents)
    tool_results = await _run_selected_tools(tool_names, tool_params, tenant_id)
    tool_block = _format_tool_results(tool_results)

    # 3. Compose full context for Claude
    parts = []
    if db_prompt:
        parts.append(db_prompt)
    if tool_block:
        parts.append(tool_block)
    if kb_context:
        parts.append(kb_context)

    full_context = "\n\n".join(parts)

    # 4. Call Claude
    try:
        claude_result = await chat_with_claude_structured(
            message,
            context=full_context,
            tenant_id=tenant_id,
            role=role,
            session_id=session_id,
        )
    except Exception as e:
        log.error("orchestrate: claude failed: %s", e)
        claude_result = {"answer": "", "suggested_actions": []}

    answer = claude_result.get("answer", "")
    suggested_actions = claude_result.get("suggested_actions", [])

    # 5. Build response
    all_sources = list(sources)
    if tool_results:
        all_sources.append(f"tools:{','.join(tool_results.keys())}")
    if memory_result.get("matched"):
        all_sources.append(f"memory:{memory_result.get('source', 'local')}")
    all_sources.append("claude:sonnet")

    confidence = 0.92
    if memory_result.get("matched"):
        confidence = max(confidence, float(memory_result.get("confidence", 0.0)))

    search_method = "orchestrator"
    if memory_result.get("matched"):
        search_method = "orchestrator_with_memory"

    return {
        "answer": answer,
        "suggested_actions": suggested_actions,
        "sources": all_sources,
        "confidence": confidence,
        "search_method": search_method,
        "session_id": session_id,
    }
