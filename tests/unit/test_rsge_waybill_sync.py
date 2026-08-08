"""tests/unit/test_rsge_waybill_sync.py — Waybill sync unit tests."""
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock


# ── 1. Waybill service has required functions ─────────────────────────────────

def test_waybill_service_has_required_functions():
    from app.api.services import rsge_waybill_service as svc
    assert hasattr(svc, "list_waybills")
    assert hasattr(svc, "sync_selected")
    assert hasattr(svc, "create_evidence_from_waybill")


# ── 2. Protocol confirmation flags ───────────────────────────────────────────

def test_waybill_protocol_confirmed_methods():
    from app.api.services.rsge_waybill_service import PROTOCOL_CONFIRMED_METHODS
    assert "save_waybill" in PROTOCOL_CONFIRMED_METHODS
    assert "get_waybill" in PROTOCOL_CONFIRMED_METHODS
    assert "get_waybills_v1" in PROTOCOL_CONFIRMED_METHODS
    assert "deactivate_waybill" in PROTOCOL_CONFIRMED_METHODS
    assert "activate_waybill" in PROTOCOL_CONFIRMED_METHODS


def test_waybill_protocol_unconfirmed_marked():
    from app.api.services.rsge_waybill_service import PROTOCOL_UNCONFIRMED_METHODS
    assert "correct_waybill" in PROTOCOL_UNCONFIRMED_METHODS


# ── 3. list_waybills merges RS.ge + local ─────────────────────────────────────

def test_list_waybills_returns_synced_status():
    from app.api.services.rsge_waybill_service import list_waybills

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[
        {"rsge_id": "WB1", "id": 10, "evidence_id": None, "synced_at": "2026-01-01"}
    ])

    mock_connector = MagicMock()
    mock_connector.history.return_value = [
        {"id": "WB1", "waybill_number": "WB-0001", "type": "2",
         "status": "1", "buyer_tin": "111", "buyer_name": "Buyer",
         "full_amount": "1500.00", "begin_date": "2026-01-01"}
    ]

    result = asyncio.run(
        list_waybills(mock_conn, "t1", mock_connector)
    )
    assert len(result) == 1
    assert result[0]["rsge_id"] == "WB1"
    assert result[0]["synced"] is True
    assert result[0]["source"] == "rs.ge"


# ── 4. sync_selected upserts and returns summary ─────────────────────────────

def test_sync_waybills_returns_summary():
    from app.api.services.rsge_waybill_service import sync_selected

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 20})

    mock_connector = MagicMock()
    mock_connector.history.return_value = [
        {"id": "WB1", "waybill_number": "WB-001", "type": "2",
         "status": "1", "buyer_tin": "111", "buyer_name": "B",
         "full_amount": "500", "begin_date": "2026-01-01"}
    ]

    result = asyncio.run(
        sync_selected(mock_conn, "t1", ["WB1"], mock_connector)
    )
    assert result["synced_count"] == 1
    assert result["error_count"] == 0
    assert "protocol_confirmed_methods" in result
    assert "protocol_unconfirmed_methods" in result


def test_sync_waybills_not_found():
    from app.api.services.rsge_waybill_service import sync_selected

    mock_conn = AsyncMock()
    mock_connector = MagicMock()
    mock_connector.history.return_value = []

    result = asyncio.run(
        sync_selected(mock_conn, "t1", ["MISSING"], mock_connector)
    )
    assert result["error_count"] == 1


# ── 5. Waybill upsert is idempotent ──────────────────────────────────────────

def test_waybill_upsert_is_idempotent():
    from app.api.services import rsge_waybill_service as svc
    src = inspect.getsource(svc._upsert_waybill)
    assert "ON CONFLICT" in src or "on conflict" in src.lower()
    assert "DO UPDATE" in src or "do update" in src.lower()


# ── 6. Waybill sync does NOT auto-post ───────────────────────────────────────

def test_waybill_sync_does_not_auto_post():
    from app.api.services import rsge_waybill_service as svc
    src = inspect.getsource(svc.sync_selected)
    assert "posting_service" not in src
    assert "apply" not in src
    assert "post_to_ledger" not in src


# ── 7. Waybill routes exist for sync ─────────────────────────────────────────

def test_waybill_routes_exist():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    assert "/waybills/sync-selected" in src or "sync_selected_waybills" in src
    assert "/waybills/{waybill_id}/create-evidence" in src or "create_waybill_evidence" in src
