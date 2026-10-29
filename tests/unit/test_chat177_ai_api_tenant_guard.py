"""Chat177 security regressions for AI API, session scope and vector isolation.

All synthetic, no network, Production credentials, Cloud SQL, or filesystem
indexing. Direct-route tests pass explicit FastAPI-injected values.
"""
import io
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.db import authenticated_tenant_context
from app.api.policy.permission_map import match_permission


def req(tenant="t_alpha", signed=None, user="101", role="admin", authenticated=True):
    request = Request({
        "type": "http", "method": "POST", "scheme": "http",
        "path": "/api/ai/chat", "raw_path": b"/api/ai/chat",
        "query_string": b"", "headers": [(b"host", b"bridge.example.test"),
                                         (b"x-tenant-id", b"t_beta")],
        "client": ("127.0.0.1", 4177), "server": ("127.0.0.1", 8080),
        "http_version": "1.1",
    })
    request.state.authenticated = authenticated
    request.state.tenant_id = tenant
    request.state.auth_tenant_id = tenant if signed is None else signed
    request.state.user_id = user
    request.state.role = role
    return request


def _scope(tenant="t_alpha"):
    return authenticated_tenant_context(tenant)


@pytest.mark.parametrize("method,path,permission", [
    ("GET", "/api/ai/stats", "chat:use"),
    ("POST", "/api/ai/chat", "chat:use"),
    ("GET", "/api/ai/search", "chat:use"),
    ("POST", "/api/ai/learn", "patterns:manage"),
    ("POST", "/api/ai/index", "patterns:manage"),
    ("POST", "/api/ai/action/confirm", "approval:write"),
    ("GET", "/api/ai/vector-stats", "patterns:manage"),
])
def test_rbac_map_never_defaults_privileged_endpoints_to_chat_use(
    method, path, permission
):
    assert match_permission(method, path) == permission


@pytest.mark.asyncio
async def test_rbac_middleware_rejects_unauthenticated_and_viewer_ai_requests():
    from app.api.middleware.rbac_middleware import rbac_middleware
    async def next_response(_request):
        return JSONResponse({"ok": True})

    anonymous = req(authenticated=False)
    anonymous.scope["path"] = "/api/ai/stats"
    anonymous.scope["method"] = "GET"
    denied = await rbac_middleware(anonymous, next_response)
    assert denied.status_code == 401

    viewer = req(role="viewer")
    viewer.scope["path"] = "/api/ai/chat"
    denied = await rbac_middleware(viewer, next_response)
    assert denied.status_code == 403

    accountant = req(role="accountant")
    accountant.scope["path"] = "/api/ai/chat"
    allowed = await rbac_middleware(accountant, next_response)
    assert allowed.status_code == 200


def test_ai_session_key_is_user_and_tenant_scoped_without_exposing_identity():
    from app.api.services.ai_session_scope import scoped_ai_session
    with _scope("t_alpha"):
        t1, first = scoped_ai_session(req(user="101"), "same-public-session")
        _, same = scoped_ai_session(req(user="101"), "same-public-session")
        _, other_user = scoped_ai_session(req(user="202"), "same-public-session")
    with _scope("t_beta"):
        _, other_tenant = scoped_ai_session(req(tenant="t_beta", user="101"), "same-public-session")
    assert t1 == "t_alpha"
    assert first == same
    assert first not in (other_user, other_tenant)
    assert first.startswith("usr2_")
    assert "t_alpha" not in first and "101" not in first


@pytest.mark.parametrize("session", ["", " ", "bad/a", "bad\nid", "x" * 129])
def test_ai_session_rejects_unsafe_user_input(session):
    from app.api.services.ai_session_scope import scoped_ai_session
    with _scope():
        with pytest.raises(HTTPException) as err:
            scoped_ai_session(req(), session)
    assert err.value.status_code == 422


@pytest.mark.asyncio
async def test_ai_chat_ignores_forged_tenant_prompt_role_and_vector_opt_in(monkeypatch):
    from app.api import routes_ai_chat as routes
    fake_result = {
        "answer": "Synthetic only", "sources": [], "confidence": 0.9,
        "search_method": "local", "session_id": "internal", "suggested_actions": [],
    }
    run = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(routes, "handle_ai_chat", run)
    with _scope():
        result = await routes.ai_chat(
            request=req(role="accountant"),
            message="Hello", session_id="share", tenant_id="t_beta",
            role="admin", use_vector_search=True, file=None, files=None,
        )
    assert result.status_code == 200
    params = run.await_args.kwargs
    assert params["tenant_id"] == "t_alpha"
    assert params["role"] == "accountant"
    assert params["session_id"].startswith("usr2_")
    assert params["use_vector_search"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("text,attach", [
    ("Please post invoice", False),
    ("ფაქტურა გატარე", False),
    ("Summarize this file", True),
])
async def test_chat_write_paths_require_posting_write(monkeypatch, text, attach):
    from app.api import routes_ai_chat as routes
    run = AsyncMock(side_effect=AssertionError("No AI write should run"))
    monkeypatch.setattr(routes, "handle_ai_chat", run)
    uploaded = UploadFile(file=io.BytesIO(b"synthetic"), filename="synthetic.txt") if attach else None
    with _scope():
        with pytest.raises(HTTPException) as denied:
            await routes.ai_chat(
                request=req(role="ai_supervisor"), message=text,
                session_id="test", tenant_id="t_beta", role="admin",
                file=uploaded, files=None,
            )
    assert denied.value.status_code == 403
    run.assert_not_awaited()


@pytest.mark.parametrize("route,payload", [
    ("vat_calc", "VATRequest"),
    ("dividend_calc", "DividendRequest"),
    ("payroll_calc", "PayrollRequest"),
    ("cit_calc", "CITRequest"),
    ("dep_calc", "DepreciationRequest"),
])
@pytest.mark.asyncio
async def test_ai_calculators_use_actual_http_request_for_auth(monkeypatch, route, payload):
    from app.api import routes_ai_chat as routes
    models = {
        "VATRequest": {"amount": 100},
        "DividendRequest": {"gross_amount": 100},
        "PayrollRequest": {"gross": 100},
        "CITRequest": {"distributed_profit": 100},
        "DepreciationRequest": {"cost": 100, "residual": 10, "useful_life_years": 5},
    }
    patch_name = {"vat_calc": "run_vat_calc", "dividend_calc": "run_dividend_calc",
                  "payroll_calc": "run_payroll_calc", "cit_calc": "run_cit_calc",
                  "dep_calc": "run_depreciation_calc"}[route]
    captured = []
    monkeypatch.setattr(routes, patch_name, lambda body: captured.append(body) or {"ok": True})
    body = getattr(routes, payload)(**models[payload])
    with _scope():
        assert (await getattr(routes, route)(body, req()))["ok"]
        with pytest.raises(HTTPException) as denied:
            await getattr(routes, route)(body, req(role="viewer"))
    assert denied.value.status_code == 403
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_classification_and_learning_bind_signed_tenant_and_disable_vector(monkeypatch):
    from app.api import routes_ai_chat as routes
    classify = []
    async_learning = AsyncMock(return_value={"status": "learned"})
    monkeypatch.setattr(routes, "run_classify_tx",
                        lambda payload: classify.append(payload) or {"ok": True})
    monkeypatch.setattr(routes, "run_learn_rule", async_learning)

    with _scope():
        await routes.classify_tx(routes.ClassifyRequest(
            description="Synthetic", tenant_id="t_beta"
        ), req(role="accountant"))
        with pytest.raises(HTTPException) as denied:
            await routes.learn_rule(routes.LearnRequest(
                pattern="synthetic", account="7110", tenant_id="t_beta"
            ), req(role="accountant"))
        await routes.learn_rule(routes.LearnRequest(
            pattern="synthetic", account="7110", tenant_id="t_beta", use_vector=True
        ), req(role="admin"))
    assert denied.value.status_code == 403
    assert classify[0].tenant_id == "t_alpha"
    args = async_learning.await_args.args[0]
    assert args.tenant_id == "t_alpha"
    assert args.use_vector is False


@pytest.mark.asyncio
async def test_indexing_and_vector_stats_are_disabled_even_for_admin(monkeypatch):
    from app.api import routes_ai_chat as routes
    index = AsyncMock(side_effect=AssertionError("must not index any directory"))
    monkeypatch.setattr(routes, "run_index_files", index)
    with _scope():
        with pytest.raises(HTTPException) as blocked:
            await routes.index_files_ep(
                routes.IndexRequest(files_dir="/somewhere", force_reindex=True), req()
            )
        with pytest.raises(HTTPException) as stats:
            await routes.vector_stats(req())
    assert blocked.value.status_code == 503
    assert stats.value.status_code == 503
    index.assert_not_awaited()


@pytest.mark.asyncio
async def test_keyword_search_requires_signed_tenant_and_never_calls_global_vector(monkeypatch):
    from app.api import routes_ai_chat as routes
    calls = []
    monkeypatch.setattr(routes, "run_ai_search",
                        lambda **kw: calls.append(kw) or {"method": "keyword", "results": []})
    with _scope():
        result = await routes.ai_search(req(), "test", top_k=500, use_vector=True)
        with pytest.raises(HTTPException) as unauthorized:
            await routes.ai_search(req(role="viewer"), "test", top_k=5)
    assert result["vector_search_tenant_isolated"] is False
    assert calls == [{"q": "test", "top_k": 20, "use_vector": False}]
    assert unauthorized.value.status_code == 403


@pytest.mark.asyncio
async def test_stats_do_not_access_global_learned_rule_counts(monkeypatch):
    from app.api import routes_ai_chat as routes
    monkeypatch.setattr(routes, "get_ai_system_stats",
                        lambda: (_ for _ in ()).throw(AssertionError("global DB scan")))
    with _scope():
        status = await routes.ai_stats(req())
    assert status["vector_search_tenant_isolated"] is False
    assert "knowledge_base" not in status


@pytest.mark.asyncio
async def test_sensitive_preview_requires_approval_read(monkeypatch):
    from app.api import routes_ai_chat as routes
    with _scope():
        with pytest.raises(HTTPException) as denied:
            await routes.preview_action(req(role="ai_supervisor"), {
                "action": "approve_draft", "params": {"draft_id": 41}
            })
    assert denied.value.status_code == 403


@asynccontextmanager
async def fake_conn(conn):
    yield conn


@pytest.mark.asyncio
async def test_llm_session_cache_is_tenant_isolated(monkeypatch):
    from app.api.services import llm_service
    saved = dict(llm_service._chat_history)
    llm_service._chat_history.clear()
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    monkeypatch.setattr(llm_service, "get_conn", lambda: fake_conn(conn))
    try:
        await llm_service._save_history(
            "same", "t_alpha", [{"role": "user", "content": "alpha-only"}]
        )
        await llm_service._save_history(
            "same", "t_beta", [{"role": "user", "content": "beta-only"}]
        )
        assert (await llm_service._load_history("same", "t_alpha"))[0]["content"] == "alpha-only"
        assert (await llm_service._load_history("same", "t_beta"))[0]["content"] == "beta-only"
        assert ("t_alpha", "same") in llm_service._chat_history
        assert ("t_beta", "same") in llm_service._chat_history
    finally:
        llm_service._chat_history.clear()
        llm_service._chat_history.update(saved)


@pytest.mark.asyncio
async def test_ai_clear_session_only_evicts_one_users_cache(monkeypatch):
    from app.api import routes_ai_chat as routes
    from app.api.services import chat_session_service, llm_service
    from app.api.services.ai_session_scope import scoped_ai_session

    cleared = AsyncMock()
    monkeypatch.setattr(chat_session_service, "clear_history", cleared)
    with _scope():
        _, first_key = scoped_ai_session(req(user="101"), "shared")
        _, other_key = scoped_ai_session(req(user="202"), "shared")
        original = dict(llm_service._chat_history)
        llm_service._chat_history.clear()
        try:
            llm_service._chat_history[("t_alpha", first_key)] = ["user-one"]
            llm_service._chat_history[("t_alpha", other_key)] = ["user-two"]
            result = await routes.clear_session("shared", req(user="101"))
            assert result["ok"] is True
            cleared.assert_awaited_once_with(first_key, "t_alpha")
            assert ("t_alpha", first_key) not in llm_service._chat_history
            assert llm_service._chat_history[("t_alpha", other_key)] == ["user-two"]
        finally:
            llm_service._chat_history.clear()
            llm_service._chat_history.update(original)


@pytest.mark.asyncio
async def test_export_loads_only_users_namespaced_session(monkeypatch):
    from app.api import routes_ai_chat as routes
    from app.api.services import chat_session_service
    loader = AsyncMock(return_value=[{"role": "user", "content": "synthetic message"}])
    monkeypatch.setattr(chat_session_service, "load_history", loader)
    with _scope():
        response = await routes.export_chat_txt("a-uuid", req(user="101"))
    assert response.status_code == 200
    args = loader.await_args.args
    assert args[0].startswith("usr2_")
    assert args[1] == "t_alpha"
    assert "a-uuid" in response.headers["content-disposition"]
