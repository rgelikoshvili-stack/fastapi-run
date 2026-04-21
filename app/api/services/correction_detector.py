"""Detects field-level corrections between document versions and logs them."""
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

log = logging.getLogger(__name__)

TRACKED_FIELDS = [
    "waybill_number", "invoice_number",
    "seller_inn", "seller_name",
    "buyer_inn", "buyer_name",
    "waybill_date", "invoice_date",
    "subtotal", "vat_amount", "total_amount",
    "transport_from", "transport_to",
    "vehicle_number", "driver_name",
    "related_waybill_number",
]


def _norm(val) -> str:
    if val is None:
        return ""
    try:
        d = Decimal(str(val))
        return str(d.quantize(Decimal("0.01")))
    except (InvalidOperation, TypeError):
        return str(val).strip()


def detect_corrections(old_doc: dict, new_doc: dict) -> list[dict]:
    """Compare two document versions. Return list of changed fields."""
    changes = []
    for field in TRACKED_FIELDS:
        old_val = _norm(old_doc.get(field))
        new_val = _norm(new_doc.get(field))
        if old_val != new_val:
            changes.append({
                "field_name": field,
                "old_value": old_val or None,
                "new_value": new_val or None,
            })
    return changes


def save_corrections(
    conn,
    tenant_id: str,
    doc_type: str,
    doc_id: int,
    changes: list[dict],
    corrected_by: Optional[str] = None,
    note: Optional[str] = None,
) -> int:
    """Persist correction records to document_corrections table. Returns count saved."""
    if not changes:
        return 0
    cur = conn.cursor()
    saved = 0
    for ch in changes:
        cur.execute(
            """
            INSERT INTO document_corrections
                (tenant_id, doc_type, doc_id, field_name, old_value, new_value,
                 correction_note, corrected_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id, doc_type, doc_id,
                ch["field_name"], ch.get("old_value"), ch.get("new_value"),
                note, corrected_by,
            ),
        )
        saved += 1
    conn.commit()
    cur.close()
    log.info("Saved %d corrections for %s id=%s", saved, doc_type, doc_id)
    return saved


def get_correction_history(conn, tenant_id: str, doc_type: str, doc_id: int) -> list[dict]:
    """Return all corrections for a document, newest first."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT field_name, old_value, new_value, correction_note, corrected_by, corrected_at
        FROM document_corrections
        WHERE tenant_id = %s AND doc_type = %s AND doc_id = %s
        ORDER BY corrected_at DESC
        """,
        (tenant_id, doc_type, doc_id),
    )
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "field": r[0], "old": r[1], "new": r[2],
            "note": r[3], "by": r[4],
            "at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


def create_corrected_waybill(conn, tenant_id: str, original_id: int, new_data: dict, corrected_by: str = None) -> dict:
    """
    Create a v2 waybill from an existing one, log all field changes,
    mark original as corrected. Returns new waybill row data.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM waybills WHERE id = %s AND tenant_id = %s",
        (original_id, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise ValueError(f"Waybill {original_id} not found for tenant {tenant_id}")

    col_names = [desc[0] for desc in cur.description]
    original = dict(zip(col_names, row))

    changes = detect_corrections(original, new_data)

    version = (original.get("version") or 1) + 1
    cur.execute(
        """
        INSERT INTO waybills
            (tenant_id, waybill_number, waybill_date, seller_inn, seller_name,
             buyer_inn, buyer_name, transport_from, transport_to, vehicle_number,
             driver_name, line_items, subtotal, vat_amount, total_amount,
             status, notes, version, original_waybill_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            tenant_id,
            new_data.get("waybill_number", original["waybill_number"]),
            new_data.get("waybill_date", original["waybill_date"]),
            new_data.get("seller_inn", original["seller_inn"]),
            new_data.get("seller_name", original["seller_name"]),
            new_data.get("buyer_inn", original["buyer_inn"]),
            new_data.get("buyer_name", original["buyer_name"]),
            new_data.get("transport_from", original["transport_from"]),
            new_data.get("transport_to", original["transport_to"]),
            new_data.get("vehicle_number", original["vehicle_number"]),
            new_data.get("driver_name", original["driver_name"]),
            new_data.get("line_items", original["line_items"]),
            new_data.get("subtotal", original["subtotal"]),
            new_data.get("vat_amount", original["vat_amount"]),
            new_data.get("total_amount", original["total_amount"]),
            "imported",
            new_data.get("notes", original.get("notes")),
            version,
            original_id,
        ),
    )
    new_id = cur.fetchone()[0]

    cur.execute(
        "UPDATE waybills SET status = 'corrected', updated_at = NOW() WHERE id = %s",
        (original_id,),
    )
    conn.commit()

    save_corrections(
        conn, tenant_id, "waybill", new_id, changes,
        corrected_by=corrected_by,
        note=f"Corrected from waybill #{original_id}",
    )

    cur.execute("SELECT * FROM waybills WHERE id = %s", (new_id,))
    row = cur.fetchone()
    col_names = [desc[0] for desc in cur.description]
    cur.close()
    return dict(zip(col_names, row))
