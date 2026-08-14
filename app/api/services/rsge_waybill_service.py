"""app/api/services/rsge_waybill_service.py — RS.ge waybill sync service.

WAYBILL_PROTOCOL_NEEDS_CONFIRMATION:
  All write waybill actions (activate, cancel via this service) require
  RSGE_TEST_MODE=true and individual action flags. See rsge_action_service.

Sync flow:
  1. list_waybills() — fetch from RS.ge WayBill SOAP service
  2. sync_selected() — upsert into rsge_waybills table
  3. create_evidence() — create evidence record (no auto-posting)
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

log = logging.getLogger(__name__)

# WAYBILL_PROTOCOL_NEEDS_CONFIRMATION = True
# Reason: The WayBill SOAP protocol (waybill_protocol.pdf) confirms
# save_waybill, get_waybill, get_waybills_v1, deactivate_waybill, activate_waybill.
# These methods are implemented in rs_ge_connector.py.
# Custom correction (correct_waybill) is NOT a documented SOAP method.
# Correction is done by deactivate + new save_waybill. Marked as stub.

PROTOCOL_CONFIRMED_METHODS = frozenset({
    "save_waybill", "get_waybill", "get_waybills_v1",
    "deactivate_waybill", "activate_waybill",
    "chek_service_user", "get_waybill_types", "get_waybill_units",
})

PROTOCOL_UNCONFIRMED_METHODS = frozenset({"correct_waybill"})


def _map_wb_to_dict(raw: dict) -> dict:
    return {
        "rsge_id":         str(raw.get("id") or raw.get("ID") or ""),
        "waybill_number":  str(raw.get("waybill_number") or raw.get("WAYBILL_NUMBER") or ""),
        "wb_type":         str(raw.get("type") or raw.get("TYPE") or ""),
        "rsge_status":     str(raw.get("status") or raw.get("STATUS") or ""),
        "buyer_tin":       str(raw.get("buyer_tin") or raw.get("BUYER_TIN") or ""),
        "buyer_name":      str(raw.get("buyer_name") or raw.get("BUYER_NAME") or ""),
        "start_address":   str(raw.get("start_address") or raw.get("START_ADDRESS") or ""),
        "end_address":     str(raw.get("end_address") or raw.get("END_ADDRESS") or ""),
        "driver_name":     str(raw.get("driver_name") or raw.get("DRIVER_NAME") or ""),
        "car_number":      str(raw.get("car_number") or raw.get("CAR_NUMBER") or ""),
        "full_amount":     float(raw.get("full_amount") or raw.get("FULL_AMOUNT") or 0),
        "begin_date":      str(raw.get("begin_date") or raw.get("BEGIN_DATE") or ""),
    }


async def list_waybills(
    conn,
    tenant_id: str,
    connector,
    limit: int = 100,
    date_from: str = "",
    date_to: str = "",
) -> List[dict]:
    """Fetch waybill list from RS.ge and merge with local sync status."""
    raw_list = connector.history(tenant_id, limit=limit,
                                 date_from=date_from, date_to=date_to)

    rsge_ids = [str(r.get("id") or r.get("ID") or "") for r in raw_list]
    local_map: dict = {}
    if rsge_ids:
        try:
            from app.api.db import _q
            rows = await conn.fetch(
                _q("SELECT rsge_id, id, evidence_id, draft_id, draft_status, synced_at "
                   "FROM rsge_waybills WHERE tenant_id = %s AND rsge_id = ANY(%s)"),
                tenant_id, rsge_ids,
            )
            local_map = {r["rsge_id"]: dict(r) for r in rows}
        except Exception as exc:
            log.debug("list_waybills local fetch skipped: %s", exc)

    results = []
    for raw in raw_list:
        wb = _map_wb_to_dict(raw)
        local = local_map.get(wb["rsge_id"], {})
        results.append({
            **wb,
            "source":       "rs.ge",
            "synced":       bool(local),
            "synced_at":    str(local.get("synced_at") or ""),
            "evidence_id":  local.get("evidence_id"),
            "draft_id":     local.get("draft_id"),
            "draft_status": local.get("draft_status"),
            "local_id":     local.get("id"),
        })
    return results


async def sync_selected(
    conn,
    tenant_id: str,
    waybill_ids: List[str],
    connector,
    actor: Optional[str] = None,
) -> dict:
    """Download and upsert selected waybills into rsge_waybills.

    Deduplicates by (tenant_id, rsge_id). No auto-posting.
    """
    all_raw = connector.history(tenant_id, limit=500)
    raw_map = {str(r.get("id") or r.get("ID") or ""): r for r in all_raw}

    synced, errors = [], []
    for wid in waybill_ids:
        raw = raw_map.get(wid)
        if raw is None:
            errors.append({"id": wid, "error": "not found in RS.ge"})
            continue
        wb = _map_wb_to_dict(raw)
        try:
            local_id = await _upsert_waybill(conn, tenant_id, wb, raw)
            synced.append({"rsge_id": wid, "local_id": local_id})
        except Exception as exc:
            log.warning("[RS.GE] waybill upsert failed id=%s: %s", wid, exc)
            errors.append({"id": wid, "error": str(exc)[:120]})

    return {
        "synced": synced,
        "errors": errors,
        "synced_count": len(synced),
        "error_count": len(errors),
        "protocol_confirmed_methods": sorted(PROTOCOL_CONFIRMED_METHODS),
        "protocol_unconfirmed_methods": sorted(PROTOCOL_UNCONFIRMED_METHODS),
    }


async def _upsert_waybill(conn, tenant_id: str, wb: dict, raw: dict) -> int:
    from app.api.db import _q
    sql = _q("""
        INSERT INTO rsge_waybills
          (tenant_id, rsge_id, waybill_number, wb_type, rsge_status,
           buyer_tin, buyer_name, start_address, end_address,
           driver_name, car_number, full_amount, begin_date,
           raw_payload, synced_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (tenant_id, rsge_id) DO UPDATE SET
          rsge_status = EXCLUDED.rsge_status,
          full_amount = EXCLUDED.full_amount,
          raw_payload = EXCLUDED.raw_payload,
          synced_at = NOW()
        RETURNING id
    """)
    row = await conn.fetchrow(
        sql,
        tenant_id, wb["rsge_id"], wb["waybill_number"], wb["wb_type"],
        wb["rsge_status"], wb["buyer_tin"], wb["buyer_name"],
        wb["start_address"], wb["end_address"], wb["driver_name"],
        wb["car_number"], wb["full_amount"],
        wb["begin_date"] or None, json.dumps(raw),
    )
    return row["id"] if row else 0


async def create_evidence_from_waybill(
    conn,
    tenant_id: str,
    local_wb_id: int,
    actor: Optional[str] = None,
) -> dict:
    """Create evidence record from a synced waybill. Idempotent."""
    from app.api.db import _q

    row = await conn.fetchrow(
        _q("SELECT * FROM rsge_waybills WHERE id = %s AND tenant_id = %s"),
        local_wb_id, tenant_id,
    )
    if not row:
        raise ValueError(f"rsge_waybill id={local_wb_id} not found for tenant={tenant_id}")

    wb = dict(row)
    if wb.get("evidence_id"):
        return {"evidence_id": wb["evidence_id"], "created": False, "duplicate": True}

    ev_sql = _q("""
        INSERT INTO documents
          (tenant_id, document_type, file_name, content_type, source,
           amount, currency, vendor_name, document_date, status, extracted_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """)
    extracted = json.dumps({
        "rsge_id": wb.get("rsge_id"),
        "waybill_number": wb.get("waybill_number"),
        "buyer_tin": wb.get("buyer_tin"),
        "buyer_name": wb.get("buyer_name"),
        "rsge_status": wb.get("rsge_status"),
        "car_number": wb.get("car_number"),
    })
    ev_row = await conn.fetchrow(
        ev_sql,
        tenant_id, "waybill",
        f"rsge_wb_{wb.get('rsge_id')}_{wb.get('waybill_number') or 'wb'}.json",
        "application/json", "rs.ge",
        float(wb.get("full_amount") or 0), "GEL",
        wb.get("buyer_name") or "", wb.get("begin_date"),
        "verified", extracted,
    )
    if not ev_row:
        raise RuntimeError("Evidence insert returned no row")

    evidence_id = ev_row["id"]
    await conn.execute(
        _q("UPDATE rsge_waybills SET evidence_id = %s WHERE id = %s AND tenant_id = %s"),
        evidence_id, local_wb_id, tenant_id,
    )
    return {"evidence_id": evidence_id, "created": True, "duplicate": False}
