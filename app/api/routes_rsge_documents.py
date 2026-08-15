"""app/api/routes_rsge_documents.py

Sprint 3A — RS.ge Document Import (file-based, no live portal).
Accountant exports XML/JSON from RS.ge portal, uploads here.
Bridge Hub parses → stores → auto-runs triangle match → AI can query.

Endpoints:
  POST /rsge-documents/import-waybill       — upload ზედნადები XML/JSON
  POST /rsge-documents/import-tax-invoice   — upload ფაქტურა XML/JSON
  GET  /rsge-documents/waybills             — list RS.ge-imported waybills
  GET  /rsge-documents/tax-invoices         — list RS.ge-imported tax invoices
  GET  /rsge-documents/import-history       — audit log of imports
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Request, Query

from app.api.authz import require_permission
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response, http_error
from app.api.security import limiter
from app.api.tenant_context import resolve_tenant_id
from app.api.services.rsge_document_parser import (
    parse_rsge_waybills,
    parse_rsge_tax_invoices,
)

router = APIRouter(prefix="/rsge-documents", tags=["rsge-documents"])
log = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


# ─────────────────────────────────────────────────────────────────────────────
# Import endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/import-waybill")
@limiter.limit("20/minute")
async def import_rsge_waybill(file: UploadFile = File(...), request: Request = None):
    """Upload RS.ge waybill export (XML or JSON) — parses and stores all waybills."""
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 5MB)", "FILE_TOO_LARGE")
    if not content:
        return http_error(400, "Empty file", "EMPTY_FILE")

    parsed = parse_rsge_waybills(content)
    if not parsed:
        return error_response(
            "Could not parse file — use RS.ge XML or JSON export",
            "PARSE_ERROR",
            f"filename={file.filename}",
        )

    inserted, skipped = 0, 0
    inserted_ids = []

    async with get_conn() as conn:
        for wb in parsed:
            waybill_number = wb.get("waybill_number")
            if not waybill_number:
                skipped += 1
                continue

            # Dedup by (tenant_id, waybill_number, source='rsge_import')
            existing = await conn.fetchrow(_q(
                "SELECT id FROM waybills WHERE tenant_id=%s AND waybill_number=%s AND source='rsge_import'"
            ), tenant_id, waybill_number)
            if existing:
                skipped += 1
                continue

            row = await conn.fetchrow(_q("""
                INSERT INTO waybills
                    (tenant_id, waybill_number, waybill_date,
                     seller_inn, seller_name, buyer_inn, buyer_name,
                     transport_from, transport_to, vehicle_number, driver_name,
                     line_items, subtotal, vat_amount, total_amount,
                     status, source, raw_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported','rsge_import',%s)
                RETURNING id
            """),
                tenant_id,
                waybill_number,
                wb.get("waybill_date"),
                wb.get("seller_inn"),
                wb.get("seller_name"),
                wb.get("buyer_inn"),
                wb.get("buyer_name"),
                wb.get("transport_from"),
                wb.get("transport_to"),
                wb.get("vehicle_number"),
                wb.get("driver_name"),
                json.dumps(wb.get("line_items") or []),
                wb.get("subtotal"),
                wb.get("vat_amount"),
                wb.get("total_amount"),
                content.decode("utf-8", errors="replace")[:4000],
            )
            inserted_ids.append(row["id"])
            inserted += 1

    # Auto-run triangle match for newly inserted waybills
    if inserted_ids:
        try:
            from app.api.services.document_processing_service import _try_match_triangle
            async with get_conn() as conn:
                for wid in inserted_ids:
                    wb_row = await conn.fetchrow(
                        "SELECT * FROM waybills WHERE id=$1", wid
                    )
                    if wb_row:
                        await _try_match_triangle(conn, dict(wb_row), "waybill", tenant_id)
        except Exception as e:
            log.warning("triangle match after rsge waybill import failed: %s", e)

    return ok_response(
        f"Imported {inserted} waybill(s) from RS.ge, {skipped} skipped (duplicate or missing number)",
        {"inserted": inserted, "skipped": skipped, "ids": inserted_ids},
    )


@router.post("/import-tax-invoice")
@limiter.limit("20/minute")
async def import_rsge_tax_invoice(file: UploadFile = File(...), request: Request = None):
    """Upload RS.ge tax invoice export (XML or JSON) — parses and stores all invoices."""
    require_permission(request, "documents:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 5MB)", "FILE_TOO_LARGE")
    if not content:
        return http_error(400, "Empty file", "EMPTY_FILE")

    parsed = parse_rsge_tax_invoices(content)
    if not parsed:
        return error_response(
            "Could not parse file — use RS.ge XML or JSON export",
            "PARSE_ERROR",
            f"filename={file.filename}",
        )

    inserted, skipped = 0, 0
    inserted_ids = []

    async with get_conn() as conn:
        for inv in parsed:
            invoice_number = inv.get("invoice_number")
            if not invoice_number:
                skipped += 1
                continue

            existing = await conn.fetchrow(_q(
                "SELECT id FROM tax_invoices WHERE tenant_id=%s AND invoice_number=%s AND source='rsge_import'"
            ), tenant_id, invoice_number)
            if existing:
                skipped += 1
                continue

            # Find related waybill if number provided
            related_waybill_id = None
            related_waybill_number = inv.get("related_waybill_number")
            if related_waybill_number:
                wb_row = await conn.fetchrow(_q(
                    "SELECT id FROM waybills WHERE tenant_id=%s AND waybill_number=%s LIMIT 1"
                ), tenant_id, related_waybill_number)
                if wb_row:
                    related_waybill_id = wb_row["id"]

            row = await conn.fetchrow(_q("""
                INSERT INTO tax_invoices
                    (tenant_id, invoice_number, invoice_series, invoice_date,
                     seller_inn, seller_name, buyer_inn, buyer_name,
                     line_items, subtotal, vat_amount, total_amount,
                     status, source, related_waybill_number, related_waybill_id, raw_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported','rsge_import',%s,%s,%s)
                RETURNING id
            """),
                tenant_id,
                invoice_number,
                inv.get("invoice_series"),
                inv.get("invoice_date"),
                inv.get("seller_inn"),
                inv.get("seller_name"),
                inv.get("buyer_inn"),
                inv.get("buyer_name"),
                json.dumps(inv.get("line_items") or []),
                inv.get("subtotal"),
                inv.get("vat_amount"),
                inv.get("total_amount"),
                related_waybill_number,
                related_waybill_id,
                content.decode("utf-8", errors="replace")[:4000],
            )
            inserted_ids.append(row["id"])
            inserted += 1

    if inserted_ids:
        try:
            from app.api.services.document_processing_service import _try_match_triangle
            async with get_conn() as conn:
                for iid in inserted_ids:
                    inv_row = await conn.fetchrow(
                        "SELECT * FROM tax_invoices WHERE id=$1", iid
                    )
                    if inv_row:
                        await _try_match_triangle(conn, dict(inv_row), "tax_invoice", tenant_id)
        except Exception as e:
            log.warning("triangle match after rsge tax_invoice import failed: %s", e)

    return ok_response(
        f"Imported {inserted} tax invoice(s) from RS.ge, {skipped} skipped",
        {"inserted": inserted, "skipped": skipped, "ids": inserted_ids},
    )


# ─────────────────────────────────────────────────────────────────────────────
# List endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/waybills")
async def list_rsge_waybills(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    seller_inn: str = Query(""),
    buyer_inn: str = Query(""),
    status: str = Query(""),
):
    """List waybills imported from RS.ge."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conditions = ["w.tenant_id=$1", "w.source='rsge_import'"]
    args: list = [tenant_id]
    i = 2
    if seller_inn:
        conditions.append(f"w.seller_inn=${i}"); args.append(seller_inn); i += 1
    if buyer_inn:
        conditions.append(f"w.buyer_inn=${i}"); args.append(buyer_inn); i += 1
    if status:
        conditions.append(f"w.status=${i}"); args.append(status); i += 1

    where = " AND ".join(conditions)
    async with get_conn() as conn:
        rows = await conn.fetch(f"""
            SELECT w.id, w.waybill_number, w.waybill_date, w.seller_inn, w.seller_name,
                   w.buyer_inn, w.buyer_name, w.total_amount, w.vat_amount, w.status,
                   w.created_at,
                   tm.match_status, tm.match_score
            FROM waybills w
            LEFT JOIN triangle_matches tm ON tm.waybill_id=w.id AND tm.tenant_id=w.tenant_id
            WHERE {where}
            ORDER BY w.created_at DESC
            LIMIT ${i} OFFSET ${i+1}
        """, *args, limit, offset)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM waybills w WHERE {where}", *args
        )

    return ok_response("RS.ge waybills", {
        "total": total,
        "limit": limit,
        "offset": offset,
        "waybills": [dict(r) for r in rows],
    })


@router.get("/tax-invoices")
async def list_rsge_tax_invoices(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    seller_inn: str = Query(""),
    buyer_inn: str = Query(""),
    status: str = Query(""),
):
    """List tax invoices imported from RS.ge."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conditions = ["ti.tenant_id=$1", "ti.source='rsge_import'"]
    args: list = [tenant_id]
    i = 2
    if seller_inn:
        conditions.append(f"ti.seller_inn=${i}"); args.append(seller_inn); i += 1
    if buyer_inn:
        conditions.append(f"ti.buyer_inn=${i}"); args.append(buyer_inn); i += 1
    if status:
        conditions.append(f"ti.status=${i}"); args.append(status); i += 1

    where = " AND ".join(conditions)
    async with get_conn() as conn:
        rows = await conn.fetch(f"""
            SELECT ti.id, ti.invoice_number, ti.invoice_series, ti.invoice_date,
                   ti.seller_inn, ti.seller_name, ti.buyer_inn, ti.buyer_name,
                   ti.total_amount, ti.vat_amount, ti.status,
                   ti.related_waybill_number, ti.created_at,
                   tm.match_status, tm.match_score
            FROM tax_invoices ti
            LEFT JOIN triangle_matches tm ON tm.tax_invoice_id=ti.id AND tm.tenant_id=ti.tenant_id
            WHERE {where}
            ORDER BY ti.created_at DESC
            LIMIT ${i} OFFSET ${i+1}
        """, *args, limit, offset)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM tax_invoices ti WHERE {where}", *args
        )

    return ok_response("RS.ge tax invoices", {
        "total": total,
        "limit": limit,
        "offset": offset,
        "tax_invoices": [dict(r) for r in rows],
    })


@router.get("/import-history")
async def get_import_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Audit log — all RS.ge-imported documents."""
    require_permission(request, "documents:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    async with get_conn() as conn:
        waybills = await conn.fetch(_q("""
            SELECT 'waybill' AS doc_type, id, waybill_number AS doc_number,
                   waybill_date AS doc_date, seller_name, total_amount, status, created_at
            FROM waybills WHERE tenant_id=%s AND source='rsge_import'
        """), tenant_id)
        invoices = await conn.fetch(_q("""
            SELECT 'tax_invoice' AS doc_type, id, invoice_number AS doc_number,
                   invoice_date AS doc_date, seller_name, total_amount, status, created_at
            FROM tax_invoices WHERE tenant_id=%s AND source='rsge_import'
        """), tenant_id)

    combined = sorted(
        [dict(r) for r in waybills] + [dict(r) for r in invoices],
        key=lambda x: x.get("created_at") or datetime.min,
        reverse=True,
    )
    page = combined[offset: offset + limit]

    return ok_response("RS.ge import history", {
        "total": len(combined),
        "limit": limit,
        "offset": offset,
        "records": page,
    })
