"""app/api/routes_bank_statements.py

Sprint 3B — Bank statement import (TBC / BOG / generic).
Cleaner successor to /bank-csv/upload:
  - Auto-detects TBC vs BOG from filename / content
  - Per-row dedup (tenant_id, bank, date, amount, transaction_ref)
  - Stores partner, operation_code, transaction_ref as first-class columns
  - Returns per-row inserted/skipped with reasons

Endpoints:
  POST /bank-statements/import         — upload CSV / XLSX / XML
  GET  /bank-statements/batches        — list import batches with stats
  GET  /bank-statements/transactions   — list transactions with filters
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import uuid
from typing import Optional

from fastapi import APIRouter, Form, Query, Request, UploadFile, File

from app.api.authz import require_permission
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response, http_error
from app.api.security import limiter
from app.api.tenant_context import resolve_tenant_id
from app.api.services.bank_format_detector import (
    detect_bank,
    get_col_map,
    extract_partner_from_description,
)

router = APIRouter(prefix="/bank-statements", tags=["bank-statements"])
log = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean(v):
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    if hasattr(v, "isoformat"):
        return v.isoformat()
    s = str(v).strip()
    return s if s and s.lower() not in ("nan", "") else None


def _amount(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace(" ", "").replace("\xa0", ""))
    except (ValueError, TypeError):
        return None


def _get_field(row: dict, candidates: list[str]):
    """Return first non-empty value matching any candidate column name."""
    for col in candidates:
        v = row.get(col)
        if v not in (None, "", "nan"):
            return v
    return None


def _parse_rows(content: bytes, filename: str, bank: str) -> list[dict]:
    """Parse CSV / XLSX / XML into list of normalised row dicts."""
    name = filename.lower()
    col_map = get_col_map(bank)

    if name.endswith(".csv"):
        return _parse_csv(content, col_map)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return _parse_xlsx(content, col_map)
    if name.endswith(".xml"):
        return _parse_xml(content)
    # Unknown extension — try CSV first
    return _parse_csv(content, col_map)


def _parse_csv(content: bytes, col_map: dict) -> list[dict]:
    import csv
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "windows-1251"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = content.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        rows.append(_normalise(raw, col_map))
    return [r for r in rows if r.get("date") or r.get("amount")]


def _parse_xlsx(content: bytes, col_map: dict) -> list[dict]:
    try:
        import pandas as pd
        xl = pd.ExcelFile(io.BytesIO(content))
        sheet = next((s for s in xl.sheet_names if "summary" not in s.lower()), xl.sheet_names[0])
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=0)
        rows = []
        for _, r in df.iterrows():
            raw = {str(k).strip(): _clean(v) for k, v in r.items()}
            row = _normalise(raw, col_map)
            if row.get("date") or row.get("amount"):
                rows.append(row)
        return rows
    except ImportError:
        log.warning("pandas not available for XLSX parsing")
        return []


def _parse_xml(content: bytes) -> list[dict]:
    import xml.etree.ElementTree as ET
    NS = {"g": "http://www.mygemini.com/schemas/mygemini"}
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        log.warning("bank XML parse failed: %s", e)
        return []
    rows = []
    for rec in root.findall(".//g:Record", NS):
        def gt(tag):
            x = rec.find(f"g:{tag}", NS)
            return _clean(x.text if x is not None else None)
        paid_out = _amount(gt("PaidOut"))
        paid_in = _amount(gt("PaidIn"))
        amount = (paid_in or 0) - (paid_out or 0)
        rows.append({
            "date": gt("Date"),
            "description": gt("Description"),
            "partner": gt("PartnerName"),
            "operation_code": gt("OperationCode"),
            "transaction_ref": gt("TransactionId"),
            "currency": gt("Currency") or "GEL",
            "balance": _amount(gt("Balance")),
            "amount": amount,
        })
    return rows


def _normalise(raw: dict, col_map: dict) -> dict:
    date = _get_field(raw, col_map.get("date", []))
    description = _get_field(raw, col_map.get("description", []))
    paid_out = _amount(_get_field(raw, col_map.get("paid_out", [])))
    paid_in = _amount(_get_field(raw, col_map.get("paid_in", [])))
    balance = _amount(_get_field(raw, col_map.get("balance", [])))
    currency = _get_field(raw, col_map.get("currency", [])) or "GEL"
    transaction_ref = _get_field(raw, col_map.get("transaction_ref", []))
    partner = _get_field(raw, col_map.get("partner", []))
    operation_code = _get_field(raw, col_map.get("operation_code", []))

    if paid_out is None and paid_in is None:
        # Try a generic "amount" column
        raw_amt = _amount(_get_field(raw, ["amount", "Amount", "თანხა"]))
        if raw_amt is not None:
            if raw_amt < 0:
                paid_out = abs(raw_amt)
            else:
                paid_in = raw_amt

    amount = (paid_in or 0) - (paid_out or 0)

    if not partner:
        partner = extract_partner_from_description(description)

    # Truncate date to 10 chars (YYYY-MM-DD)
    if date:
        date = str(date).strip()[:10]
    if currency:
        currency = str(currency).strip().upper()[:3]

    return {
        "date": date,
        "description": _clean(description),
        "partner": _clean(partner),
        "operation_code": _clean(operation_code),
        "transaction_ref": _clean(transaction_ref),
        "currency": currency,
        "balance": balance,
        "amount": amount,
        "_raw": raw,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/import")
@limiter.limit("10/minute")
async def import_bank_statement(
    request: Request,
    file: UploadFile = File(...),
    bank: str = Form(default=""),
    account_number: str = Form(default=""),
):
    """Upload TBC / BOG / generic bank statement (CSV, XLSX, XML)."""
    require_permission(request, "bank:upload")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    content = await file.read()
    if not content:
        return http_error(400, "Empty file", "EMPTY_FILE")
    if len(content) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    filename = file.filename or "upload"
    detected_bank = bank.upper() if bank.strip() else detect_bank(filename, content)
    file_hash = hashlib.sha256(content).hexdigest()
    batch_id = str(uuid.uuid4())

    rows = _parse_rows(content, filename, detected_bank)
    if not rows:
        return error_response(
            "Could not parse file — use CSV, XLSX, or XML format",
            "PARSE_ERROR",
            f"filename={filename}, bank={detected_bank}",
        )

    inserted, skipped = 0, 0
    skip_reasons: list[str] = []

    async with get_conn() as conn:
        for row in rows:
            date = row.get("date")
            amount = row.get("amount")
            if not date or amount is None:
                skipped += 1
                skip_reasons.append("missing date or amount")
                continue

            # Per-row dedup: (tenant_id, bank, date, amount, transaction_ref)
            txn_ref = row.get("transaction_ref")
            if txn_ref:
                existing = await conn.fetchrow(_q("""
                    SELECT id FROM bank_transactions
                    WHERE tenant_id=%s AND bank=%s AND transaction_ref=%s
                    LIMIT 1
                """), tenant_id, detected_bank, txn_ref)
            else:
                # Fall back to (bank, date, amount, description) dedup
                existing = await conn.fetchrow(_q("""
                    SELECT id FROM bank_transactions
                    WHERE tenant_id=%s AND bank=%s AND date=%s
                      AND ABS(amount - %s) < 0.005
                      AND description=%s
                    LIMIT 1
                """), tenant_id, detected_bank, date, float(amount),
                    row.get("description") or "")

            if existing:
                skipped += 1
                skip_reasons.append("duplicate")
                continue

            txn_id = str(uuid.uuid4())
            raw_payload = json.dumps({**row.pop("_raw", {}), "file_hash": file_hash},
                                     ensure_ascii=False, default=str)

            await conn.execute(_q("""
                INSERT INTO bank_transactions
                    (id, tenant_id, batch_id, bank, date, amount, description,
                     partner, operation_code, transaction_ref,
                     balance, currency, raw, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """),
                txn_id, tenant_id, batch_id, detected_bank,
                date, float(amount),
                row.get("description"),
                row.get("partner"),
                row.get("operation_code"),
                txn_ref,
                row.get("balance"),
                row.get("currency") or "GEL",
                raw_payload,
            )
            inserted += 1

    return ok_response(
        f"Imported {inserted} transaction(s) from {detected_bank}, {skipped} skipped",
        {
            "bank": detected_bank,
            "detected_from": "provided" if bank.strip() else "auto",
            "filename": filename,
            "batch_id": batch_id,
            "parsed": len(rows),
            "inserted": inserted,
            "skipped": skipped,
        },
    )


@router.get("/batches")
async def list_batches(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List import batches with row counts and date ranges."""
    require_permission(request, "bank:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    async with get_conn() as conn:
        rows = await conn.fetch(_q("""
            SELECT batch_id, bank,
                   COUNT(*) AS rows,
                   MIN(date)::text AS from_date,
                   MAX(date)::text AS to_date,
                   SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS total_in,
                   SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS total_out,
                   MIN(created_at) AS imported_at
            FROM bank_transactions
            WHERE tenant_id=%s
            GROUP BY batch_id, bank
            ORDER BY MIN(created_at) DESC
            LIMIT %s OFFSET %s
        """), tenant_id, limit, offset)
        total = await conn.fetchval(
            _q("SELECT COUNT(DISTINCT batch_id) FROM bank_transactions WHERE tenant_id=%s"),
            tenant_id,
        )

    return ok_response("Bank statement batches", {
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "batches": [dict(r) for r in rows],
    })


@router.get("/transactions")
async def list_transactions(
    request: Request,
    bank: str = Query(""),
    partner: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    batch_id: str = Query(""),
):
    """List bank transactions with filters."""
    require_permission(request, "bank:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conditions = ["bt.tenant_id=$1"]
    args: list = [tenant_id]
    i = 2
    if bank:
        conditions.append(f"bt.bank=${i}"); args.append(bank.upper()); i += 1
    if partner:
        conditions.append(f"LOWER(COALESCE(bt.partner,'') || ' ' || COALESCE(bt.description,'')) LIKE ${i}")
        args.append(f"%{partner.lower()}%"); i += 1
    if date_from:
        conditions.append(f"bt.date >= ${i}"); args.append(date_from); i += 1
    if date_to:
        conditions.append(f"bt.date <= ${i}"); args.append(date_to); i += 1
    if batch_id:
        conditions.append(f"bt.batch_id=${i}"); args.append(batch_id); i += 1

    where = " AND ".join(conditions)
    async with get_conn() as conn:
        rows = await conn.fetch(f"""
            SELECT bt.id, bt.bank, bt.date, bt.amount, bt.currency,
                   bt.description, bt.partner, bt.operation_code,
                   bt.transaction_ref, bt.balance, bt.batch_id, bt.created_at,
                   br.id IS NOT NULL AS is_reconciled
            FROM bank_transactions bt
            LEFT JOIN bank_reconciliations br
                ON br.bank_transaction_id::text = bt.id::text
               AND br.tenant_id = bt.tenant_id
            WHERE {where}
            ORDER BY bt.date DESC, bt.created_at DESC
            LIMIT ${i} OFFSET ${i+1}
        """, *args, limit, offset)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM bank_transactions bt WHERE {where}", *args
        )

    return ok_response("Bank transactions", {
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "transactions": [dict(r) for r in rows],
    })
