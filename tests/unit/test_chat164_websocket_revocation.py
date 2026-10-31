"""Chat164: WebSocket notifications require signed tenant-bound access tokens.

WebSockets bypass HTTP auth middleware, so revocation must be checked here.
No network or production database connections.
"""
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from app.api import db
from app.api import routes_notifications_ws as ws_mod


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.closed = []
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def close(self, code):
        self.closed.append(code)

    async def send_text(self, text):
        self.messages.append(json.loads(text))


def signed_claims(tenant="t_alpha"):
    return {
        "sub": "42", "email": "member@example.test",
        "role": "accountant", "tenant_id": tenant, "type": "access",
    }


@pytest.mark.asyncio
async def test_missing_websocket_token_denied_without_accept():
    ws = FakeWebSocket()
    await ws_mod.websocket_notifications(ws, tenant_id="t_alpha", token="")
    assert ws.accepted is False
    assert ws.closed == [4001]


@pytest.mark.asyncio
async def test_invalid_or_refresh_websocket_token_denied(monkeypatch):
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_token",
        lambda token, expected_type: None,
    )
    ws = FakeWebSocket()
    await ws_mod.websocket_notifications(ws, tenant_id="t_alpha", token="refresh-only-token")
    assert ws.accepted is False
    assert ws.closed == [4001]


@pytest.mark.asyncio
@pytest.mark.parametrize("signed_tenant,requested", [
    ("t_alpha", "t_beta"),
    ("default", "default"),
    (" t_alpha ", " t_alpha "),
])
async def test_websocket_tenant_mismatch_or_default_denied(monkeypatch, signed_tenant, requested):
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_token",
        lambda token, expected_type: signed_claims(signed_tenant),
    )
    ws = FakeWebSocket()
    await ws_mod.websocket_notifications(ws, tenant_id=requested, token="synthetic-token")
    assert ws.accepted is False
    assert ws.closed == [4003]


@pytest.mark.asyncio
async def test_websocket_denied_for_disabled_user_before_accept(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_token",
        lambda token, expected_type: signed_claims(),
    )
    check = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_live_access_membership", check,
    )
    ws = FakeWebSocket()
    await ws_mod.websocket_notifications(ws, tenant_id="t_alpha", token="signed")
    assert ws.accepted is False
    assert ws.closed == [4003]
    check.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_websocket_closes_when_user_revoked(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_token",
        lambda token, expected_type: signed_claims(),
    )
    # Initially active on handshake, revoked before the first statistics poll.
    check = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_live_access_membership", check,
    )
    stats = AsyncMock(side_effect=AssertionError("revoked member must not see stats"))
    monkeypatch.setattr(ws_mod, "_get_tenant_stats", stats)
    ws = FakeWebSocket()
    await ws_mod.websocket_notifications(ws, tenant_id="t_alpha", token="signed")
    assert ws.accepted is True
    assert ws.closed == [4003]
    assert ws not in ws_mod.manager.connections.get("t_alpha", set())
    assert len(ws.messages) == 1  # only the non-sensitive connected message
    stats.assert_not_awaited()


@pytest.mark.asyncio
async def test_websocket_read_is_bound_to_signed_tenant_context(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_token",
        lambda token, expected_type: signed_claims(),
    )
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_live_access_membership",
        AsyncMock(return_value=True),
    )

    async def scoped_stats(tenant_id):
        assert tenant_id == "t_alpha"
        assert db.require_current_tenant_id() == "t_alpha"
        return {"pending_approval": 0}

    async def stop_after_first_poll(_seconds):
        raise WebSocketDisconnect()

    monkeypatch.setattr(ws_mod, "_get_tenant_stats", scoped_stats)
    monkeypatch.setattr(ws_mod.asyncio, "sleep", stop_after_first_poll)
    ws = FakeWebSocket()
    await ws_mod.websocket_notifications(ws, tenant_id="t_alpha", token="signed")
    assert ws.accepted is True
    assert ws.closed == []
    assert len(ws.messages) == 2
    assert ws.messages[1]["type"] == "stats_update"
    assert ws.messages[1]["tenant_id"] == "t_alpha"
    assert ws not in ws_mod.manager.connections.get("t_alpha", set())
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
async def test_websocket_fails_closed_when_membership_database_unavailable(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_LIVE_MEMBERSHIP_CHECK", "1")
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_token",
        lambda token, expected_type: signed_claims(),
    )
    monkeypatch.setattr(
        "app.api.services.auth_service.verify_live_access_membership",
        AsyncMock(side_effect=ConnectionError("synthetic database outage")),
    )
    ws = FakeWebSocket()
    await ws_mod.websocket_notifications(ws, tenant_id="t_alpha", token="signed")
    assert ws.accepted is False
    assert ws.closed == [4003]
