"""Outgoing invoice service — create drafts, auto-save, finalize."""
import json
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

log = logging.getLogger(__name__)

_VAT_RATE = Decimal("0.18")


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        return Decimal("0.00")


def _next_invoice_number(conn, tenant_id: str) -> str:
    year = datetime.now().year
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO invoice_counters (tenant_id, year, counter)
        VALUES (%s, %s, 1)
        ON CONFLICT (tenant_id, year)
        DO UPDATE SET counter = invoice_counters.counter + 1
        RETURNING counter
        """,
        (tenant_id, year),
    )
    counter = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return f"INV-{year}-{counter:03d}"


def _calc_totals(line_items: list) -> dict:
    subtotal = Decimal("0.00")
    for item in line_items:
        qty = _dec(item.get("qty") or item.get("quantity") or 1)
        price = _dec(item.get("unit_price") or item.get("price") or item.get("amount") or 0)
        subtotal += qty * price
    vat = (subtotal * _VAT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = subtotal + vat
    return {
        "subtotal": float(subtotal),
        "vat_amount": float(vat),
        "total_amount": float(total),
    }


def _ensure_outgoing_columns(conn) -> None:
    """Idempotent: add new columns to outgoing_invoices if they don't exist yet."""
    cur = conn.cursor()
    try:
        cur.execute("""
            ALTER TABLE outgoing_invoices
              ADD COLUMN IF NOT EXISTS due_date       DATE,
              ADD COLUMN IF NOT EXISTS currency       TEXT DEFAULT 'GEL',
              ADD COLUMN IF NOT EXISTS exchange_rate  NUMERIC(18,6),
              ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP
        """)
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()


def create_draft(conn, tenant_id: str, data: dict) -> dict:
    """Insert a new outgoing invoice draft. Returns the created row."""
    _ensure_outgoing_columns(conn)
    invoice_type = data.get("invoice_type", "service")
    if invoice_type not in ("goods", "service"):
        raise ValueError("invoice_type must be 'goods' or 'service'")

    line_items = data.get("line_items") or []
    totals = _calc_totals(line_items)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO outgoing_invoices
            (tenant_id, invoice_type, status,
             seller_name, seller_inn, seller_address, seller_phone,
             seller_bank, seller_swift, seller_account,
             buyer_inn, buyer_name, buyer_email, buyer_address, buyer_phone,
             invoice_date, delivery_date, due_date,
             transport_from, transport_to, vehicle_number, driver_name,
             line_items, subtotal, vat_amount, total_amount, comment,
             currency, exchange_rate,
             created_by)
        VALUES (%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id, invoice_type, status, buyer_inn, buyer_name,
                  subtotal, vat_amount, total_amount, comment, currency, exchange_rate, created_at
        """,
        (
            tenant_id, invoice_type,
            data.get("seller_name"), data.get("seller_inn"),
            data.get("seller_address"), data.get("seller_phone"),
            data.get("seller_bank"), data.get("seller_swift"), data.get("seller_account"),
            data.get("buyer_inn"), data.get("buyer_name"), data.get("buyer_email"),
            data.get("buyer_address"), data.get("buyer_phone"),
            data.get("invoice_date") or None, data.get("delivery_date") or None,
            data.get("due_date") or None,
            data.get("transport_from"), data.get("transport_to"),
            data.get("vehicle_number"), data.get("driver_name"),
            json.dumps(line_items),
            totals["subtotal"], totals["vat_amount"], totals["total_amount"],
            data.get("comment"),
            data.get("currency") or "GEL",
            data.get("exchange_rate"),
            data.get("created_by"),
        ),
    )
    row = cur.fetchone()
    col_names = [d[0] for d in cur.description]
    conn.commit()
    cur.close()
    result = dict(zip(col_names, row))
    result["created_at"] = result["created_at"].isoformat() if result.get("created_at") else None
    return result


def update_draft(conn, tenant_id: str, invoice_id: int, data: dict) -> dict:
    """Partial update (auto-save). Returns updated row or raises if not found."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM outgoing_invoices WHERE id = %s AND tenant_id = %s AND status = 'draft'",
        (invoice_id, tenant_id),
    )
    if not cur.fetchone():
        cur.close()
        raise LookupError(f"Draft invoice {invoice_id} not found for tenant {tenant_id}")

    allowed = [
        "seller_name", "seller_inn", "seller_address", "seller_phone",
        "seller_bank", "seller_swift", "seller_account",
        "buyer_inn", "buyer_name", "buyer_email", "buyer_address", "buyer_phone",
        "invoice_date", "delivery_date", "due_date",
        "transport_from", "transport_to", "vehicle_number", "driver_name",
        "line_items", "comment", "currency", "exchange_rate",
    ]
    sets = []
    params = []
    for field in allowed:
        if field in data:
            val = data[field]
            if field == "line_items" and isinstance(val, list):
                val = json.dumps(val)
            sets.append(f"{field} = %s")
            params.append(val)

    if "line_items" in data:
        totals = _calc_totals(data["line_items"] if isinstance(data["line_items"], list) else json.loads(data["line_items"]))
        sets += ["subtotal = %s", "vat_amount = %s", "total_amount = %s"]
        params += [totals["subtotal"], totals["vat_amount"], totals["total_amount"]]

    if not sets:
        cur.close()
        return {"id": invoice_id, "status": "no_changes"}

    sets.append("updated_at = NOW()")
    params += [invoice_id, tenant_id]

    cur.execute(
        f"""
        UPDATE outgoing_invoices
        SET {', '.join(sets)}
        WHERE id = %s AND tenant_id = %s
        RETURNING id, invoice_type, status, buyer_inn, buyer_name,
                  subtotal, vat_amount, total_amount, comment, updated_at
        """,
        params,
    )
    row = cur.fetchone()
    col_names = [d[0] for d in cur.description]
    conn.commit()
    cur.close()
    result = dict(zip(col_names, row))
    if result.get("updated_at"):
        result["updated_at"] = result["updated_at"].isoformat()
    return result


def finalize(conn, tenant_id: str, invoice_id: int) -> dict:
    """
    Finalize: assign invoice number, generate waybill (goods) + tax_invoice,
    propagate comment → notes, mark as finalized.
    Uses SELECT FOR UPDATE NOWAIT to prevent double-finalize race condition.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, invoice_type, buyer_inn, buyer_name, buyer_email,
               transport_from, transport_to, vehicle_number, driver_name,
               line_items, subtotal, vat_amount, total_amount, comment, status
        FROM outgoing_invoices
        WHERE id = %s AND tenant_id = %s
        FOR UPDATE NOWAIT
        """,
        (invoice_id, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise LookupError(f"Invoice {invoice_id} not found for tenant {tenant_id}")

    col_names = [d[0] for d in cur.description]
    inv = dict(zip(col_names, row))

    if inv["status"] != "draft":
        cur.close()
        raise ValueError(f"Invoice {invoice_id} is already {inv['status']}")

    invoice_number = _next_invoice_number(conn, tenant_id)
    comment = inv.get("comment") or ""
    now_date = datetime.now().strftime("%Y-%m-%d")

    line_items = inv.get("line_items") or []
    if isinstance(line_items, str):
        line_items = json.loads(line_items)

    waybill_id = None
    tax_invoice_id = None

    # ── Generate waybill (goods only) ─────────────────────────────────────
    if inv["invoice_type"] == "goods":
        cur.execute(
            """
            INSERT INTO waybills
                (tenant_id, waybill_number, waybill_date,
                 buyer_inn, buyer_name, transport_from, transport_to,
                 vehicle_number, driver_name,
                 line_items, subtotal, vat_amount, total_amount,
                 status, notes, version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported',%s,1)
            RETURNING id
            """,
            (
                tenant_id, invoice_number, now_date,
                inv["buyer_inn"], inv["buyer_name"],
                inv["transport_from"], inv["transport_to"],
                inv["vehicle_number"], inv["driver_name"],
                json.dumps(line_items),
                inv["subtotal"], inv["vat_amount"], inv["total_amount"],
                comment,
            ),
        )
        waybill_id = cur.fetchone()[0]
        log.info("Generated waybill id=%s for invoice %s", waybill_id, invoice_number)

    # ── Generate tax invoice ───────────────────────────────────────────────
    cur.execute(
        """
        INSERT INTO tax_invoices
            (tenant_id, invoice_number, invoice_date,
             buyer_inn, buyer_name,
             line_items, subtotal, vat_amount, total_amount,
             status, notes,
             related_waybill_number, related_waybill_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported',%s,%s,%s)
        RETURNING id
        """,
        (
            tenant_id, invoice_number, now_date,
            inv["buyer_inn"], inv["buyer_name"],
            json.dumps(line_items),
            inv["subtotal"], inv["vat_amount"], inv["total_amount"],
            comment,
            invoice_number if waybill_id else None,
            waybill_id,
        ),
    )
    tax_invoice_id = cur.fetchone()[0]
    log.info("Generated tax_invoice id=%s for invoice %s", tax_invoice_id, invoice_number)

    # ── Journal entries: Dr 1210 / Cr 6110 + Cr 3310 ─────────────────────
    journal_entries = [
        {
            "dr": "1210", "cr": "6110",
            "amount": float(inv["subtotal"] or 0),
            "note": f"{invoice_number} — შემოსავალი",
        },
        {
            "dr": "1210", "cr": "3310",
            "amount": float(inv["vat_amount"] or 0),
            "note": f"{invoice_number} — დღგ",
        },
    ]

    cur.execute(
        """
        INSERT INTO journal_drafts
            (tenant_id, date, description, partner, amount,
             debit_account, credit_account, account_code,
             reason, confidence, status, source_type, journal_entries)
        VALUES (%s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, 'pending_approval', 'sales_invoice', %s)
        RETURNING id
        """,
        (
            tenant_id,
            now_date,
            f"Outgoing invoice {invoice_number}",
            inv["buyer_name"],
            inv["total_amount"],
            "1210",
            "6110",
            "1210",
            "sales_invoice_finalized",
            0.95,
            json.dumps(journal_entries),
        ),
    )
    journal_draft_id = cur.fetchone()[0]

    # ── Mark finalized ─────────────────────────────────────────────────────
    cur.execute(
        """
        UPDATE outgoing_invoices
        SET status = 'finalized',
            invoice_number = %s,
            generated_waybill_id = %s,
            generated_tax_invoice_id = %s,
            finalized_at = NOW(),
            updated_at = NOW()
        WHERE id = %s AND tenant_id = %s
        """,
        (invoice_number, waybill_id, tax_invoice_id, invoice_id, tenant_id),
    )
    conn.commit()
    cur.close()

    log.info("action=invoice_finalized tenant=%s id=%s num=%s", tenant_id, invoice_id, invoice_number)

    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "invoice_type": inv["invoice_type"],
        "waybill_id": waybill_id,
        "tax_invoice_id": tax_invoice_id,
        "subtotal": float(inv["subtotal"] or 0),
        "vat_amount": float(inv["vat_amount"] or 0),
        "total_amount": float(inv["total_amount"] or 0),
        "journal_entries": journal_entries,
        "journal_draft_id": journal_draft_id,
        "comment": comment,
    }


def list_invoices(conn, tenant_id: str, status: str = None, limit: int = 20, offset: int = 0) -> dict:
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = "WHERE tenant_id = %s"
    params = [tenant_id]
    if status:
        where += " AND status = %s"
        params.append(status)

    cur.execute(
        f"""
        SELECT id, invoice_number, invoice_type, status,
               buyer_inn, buyer_name, total_amount, comment,
               generated_waybill_id, generated_tax_invoice_id,
               created_at, finalized_at
        FROM outgoing_invoices {where}
        ORDER BY created_at DESC LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    )
    rows = [dict(r) for r in cur.fetchall()]

    cur.execute(f"SELECT COUNT(*) AS total FROM outgoing_invoices {where}", params)
    total = cur.fetchone()["total"]
    cur.close()

    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        if r.get("finalized_at"):
            r["finalized_at"] = r["finalized_at"].isoformat()

    return {"total": total, "limit": limit, "offset": offset, "items": rows}
