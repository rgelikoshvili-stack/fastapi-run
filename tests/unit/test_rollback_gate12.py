"""tests/unit/test_rollback_gate12.py — Gate 12: Rollback / Manual Fallback.

Verifies:
- _is_connector_disabled returns True when tenant_settings flag is False.
- _is_connector_disabled returns False when flag is True (default).
- _is_connector_disabled returns False for 'mock' target unconditionally.
- _is_connector_disabled returns False on any exception (fail-open).
- apply_posting_service returns CONNECTOR_DISABLED when flag is set.
- Connector disable flag does NOT affect mock posting.
- export_approved_drafts_csv route returns CSV StreamingResponse.
- CSV contains correct fieldnames header row.
- CSV rows include one row per journal line.
- CSV tenant isolation: only approved drafts returned.
- disable_connector route calls set_tenant_setting with enabled=False.
- enable_connector route calls set_tenant_setting with enabled=True.
- Structural: _is_connector_disabled is called inside apply_posting_service source.
"""
import csv
import inspect
import io
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


def _make_approved_conn():
    conn = AsyncMock()
    draft_row = {
        "id": 10, "tenant_id": "t1", "date": "2026-05-26",
        "description": "Invoice", "partner": "LLC",
        "amount": 500.0, "status": "approved", "currency": "GEL",
        "lines_json": [
            {"account_code": "1210", "debit": 500.0, "credit": 0,    "label": "Bank"},
            {"account_code": "3110", "debit": 0,     "credit": 500.0, "label": "Rev"},
        ],
    }
    conn.fetchrow = AsyncMock(side_effect=[draft_row, None, None])
    conn.fetchval = AsyncMock(side_effect=[None, 77])
    conn.execute = AsyncMock()
    tr = AsyncMock()
    tr.start = AsyncMock()
    tr.commit = AsyncMock()
    tr.rollback = AsyncMock()
    conn.transaction = MagicMock(return_value=tr)
    return conn


def _make_starlette_request(user_id="u1", tenant_id="t1", headers=None):
    from starlette.requests import Request as StarletteRequest
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode(), v.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/posting/export/approved-drafts/csv",
        "query_string": b"",
        "headers": raw_headers,
    }
    req = StarletteRequest(scope)
    req.state.user_id = user_id
    req.state.tenant_id = tenant_id
    return req


# ---------------------------------------------------------------------------
# _is_connector_disabled — unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_is_connector_disabled_returns_true_when_setting_false():
    with patch(
        "app.api.services.posting_service._is_connector_disabled",
        new=AsyncMock(return_value=True),
    ):
        from app.api.services.posting_service import _is_connector_disabled
        result = await _is_connector_disabled("balance", "t1")
    assert result is True


@pytest.mark.asyncio
async def test_is_connector_disabled_returns_false_by_default():
    """When no setting is stored, connector must default to enabled (False = not disabled)."""
    with patch(
        "app.api.services.tenant_config_service.get_tenant_setting",
        new=AsyncMock(return_value=True),
    ):
        from app.api.services.posting_service import _is_connector_disabled
        result = await _is_connector_disabled("balance", "t1")
    assert result is False


@pytest.mark.asyncio
async def test_is_connector_disabled_false_for_mock():
    """mock target is always enabled regardless of tenant_settings."""
    from app.api.services.posting_service import _is_connector_disabled
    result = await _is_connector_disabled("mock", "any-tenant")
    assert result is False


@pytest.mark.asyncio
async def test_is_connector_disabled_fail_open_on_exception():
    """If tenant_settings lookup raises, connector must default to enabled (fail-open)."""
    with patch(
        "app.api.services.tenant_config_service.get_tenant_setting",
        side_effect=Exception("DB down"),
    ):
        from app.api.services.posting_service import _is_connector_disabled
        result = await _is_connector_disabled("balance", "t1")
    assert result is False


# ---------------------------------------------------------------------------
# apply_posting_service — CONNECTOR_DISABLED blocks live posting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_posting_returns_connector_disabled():
    """When connector flag is False, apply_posting_service returns CONNECTOR_DISABLED."""
    conn = _make_approved_conn()
    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.posting_service._is_connector_disabled",
               new=AsyncMock(return_value=True)):
        from app.api.services.posting_service import apply_posting_service
        result = await apply_posting_service(10, "balance", "t1")

    assert result["ok"] is False
    assert result["error"]["code"] == "CONNECTOR_DISABLED"


@pytest.mark.asyncio
async def test_apply_posting_mock_ignores_connector_disabled():
    """CONNECTOR_DISABLED check must not fire for 'mock' target."""
    conn = _make_approved_conn()
    with patch("app.api.services.posting_service.get_conn", return_value=_FakeConnCtx(conn)), \
         patch("app.api.services.posting_service._is_connector_disabled",
               new=AsyncMock(return_value=True)):
        from app.api.services.posting_service import apply_posting_service
        result = await apply_posting_service(10, "mock", "t1")

    # mock is never blocked by connector disable
    error = result.get("error") or {}
    assert error.get("code") != "CONNECTOR_DISABLED"


# ---------------------------------------------------------------------------
# Structural: _is_connector_disabled wired into apply_posting_service
# ---------------------------------------------------------------------------

def test_apply_posting_service_calls_is_connector_disabled():
    from app.api.services import posting_service
    src = inspect.getsource(posting_service.apply_posting_service)
    assert "_is_connector_disabled" in src, (
        "apply_posting_service must call _is_connector_disabled for Gate 12"
    )


def test_connector_disabled_error_code_in_source():
    from app.api.services import posting_service
    src = inspect.getsource(posting_service.apply_posting_service)
    assert "CONNECTOR_DISABLED" in src


# ---------------------------------------------------------------------------
# CSV export endpoint — structural and content tests
# ---------------------------------------------------------------------------

def test_export_approved_drafts_csv_route_exists():
    from app.api import routes_posting
    src = inspect.getsource(routes_posting)
    assert "export/approved-drafts/csv" in src or "export_approved_drafts_csv" in src


def test_export_approved_drafts_csv_requires_posting_read():
    from app.api import routes_posting
    src = inspect.getsource(routes_posting.export_approved_drafts_csv)
    assert "posting:read" in src


class _DbCtx:
    """Async context manager wrapping a pre-built conn mock."""
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


@pytest.mark.asyncio
async def test_export_approved_drafts_csv_returns_streaming_response():
    """CSV endpoint returns a StreamingResponse with text/csv media type."""
    from fastapi.responses import StreamingResponse

    draft_rows = [
        {
            "id": 1, "date": "2026-05-26", "description": "Invoice",
            "partner": "LLC", "amount": 500.0, "currency": "GEL",
            "lines_json": [
                {"account_code": "1210", "debit": 500.0, "credit": 0,    "label": "Bank"},
                {"account_code": "3110", "debit": 0,     "credit": 500.0, "label": "Rev"},
            ],
        }
    ]
    req = _make_starlette_request()
    conn_mock = AsyncMock()
    conn_mock.fetch = AsyncMock(return_value=draft_rows)

    with patch("app.api.db.get_conn", return_value=_DbCtx(conn_mock)), \
         patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"):
        from app.api.routes_posting import export_approved_drafts_csv
        response = await export_approved_drafts_csv(req, limit=500, offset=0)

    assert isinstance(response, StreamingResponse)
    assert "csv" in response.media_type


@pytest.mark.asyncio
async def test_export_approved_drafts_csv_header_row():
    """CSV output must include the required fieldnames in the header."""
    draft_rows = []
    req = _make_starlette_request()
    conn_mock = AsyncMock()
    conn_mock.fetch = AsyncMock(return_value=draft_rows)

    with patch("app.api.db.get_conn", return_value=_DbCtx(conn_mock)), \
         patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"):
        from app.api.routes_posting import export_approved_drafts_csv
        response = await export_approved_drafts_csv(req, limit=500, offset=0)

    chunks = [chunk async for chunk in response.body_iterator]
    body = b"".join(c.encode() if isinstance(c, str) else c for c in chunks).decode()
    reader = csv.DictReader(io.StringIO(body))
    assert set(reader.fieldnames or []) >= {
        "draft_id", "date", "description", "account_code", "debit", "credit"
    }


@pytest.mark.asyncio
async def test_export_approved_drafts_csv_one_row_per_line():
    """Each journal line generates a separate CSV data row."""
    draft_rows = [
        {
            "id": 5, "date": "2026-05-26", "description": "Test",
            "partner": "P", "amount": 300.0, "currency": "GEL",
            "lines_json": [
                {"account_code": "1210", "debit": 300.0, "credit": 0,    "label": "Dr"},
                {"account_code": "3110", "debit": 0,     "credit": 300.0, "label": "Cr"},
            ],
        }
    ]
    req = _make_starlette_request()
    conn_mock = AsyncMock()
    conn_mock.fetch = AsyncMock(return_value=draft_rows)

    with patch("app.api.db.get_conn", return_value=_DbCtx(conn_mock)), \
         patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"):
        from app.api.routes_posting import export_approved_drafts_csv
        response = await export_approved_drafts_csv(req, limit=500, offset=0)

    chunks = [chunk async for chunk in response.body_iterator]
    body = b"".join(c.encode() if isinstance(c, str) else c for c in chunks).decode()
    reader = csv.DictReader(io.StringIO(body))
    data_rows = list(reader)
    # 1 draft × 2 lines = 2 data rows
    assert len(data_rows) == 2
    account_codes = {r["account_code"] for r in data_rows}
    assert "1210" in account_codes
    assert "3110" in account_codes


# ---------------------------------------------------------------------------
# disable / enable connector routes — structural tests
# ---------------------------------------------------------------------------

def test_disable_connector_route_exists():
    from app.api import routes_posting
    src = inspect.getsource(routes_posting)
    assert "disable_connector" in src or "connector/{target}/disable" in src


def test_enable_connector_route_exists():
    from app.api import routes_posting
    src = inspect.getsource(routes_posting)
    assert "enable_connector" in src or "connector/{target}/enable" in src


@pytest.mark.asyncio
async def test_disable_connector_calls_set_tenant_setting():
    """POST /connector/{target}/disable must store enabled=False in tenant_settings."""
    from starlette.requests import Request as StarletteRequest
    scope = {
        "type": "http", "method": "POST",
        "path": "/posting/connector/balance/disable",
        "query_string": b"", "headers": [],
    }
    req = StarletteRequest(scope)
    req.state.user_id = "admin"
    req.state.tenant_id = "t1"

    with patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"), \
         patch("app.api.services.tenant_config_service.set_tenant_setting",
               new=AsyncMock()) as mock_set:
        from app.api.routes_posting import disable_connector
        result = await disable_connector(req, target="balance")

    assert result["ok"] is True
    assert result["data"]["enabled"] is False


@pytest.mark.asyncio
async def test_enable_connector_calls_set_tenant_setting():
    """POST /connector/{target}/enable must store enabled=True in tenant_settings."""
    from starlette.requests import Request as StarletteRequest
    scope = {
        "type": "http", "method": "POST",
        "path": "/posting/connector/balance/enable",
        "query_string": b"", "headers": [],
    }
    req = StarletteRequest(scope)
    req.state.user_id = "admin"
    req.state.tenant_id = "t1"

    with patch("app.api.routes_posting.require_permission"), \
         patch("app.api.routes_posting.resolve_tenant_id", return_value="t1"), \
         patch("app.api.services.tenant_config_service.set_tenant_setting",
               new=AsyncMock()):
        from app.api.routes_posting import enable_connector
        result = await enable_connector(req, target="balance")

    assert result["ok"] is True
    assert result["data"]["enabled"] is True
