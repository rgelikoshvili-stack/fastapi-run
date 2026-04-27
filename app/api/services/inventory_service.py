"""app/api/services/inventory_service.py
Inventory management: CRUD, stock movements, FIFO/LIFO/Average valuation.
"""
from __future__ import annotations
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from app.api.db import get_db

log = logging.getLogger(__name__)


# ── Table bootstrap ───────────────────────────────────────────────────────────

def ensure_inventory_tables(conn=None):
    close = conn is None
    if conn is None:
        conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory_categories (
                id          SERIAL PRIMARY KEY,
                tenant_id   TEXT NOT NULL,
                code        TEXT NOT NULL,
                name        TEXT NOT NULL,
                parent_id   INTEGER REFERENCES inventory_categories(id),
                is_active   BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (tenant_id, code)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warehouses (
                id              SERIAL PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                code            TEXT NOT NULL,
                name            TEXT NOT NULL,
                address         TEXT,
                is_active       BOOLEAN DEFAULT TRUE,
                is_default      BOOLEAN DEFAULT FALSE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (tenant_id, code)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory_items (
                id              SERIAL PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                item_code       TEXT NOT NULL,
                item_name       TEXT NOT NULL,
                description     TEXT,
                category_id     INTEGER REFERENCES inventory_categories(id),
                purchase_price  NUMERIC(15,2) DEFAULT 0,
                selling_price   NUMERIC(15,2) DEFAULT 0,
                unit_of_measure TEXT NOT NULL DEFAULT 'piece',
                reorder_level   INTEGER DEFAULT 0,
                costing_method  TEXT DEFAULT 'fifo' CHECK (costing_method IN ('fifo','lifo','average')),
                default_warehouse_id INTEGER REFERENCES warehouses(id),
                is_active       BOOLEAN DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (tenant_id, item_code)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_movements (
                id              SERIAL PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                item_id         INTEGER NOT NULL REFERENCES inventory_items(id),
                movement_type   TEXT NOT NULL CHECK (movement_type IN ('in','out','transfer','adjustment')),
                quantity        NUMERIC(15,3) NOT NULL,
                unit_cost       NUMERIC(15,4) NOT NULL DEFAULT 0,
                warehouse_from  INTEGER REFERENCES warehouses(id),
                warehouse_to    INTEGER REFERENCES warehouses(id),
                reference_type  TEXT,
                reference_doc   TEXT,
                movement_date   DATE NOT NULL DEFAULT CURRENT_DATE,
                notes           TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id              SERIAL PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                po_number       TEXT NOT NULL,
                supplier_name   TEXT,
                supplier_inn    TEXT,
                po_date         DATE NOT NULL DEFAULT CURRENT_DATE,
                expected_date   DATE,
                received_date   DATE,
                status          TEXT DEFAULT 'draft' CHECK (status IN ('draft','sent','partial','received','cancelled')),
                subtotal        NUMERIC(15,2) DEFAULT 0,
                vat_amount      NUMERIC(15,2) DEFAULT 0,
                total_amount    NUMERIC(15,2) DEFAULT 0,
                notes           TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (tenant_id, po_number)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS purchase_order_lines (
                id              SERIAL PRIMARY KEY,
                po_id           INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
                item_id         INTEGER NOT NULL REFERENCES inventory_items(id),
                quantity_ordered NUMERIC(15,3) NOT NULL,
                quantity_received NUMERIC(15,3) DEFAULT 0,
                unit_price      NUMERIC(15,4) NOT NULL,
                line_number     INTEGER,
                notes           TEXT
            )
        """)
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_inventory_items_tenant ON inventory_items(tenant_id, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_stock_movements_tenant_item ON stock_movements(tenant_id, item_id, movement_date DESC)",
            "CREATE INDEX IF NOT EXISTS idx_purchase_orders_tenant_status ON purchase_orders(tenant_id, status)",
        ]:
            cur.execute(idx)
        conn.commit()
    finally:
        cur.close()
        if close:
            conn.close()


# ── Item CRUD ─────────────────────────────────────────────────────────────────

def list_items(tenant_id: str, search: str = "", category_id: Optional[int] = None,
               low_stock: bool = False, limit: int = 50, offset: int = 0) -> dict:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        params: list = [tenant_id]
        where = ["i.tenant_id = %s", "i.is_active = TRUE"]
        if search:
            where.append("(i.item_code ILIKE %s OR i.item_name ILIKE %s)")
            params += [f"%{search}%", f"%{search}%"]
        if category_id:
            where.append("i.category_id = %s")
            params.append(category_id)

        where_sql = " AND ".join(where)

        cur.execute(f"SELECT COUNT(*) FROM inventory_items i WHERE {where_sql}", params)
        total = cur.fetchone()[0]

        # current stock = sum of movements
        cur.execute(f"""
            SELECT i.id, i.item_code, i.item_name, i.unit_of_measure,
                   i.purchase_price, i.selling_price, i.reorder_level,
                   i.costing_method, i.description,
                   c.name AS category_name,
                   COALESCE((
                       SELECT SUM(CASE WHEN m.movement_type IN ('in','transfer') THEN m.quantity
                                       ELSE -m.quantity END)
                       FROM stock_movements m
                       WHERE m.item_id = i.id AND m.tenant_id = i.tenant_id
                   ), 0) AS current_stock
            FROM inventory_items i
            LEFT JOIN inventory_categories c ON c.id = i.category_id
            WHERE {where_sql}
            ORDER BY i.item_name
            LIMIT %s OFFSET %s
        """, params + [limit, offset])

        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, r)) for r in rows]

        if low_stock:
            items = [it for it in items if it["current_stock"] <= it["reorder_level"]]

        total_value = sum(float(it["current_stock"]) * float(it["selling_price"] or 0) for it in items)
        low_stock_count = sum(1 for it in items if it["current_stock"] <= it["reorder_level"])

        return {
            "items": items, "total": total,
            "total_value": round(total_value, 2),
            "low_stock_count": low_stock_count,
        }
    finally:
        cur.close()
        conn.close()


def get_item(tenant_id: str, item_id: int) -> Optional[dict]:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT * FROM inventory_items WHERE id = %s AND tenant_id = %s",
            (item_id, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip([d[0] for d in cur.description], row))
    finally:
        cur.close()
        conn.close()


def create_item(tenant_id: str, data: dict) -> dict:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO inventory_items
                (tenant_id, item_code, item_name, description, category_id,
                 purchase_price, selling_price, unit_of_measure, reorder_level, costing_method)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                tenant_id,
                data["item_code"], data["item_name"],
                data.get("description"), data.get("category_id"),
                data.get("purchase_price", 0), data.get("selling_price", 0),
                data.get("unit_of_measure", "piece"),
                data.get("reorder_level", 0),
                data.get("costing_method", "fifo"),
            ),
        )
        item_id = cur.fetchone()[0]
        conn.commit()
        return {**data, "id": item_id, "tenant_id": tenant_id}
    finally:
        cur.close()
        conn.close()


def update_item(tenant_id: str, item_id: int, data: dict) -> Optional[dict]:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        allowed = ["item_name", "description", "category_id", "purchase_price",
                   "selling_price", "unit_of_measure", "reorder_level", "costing_method", "is_active"]
        sets = [f"{k} = %s" for k in allowed if k in data]
        if not sets:
            return get_item(tenant_id, item_id)
        vals = [data[k] for k in allowed if k in data]
        cur.execute(
            f"UPDATE inventory_items SET {', '.join(sets)}, updated_at=NOW() "
            f"WHERE id=%s AND tenant_id=%s RETURNING id",
            vals + [item_id, tenant_id],
        )
        row = cur.fetchone()
        conn.commit()
        return get_item(tenant_id, item_id) if row else None
    finally:
        cur.close()
        conn.close()


# ── Stock movements ───────────────────────────────────────────────────────────

def record_movement(tenant_id: str, data: dict) -> dict:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO stock_movements
                (tenant_id, item_id, movement_type, quantity, unit_cost,
                 warehouse_from, warehouse_to, reference_type, reference_doc,
                 movement_date, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                tenant_id,
                data["item_id"], data["movement_type"],
                data["quantity"], data.get("unit_cost", 0),
                data.get("warehouse_from"), data.get("warehouse_to"),
                data.get("reference_type"), data.get("reference_doc"),
                data.get("movement_date") or date.today().isoformat(),
                data.get("notes"),
            ),
        )
        mv_id = cur.fetchone()[0]
        conn.commit()
        return {**data, "id": mv_id}
    finally:
        cur.close()
        conn.close()


def get_movements(tenant_id: str, item_id: Optional[int] = None,
                  movement_type: Optional[str] = None,
                  date_from: Optional[str] = None, date_to: Optional[str] = None,
                  limit: int = 50, offset: int = 0) -> dict:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        params: list = [tenant_id]
        where = ["m.tenant_id = %s"]
        if item_id:
            where.append("m.item_id = %s"); params.append(item_id)
        if movement_type:
            where.append("m.movement_type = %s"); params.append(movement_type)
        if date_from:
            where.append("m.movement_date >= %s"); params.append(date_from)
        if date_to:
            where.append("m.movement_date <= %s"); params.append(date_to)

        where_sql = " AND ".join(where)
        cur.execute(f"SELECT COUNT(*) FROM stock_movements m WHERE {where_sql}", params)
        total = cur.fetchone()[0]

        cur.execute(f"""
            SELECT m.id, m.item_id, i.item_code, i.item_name,
                   m.movement_type, m.quantity, m.unit_cost,
                   m.quantity * m.unit_cost AS total_value,
                   m.reference_doc, m.movement_date, m.notes, m.created_at
            FROM stock_movements m
            JOIN inventory_items i ON i.id = m.item_id
            WHERE {where_sql}
            ORDER BY m.movement_date DESC, m.id DESC
            LIMIT %s OFFSET %s
        """, params + [limit, offset])

        cols = [d[0] for d in cur.description]
        return {
            "movements": [dict(zip(cols, r)) for r in cur.fetchall()],
            "total": total,
        }
    finally:
        cur.close()
        conn.close()


def get_current_stock(tenant_id: str, item_id: int) -> float:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN movement_type IN ('in','transfer') THEN quantity
                                     ELSE -quantity END), 0)
            FROM stock_movements
            WHERE tenant_id = %s AND item_id = %s
        """, (tenant_id, item_id))
        return float(cur.fetchone()[0])
    finally:
        cur.close()
        conn.close()


# ── Valuation ─────────────────────────────────────────────────────────────────

def calculate_valuation(tenant_id: str, method: str = "fifo",
                        as_of_date: Optional[str] = None) -> dict:
    as_of = as_of_date or date.today().isoformat()
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, item_code, item_name, unit_of_measure FROM inventory_items "
            "WHERE tenant_id = %s AND is_active = TRUE",
            (tenant_id,),
        )
        items = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

    valued = []
    for item in items:
        if method == "fifo":
            v = _fifo_value(tenant_id, item["id"], as_of)
        elif method == "lifo":
            v = _lifo_value(tenant_id, item["id"], as_of)
        else:
            v = _average_value(tenant_id, item["id"], as_of)
        valued.append({**item, **v})

    total_value = sum(it["total_value"] for it in valued)
    total_qty   = sum(it["quantity"] for it in valued)
    return {"method": method, "as_of": as_of,
            "total_value": round(total_value, 2), "total_qty": total_qty,
            "items": [it for it in valued if it["quantity"] > 0]}


def _in_out_movements(tenant_id: str, item_id: int, as_of: str):
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT movement_type, quantity, unit_cost, movement_date
            FROM stock_movements
            WHERE tenant_id=%s AND item_id=%s AND movement_date <= %s
            ORDER BY movement_date, id
        """, (tenant_id, item_id, as_of))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    ins  = [{"qty": float(r[1]), "cost": float(r[2]), "date": r[3]}
            for r in rows if r[0] in ("in",)]
    outs = [{"qty": float(r[1])} for r in rows if r[0] in ("out", "transfer")]
    return ins, outs


def _fifo_value(tenant_id: str, item_id: int, as_of: str) -> dict:
    ins, outs = _in_out_movements(tenant_id, item_id, as_of)
    total_out = sum(o["qty"] for o in outs)
    batches = []
    consumed = 0.0
    for batch in ins:
        if consumed < total_out:
            take = min(batch["qty"], total_out - consumed)
            consumed += take
            remaining = batch["qty"] - take
        else:
            remaining = batch["qty"]
        if remaining > 0:
            batches.append({"qty": remaining, "cost": batch["cost"]})
    qty   = sum(b["qty"] for b in batches)
    value = sum(b["qty"] * b["cost"] for b in batches)
    return {"quantity": qty, "total_value": round(value, 2),
            "avg_cost": round(value / qty, 4) if qty else 0}


def _lifo_value(tenant_id: str, item_id: int, as_of: str) -> dict:
    ins, outs = _in_out_movements(tenant_id, item_id, as_of)
    total_out = sum(o["qty"] for o in outs)
    batches = []
    consumed = 0.0
    for batch in reversed(ins):
        if consumed < total_out:
            take = min(batch["qty"], total_out - consumed)
            consumed += take
            remaining = batch["qty"] - take
        else:
            remaining = batch["qty"]
        if remaining > 0:
            batches.append({"qty": remaining, "cost": batch["cost"]})
    qty   = sum(b["qty"] for b in batches)
    value = sum(b["qty"] * b["cost"] for b in batches)
    return {"quantity": qty, "total_value": round(value, 2),
            "avg_cost": round(value / qty, 4) if qty else 0}


def _average_value(tenant_id: str, item_id: int, as_of: str) -> dict:
    ins, outs = _in_out_movements(tenant_id, item_id, as_of)
    total_in   = sum(b["qty"] for b in ins)
    total_out  = sum(o["qty"] for o in outs)
    total_cost = sum(b["qty"] * b["cost"] for b in ins)
    avg_cost   = total_cost / total_in if total_in else 0
    qty        = max(0.0, total_in - total_out)
    return {"quantity": qty, "total_value": round(qty * avg_cost, 2),
            "avg_cost": round(avg_cost, 4)}


# ── Purchase Orders ───────────────────────────────────────────────────────────

def create_purchase_order(tenant_id: str, data: dict) -> dict:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        # auto-generate PO number if missing
        if not data.get("po_number"):
            cur.execute(
                "SELECT COUNT(*)+1 FROM purchase_orders WHERE tenant_id=%s", (tenant_id,)
            )
            n = cur.fetchone()[0]
            data["po_number"] = f"PO-{date.today().year}-{n:04d}"

        cur.execute(
            """
            INSERT INTO purchase_orders
                (tenant_id, po_number, supplier_name, supplier_inn,
                 po_date, expected_date, total_amount, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                tenant_id, data["po_number"],
                data.get("supplier_name"), data.get("supplier_inn"),
                data.get("po_date") or date.today().isoformat(),
                data.get("expected_date"),
                data.get("total_amount", 0),
                data.get("notes"),
            ),
        )
        po_id = cur.fetchone()[0]

        for line in data.get("lines", []):
            cur.execute(
                """
                INSERT INTO purchase_order_lines
                    (po_id, item_id, quantity_ordered, unit_price, line_number, notes)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (po_id, line["item_id"], line["quantity"],
                 line["unit_price"], line.get("line_number"), line.get("notes")),
            )
        conn.commit()
        return {**data, "id": po_id}
    finally:
        cur.close()
        conn.close()


def list_purchase_orders(tenant_id: str, status: Optional[str] = None,
                         limit: int = 50, offset: int = 0) -> dict:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        params: list = [tenant_id]
        where = ["tenant_id = %s"]
        if status:
            where.append("status = %s"); params.append(status)
        where_sql = " AND ".join(where)
        cur.execute(f"SELECT COUNT(*) FROM purchase_orders WHERE {where_sql}", params)
        total = cur.fetchone()[0]
        cur.execute(f"""
            SELECT id, po_number, supplier_name, po_date, expected_date,
                   status, total_amount, notes, created_at
            FROM purchase_orders WHERE {where_sql}
            ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, params + [limit, offset])
        cols = [d[0] for d in cur.description]
        return {"orders": [dict(zip(cols, r)) for r in cur.fetchall()], "total": total}
    finally:
        cur.close()
        conn.close()


def receive_purchase_order(tenant_id: str, po_id: int, lines_received: list) -> dict:
    """Receive PO lines → create stock_movements, update po status."""
    conn = get_db(tenant_id)
    cur = conn.cursor()
    received_count = 0
    try:
        for line in lines_received:
            line_id = line["line_id"]
            qty     = float(line["quantity_received"])
            cost    = float(line.get("unit_cost", 0))

            cur.execute(
                "SELECT pol.item_id, pol.quantity_ordered, pol.quantity_received "
                "FROM purchase_order_lines pol "
                "JOIN purchase_orders po ON po.id = pol.po_id "
                "WHERE pol.id = %s AND po.tenant_id = %s",
                (line_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                continue
            item_id, ordered, already_received = row[0], float(row[1]), float(row[2])
            qty = min(qty, ordered - already_received)
            if qty <= 0:
                continue

            cur.execute(
                "UPDATE purchase_order_lines SET quantity_received = quantity_received + %s "
                "WHERE id = %s",
                (qty, line_id),
            )
            cur.execute(
                """
                INSERT INTO stock_movements
                    (tenant_id, item_id, movement_type, quantity, unit_cost,
                     reference_type, reference_doc, movement_date)
                VALUES (%s,%s,'in',%s,%s,'purchase_order',%s,CURRENT_DATE)
                """,
                (tenant_id, item_id, qty, cost,
                 f"PO-{po_id}"),
            )
            received_count += 1

        # update PO status
        cur.execute(
            """
            UPDATE purchase_orders SET status = CASE
                WHEN (SELECT SUM(quantity_ordered - quantity_received) FROM purchase_order_lines WHERE po_id=%s) <= 0
                     THEN 'received'
                ELSE 'partial'
            END, updated_at=NOW()
            WHERE id=%s AND tenant_id=%s
            """,
            (po_id, po_id, tenant_id),
        )
        conn.commit()
        return {"po_id": po_id, "lines_received": received_count}
    finally:
        cur.close()
        conn.close()


# ── Warehouses & Categories ───────────────────────────────────────────────────

def list_warehouses(tenant_id: str) -> list:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, code, name, address, is_default FROM warehouses "
            "WHERE tenant_id=%s AND is_active=TRUE ORDER BY is_default DESC, name",
            (tenant_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def list_categories(tenant_id: str) -> list:
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, code, name, parent_id FROM inventory_categories "
            "WHERE tenant_id=%s AND is_active=TRUE ORDER BY name",
            (tenant_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
