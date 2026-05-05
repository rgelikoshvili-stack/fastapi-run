import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from datetime import date as _date
from typing import Any, List, Optional

import psycopg2.extras

from app.api.db import get_db, get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event

from app.api.connectors.balance_connector import BalanceConnector
from app.api.connectors.onec_connector import OneCConnector


BLOCKING_POST_STATUSES = {"posted", "simulated_success"}


class OrisConnector:
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id

    def status(self) -> dict:
        return {
            "connected": False,
            "mode": "demo",
            "message": "ORIS connector not implemented yet",
            "tenant_id": self.tenant_id,
        }

    def preview(self, draft: dict) -> dict:
        lines = draft.get("lines", [])
        if not lines:
            return {"valid": False, "errors": ["lines აკლია"], "warnings": []}
        return {"valid": True, "errors": [], "warnings": []}

    def post(self, draft: dict) -> dict:
        return {
            "success": False,
            "erp_id": None,
            "error": "ORIS connector not implemented yet",
        }

    def history(self, tenant_id: str, limit: int = 50) -> list:
        return []


def _normalize_target(target: str) -> str:
    t = (target or "").strip().lower()
    if t == "1c":
        return "onec"
    return t


def _to_decimal(v) -> Decimal:
    """Safely convert any numeric value to Decimal for financial calculations."""
    if isinstance(v, Decimal):
        return v
    if v is None:
        return Decimal("0")
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _sum_debits(lines: List[dict]) -> Decimal:
    return sum((_to_decimal(x.get("debit", 0)) for x in lines), Decimal("0"))


def _sum_credits(lines: List[dict]) -> Decimal:
    return sum((_to_decimal(x.get("credit", 0)) for x in lines), Decimal("0"))


def _derive_amount_from_lines(lines: List[dict]) -> Decimal:
    return max(_sum_debits(lines), _sum_credits(lines))


def _normalize_lines(lines: Any) -> List[dict]:
    result: List[dict] = []

    if not lines:
        return result

    if isinstance(lines, str):
        text = lines.strip()
        if not text:
            return result
        try:
            parsed = json.loads(text)
            return _normalize_lines(parsed)
        except Exception:
            return result

    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, dict):
                result.append(
                    {
                        "account_code": str(line.get("account_code", "")).strip(),
                        "label": line.get("label", ""),
                        "debit": float(_to_decimal(line.get("debit", 0) or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                        "credit": float(_to_decimal(line.get("credit", 0) or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                    }
                )
            elif isinstance(line, (list, tuple)) and len(line) >= 3:
                account_code, debit, credit = line[:3]
                result.append(
                    {
                        "account_code": str(account_code).strip(),
                        "label": "",
                        "debit": float(_to_decimal(debit or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                        "credit": float(_to_decimal(credit or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                    }
                )

    return result


def _validate_lines(lines: List[dict]) -> Optional[str]:
    if not lines:
        return "journal lines აკლია"

    for idx, line in enumerate(lines, start=1):
        if not line.get("account_code"):
            return f"line #{idx}: account_code აკლია"

        debit = _to_decimal(line.get("debit", 0) or 0)
        credit = _to_decimal(line.get("credit", 0) or 0)

        if debit < 0 or credit < 0:
            return f"line #{idx}: debit/credit უარყოფითი ვერ იქნება"

        if debit == 0 and credit == 0:
            return f"line #{idx}: debit ან credit უნდა ჰქონდეს"

        if debit > 0 and credit > 0:
            return f"line #{idx}: ერთ ხაზზე debit და credit ერთად არ შეიძლება"

    debit_total = _sum_debits(lines)
    credit_total = _sum_credits(lines)

    dt = debit_total.quantize(Decimal("0.01"), ROUND_HALF_UP)
    ct = credit_total.quantize(Decimal("0.01"), ROUND_HALF_UP)
    if dt != ct:
        return f"დებეტი და კრედიტი არ ემთხვევა (Dr={dt}, Cr={ct})"

    return None


def _draft_to_posting_payload(draft: dict) -> dict:
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
            from app.api.services.currency_service import get_rate
            rate = _to_decimal(get_rate(currency, "GEL", draft.get("date")))
            amount_gel = (amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
            payload["amount_gel"]    = float(amount_gel)
            payload["exchange_rate"] = float(rate.quantize(Decimal("0.000001"), ROUND_HALF_UP))
        except Exception:
            payload["amount_gel"]    = float(amount)
            payload["exchange_rate"] = 1.0
    else:
        payload["amount_gel"]    = float(amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
        payload["exchange_rate"] = 1.0

    return payload


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


def create_journal_draft(
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

    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO journal_drafts
                    (tenant_id, date, description, partner, amount, currency, status, lines_json, source_document_id)
                    VALUES (
                        %s,
                        COALESCE(%s::date, CURRENT_DATE),
                        %s,
                        %s,
                        %s,
                        %s,
                        'pending_approval',
                        %s::jsonb,
                        %s
                    )
                    RETURNING id, tenant_id, date, description, partner, amount, currency, status, lines_json
                    """,
                    (
                        tenant_id,
                        date,
                        description,
                        partner,
                        amount,
                        currency,
                        json.dumps(lines, ensure_ascii=False),
                        source_document_id,
                    ),
                )
                row = cur.fetchone()

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
                }
    finally:
        conn.close()


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
    payload = _draft_to_posting_payload(draft)
    return ok_response("posting payload ready", payload)


async def mock_posting_service(draft_id: int, tenant_id: str = "default"):
    return await apply_posting_service(draft_id, "mock", tenant_id=tenant_id)


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


async def post_draft_to_balance_service(draft_id: int, tenant_id: str = "default"):
    return await apply_posting_service(draft_id, "balance", tenant_id=tenant_id)


def get_onec_status_service(tenant_id: str = "default"):
    readiness = _get_connector_readiness("onec", tenant_id)
    return ok_response("1c status", readiness)


async def post_draft_to_onec_service(draft_id: int, tenant_id: str = "default"):
    return await apply_posting_service(draft_id, "onec", tenant_id=tenant_id)


def get_oris_status_service(tenant_id: str = "default"):
    readiness = _get_connector_readiness("oris", tenant_id)
    return ok_response("oris status", readiness)


async def post_draft_to_oris_service(draft_id: int, tenant_id: str = "default"):
    return await apply_posting_service(draft_id, "oris", tenant_id=tenant_id)


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
    except Exception:
        pass
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

async def apply_posting_service(draft_id: int, target: str, tenant_id: str = "default", force: bool = False):
    import asyncpg
    target_normalized = _normalize_target(target)

    if target_normalized not in {"mock", "balance", "onec", "oris"}:
        return error_response("unsupported posting target", code="VALIDATION_ERROR")

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
                return error_response(
                    "Draft is being processed by another request",
                    code="DRAFT_LOCKED",
                    details={"draft_id": draft_id},
                )

            if not draft_row:
                await tr.rollback()
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
                        return error_response(
                            "accounting period is locked",
                            code="PERIOD_LOCKED",
                            details={"date": str(entry_date_raw), "tenant_id": tenant_id},
                        )
                except Exception:
                    pass

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
                    except Exception:
                        pass

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
                         status, error_message, entry_hash, source_draft_id)
                        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
                        ON CONFLICT (entry_hash) WHERE entry_hash IS NOT NULL DO NOTHING
                        RETURNING id
                    """),
                    tenant_id, draft_id, target_normalized,
                    json.dumps({}, ensure_ascii=False),
                    json.dumps(readiness, ensure_ascii=False),
                    "config_missing",
                    readiness.get("message", "connector not ready"),
                    None, draft_id,
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
                return error_response(
                    f"{target_normalized} connector not ready",
                    code="CONNECTOR_NOT_READY",
                    details=readiness,
                )

            payload = _draft_to_posting_payload(draft)
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
                     status, error_message, entry_hash, source_draft_id)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
                    ON CONFLICT (entry_hash) WHERE entry_hash IS NOT NULL DO NOTHING
                    RETURNING id
                """),
                tenant_id, draft_id, target_normalized,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(response, ensure_ascii=False),
                post_status, error_message, entry_hash, draft_id,
            )

            if success:
                await conn.execute(
                    _q("UPDATE journal_drafts SET status = 'posted' WHERE id = %s AND tenant_id = %s"),
                    draft_id, tenant_id,
                )
                await tr.commit()
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
        return error_response("Posting failed", "POSTING_ERROR", str(e))