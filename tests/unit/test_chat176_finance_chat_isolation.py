"""Chat176: AI financial truth and isolated chat history (synthetic only).

No Anthropic network, real credentials, customer records, Production DB,
Cloud Run or Windows-original filesystem access.
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.db import authenticated_tenant_context


@pytest.fixture(autouse=True)
def no_legacy_chat_sessions():
    from app.api.routes_chat import _sessions
    original = dict(_sessions)
    _sessions.clear()
    yield
    _sessions.clear()
    _sessions.update(original)


def req(tenant="t_alpha", user="101", role="admin", authenticated=True, signed=None):
    r = Request({
        "type": "http", "method": "POST", "scheme": "http",
        "path": "/chat/message", "raw_path": b"/chat/message",
        "query_string": b"",
        "headers": [(b"x-tenant-id", b"t_evil")],
        "client": ("127.0.0.1", 5176), "server": ("127.0.0.1", 8080),
        "http_version": "1.1",
    })
    r.state.authenticated = authenticated
    r.state.user_id = user
    r.state.role = role
    r.state.tenant_id = tenant
    r.state.auth_tenant_id = tenant if signed is None else signed
    return r


def fake_anthropic(answer="Synthetic AI answer"):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(text=answer)],
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
    )
    return client


@pytest.mark.asyncio
async def test_chat_history_is_private_to_tenant_and_user(monkeypatch):
    from app.api import routes_chat

    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key-never-used")
    llm = fake_anthropic()
    with patch.object(routes_chat.anthropic, "Anthropic", return_value=llm), \
         patch.object(routes_chat, "_get_db_context", new=AsyncMock(return_value="synthetic context")):
        with authenticated_tenant_context("t_alpha"):
            first = await routes_chat.send_message(
                req(), message="private alpha", session_id="shared-id", file=None
            )
            own = routes_chat.chat_history(req(), session_id="shared-id")
            other_user = routes_chat.chat_history(req(user="202"), session_id="shared-id")
        with authenticated_tenant_context("t_beta"):
            isolated = routes_chat.chat_history(
                req(tenant="t_beta", user="101"), session_id="shared-id"
            )
            second = await routes_chat.send_message(
                req(tenant="t_beta", user="101"),
                message="private beta", session_id="shared-id", file=None
            )
        with authenticated_tenant_context("t_alpha"):
            removed = routes_chat.clear_session("shared-id", req())
            now_gone = routes_chat.chat_history(req(), session_id="shared-id")
        with authenticated_tenant_context("t_beta"):
            still_there = routes_chat.chat_history(
                req(tenant="t_beta", user="101"), session_id="shared-id"
            )

    assert first["ok"] and second["ok"] and removed["ok"]
    assert own["data"]["count"] == 2
    assert other_user["data"]["count"] == 0
    assert isolated["data"]["count"] == 0
    assert now_gone["data"]["count"] == 0
    assert still_there["data"]["count"] == 2
    assert "private beta" not in str(own)
    assert "private alpha" not in str(still_there)
    assert llm.messages.create.call_count == 2


@pytest.mark.parametrize("role,authenticated,expected", [
    ("viewer", True, 403),
    ("admin", False, 401),
])
def test_history_refuses_anonymous_and_insufficient_role(role, authenticated, expected):
    from app.api import routes_chat
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(HTTPException) as denied:
            routes_chat.chat_history(
                req(role=role, authenticated=authenticated), session_id="default"
            )
    assert denied.value.status_code == expected


def test_history_requires_signed_and_matching_db_tenant():
    from app.api import routes_chat
    with pytest.raises(HTTPException) as no_scope:
        routes_chat.chat_history(req(), session_id="shared")
    assert no_scope.value.status_code == 403

    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(HTTPException) as forged:
            routes_chat.chat_history(
                req(tenant="t_evil", signed="t_alpha"), session_id="shared"
            )
    assert forged.value.status_code == 403


@pytest.mark.parametrize("invalid", ["", " ", "a" * 129, "bad\nid"])
def test_chat_session_id_is_bounded_and_canonical(invalid):
    from app.api import routes_chat
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(HTTPException) as failure:
            routes_chat.chat_history(req(), session_id=invalid)
    assert failure.value.status_code == 422


@pytest.mark.asyncio
async def test_provider_failure_does_not_leak_credentials_or_commit_chat(monkeypatch):
    from app.api import routes_chat

    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-secret-api-key")
    llm = fake_anthropic()
    llm.messages.create.side_effect = RuntimeError("synthetic-secret-api-key in provider")
    with patch.object(routes_chat.anthropic, "Anthropic", return_value=llm), \
         patch.object(routes_chat, "_get_db_context", new=AsyncMock(return_value="context")):
        with authenticated_tenant_context("t_alpha"):
            response = await routes_chat.send_message(
                req(), message="private message", session_id="test"
            )
            history = routes_chat.chat_history(req(), session_id="test")
    assert response.status_code == 503
    assert "synthetic-secret" not in response.body.decode()
    assert history["data"]["count"] == 0


@asynccontextmanager
async def _fake_conn(conn):
    yield conn


def _db(monkeypatch):
    from app.api.services import chat_context_service as service
    conn = AsyncMock()
    conn.fetch.return_value = []
    conn.fetchrow.return_value = None
    conn.fetchval.return_value = 0
    monkeypatch.setattr(service, "get_conn", lambda: _fake_conn(conn))
    return conn


@pytest.mark.asyncio
async def test_chat_pnl_uses_identical_canonical_financial_statement(monkeypatch):
    from app.api.services import chat_context_service as service

    conn = _db(monkeypatch)
    canonical = {
        "ok": True,
        "data": {
            "source": "posted_ledger",
            "revenue": {"total": 1500.0},
            "cogs": {"total": 400.0},
            "opex": {"total": 200.0},
            "ebit": 900.0,
        },
    }
    build = AsyncMock(return_value=canonical)
    monkeypatch.setattr(service, "build_profit_and_loss", build)

    ctx = await service.build_chat_context("t_alpha", "show P&L report")
    assert ctx["reports_summary"] == {
        "revenue": 1500.0,
        "expenses": 600.0,
        "profit": 900.0,
        "margin_pct": 60.0,
        "source": "posted_ledger",
    }
    assert not ctx["reports_unavailable"]
    build.assert_awaited_once_with("t_alpha")
    sqls = [call.args[0] for call in conn.fetchrow.await_args_list]
    assert not any("credit_account LIKE '6" in sql for sql in sqls)
    prompt = service.format_context_for_prompt(ctx)
    assert "posted-ledger" in prompt
    assert "900.00" in prompt


@pytest.mark.asyncio
async def test_canonical_pnl_unavailable_is_not_fabricated(monkeypatch):
    from app.api.services import chat_context_service as service

    _db(monkeypatch)
    monkeypatch.setattr(
        service, "build_profit_and_loss",
        AsyncMock(return_value={"ok": False, "error": {"details": "secret-db-error"}}),
    )
    ctx = await service.build_chat_context("t_alpha", "show P&L report")
    assert ctx["reports_summary"] is None
    assert ctx["reports_unavailable"] is True
    rendered = service.format_context_for_prompt(ctx)
    assert "P&L UNAVAILABLE" in rendered
    assert "secret-db-error" not in rendered


@pytest.mark.asyncio
async def test_ai_audit_context_never_includes_null_tenant_rows(monkeypatch):
    from app.api.services import chat_context_service as service

    conn = _db(monkeypatch)
    await service.build_chat_context("t_alpha", "show audit history")
    sqls = [call.args[0] for call in conn.fetch.await_args_list]
    matching = [sql for sql in sqls if "FROM audit_log" in sql]
    assert len(matching) == 1
    assert "WHERE tenant_id::text = $1" in matching[0]
    assert "tenant_id IS NULL" not in matching[0]
    params = [call.args[1] for call in conn.fetch.await_args_list if "FROM audit_log" in call.args[0]]
    assert params == ["t_alpha"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["expenses", "revenue", "balance_summary"])
async def test_ask_finance_activity_excludes_unposted_approvals(monkeypatch, kind):
    from app.api.services import ask_bridge_hub_service as ask

    conn = AsyncMock()
    conn.fetch.return_value = [{
        "id": 41, "description": "posted expense", "amount": 123.0,
        "account_code": "7110", "status": "posted", "created_at": "2026-02-01",
    }]
    conn.fetchval.return_value = 123
    monkeypatch.setattr(ask, "get_conn", lambda: _fake_conn(conn))

    await ask.execute_intent_query("t_alpha", {
        "query_type": kind, "filters": {},
    })
    assert conn.fetch.await_count == 1
    sql = conn.fetch.await_args.args[0]
    assert "tenant_id" in sql
    assert "status = 'posted'" in sql
    assert "status IN ('posted', 'approved')" not in sql
    assert conn.fetch.await_args.args[1] == "t_alpha"


def test_ask_answer_does_not_present_draft_activities_as_official_pnl():
    from app.api.services.ask_bridge_hub_service import format_answer

    intent = {"query_type": "revenue", "original": "revenue",
              "filters": {"month": None}}
    answer = format_answer({
        "rows": [{"amount": 42}], "total": 42,
    }, intent)
    assert "posted draft" in answer.lower()
    assert "not audited P&L" in answer
    assert "Total revenue:" not in answer


@pytest.mark.asyncio
async def test_ask_route_requires_signed_tenant_before_db(monkeypatch):
    from app.api import routes_ask_bridge_hub
    query = AsyncMock(side_effect=AssertionError("DB should not be called"))
    monkeypatch.setattr(routes_ask_bridge_hub, "ask", query)
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(HTTPException) as denied:
            await routes_ask_bridge_hub.ask_question(
                routes_ask_bridge_hub.AskPayload(question="show revenue"),
                req(tenant="t_evil", signed="t_alpha"),
            )
    assert denied.value.status_code == 403
    query.assert_not_awaited()
