"""app/api/services/rsge_document_service.py — RS.ge document sync service.

Handles:
  - Listing invoices/tax documents from RS.ge
  - Syncing selected documents to local rsge_documents table
  - Creating evidence records from synced documents
  - Creating accounting draft suggestions
  - Deduplication by rsge_id

Security: never returns raw RS.ge auth credentials.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

log = logging.getLogger(__name__)


# ── Internal DTO ─────────────────────────────────────────────────────────────

@dataclass
class RsgeDocumentDTO:
    rsge_id: str
    reg_no: str
    doc_type: str                        # invoice | tax_doc | correction
    seller_inn: str
    seller_name: str
    buyer_inn: str
    buyer_name: str
    doc_date: str
    amount: float
    vat_amount: float
    status: str                          # RS.ge status text
    status_code: str                     # RS.ge status code (0-6)
    direction: str                       # incoming | outgoing | unknown
    currency: str = "GEL"
    lines: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def source_hash(self) -> str:
        key = f"{self.rsge_id}|{self.reg_no}|{self.amount}|{self.status_code}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]


def _map_invoice_to_dto(raw: dict, own_inn: str = "") -> RsgeDocumentDTO:
    """Map RS.ge SOAP get_user_invoices response row → internal DTO."""
    buyer_inn = str(raw.get("BUYER_TIN") or raw.get("buyer_tin") or "")
    seller_inn = str(raw.get("SELLER_TIN") or raw.get("seller_inn") or "")
    direction = "unknown"
    if own_inn:
        if buyer_inn == own_inn:
            direction = "incoming"
        elif seller_inn == own_inn:
            direction = "outgoing"
    return RsgeDocumentDTO(
        rsge_id=str(raw.get("ID") or raw.get("id") or ""),
        reg_no=str(raw.get("INVOICE_NUMBER") or raw.get("invoice_no") or ""),
        doc_type="invoice",
        seller_inn=seller_inn,
        seller_name=str(raw.get("SELLER_NAME") or raw.get("seller_name") or ""),
        buyer_inn=buyer_inn,
        buyer_name=str(raw.get("BUYER_NAME") or raw.get("buyer_name") or ""),
        doc_date=str(raw.get("OPERATION_DATE") or raw.get("operation_date") or ""),
        amount=float(raw.get("TOTAL") or raw.get("total") or 0),
        vat_amount=float(raw.get("VAT") or raw.get("vat") or 0),
        status=str(raw.get("STATUS_TXT") or raw.get("status") or ""),
        status_code=str(raw.get("STATUS") or raw.get("status_code") or ""),
        direction=direction,
        lines=raw.get("lines") or [],
        raw=raw,
    )


# ── Listing ───────────────────────────────────────────────────────────────────

async def list_documents(
    conn,
    tenant_id: str,
    connector,
    own_inn: str = "",
    limit: int = 100,
) -> List[dict]:
    """Fetch invoice list from RS.ge and merge with local sync status.

    Returns list of document dicts ready for API response.
    Never returns raw credentials.
    """
    # Fetch from RS.ge
    raw_list = connector.get_user_invoices(limit=limit)

    # Fetch local sync status for these IDs
    rsge_ids = [str(r.get("id") or r.get("ID") or "") for r in raw_list]
    local_map: dict = {}
    if rsge_ids:
        try:
            from app.api.db import _q
            rows = await conn.fetch(
                _q("SELECT rsge_id, id, evidence_id, draft_id, synced_at "
                   "FROM rsge_documents WHERE tenant_id = %s AND rsge_id = ANY(%s)"),
                tenant_id, rsge_ids,
            )
            local_map = {r["rsge_id"]: dict(r) for r in rows}
        except Exception as exc:
            log.debug("list_documents local fetch skipped: %s", exc)

    results = []
    for raw in raw_list:
        dto = _map_invoice_to_dto(raw, own_inn)
        local = local_map.get(dto.rsge_id, {})
        results.append({
            "id":                dto.rsge_id,
            "reg_no":            dto.reg_no,
            "doc_type":          dto.doc_type,
            "seller_inn":        dto.seller_inn,
            "seller_name":       dto.seller_name,
            "buyer_inn":         dto.buyer_inn,
            "buyer_name":        dto.buyer_name,
            "doc_date":          dto.doc_date,
            "amount":            dto.amount,
            "vat_amount":        dto.vat_amount,
            "currency":          dto.currency,
            "status":            dto.status,
            "status_code":       dto.status_code,
            "direction":         dto.direction,
            "source":            "rs.ge",
            "synced":            bool(local),
            "synced_at":         str(local.get("synced_at") or ""),
            "evidence_id":       local.get("evidence_id"),
            "draft_id":          local.get("draft_id"),
            "local_id":          local.get("id"),
        })
    return results


# ── Sync ─────────────────────────────────────────────────────────────────────

async def sync_selected(
    conn,
    tenant_id: str,
    rsge_ids: List[str],
    connector,
    own_inn: str = "",
    actor: Optional[str] = None,
    job_id: Optional[int] = None,
) -> dict:
    """Download and upsert selected documents into rsge_documents.

    Deduplicates by (tenant_id, rsge_id) — safe to call multiple times.
    Does NOT create evidence or drafts automatically.
    Does NOT post anything.

    Returns sync result summary.
    """
    all_raw = connector.get_user_invoices(limit=500)
    raw_map = {str(r.get("id") or r.get("ID") or ""): r for r in all_raw}

    synced, skipped, errors = [], [], []
    for rid in rsge_ids:
        raw = raw_map.get(rid)
        if raw is None:
            errors.append({"id": rid, "error": "not found in RS.ge"})
            continue
        dto = _map_invoice_to_dto(raw, own_inn)
        try:
            local_id = await _upsert_document(conn, tenant_id, dto, actor)
            synced.append({"rsge_id": rid, "local_id": local_id})
        except Exception as exc:
            log.warning("[RS.GE] sync_selected upsert failed id=%s: %s", rid, exc)
            errors.append({"id": rid, "error": str(exc)[:120]})

    if job_id:
        await _update_sync_job(conn, job_id, len(synced), len(skipped), len(errors))

    return {
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "total_requested": len(rsge_ids),
        "synced_count": len(synced),
        "error_count": len(errors),
    }


async def _upsert_document(conn, tenant_id: str, dto: RsgeDocumentDTO,
                           actor: Optional[str]) -> int:
    from app.api.db import _q
    sql = _q("""
        INSERT INTO rsge_documents
          (tenant_id, rsge_id, reg_no, doc_type, seller_inn, seller_name,
           buyer_inn, buyer_name, doc_date, amount, vat_amount, currency,
           rsge_status, rsge_status_code, direction, source_hash, raw_payload,
           synced_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (tenant_id, rsge_id) DO UPDATE SET
          reg_no = EXCLUDED.reg_no,
          rsge_status = EXCLUDED.rsge_status,
          rsge_status_code = EXCLUDED.rsge_status_code,
          amount = EXCLUDED.amount,
          vat_amount = EXCLUDED.vat_amount,
          source_hash = EXCLUDED.source_hash,
          raw_payload = EXCLUDED.raw_payload,
          synced_at = NOW()
        RETURNING id
    """)
    row = await conn.fetchrow(
        sql,
        tenant_id, dto.rsge_id, dto.reg_no, dto.doc_type,
        dto.seller_inn, dto.seller_name, dto.buyer_inn, dto.buyer_name,
        dto.doc_date or None, dto.amount, dto.vat_amount, dto.currency,
        dto.status, dto.status_code, dto.direction,
        dto.source_hash(), json.dumps(dto.raw),
    )
    return row["id"] if row else 0


# ── Evidence creation ─────────────────────────────────────────────────────────

async def create_evidence_from_document(
    conn,
    tenant_id: str,
    local_doc_id: int,
    actor: Optional[str] = None,
) -> dict:
    """Create an evidence record from a synced RS.ge document.

    Idempotent: if evidence_id already set on the document, returns existing.
    Does NOT post to ledger.
    """
    from app.api.db import _q

    doc_row = await conn.fetchrow(
        _q("SELECT * FROM rsge_documents WHERE id = %s AND tenant_id = %s"),
        local_doc_id, tenant_id,
    )
    if not doc_row:
        raise ValueError(f"rsge_document id={local_doc_id} not found for tenant={tenant_id}")

    doc = dict(doc_row)
    if doc.get("evidence_id"):
        return {"evidence_id": doc["evidence_id"], "created": False, "duplicate": True}

    # Insert into documents table (Bridge Hub evidence)
    ev_sql = _q("""
        INSERT INTO documents
          (tenant_id, document_type, file_name, content_type, source,
           amount, currency, vendor_name, document_date, status, extracted_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """)
    ev_type = "invoice" if doc.get("doc_type") == "invoice" else "tax_document"
    file_name = f"rsge_{doc.get('rsge_id')}_{doc.get('reg_no') or 'doc'}.json"
    extracted = json.dumps({
        "rsge_id": doc.get("rsge_id"),
        "reg_no": doc.get("reg_no"),
        "seller_inn": doc.get("seller_inn"),
        "seller_name": doc.get("seller_name"),
        "buyer_inn": doc.get("buyer_inn"),
        "buyer_name": doc.get("buyer_name"),
        "direction": doc.get("direction"),
        "rsge_status": doc.get("rsge_status"),
        "vat_amount": float(doc.get("vat_amount") or 0),
    })
    ev_row = await conn.fetchrow(
        ev_sql,
        tenant_id, ev_type, file_name, "application/json", "rs.ge",
        float(doc.get("amount") or 0), doc.get("currency") or "GEL",
        doc.get("seller_name") or "",
        doc.get("doc_date"), "verified", extracted,
    )
    if not ev_row:
        raise RuntimeError("Evidence insert returned no row")

    evidence_id = ev_row["id"]
    await conn.execute(
        _q("UPDATE rsge_documents SET evidence_id = %s WHERE id = %s AND tenant_id = %s"),
        evidence_id, local_doc_id, tenant_id,
    )
    log.info("[RS.GE] evidence created id=%s for rsge_doc=%s tenant=%s",
             evidence_id, local_doc_id, tenant_id)
    return {"evidence_id": evidence_id, "created": True, "duplicate": False}


# ── Draft suggestion ──────────────────────────────────────────────────────────

async def create_draft_from_document(
    conn,
    tenant_id: str,
    local_doc_id: int,
    own_inn: str = "",
    actor: Optional[str] = None,
) -> dict:
    """Create a journal draft suggestion from a synced RS.ge document.

    Direction logic:
      buyer_inn == own_inn  → incoming purchase → debit 1310 / credit 3110
      seller_inn == own_inn → outgoing sales    → debit 1210 / credit 6110 + 3310
      unknown               → status=drafted, review required

    Human must approve. No autonomous posting.
    """
    from app.api.db import _q

    doc_row = await conn.fetchrow(
        _q("SELECT * FROM rsge_documents WHERE id = %s AND tenant_id = %s"),
        local_doc_id, tenant_id,
    )
    if not doc_row:
        raise ValueError(f"rsge_document id={local_doc_id} not found")

    doc = dict(doc_row)
    if doc.get("draft_id"):
        return {"draft_id": doc["draft_id"], "created": False, "duplicate": True}

    amount = float(doc.get("amount") or 0)
    vat = float(doc.get("vat_amount") or 0)
    net = round(amount - vat, 4)
    direction = doc.get("direction") or "unknown"

    if own_inn and doc.get("buyer_inn") == own_inn:
        direction = "incoming"
    elif own_inn and doc.get("seller_inn") == own_inn:
        direction = "outgoing"

    if direction == "incoming":
        # Purchase: goods received + VAT credit / AP liability
        description = (f"RS.ge შესყიდვა — {doc.get('seller_name') or doc.get('seller_inn')} | "
                       f"№{doc.get('reg_no') or doc.get('rsge_id')}")
        debit_acc, credit_acc = "1310", "3110"
        draft_type = "purchase"
    elif direction == "outgoing":
        # Sale: AR receivable / revenue + VAT payable
        description = (f"RS.ge გაყიდვა — {doc.get('buyer_name') or doc.get('buyer_inn')} | "
                       f"№{doc.get('reg_no') or doc.get('rsge_id')}")
        debit_acc, credit_acc = "1210", "6110"
        draft_type = "sale"
    else:
        description = (f"RS.ge დოკუმენტი (გადამოწმება საჭიროა) — "
                       f"№{doc.get('reg_no') or doc.get('rsge_id')}")
        debit_acc, credit_acc = "1000", "3000"
        draft_type = "review_required"

    draft_sql = _q("""
        INSERT INTO journal_drafts
          (tenant_id, description, amount, debit_account, credit_account,
           date, status, partner, reason, source, ai_confidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """)
    doc_date = doc.get("doc_date") or date.today().isoformat()
    partner = doc.get("seller_name") if direction == "incoming" else doc.get("buyer_name")

    row = await conn.fetchrow(
        draft_sql,
        tenant_id, description, net,
        debit_acc, credit_acc, doc_date,
        "drafted", partner or "", f"RS.ge {draft_type}", "rs_ge", 0.85,
    )
    if not row:
        raise RuntimeError("Draft insert returned no row")

    draft_id = row["id"]
    await conn.execute(
        _q("UPDATE rsge_documents SET draft_id = %s WHERE id = %s AND tenant_id = %s"),
        draft_id, local_doc_id, tenant_id,
    )
    log.info("[RS.GE] draft created id=%s direction=%s tenant=%s",
             draft_id, direction, tenant_id)
    return {
        "draft_id": draft_id,
        "created": True,
        "direction": direction,
        "draft_type": draft_type,
        "amount": net,
        "vat": vat,
        "debit_account": debit_acc,
        "credit_account": credit_acc,
    }


# ── Sync job helpers ──────────────────────────────────────────────────────────

async def create_sync_job(conn, tenant_id: str, job_type: str, actor: str) -> int:
    from app.api.db import _q
    row = await conn.fetchrow(
        _q("INSERT INTO rsge_sync_jobs (tenant_id, job_type, status, started_by) "
           "VALUES (%s, %s, 'running', %s) RETURNING id"),
        tenant_id, job_type, actor,
    )
    return row["id"] if row else 0


async def _update_sync_job(conn, job_id: int, synced: int, skipped: int, errors: int) -> None:
    try:
        from app.api.db import _q
        await conn.execute(
            _q("UPDATE rsge_sync_jobs SET status='done', synced_count=%s, "
               "skipped_count=%s, doc_count=%s, finished_at=NOW() WHERE id=%s"),
            synced, skipped, synced + skipped + errors, job_id,
        )
    except Exception as exc:
        log.debug("sync job update skipped: %s", exc)
