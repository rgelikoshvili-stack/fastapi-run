"""
tests/integration/test_chat_context_injection.py
Bridge Hub — Chat Context Injection tests

Test 1: draft_id provided → real data returned (no hallucination)
Test 2: draft_id not found → "ვერ ვიპოვე" (no hallucination)
Test 3: invoice/draft question → _local_answer() bypassed → Claude handles it
"""
from unittest.mock import MagicMock, patch
import pytest

# ─── Mock DB row ────────────────────────────────────────────────────────────
_DRAFT_ROW = {
    "id": 1130,
    "description": "Invoice — შპს ალტე უნივერსიტეტი",
    "amount": 9756220.00,
    "partner": "შპს ალტე უნივერსიტეტი",
    "account_code": "7100",
    "debit_account": "7100",
    "credit_account": "3110",
    "status": "pending_approval",
    "confidence": 0.75,
    "source_type": "manual",
    "created_at": "2026-04-25T10:00:00",
    "date": "2026-04-25",
}


def _make_cursor(draft_row=_DRAFT_ROW, pending_count=3, drafts=None, banks=None, kpi=None):
    """Return a mock RealDictCursor that returns preset data."""
    cur = MagicMock()
    # fetchone cycles through: draft, pending_count, kpi
    fetchone_sequence = [
        draft_row,
        {"cnt": pending_count},
        kpi or {"total": 10, "pending": 3, "approved": 7, "avg_confidence": 0.85},
    ]
    fetchone_iter = iter(fetchone_sequence)
    cur.fetchone.side_effect = lambda: next(fetchone_iter, None)
    # fetchall cycles through: recent_drafts, bank_accounts
    fetchall_sequence = [
        drafts or [],
        banks or [{"name": "TBC", "balance": 50000.0, "currency": "GEL", "account_type": "checking"}],
    ]
    fetchall_iter = iter(fetchall_sequence)
    cur.fetchall.side_effect = lambda: next(fetchall_iter, [])
    return cur


# ─── Test 1: Draft context injected correctly ───────────────────────────────

def test_build_chat_context_with_draft_id():
    """build_chat_context returns real draft data when draft_id exists."""
    from app.api.services.chat_context_service import build_chat_context, format_context_for_prompt

    mock_conn = MagicMock()
    mock_cur = _make_cursor(draft_row=_DRAFT_ROW)
    mock_conn.cursor.return_value = mock_cur

    with patch("app.api.services.chat_context_service.get_db", return_value=mock_conn):
        ctx = build_chat_context(tenant_id="tenant_a", message="ეს დრაფტი ამიხსენი", draft_id=1130)

    assert ctx["draft"] is not None
    assert ctx["draft"]["id"] == 1130
    assert ctx["draft"]["amount"] == 9756220.00
    assert ctx["draft"]["partner"] == "შპს ალტე უნივერსიტეტი"
    assert ctx["not_found"] is False

    prompt = format_context_for_prompt(ctx)
    assert "9,756,220.00" in prompt or "9756220" in prompt
    assert "შპს ალტე უნივერსიტეტი" in prompt
    assert "REAL SYSTEM CONTEXT" in prompt


# ─── Test 2: Draft not found → "ვერ ვიპოვე" ───────────────────────────────

def test_build_chat_context_draft_not_found():
    """build_chat_context sets not_found=True when draft doesn't exist for tenant."""
    from app.api.services.chat_context_service import build_chat_context, format_context_for_prompt

    mock_conn = MagicMock()
    mock_cur = _make_cursor(draft_row=None)  # fetchone returns None for draft
    mock_conn.cursor.return_value = mock_cur

    with patch("app.api.services.chat_context_service.get_db", return_value=mock_conn):
        ctx = build_chat_context(tenant_id="tenant_a", message="დრაფტი ამიხსენი", draft_id=999999)

    assert ctx["not_found"] is True
    assert ctx["draft"] is None

    prompt = format_context_for_prompt(ctx)
    assert "ვერ მოიძებნა" in prompt


def test_handle_ai_chat_draft_not_found_returns_not_found_message():
    """handle_ai_chat returns 'ვერ ვიპოვე' immediately when draft not found."""
    import asyncio
    from app.api.services.ai_chat_service import handle_ai_chat

    _not_found_ctx = {
        "draft": None, "pending_count": 0, "recent_drafts": [],
        "bank_accounts": [], "kpi": None, "not_found": True,
    }

    with patch("app.api.services.chat_context_service.get_db", side_effect=Exception("no db")):
        with patch(
            "app.api.services.ai_chat_service.build_chat_context",
            return_value=_not_found_ctx,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                handle_ai_chat(
                    message="დრაფტი 999999 ამიხსენი",
                    tenant_id="tenant_a",
                    draft_id=999999,
                )
            )

    assert "ვერ ვიპოვე" in result["answer"] or "999999" in result["answer"]
    # Must NOT invent any data
    assert "შპს" not in result["answer"]


# ─── Test 3: _local_answer bypassed for draft/invoice questions ─────────────

def test_local_answer_not_intercepting_draft_questions():
    """
    When message contains 'ინვოის' or 'draft', _local_answer() must be bypassed
    even if the message also contains a calculable keyword like 'მოგება'.
    """
    import asyncio
    from app.api.services import ai_chat_service
    from app.api.services.ai_chat_service import handle_ai_chat

    intercepted = []

    original_local = ai_chat_service._local_answer

    def spy_local(msg):
        intercepted.append(msg)
        return original_local(msg)

    _found_ctx = {
        "draft": _DRAFT_ROW,
        "pending_count": 1,
        "recent_drafts": [],
        "bank_accounts": [],
        "kpi": None,
        "not_found": False,
    }

    with patch.object(ai_chat_service, "_local_answer", side_effect=spy_local):
        with patch(
            "app.api.services.ai_chat_service.build_chat_context",
            return_value=_found_ctx,
        ):
            with patch(
                "app.api.services.ai_chat_service.format_context_for_prompt",
                return_value="REAL SYSTEM CONTEXT:\nDraft #1130",
            ):
                with patch(
                    "app.api.services.ai_chat_service.chat_with_claude",
                    return_value="ეს ინვოისი 7100 ანგარიშზე მიეკუთვნება რადგან...",
                ):
                    result = asyncio.get_event_loop().run_until_complete(
                        handle_ai_chat(
                            message="ამ ინვოისს რატომ მიაკუთვნე 7100?",
                            tenant_id="tenant_a",
                            draft_id=1130,
                        )
                    )

    # _local_answer must NOT have been called (draft_id present → is_db_question=True)
    assert len(intercepted) == 0, "_local_answer() must be bypassed for draft questions"
    assert "7100" in result["answer"]


# ─── Test 4: format_context_for_prompt structure ────────────────────────────

def test_format_context_for_prompt_includes_all_fields():
    from app.api.services.chat_context_service import format_context_for_prompt

    ctx = {
        "draft": {
            "id": 42,
            "description": "Test invoice",
            "amount": 1000.0,
            "partner": "Test Partner",
            "account_code": "7110",
            "debit_account": "7110",
            "credit_account": "3110",
            "status": "approved",
            "confidence": 0.95,
            "created_at": "2026-04-25",
            "date": "2026-04-25",
        },
        "pending_count": 5,
        "recent_drafts": [],
        "bank_accounts": [{"name": "BOG", "balance": 10000.0, "currency": "GEL"}],
        "kpi": {"total_drafts": 20, "pending": 5, "approved": 15, "avg_confidence": 0.90},
        "not_found": False,
    }

    prompt = format_context_for_prompt(ctx)

    assert "REAL SYSTEM CONTEXT" in prompt
    assert "Test Partner" in prompt
    assert "1,000.00" in prompt
    assert "7110" in prompt
    assert "BOG" in prompt
    assert "10,000.00" in prompt
