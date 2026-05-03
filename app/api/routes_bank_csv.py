from fastapi import APIRouter, UploadFile, File, Form, Request
from typing import Optional
import hashlib, uuid, json

from app.api.response_utils import ok_response, error_response
from app.api.bank_statement_parser import parse_csv_bytes, parse_xlsx_bytes, parse_xml_bytes
from app.api.tenant_context import resolve_tenant_id
from app.api.security import limiter
from app.api.db import get_conn, _q

router = APIRouter(prefix="/bank-csv", tags=["bank"])


@router.post("/upload")
@limiter.limit("20/minute")
async def upload_bank_file(
    request: Request,
    file: UploadFile = File(...),
    bank: Optional[str] = Form(default="UNKNOWN")
):
    try:
        tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
        content = await file.read()
        name = (file.filename or "").lower()
        file_hash = hashlib.sha256(content).hexdigest()

        try:
            async with get_conn() as conn:
                existing = await conn.fetchrow(_q("""
                    SELECT batch_id, created_at
                    FROM bank_transactions
                    WHERE tenant_id = %s
                      AND raw::json->>'hash' = %s
                    LIMIT 1
                """), tenant_id, file_hash)
            if existing:
                return ok_response("Duplicate file detected", {
                    "duplicate": True,
                    "tenant_id": tenant_id,
                    "original_batch_id": str(existing["batch_id"]),
                    "message": "ეს ფაილი უკვე ატვირთულია"
                })
        except Exception:
            pass

        if name.endswith(".csv"):
            rows = parse_csv_bytes(content)
        elif name.endswith(".xlsx"):
            rows = parse_xlsx_bytes(content)
        elif name.endswith(".xml"):
            rows = parse_xml_bytes(content)
        else:
            return error_response("Unsupported file format", "BANK_FILE_ERROR", "Use csv, xlsx or xml")

        saved = 0
        batch_id = str(uuid.uuid4())
        try:
            async with get_conn() as conn:
                for row in rows:
                    await conn.execute(_q("""
                        INSERT INTO bank_transactions
                        (id, tenant_id, batch_id, bank, date, amount, description, balance, raw, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """),
                        str(uuid.uuid4()), tenant_id, batch_id, bank,
                        str(row.get("date", ""))[:10],
                        float(row.get("paid_in") or 0) - float(row.get("paid_out") or 0),
                        row.get("description", ""),
                        float(row.get("balance") or 0),
                        json.dumps({**row, "hash": file_hash}, ensure_ascii=False),
                    )
                    saved += 1
        except Exception:
            saved = 0

        return ok_response("Bank statement parsed", {
            "filename": file.filename,
            "bank": bank,
            "tenant_id": tenant_id,
            "file_hash": file_hash,
            "duplicate": False,
            "rows_count": len(rows),
            "saved": saved,
            "batch_id": batch_id,
            "transactions": rows[:5],
        })
    except Exception as e:
        return error_response("Upload failed", "UPLOAD_ERROR", str(e))


@router.get("/history")
async def bank_csv_history(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT
                    batch_id,
                    bank,
                    COUNT(*) as rows,
                    MIN(date) as from_date,
                    MAX(date) as to_date,
                    MIN(created_at) as uploaded_at
                FROM bank_transactions
                WHERE tenant_id = %s
                GROUP BY batch_id, bank
                ORDER BY uploaded_at DESC
                LIMIT 20
            """), tenant_id)]
    except Exception:
        rows = []

    return ok_response("Bank CSV history", {
        "count": len(rows),
        "tenant_id": tenant_id,
        "history": rows
    })
