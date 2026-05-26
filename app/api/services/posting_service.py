import hashlib
import json
import logging
import os
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import date as _date
from typing import Any, List, Optional

from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event
from app.api.observability import structured_log
from app.api.services.posting_helpers import (
    _to_decimal,
    _sum_debits,
    _sum_credits,
    _derive_amount_from_lines,
    _normalize_lines,
    _validate_lines,
)

log = logging.getLogger(__name__)

from app.api.connectors.balance_connector import BalanceConnector
from app.api.connectors.onec_connector import OneCConnector
from app.api.connectors.oris_connector import OrisConnector


BLOCKING_POST_STATUSES = {"posted", "simulated_success"}


def _normalize_target(target: str) -> str:
    t = (target or "").strip().lower()
    if t == "1c":
        return "onec"
    return t




async def _draft_to_posting_payload(draft: dict) -> dict:
    lines = _normalize_lines(
        draft.get("lines_json") if draft.get("lines_json") is not None else draft.get("lines", [])
    )
    currency = (draft.get("currency") or "GEL").upper()
    amount   = _to_decimal(draft.get("amount") or _derive_amount_from_lines(lines))

    payload: dict = {
        "id":          draft.get("id"),
        "tenant_id":   draft.get("tenant_id"),
        "date":        draft.get("date"),
        "description": draft.get("description", ""),
        "partner":     draft.get("partner", ""),
        "amount":      float(amount.quantize(Decimal("0.01"), ROUND_HALF_UP)),
        "currency":    currency,
        "status":      draft.get("status", ""),
        "lines":       lines,
    }

    if currency != "GEL":
        try:
            from app.api.services.currency_service import get_rate_async
            rate = _to_decimal(await get_rate_async(currency, "GEL", draft.get("date")))
            amount_gel = (amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
            payload["amount_gel"]    = float(amount_gel)
            payload["exchange_rate"] = float(rate.quantize(Decimal("0.000001"), ROUND_HALF_UP))
        except Exception as _fx_exc:
            # Currency rate lookup failed — falling back to 1.0 is financially wrong.
            # Log so ops can fix the rate table; the caller should not silently receive
            # a GEL-equivalent that equals the foreign-currency face value.
            log.warning(
                "FX rate lookup failed for %s→GEL (draft date=%s): %s — "
                "falling back to exchange_rate=1.0 which IS INCORRECT. "
                "Populate the currency_rates table to fix this.",
                currency, draft.get("date"), _fx_exc,
            )
            payload["amount_gel"]    = float(amount)
            payload["exchange_rate"] = 1.0
    else:
        payload["amount_gel"]    = float(amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
        payload["exchange_rate"] = 1.0

    return payload


def _lines_to_journal_entries(lines: List[dict]) -> list[dict]:
    entries: list[dict] = []
    for idx, line in enumerate(lines, start=1):
        account_code = str(line.get("account_code", "")).strip()
        debit = _to_decimal(line.get("debit", 0) or 0)
        credit = _to_decimal(line.get("credit", 0) or 0)
        note = str(line.get("label", "") or "").strip()

        if debit > 0:
            entries.append(
                {
                    "line": idx,
                    "dr": account_code,
                    "cr": None,
                    "amount": float(debit.quantize(Decimal("0.01"), ROUND_HALF_UP)),
                    "note": note,
                }
            )
        elif credit > 0:
            entries.append(
                {
                    "line": idx,
                    "dr": None,
                    "cr": account_code,
                    "amount": float(credit.quantize(Decimal("0.01"), ROUND_HALF_UP)),
                    "note": note,
                }
            )

    return entries


def _fetch_draft(cur, draft_id: int, tenant_id: str):
    cur.execute(
        """
        SELECT
            id,
            tenant_id,
            date,
            description,
            COALESCE(partner, '') AS partner,
            COALESCE(amount, 0) AS amount,
            COALESCE(status, '') AS status,
            COALESCE(currency, 'GEL') AS currency,
            COALESCE(lines_json, '[]'::jsonb) AS lines_json
        FROM journal_drafts
        WHERE id = %s
          AND tenant_id = %s
        FOR UPDATE
        """,
        (draft_id, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        return None

    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "date": str(row["date"]) if row["date"] else None,
        "description": row["description"],
        "partner": row["partner"],
        "amount": float(row["amount"] or 0),
        "status": row["status"],
        "currency": row["currency"],
        "lines_json": row["lines_json"],
        "lines": _normalize_lines(row["lines_json"]),
    }


def _validate_approved_draft(draft, draft_id: int, tenant_id: str):
    if not draft:
        return error_response(
            f"journal_drafts id={draft_id} does not exist for tenant {tenant_id}",
            code="NOT_FOUND",
        )

    if draft["status"] != "approved":
        return error_response(
            f"journal_drafts id={draft_id} has status={draft['status']} for tenant {tenant_id}",
            code="DRAFT_NOT_APPROVED",
        )

    line_error = _validate_lines(draft.get("lines", []))
    if line_error:
        return error_response(line_error, code="INVALID_JOURNAL_LINES")

    return None


def _compute_entry_hash(draft_id: int, tenant_id: str, amount: float, date: str, target: str) -> str:
    raw = f"{draft_id}:{tenant_id}:{amount}:{date}:{target}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _insert_posting_log(cur, tenant_id, draft_id, target_system, payload, response, status, error_message, entry_hash=None):
    cur.execute(
        """
        INSERT INTO posting_logs
        (tenant_id, draft_id, target_system, payload_json, response_json, status, error_message, entry_hash, source_draft_id)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
        ON CONFLICT (entry_hash) WHERE entry_hash IS NOT NULL DO NOTHING
        RETURNING id
        """,
        (
            tenant_id,
            draft_id,
            target_system,
            json.dumps(payload, ensure_ascii=False),
            json.dumps(response, ensure_ascii=False),
            status,
            error_message,
            entry_hash,
            draft_id,
        ),
    )
    row = cur.fetchone()
    return row["id"] if row else None


def _find_successful_post(cur, tenant_id: str, draft_id: int, target_system: str):
    cur.execute(
        """
        SELECT id, status, response_json
        FROM posting_logs
        WHERE tenant_id = %s
          AND draft_id = %s
          AND target_system = %s
          AND status = ANY(%s)
        ORDER BY id DESC
        LIMIT 1
        """,
        (tenant_id, draft_id, target_system, list(BLOCKING_POST_STATUSES)),
    )
    return cur.fetchone()


def _get_connector(target_normalized: str, tenant_id: str):
    if target_normalized == "balance":
        return BalanceConnector(tenant_id=tenant_id)
    if target_normalized == "onec":
        return OneCConnector(tenant_id=tenant_id)
    if target_normalized == "oris":
        return OrisConnector(tenant_id=tenant_id)
    return None


def _get_connector_readiness(target_normalized: str, tenant_id: str) -> dict:
    if target_normalized == "mock":
        return {
            "ok": True,
            "status": {"ok": True, "mode": "mock", "tenant_id": tenant_id},
            "message": "mock connector ready",
        }

    connector = _get_connector(target_normalized, tenant_id)
    if connector is None:
        return {
            "ok": False,
            "status": {"ok": False, "tenant_id": tenant_id},
            "message": f"unsupported target: {target_normalized}",
        }

    status = connector.status()
    return {
        "ok": bool(status.get("connected", False)),
        "status": {"tenant_id": tenant_id, **status},
        "message": status.get("message", ""),
    }


def _post_via_connector(target_normalized: str, payload: dict, tenant_id: str) -> dict:
    if target_normalized == "mock":
        return {
            "success": True,
            "erp_id": f"MOCK-{payload.get('id')}",
            "error": None,
            "mode": "mock",
        }

    connector = _get_connector(target_normalized, tenant_id)
    if connector is None:
        return {
            "success": False,
            "erp_id": None,
            "error": f"unsupported target: {target_normalized}",
        }

    return connector.post(payload)


async def create_journal_draft(
    description: str,
    lines: List[dict],
    tenant_id: str = "default",
    partner: str = "",
    date: Optional[str] = None,
    currency: str = "GEL",
    source_document_id: Optional[int] = None,
) -> dict:
    lines = _normalize_lines(lines)
    line_error = _validate_lines(lines)
    if line_error:
        raise ValueError(line_error)

    amount = _derive_amount_from_lines(lines)
    journal_entries = _lines_to_journal_entries(lines)

    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            INSERT INTO journal_drafts
            (tenant_id, date, description, partner, amount, currency, status, lines_json, journal_entries, source_document_id)
            VALUES (
                %s,
                COALESCE(%s::date, CURRENT_DATE),
                %s,
                %s,
                %s,
                %s,
                'pending_approval',
                %s::jsonb,
                %s::jsonb,
                %s
            )
            RETURNING id, tenant_id, date, description, partner, amount, currency, status, lines_json, journal_entries
        """),
            tenant_id,
            date,
            description,
            partner,
            amount,
            currency,
            json.dumps(lines, ensure_ascii=False),
            json.dumps(journal_entries, ensure_ascii=False),
            source_document_id,
        )

        log_event(
            "draft_created",
            {
                "entity_type": "journal_draft",
                "entity_id": row["id"],
                "description": description,
                "amount": amount,
                "currency": currency,
                "lines_count": len(lines),
            },
            tenant_id=tenant_id,
        )

        return {
            "id": row["id"],
            "tenant_id": row["tenant_id"],
            "date": str(row["date"]) if row["date"] else None,
            "description": row["description"],
            "partner": row["partner"],
            "amount": float(row["amount"] or 0),
            "currency": row["currency"],
            "status": row["status"],
            "lines": _normalize_lines(row["lines_json"]),
            "journal_entries": row["journal_entries"],
        }


async def get_approved_drafts_service(limit: int = 100, offset: int = 0, tenant_id: str = "default"):
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        rows = await conn.fetch(_q("""
            SELECT
                id, tenant_id, date, description,
                COALESCE(partner, '') AS partner,
                COALESCE(amount, 0) AS amount,
                COALESCE(currency, 'GEL') AS currency,
                COALESCE(status, '') AS status,
                COALESCE(lines_json, '[]'::jsonb) AS lines_json
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status = 'approved'
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """), tenant_id, limit, offset)
    items = [
        {
            "id": r["id"],
            "tenant_id": r["tenant_id"],
            "date": str(r["date"]) if r["date"] else None,
            "description": r["description"],
            "partner": r["partner"],
            "amount": float(r["amount"] or 0),
            "currency": r["currency"],
            "status": r["status"],
            "lines": _normalize_lines(r["lines_json"]),
        }
        for r in rows
    ]
    return ok_response("approved drafts fetched", items)


async def get_posting_payload_service(draft_id: int, tenant_id: str = "default"):
    async with get_conn() as conn:
        draft_row = await conn.fetchrow(
            _q("""
                SELECT id, tenant_id, date, description,
                    COALESCE(partner, '') AS partner,
                    COALESCE(amount, 0) AS amount,
                    COALESCE(status, '') AS status,
                    COALESCE(currency, 'GEL') AS currency,
                    COALESCE(lines_json, '[]'::jsonb) AS lines_json
                FROM journal_drafts
                WHERE id = %s AND tenant_id = %s
            """),
            draft_id, tenant_id,
        )
    if not draft_row:
        return error_response(
            f"journal_drafts id={draft_id} does not exist for tenant {tenant_id}",
            code="NOT_FOUND",
        )
    draft = {
        "id": draft_row["id"],
        "tenant_id": draft_row["tenant_id"],
        "date": str(draft_row["date"]) if draft_row["date"] else None,
        "description": draft_row["description"],
        "partner": draft_row["partner"],
        "amount": float(draft_row["amount"] or 0),
        "status": draft_row["status"],
        "currency": draft_row["currency"],
        "lines_json": draft_row["lines_json"],
        "lines": _normalize_lines(draft_row["lines_json"]),
    }
    err = _validate_approved_draft(draft, draft_id, tenant_id)
    if err:
        return err
    payload = await _draft_to_posting_payload(draft)
    return ok_response("posting payload ready", payload)


async def mock_posting_service(draft_id: int, tenant_id: str = "default", actor: Optional[str] = None):
    return await apply_posting_service(draft_id, "mock", tenant_id=tenant_id, actor=actor)


async def get_posting_logs_service(
    limit: int = 100,
    offset: int = 0,
    tenant_id: str = "default",
    target_system: Optional[str] = None,
    draft_id: Optional[int] = None,
):
    from app.api.db import get_conn, _q
    conditions = ["tenant_id = %s"]
    params: List[Any] = [tenant_id]
    if target_system:
        conditions.append("target_system = %s")
        params.append(_normalize_target(target_system))
    if draft_id is not None:
        conditions.append("draft_id = %s")
        params.append(draft_id)
    params.extend([limit, offset])
    where = " AND ".join(conditions)
    sql = _q(f"""
        SELECT id, tenant_id, draft_id, target_system, status, error_message, created_at
        FROM posting_logs
        WHERE {where}
        ORDER BY id DESC LIMIT %s OFFSET %s
    """)
    async with get_conn() as conn:
        rows = await conn.fetch(sql, *params)
    return ok_response("posting logs fetched", [dict(r) for r in rows])


async def get_posting_log_detail_service(log_id: int, tenant_id: str = "default"):
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "SELECT * FROM posting_logs WHERE id = %s AND tenant_id = %s"
        ), log_id, tenant_id)
    if not row:
        return error_response("posting log not found", code="NOT_FOUND")
    return ok_response("posting log fetched", dict(row))


def get_balance_status_service(tenant_id: str = "default"):
    readiness = _get_connector_readiness("balance", tenant_id)
    return ok_response("balance status", readiness)


async def post_draft_to_balance_service(draft_id: int, tenant_id: str = "default", actor: Optional[str] = None):
    return await apply_posting_service(draft_id, "balance", tenant_id=tenant_id, actor=actor)


def get_onec_status_service(tenant_id: str = "default"):
    readiness = _get_connector_readiness("onec", tenant_id)
    return ok_response("1c status", readiness)


async def post_draft_to_onec_service(draft_id: int, tenant_id: str = "default", actor: Optional[str] = None):
    return await apply_posting_service(draft_id, "onec", tenant_id=tenant_id, actor=actor)


def get_oris_status_service(tenant_id: str = "default"):
    readiness = _get_connector_readiness("oris", tenant_id)
    return ok_response("oris status", readiness)


async def post_draft_to_oris_service(draft_id: int, tenant_id: str = "default", actor: Optional[str] = None):
    return await apply_posting_service(draft_id, "oris", tenant_id=tenant_id, actor=actor)


def _check_duplicate_invoice(cur, draft: dict, tenant_id: str) -> Optional[dict]:
    """Return a duplicate warning dict if a similar posted draft exists (same partner+amount±1GEL, ±3 days)."""
    partner = (draft.get("partner") or "").strip()
    amount = float(draft.get("amount") or 0)
    date_str = draft.get("date")
    if not partner or not amount or not date_str:
        return None
    try:
        cur.execute(
            """
            SELECT id, date, description, amount, partner
            FROM journal_drafts
            WHERE tenant_id = %s
              AND id <> %s
              AND LOWER(TRIM(COALESCE(partner, ''))) = LOWER(TRIM(%s))
              AND ABS(COALESCE(amount, 0) - %s) < 1.0
              AND status IN ('approved', 'posted', 'simulated_success')
              AND date IS NOT NULL
              AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
              AND ABS(date::date - %s::date) <= 3
            ORDER BY id DESC
            LIMIT 1
            """,
            (tenant_id, draft["id"], partner, amount, date_str),
        )
        row = cur.fetchone()
        if row:
            return {
                "id": row["id"],
                "date": str(row["date"]),
                "description": row["description"],
                "amount": float(row["amount"] or 0),
                "partner": row["partner"],
            }
    except Exception as _dup_sync_exc:
        log.warning("_check_duplicate_invoice (sync) failed for draft %s: %s — check skipped",
                    draft.get("id"), _dup_sync_exc)
    return None



def _is_period_locked_sync(cur, tenant_id: str, entry_date) -> bool:
    if not entry_date:
        return False
    if isinstance(entry_date, _date):
        d = entry_date
    else:
        d = _date.fromisoformat(str(entry_date)[:10])
    cur.execute(
        """
        SELECT 1 FROM period_locks
        WHERE tenant_id = %s
          AND unlocked_at IS NULL
          AND period_year = %s
          AND (period_month = 0 OR period_month = %s)
        LIMIT 1
        """,
        (tenant_id, d.year, d.month),
    )
    return cur.fetchone() is not None

def _ledger_writes_enabled() -> bool:
    return os.getenv("POSTED_LEDGER_WRITES_ENABLED", "false").lower() == "true"


async def _write_ledger_entries(
    conn,
    draft: dict,
    payload: dict,
    tenant_id: str,
    target: str,
    entry_hash: str,
) -> None:
    """Write header + lines + source to posted ledger tables.

    Runs inside the caller's transaction (separate from the main posting tx).
    Tables created by migration 011; only reached when POSTED_LEDGER_WRITES_ENABLED=true.
    """
    # REQ-5: idempotent pre-check — skip if source already written for this draft
    draft_id_str = str(draft.get("id", ""))
    if draft_id_str:
        existing = await conn.fetchval(_q("""
            SELECT id FROM journal_entry_sources
            WHERE tenant_id = %s AND source_type = 'journal_draft' AND source_id = %s
            LIMIT 1
        """), tenant_id, draft_id_str)
        if existing is not None:
            log_event("ledger_write_skipped", {
                "entity_type": "journal_draft",
                "entity_id": draft.get("id"),
                "target": target,
                "existing_source_id": str(existing),
            }, tenant_id=tenant_id)
            return

    lines = draft.get("lines", [])
    total_debit  = sum(_to_decimal(ln.get("debit",  0) or 0) for ln in lines)
    total_credit = sum(_to_decimal(ln.get("credit", 0) or 0) for ln in lines)

    entry_date_str = (draft.get("date") or "")[:10] or None
    period = entry_date_str[:7] if entry_date_str and len(entry_date_str) >= 7 else "1970-01"
    # asyncpg requires a datetime.date object for date columns
    entry_date_val = _date.fromisoformat(entry_date_str) if entry_date_str else None

    # posting_log_id linkage: schema column is UUID; accept string or uuid.UUID from payload
    posting_log_id: Optional[uuid.UUID] = None
    _pl_raw = payload.get("posting_log_id")
    if _pl_raw:
        try:
            posting_log_id = uuid.UUID(str(_pl_raw))
        except (ValueError, AttributeError):
            pass

    exchange_rate = Decimal(str(payload.get("exchange_rate", 1) or 1))
    currency = (draft.get("currency") or "GEL").upper()

    header_id = await conn.fetchval(_q("""
        INSERT INTO journal_entry_headers (
            tenant_id, entry_date, period, status, source_type, source_hash,
            currency, exchange_rate, total_debit, total_credit, metadata_json, posting_log_id
        ) VALUES (
            %s, %s, %s, 'posted', 'journal_draft', %s, %s, %s, %s, %s, %s::jsonb, %s
        )
        RETURNING id
    """),
        tenant_id,
        entry_date_val,
        period,
        entry_hash,
        currency,
        float(exchange_rate.quantize(Decimal("0.00000001"), ROUND_HALF_UP)),
        float(total_debit.quantize(Decimal("0.01"), ROUND_HALF_UP)),
        float(total_credit.quantize(Decimal("0.01"), ROUND_HALF_UP)),
        json.dumps({"target_system": target, "source_hash": entry_hash}, ensure_ascii=False),
        posting_log_id,
    )

    for idx, line in enumerate(lines, start=1):
        account_code = str(line.get("account_code", "") or "").strip()
        if not account_code:
            continue
        debit  = _to_decimal(line.get("debit",  0) or 0)
        credit = _to_decimal(line.get("credit", 0) or 0)
        amount = debit if debit > 0 else credit
        amount_gel = (amount * exchange_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        await conn.execute(_q("""
            INSERT INTO journal_entry_lines (
                tenant_id, journal_entry_id, line_no, account_code,
                debit, credit, currency, exchange_rate, amount_gel, description
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """),
            tenant_id, header_id, idx, account_code,
            float(debit.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            float(credit.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            currency,
            float(exchange_rate.quantize(Decimal("0.00000001"), ROUND_HALF_UP)),
            float(amount_gel),
            str(line.get("label", "") or draft.get("description", "") or ""),
        )

    # Source row 1: journal_draft (always present — drives idempotency pre-check)
    await conn.execute(_q("""
        INSERT INTO journal_entry_sources (
            tenant_id, journal_entry_id, source_type, source_id
        ) VALUES (%s, %s, 'journal_draft', %s)
    """),
        tenant_id, header_id, str(draft.get("id", "")),
    )

    # Source row 2: posting_log (written when the ERP connector provides a log id)
    if posting_log_id is not None:
        await conn.execute(_q("""
            INSERT INTO journal_entry_sources (
                tenant_id, journal_entry_id, source_type, source_id
            ) VALUES (%s, %s, 'posting_log', %s)
        """),
            tenant_id, header_id, str(posting_log_id),
        )


async def get_ledger_recovery_candidates(tenant_id: str) -> list[dict]:
    """REQ-2: Return posted drafts with no corresponding journal_entry_sources row."""
    sql = _q("""
        SELECT jd.id, jd.date, jd.description, jd.amount
        FROM journal_drafts jd
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
          AND NOT EXISTS (
              SELECT 1 FROM journal_entry_sources jes
              WHERE jes.tenant_id = %s
                AND jes.source_type = 'journal_draft'
                AND jes.source_id = jd.id::text
          )
        ORDER BY jd.id
        LIMIT 500
    """)
    async with get_conn() as conn:
        rows = await conn.fetch(sql, tenant_id, tenant_id)
    return [
        {
            "id": r["id"],
            "date": str(r["date"] or ""),
            "description": r["description"],
            "amount": float(r["amount"] or 0),
        }
        for r in rows
    ]


async def retry_ledger_write(draft_id: int, tenant_id: str) -> dict:
    """REQ-3 + REQ-4: Idempotent retry of a failed ledger write. Emits ledger_write_recovered on success."""
    async with get_conn() as conn:
        draft_row = await conn.fetchrow(_q("""
            SELECT id, tenant_id, date, description,
                   COALESCE(currency, 'GEL') AS currency,
                   COALESCE(lines_json, '[]'::jsonb) AS lines_json
            FROM journal_drafts
            WHERE id = %s AND tenant_id = %s AND status = 'posted'
        """), draft_id, tenant_id)

        if not draft_row:
            return {"ok": False, "error": "draft not found or not posted"}

        draft = {
            "id": draft_row["id"],
            "date": str(draft_row["date"] or ""),
            "description": draft_row["description"],
            "currency": draft_row["currency"],
            "lines": _normalize_lines(draft_row["lines_json"]),
        }
        payload: dict = {}
        entry_hash = hashlib.sha256(
            json.dumps({"id": draft_id, "tenant_id": tenant_id}, sort_keys=True).encode()
        ).hexdigest()

        try:
            async with conn.transaction():
                await _write_ledger_entries(conn, draft, payload, tenant_id, "recovery", entry_hash)
            log_event("ledger_write_recovered", {
                "entity_type": "journal_draft",
                "entity_id": draft_id,
                "target": "recovery",
            }, tenant_id=tenant_id)
            return {"ok": True, "draft_id": draft_id}
        except Exception as exc:
            log.error("ledger_retry_failed draft_id=%s tenant=%s error=%s", draft_id, tenant_id, exc)
            return {"ok": False, "error": str(exc)}


async def apply_posting_service(draft_id: int, target: str, tenant_id: str = "default", force: bool = False, actor: Optional[str] = None):
    import asyncpg
    target_normalized = _normalize_target(target)

    if target_normalized not in {"mock", "balance", "onec", "oris"}:
        return error_response("unsupported posting target", code="VALIDATION_ERROR")

    structured_log(
        log,
        logging.INFO,
        "posting_attempt_started",
        draft_id=draft_id,
        tenant_id=tenant_id,
        target=target_normalized,
        result="started",
    )

    try:
        async with get_conn() as conn:
            tr = conn.transaction()
            await tr.start()
            try:
                draft_row = await conn.fetchrow(
                    _q("""
                        SELECT id, tenant_id, date, description,
                            COALESCE(partner, '') AS partner,
                            COALESCE(amount, 0) AS amount,
                            COALESCE(status, '') AS status,
                            COALESCE(currency, 'GEL') AS currency,
                            COALESCE(lines_json, '[]'::jsonb) AS lines_json
                        FROM journal_drafts
                        WHERE id = %s AND tenant_id = %s
                        FOR UPDATE NOWAIT
                    """),
                    draft_id, tenant_id,
                )
            except asyncpg.exceptions.LockNotAvailableError:
                await tr.rollback()
                structured_log(
                    log,
                    logging.WARNING,
                    "posting_attempt_failed",
                    draft_id=draft_id,
                    tenant_id=tenant_id,
                    target=target_normalized,
                    result="error",
                    error_code="DRAFT_LOCKED",
                )
                return error_response(
                    "Draft is being processed by another request",
                    code="DRAFT_LOCKED",
                    details={"draft_id": draft_id},
                )

            if not draft_row:
                await tr.rollback()
                structured_log(
                    log,
                    logging.WARNING,
                    "posting_attempt_failed",
                    draft_id=draft_id,
                    tenant_id=tenant_id,
                    target=target_normalized,
                    result="error",
                    error_code="NOT_FOUND",
                )
                return error_response(
                    f"journal_drafts id={draft_id} does not exist for tenant {tenant_id}",
                    code="NOT_FOUND",
                )

            draft = {
                "id": draft_row["id"],
                "tenant_id": draft_row["tenant_id"],
                "date": str(draft_row["date"]) if draft_row["date"] else None,
                "description": draft_row["description"],
                "partner": draft_row["partner"],
                "amount": float(draft_row["amount"] or 0),
                "status": draft_row["status"],
                "currency": draft_row["currency"],
                "lines_json": draft_row["lines_json"],
                "lines": _normalize_lines(draft_row["lines_json"]),
            }

            err = _validate_approved_draft(draft, draft_id, tenant_id)
            if err:
                await tr.rollback()
                return err

            # period lock check
            entry_date_raw = draft.get("date")
            if entry_date_raw:
                try:
                    d = _date.fromisoformat(str(entry_date_raw)[:10])
                    lock_val = await conn.fetchval(
                        _q("""
                            SELECT 1 FROM period_locks
                            WHERE tenant_id = %s
                              AND unlocked_at IS NULL
                              AND period_year = %s
                              AND (period_month = 0 OR period_month = %s)
                            LIMIT 1
                        """),
                        tenant_id, d.year, d.month,
                    )
                    if lock_val is not None:
                        await tr.rollback()
                        structured_log(
                            log,
                            logging.WARNING,
                            "posting_attempt_failed",
                            draft_id=draft_id,
                            tenant_id=tenant_id,
                            target=target_normalized,
                            result="error",
                            error_code="PERIOD_LOCKED",
                        )
                        return error_response(
                            "accounting period is locked",
                            code="PERIOD_LOCKED",
                            details={"date": str(entry_date_raw), "tenant_id": tenant_id},
                        )
                except Exception as _pl_exc:
                    # Period-lock query failed unexpectedly; log and continue so a
                    # broken lock-check does not block all postings.  Operator must
                    # investigate — a silent pass here could permit posting to a
                    # locked period without anyone knowing.
                    log.warning(
                        "period_lock query raised an unexpected exception for draft %s "
                        "(posting proceeding — investigate period_lock table): %s",
                        draft.get("id"), _pl_exc,
                    )

            # duplicate invoice check
            if not force:
                partner = (draft.get("partner") or "").strip()
                amount_val = float(draft.get("amount") or 0)
                date_str = draft.get("date")
                if partner and amount_val and date_str:
                    try:
                        dup_row = await conn.fetchrow(
                            _q("""
                                SELECT id, date, description, amount, partner
                                FROM journal_drafts
                                WHERE tenant_id = %s
                                  AND id <> %s
                                  AND LOWER(TRIM(COALESCE(partner, ''))) = LOWER(TRIM(%s))
                                  AND ABS(COALESCE(amount, 0) - %s) < 1.0
                                  AND status IN ('approved', 'posted', 'simulated_success')
                                  AND date IS NOT NULL
                                  AND date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                                  AND ABS(date::date - %s::date) <= 3
                                ORDER BY id DESC
                                LIMIT 1
                            """),
                            tenant_id, draft["id"], partner, amount_val, date_str,
                        )
                        if dup_row:
                            await tr.rollback()
                            dup = {
                                "id": dup_row["id"],
                                "date": str(dup_row["date"]),
                                "description": dup_row["description"],
                                "amount": float(dup_row["amount"] or 0),
                                "partner": dup_row["partner"],
                            }
                            return error_response(
                                f"სავარაუდო დუბლიკატი: draft #{dup['id']} ({dup['partner']}, {dup['amount']}, {dup['date']})",
                                code="DUPLICATE_INVOICE_WARNING",
                                details={"duplicate_draft": dup, "hint": "force=true-ით გაიმეორე თუ განზრახ გინდა"},
                            )
                    except Exception as _dup_exc:
                        # Duplicate-check query failed — skip the guard but log so it
                        # does not silently vanish. A broken dup-check is not a posting
                        # blocker but the operator should know the guard was skipped.
                        log.warning(
                            "Duplicate-invoice check raised an unexpected exception "
                            "for draft %s (check skipped — posting will proceed): %s",
                            draft_id, _dup_exc,
                        )

            # block re-posting
            existing = await conn.fetchrow(
                _q("""
                    SELECT id, status, response_json
                    FROM posting_logs
                    WHERE tenant_id = %s
                      AND draft_id = %s
                      AND target_system = %s
                      AND status IN ('posted', 'simulated_success')
                    ORDER BY id DESC
                    LIMIT 1
                """),
                tenant_id, draft_id, target_normalized,
            )
            if existing:
                await tr.rollback()
                structured_log(
                    log,
                    logging.INFO,
                    "posting_attempt_completed",
                    draft_id=draft_id,
                    tenant_id=tenant_id,
                    target=target_normalized,
                    result="error",
                    error_code="POSTING_DUPLICATE_BLOCKED",
                )
                return error_response(
                    f"draft {draft_id} already posted to {target_normalized}",
                    code="POSTING_DUPLICATE_BLOCKED",
                    details={"existing_log_id": existing["id"], "status": existing["status"]},
                )

            readiness = _get_connector_readiness(target_normalized, tenant_id)
            if target_normalized != "mock" and not readiness["ok"]:
                log_id = await conn.fetchval(
                    _q("""
                        INSERT INTO posting_logs
                        (tenant_id, draft_id, target_system, payload_json, response_json,
                         status, error_message, entry_hash, source_draft_id,
                         mode, actor, connector)
                        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (entry_hash) WHERE entry_hash IS NOT NULL DO NOTHING
                        RETURNING id
                    """),
                    tenant_id, draft_id, target_normalized,
                    json.dumps({}, ensure_ascii=False),
                    json.dumps(readiness, ensure_ascii=False),
                    "config_missing",
                    readiness.get("message", "connector not ready"),
                    None, draft_id,
                    "live", actor, target_normalized,
                )
                await tr.commit()
                log_event(
                    "connector_not_ready",
                    {
                        "entity_type": "journal_draft",
                        "entity_id": draft_id,
                        "target": target_normalized,
                        "log_id": log_id,
                        "status": readiness,
                    },
                    tenant_id=tenant_id,
                )
                structured_log(
                    log,
                    logging.INFO,
                    "posting_attempt_completed",
                    draft_id=draft_id,
                    tenant_id=tenant_id,
                    target=target_normalized,
                    result="error",
                    error_code="CONNECTOR_NOT_READY",
                )
                return error_response(
                    f"{target_normalized} connector not ready",
                    code="CONNECTOR_NOT_READY",
                    details=readiness,
                )

            payload = await _draft_to_posting_payload(draft)
            entry_hash = _compute_entry_hash(
                draft_id, tenant_id,
                draft.get("amount", 0),
                draft.get("date", ""),
                target_normalized,
            )

            log_event(
                "posting_attempt_started",
                {
                    "entity_type": "journal_draft",
                    "entity_id": draft_id,
                    "target": target_normalized,
                    "payload": payload,
                },
                tenant_id=tenant_id,
            )

            response = _post_via_connector(target_normalized, payload, tenant_id)

            success = bool(response.get("success", False))
            post_status = (
                "simulated_success"
                if target_normalized == "mock" and success
                else ("posted" if success else "failed")
            )
            error_message = response.get("error")

            log_id = await conn.fetchval(
                _q("""
                    INSERT INTO posting_logs
                    (tenant_id, draft_id, target_system, payload_json, response_json,
                     status, error_message, entry_hash, source_draft_id,
                     mode, actor, connector)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entry_hash) WHERE entry_hash IS NOT NULL DO NOTHING
                    RETURNING id
                """),
                tenant_id, draft_id, target_normalized,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(response, ensure_ascii=False),
                post_status, error_message, entry_hash, draft_id,
                "live", actor, target_normalized,
            )

            if success:
                await conn.execute(
                    _q("UPDATE journal_drafts SET status = 'posted' WHERE id = %s AND tenant_id = %s"),
                    draft_id, tenant_id,
                )
                await tr.commit()

                # H70 — write to posted ledger tables (gated by POSTED_LEDGER_WRITES_ENABLED)
                if _ledger_writes_enabled():
                    try:
                        async with conn.transaction():
                            await _write_ledger_entries(
                                conn, draft, payload, tenant_id, target_normalized, entry_hash
                            )
                    except Exception as _ledger_exc:
                        log_event("ledger_write_failed", {
                            "entity_type": "journal_draft",
                            "entity_id": draft_id,
                            "target": target_normalized,
                            "error": str(_ledger_exc),
                        }, tenant_id=tenant_id)
                        log.error(
                            "action=ledger_write_failed draft_id=%s tenant=%s target=%s error=%s",
                            draft_id, tenant_id, target_normalized, _ledger_exc,
                        )

                log_event(
                    "posting_attempt_finished",
                    {
                        "entity_type": "journal_draft",
                        "entity_id": draft_id,
                        "target": target_normalized,
                        "log_id": log_id,
                        "response": response,
                    },
                    tenant_id=tenant_id,
                )
                structured_log(
                    log,
                    logging.INFO,
                    "posting_attempt_completed",
                    draft_id=draft_id,
                    tenant_id=tenant_id,
                    target=target_normalized,
                    result="success",
                    error_code=None,
                )
                return ok_response(
                    f"draft {draft_id} posted to {target_normalized}",
                    {
                        "draft_id": draft_id,
                        "target": target_normalized,
                        "log_id": log_id,
                        "response": response,
                        "payload": payload,
                    },
                )

            await tr.commit()
            log_event(
                "posting_attempt_failed",
                {
                    "entity_type": "journal_draft",
                    "entity_id": draft_id,
                    "target": target_normalized,
                    "log_id": log_id,
                    "response": response,
                },
                tenant_id=tenant_id,
            )
            structured_log(
                log,
                logging.WARNING,
                "posting_attempt_completed",
                draft_id=draft_id,
                tenant_id=tenant_id,
                target=target_normalized,
                result="error",
                error_code="POSTING_FAILED",
            )
            return error_response(
                f"posting to {target_normalized} failed",
                code="POSTING_FAILED",
                details={
                    "draft_id": draft_id,
                    "target": target_normalized,
                    "log_id": log_id,
                    "response": response,
                },
            )
    except Exception as e:
        structured_log(
            log,
            logging.ERROR,
            "posting_attempt_failed",
            draft_id=draft_id,
            tenant_id=tenant_id,
            target=target_normalized,
            result="error",
            error_code="POSTING_ERROR",
            error=str(e),
        )
        return error_response("Posting failed", "POSTING_ERROR", str(e))


async def dry_run_posting_service(
    draft_id: int,
    target: str = "balance",
    tenant_id: str = "default",
    actor: Optional[str] = None,
) -> dict:
    """Build the Balance.ge posting payload and log it — no ERP call is made.

    Gate 6 (Dry-run mode): this is the only path that must be tested before
    any live Balance.ge execution. Returns the exact payload that would be sent
    and writes a posting_log row with mode='dry_run' and status='dry_run'.
    Draft status is NOT changed. Ledger tables are NOT written.
    """
    target_normalized = _normalize_target(target)

    async with get_conn() as conn:
        draft_row = await conn.fetchrow(_q("""
            SELECT id, tenant_id, date, description,
                   COALESCE(partner, '') AS partner,
                   COALESCE(amount, 0) AS amount,
                   COALESCE(status, '') AS status,
                   COALESCE(currency, 'GEL') AS currency,
                   COALESCE(lines_json, '[]'::jsonb) AS lines_json
            FROM journal_drafts
            WHERE id = %s AND tenant_id = %s
        """), draft_id, tenant_id)

        if not draft_row:
            return error_response(
                f"journal_drafts id={draft_id} does not exist for tenant {tenant_id}",
                code="NOT_FOUND",
            )

        if draft_row["status"] not in ("approved", "pending_approval", "drafted"):
            return error_response(
                f"dry-run requires draft status approved/pending_approval/drafted, got {draft_row['status']}",
                code="DRAFT_NOT_APPROVABLE",
            )

        draft = {
            "id": draft_row["id"],
            "tenant_id": draft_row["tenant_id"],
            "date": str(draft_row["date"]) if draft_row["date"] else None,
            "description": draft_row["description"],
            "partner": draft_row["partner"],
            "amount": float(draft_row["amount"] or 0),
            "status": draft_row["status"],
            "currency": draft_row["currency"],
            "lines_json": draft_row["lines_json"],
            "lines": _normalize_lines(draft_row["lines_json"]),
        }

        line_error = _validate_lines(draft.get("lines", []))
        if line_error:
            return error_response(line_error, code="INVALID_JOURNAL_LINES")

        payload = await _draft_to_posting_payload(draft)
        entry_hash = _compute_entry_hash(
            draft_id, tenant_id,
            draft.get("amount", 0),
            draft.get("date", ""),
            f"dry_run_{target_normalized}",
        )

        dry_run_response = {
            "success": True,
            "mode": "dry_run",
            "connector": target_normalized,
            "message": "Dry-run complete — no ERP entry created",
            "would_post_to": f"{target_normalized} connector",
        }

        log_id = await conn.fetchval(_q("""
            INSERT INTO posting_logs
            (tenant_id, draft_id, target_system, payload_json, response_json,
             status, error_message, entry_hash, source_draft_id, mode, actor, connector)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, NULL, %s, %s, %s, %s, %s)
            ON CONFLICT (entry_hash) WHERE entry_hash IS NOT NULL DO NOTHING
            RETURNING id
        """),
            tenant_id, draft_id, target_normalized,
            json.dumps(payload, ensure_ascii=False),
            json.dumps(dry_run_response, ensure_ascii=False),
            "dry_run",
            entry_hash, draft_id,
            "dry_run", actor, target_normalized,
        )

        # Evidence bundle — best-effort, payload hash only (never raw payload)
        if log_id:
            try:
                from app.api.services.evidence_bundle_service import EvidenceBundleService
                from app.api.services.evidence_bundle_repository import EvidenceBundleRepository
                _payload_hash = hashlib.sha256(
                    json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()[:32]
                _repo = EvidenceBundleRepository(conn)
                _svc = EvidenceBundleService(_repo)
                _bundle = await _svc.create_bundle(
                    tenant_id=tenant_id,
                    source_type="journal_draft",
                    source_id=str(draft_id),
                    actor=actor,
                    metadata={"mode": "dry_run", "target": target_normalized},
                )
                await _svc.link_posting(
                    bundle_id=str(_bundle["id"]),
                    tenant_id=tenant_id,
                    posting_log_id=str(log_id),
                    payload_preview_hash=_payload_hash,
                    connector_provider=target_normalized,
                    connector_operation="dry_run",
                    actor=actor,
                )
            except Exception as _eb_exc:
                log.warning("evidence_bundle dry_run link skipped: %s", _eb_exc)

    log.info(
        "action=dry_run_ok draft_id=%s tenant=%s target=%s log_id=%s",
        draft_id, tenant_id, target_normalized, log_id,
    )
    log_event(
        "posting_dry_run",
        {
            "entity_type": "journal_draft",
            "entity_id": draft_id,
            "target": target_normalized,
            "log_id": log_id,
            "payload_amount": payload.get("amount"),
            "payload_currency": payload.get("currency"),
        },
        tenant_id=tenant_id,
    )

    return ok_response(
        f"dry-run complete — no ERP entry created for draft {draft_id}",
        {
            "draft_id": draft_id,
            "target": target_normalized,
            "mode": "dry_run",
            "log_id": log_id,
            "payload": payload,
            "would_post_to": f"{target_normalized} connector",
        },
    )
