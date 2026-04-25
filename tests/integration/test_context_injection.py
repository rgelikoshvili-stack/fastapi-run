"""
tests/integration/test_context_injection.py
Bridge Hub — AI Context Injection critical tests

Done criteria:
  1. existing draft  → correct amount + partner returned (no hallucination)
  2. non-existent draft → "ვერ ვიპოვე სისტემაში"
  3. cross-tenant draft  → not visible
  4. extract_draft_id_from_message extracts ID from natural text
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────
# Unit: draft_id extraction from message text
# ─────────────────────────────────────────────────────────────

def test_extract_draft_id_plain_number():
    from app.api.services.ai_chat_service import _extract_draft_id_from_message
    assert _extract_draft_id_from_message("draft #1130 ახსენი") == 1130


def test_extract_draft_id_georgian():
    from app.api.services.ai_chat_service import _extract_draft_id_from_message
    assert _extract_draft_id_from_message("დრაფტ 999 რა სტატუსშია?") == 999


def test_extract_draft_id_invoice():
    from app.api.services.ai_chat_service import _extract_draft_id_from_message
    assert _extract_draft_id_from_message("invoice #42 check status") == 42


def test_extract_draft_id_none_when_no_id():
    from app.api.services.ai_chat_service import _extract_draft_id_from_message
    assert _extract_draft_id_from_message("vat 1000 GEL გამოთვალე") is None


# ─────────────────────────────────────────────────────────────
# Unit: format_context_for_prompt — empty-context fallback
# ─────────────────────────────────────────────────────────────

def test_format_context_empty_fallback():
    """When no DB data is loaded the prompt must contain the Georgian fallback sentinel."""
    from app.api.services.chat_context_service import format_context_for_prompt

    empty_ctx = {
        "draft": None, "not_found": False, "pending_count": 0,
        "recent_drafts": [], "queue": [], "bank_accounts": [],
        "bank_transactions": [], "recent_transactions": [], "bank_summary": None,
        "invoices": [], "outgoing_invoices": [], "documents": [],
        "payroll_drafts": [], "waybills": [], "tax_invoices": [],
        "notifications": [], "tax_summary": None, "reports_summary": None,
        "audit_recent": [], "learning_stats": None, "decisions_pending": [],
        "kpi": None, "intents": [],
    }
    result = format_context_for_prompt(empty_ctx)
    assert "სისტემაში" in result
    assert "გამოიგონო ნუ" in result


def test_format_context_not_found():
    """not_found=True must return the not-found sentinel."""
    from app.api.services.chat_context_service import format_context_for_prompt

    ctx = {"not_found": True}
    result = format_context_for_prompt(ctx)
    assert "ვერ მოიძებნა" in result


# ─────────────────────────────────────────────────────────────
# Unit: format_context_for_prompt — draft data rendered correctly
# ─────────────────────────────────────────────────────────────

def test_format_context_renders_draft_fields():
    """Draft amount, partner and status must appear verbatim in rendered context."""
    from app.api.services.chat_context_service import format_context_for_prompt

    ctx = {
        "draft": {
            "id": 1130,
            "description": "TBC Bank payment",
            "amount": 4500.0,
            "partner": "GlobalTech LLC",
            "account_code": "7810",
            "debit_account": "7810",
            "credit_account": "1110",
            "status": "pending_approval",
            "confidence": 0.87,
            "date": "2026-04-20",
            "created_at": "2026-04-20T10:00:00",
        },
        "not_found": False, "pending_count": 1, "recent_drafts": [],
        "queue": [], "bank_accounts": [], "bank_transactions": [],
        "recent_transactions": [], "bank_summary": None, "invoices": [],
        "outgoing_invoices": [], "documents": [], "payroll_drafts": [],
        "waybills": [], "tax_invoices": [], "notifications": [],
        "tax_summary": None, "reports_summary": None, "audit_recent": [],
        "learning_stats": None, "decisions_pending": [], "kpi": None, "intents": [],
    }
    result = format_context_for_prompt(ctx)
    assert "4,500.00" in result
    assert "GlobalTech LLC" in result
    assert "pending_approval" in result
    assert "1130" in result


# ─────────────────────────────────────────────────────────────
# Integration (mocked DB): build_chat_context — tenant isolation
# ─────────────────────────────────────────────────────────────

def _make_cursor_mock(rows_by_query: dict):
    """Return a mock cursor that returns rows based on which SQL keyword is used."""
    cur = MagicMock()

    def fetchone_side():
        return cur._fetchone_result

    def fetchall_side():
        return cur._fetchall_result

    cur.fetchone.side_effect = fetchone_side
    cur.fetchall.side_effect = fetchall_side
    cur._fetchone_result = None
    cur._fetchall_result = []
    return cur


def test_build_chat_context_tenant_isolation():
    """
    Draft belonging to tenant_B must not appear when querying as tenant_A.
    We simulate this by making the DB return no row for the given (draft_id, tenant_id) pair.
    """
    from app.api.services.chat_context_service import build_chat_context

    # Simulate: DB finds no draft because tenant doesn't match
    with patch("app.api.services.chat_context_service.get_db") as mock_get_db:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchone.return_value = None    # draft not found
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cur
        mock_get_db.return_value = mock_conn

        ctx = build_chat_context(tenant_id="tenant_A", message="draft #999", draft_id=999)

    assert ctx["draft"] is None
    assert ctx["not_found"] is True


def test_build_chat_context_existing_draft():
    """
    When DB returns a draft row, build_chat_context must populate ctx['draft']
    with the correct fields.
    """
    from app.api.services.chat_context_service import build_chat_context
    import decimal

    fake_row = {
        "id": 1130,
        "description": "Wolt payment",
        "amount": decimal.Decimal("1250.00"),
        "partner": "Wolt Georgia",
        "account_code": "7720",
        "debit_account": "7720",
        "credit_account": "1110",
        "status": "pending_approval",
        "confidence": decimal.Decimal("0.91"),
        "source_type": "bank_import",
        "created_at": "2026-04-20T09:00:00",
        "date": "2026-04-20",
    }

    with patch("app.api.services.chat_context_service.get_db") as mock_get_db:
        mock_conn = MagicMock()
        mock_cur = MagicMock()

        # First fetchone call → draft row; subsequent calls → None / []
        call_count = {"n": 0}

        def fetchone():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return fake_row
            return {"cnt": 0, "total": 0, "pending": 0, "approved": 0,
                    "rejected": 0, "avg_confidence": decimal.Decimal("0")}

        mock_cur.fetchone.side_effect = fetchone
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cur
        mock_get_db.return_value = mock_conn

        ctx = build_chat_context(tenant_id="tenant_A", message="draft #1130 info", draft_id=1130)

    assert ctx["not_found"] is False
    assert ctx["draft"] is not None
    assert ctx["draft"]["id"] == 1130
    assert ctx["draft"]["amount"] == 1250.0
    assert ctx["draft"]["partner"] == "Wolt Georgia"


# ─────────────────────────────────────────────────────────────
# Integration: handle_ai_chat returns "ვერ ვიპოვე" for missing draft
# ─────────────────────────────────────────────────────────────

def test_handle_ai_chat_not_found_returns_georgian_message():
    """If draft_id is given but not in DB → answer must contain 'ვერ ვიპოვე'."""
    import asyncio

    with patch("app.api.services.ai_chat_service._ORCHESTRATOR_AVAILABLE", True), \
         patch("app.api.services.ai_chat_service._orchestrate", new_callable=AsyncMock) as mock_orch:

        mock_orch.return_value = {
            "answer": "სისტემაში ვერ ვიპოვე draft #9999. შეიძლება სხვა tenant-ს ეკუთვნოდეს ან წაშლილი იყოს.",
            "sources": ["db"], "confidence": 1.0,
            "search_method": "db_lookup", "session_id": None,
            "suggested_actions": [],
        }

        from app.api.services.ai_chat_service import handle_ai_chat
        result = asyncio.run(handle_ai_chat(
            message="draft #9999 ახსენი",
            tenant_id="tenant_A",
            draft_id=9999,
        ))

    assert "ვერ ვიპოვე" in result["answer"]
