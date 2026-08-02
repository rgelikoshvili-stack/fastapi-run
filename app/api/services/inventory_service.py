"""app/api/services/inventory_service.py
Inventory management: CRUD, stock movements, FIFO/LIFO/Average valuation.
"""
from __future__ import annotations
import logging
import os
from datetime import date
from decimal import Decimal
from typing import Optional

from app.api.db import get_conn, _q
from app.api.services.posting_service import create_journal_draft
from app.api.services.inventory_costing_service import compute_dispatch_cogs, cogs_journal_lines

log = logging.getLogger(__name__)

MOVEMENT_TYPES = {"in", "out", "transfer", "adjustment"}
ACCOUNTING_MOVEMENT_TYPES = {"in", "out", "adjustment"}


# ── Table bootstrap (sync, DDL — kept psycopg2) ──────────────────────────────

def ensure_inventory_tables(conn=None):
    close = conn is None
    if conn is None:
        import psycopg2  # lazy — DDL bootstrap only, called via run_in_executor
        url = os.environ.get("DATABASE_URL")
        if not url:
            return
        conn = psycopg2.connect(url)
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

async def list_items(tenant_id: str, search: str = "", category_id: Optional[int] = None,
                     low_stock: bool = False, limit: int = 50, offset: int = 0) -> dict:
    async with get_conn() as conn:
        params: list = [tenant_id]
        where = ["i.tenant_id = $1", "i.is_active = TRUE"]
        if search:
            params += [f"%{search}%", f"%{search}%"]
            i2, i3 = len(params) - 1, len(params)
            where.append(f"(i.item_code ILIKE ${i2} OR i.item_name ILIKE ${i3})")
        if category_id:
            params.append(category_id)
            where.append(f"i.category_id = ${len(params)}")

        where_sql = " AND ".join(where)

        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM inventory_items i WHERE {where_sql}", *params
        )

        params_page = params + [limit, offset]
        lim_p = len(params_page) - 1
        off_p = len(params_page)
        rows = await conn.fetch(f"""
            SELECT i.id, i.item_code, i.item_name, i.unit_of_measure,
                   i.purchase_price, i.selling_price, i.reorder_level,
                   i.costing_method, i.description,
                   c.name AS category_name,
                   COALESCE((
                       SELECT SUM(CASE WHEN m.movement_type = 'in' THEN m.quantity
                                       WHEN m.movement_type = 'out' THEN -m.quantity
                                       ELSE 0 END)
                       FROM stock_movements m
                       WHERE m.item_id = i.id AND m.tenant_id = i.tenant_id
                   ), 0) AS current_stock
            FROM inventory_items i
            LEFT JOIN inventory_categories c ON c.id = i.category_id
            WHERE {where_sql}
            ORDER BY i.item_name
            LIMIT ${lim_p} OFFSET ${off_p}
        """, *params_page)

        items = [dict(r) for r in rows]
        for it in items:
            for k, v in it.items():
                if isinstance(v, Decimal):
                    it[k] = float(v)

        if low_stock:
            items = [it for it in items if float(it["current_stock"]) <= float(it["reorder_level"])]

        total_value = sum(float(it["current_stock"]) * float(it["selling_price"] or 0) for it in items)
        low_stock_count = sum(1 for it in items if float(it["current_stock"]) <= float(it["reorder_level"]))

    return {
        "items": items, "total": total,
        "total_value": round(total_value, 2),
        "low_stock_count": low_stock_count,
    }


async def get_item(tenant_id: str, item_id: int) -> Optional[dict]:
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "SELECT * FROM inventory_items WHERE id = %s AND tenant_id = %s",
        ), item_id, tenant_id)
    if not row:
        return None
    result = dict(row)
    for k, v in result.items():
        if isinstance(v, Decimal):
            result[k] = float(v)
    return result


async def create_item(tenant_id: str, data: dict) -> dict:
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            INSERT INTO inventory_items
                (tenant_id, item_code, item_name, description, category_id,
                 purchase_price, selling_price, unit_of_measure, reorder_level, costing_method)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """), tenant_id,
            data["item_code"], data["item_name"],
            data.get("description"), data.get("category_id"),
            data.get("purchase_price", 0), data.get("selling_price", 0),
            data.get("unit_of_measure", "piece"),
            data.get("reorder_level", 0),
            data.get("costing_method", "fifo"),
        )
    return {**data, "id": row["id"], "tenant_id": tenant_id}


async def update_item(tenant_id: str, item_id: int, data: dict) -> Optional[dict]:
    allowed = ["item_name", "description", "category_id", "purchase_price",
               "selling_price", "unit_of_measure", "reorder_level", "costing_method", "is_active"]
    sets = [k for k in allowed if k in data]
    if not sets:
        return await get_item(tenant_id, item_id)

    async with get_conn() as conn:
        params = [data[k] for k in sets] + [item_id, tenant_id]
        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(sets)]
        set_clauses.append("updated_at=NOW()")
        row = await conn.fetchrow(
            f"UPDATE inventory_items SET {', '.join(set_clauses)} "
            f"WHERE id=${len(sets)+1} AND tenant_id=${len(sets)+2} RETURNING id",
            *params,
        )
    return await get_item(tenant_id, item_id) if row else None


# ── Stock movements ───────────────────────────────────────────────────────────

async def record_movement(tenant_id: str, data: dict) -> dict:
    item_id = int(data["item_id"])
    movement_type = str(data["movement_type"])
    quantity = float(data["quantity"])
    unit_cost = float(data.get("unit_cost") or 0)

    if movement_type not in MOVEMENT_TYPES:
        raise ValueError("INVALID_MOVEMENT_TYPE")
    if quantity <= 0:
        raise ValueError("INVALID_QUANTITY")
    if unit_cost < 0:
        raise ValueError("INVALID_UNIT_COST")

    async with get_conn() as conn:
        item = await conn.fetchrow(_q("""
            SELECT id, item_code, item_name
            FROM inventory_items
            WHERE id = %s AND tenant_id = %s AND is_active = TRUE
        """), item_id, tenant_id)
        if not item:
            raise ValueError("ITEM_NOT_FOUND")

        if movement_type == "out":
            available = await conn.fetchval(_q("""
                SELECT COALESCE(SUM(CASE WHEN movement_type = 'in' THEN quantity
                                         WHEN movement_type = 'out' THEN -quantity
                                         ELSE 0 END), 0)
                FROM stock_movements
                WHERE tenant_id = %s AND item_id = %s
            """), tenant_id, item_id)
            if float(available or 0) < quantity:
                raise ValueError("INSUFFICIENT_STOCK")

        row = await conn.fetchrow(_q("""
            INSERT INTO stock_movements
                (tenant_id, item_id, movement_type, quantity, unit_cost,
                 warehouse_from, warehouse_to, reference_type, reference_doc,
                 movement_date, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """), tenant_id,
            item_id, movement_type,
            quantity, unit_cost,
            data.get("warehouse_from"), data.get("warehouse_to"),
            data.get("reference_type"), data.get("reference_doc"),
            data.get("movement_date") or date.today().isoformat(),
            data.get("notes"),
        )

    draft_id = None
    costing_result = None
    if movement_type == "out":
        movement_date_str = str(data.get("movement_date") or date.today().isoformat())
        costing_result = await compute_dispatch_cogs(
            tenant_id, item_id, quantity, movement_date_str
        )
        amount = costing_result["cogs"]
    else:
        amount = round(quantity * unit_cost, 2)

    if amount > 0 and movement_type in ACCOUNTING_MOVEMENT_TYPES:
        lines = (
            cogs_journal_lines(amount)
            if movement_type == "out"
            else _movement_journal_lines(movement_type, amount)
        )
        draft = await create_journal_draft(
            description=f"Inventory {movement_type} movement #{row['id']} for {item['item_code']}",
            lines=lines,
            tenant_id=tenant_id,
            partner="Inventory movement",
            source_document_id=row["id"],
        )
        draft_id = draft["id"]

    return {
        **data,
        "id": row["id"],
        "item_id": item_id,
        "movement_type": movement_type,
        "quantity": quantity,
        "unit_cost": unit_cost,
        "tenant_id": tenant_id,
        "journal_draft_id": draft_id,
        "draft_id": draft_id,
        "cogs_amount": amount if movement_type == "out" else None,
        "costing_method": costing_result.get("costing_method") if costing_result else None,
    }


def _movement_journal_lines(movement_type: str, amount: float) -> list[dict]:
    if movement_type == "in":
        return [
            {"account_code": "1310", "debit": amount, "credit": 0},
            {"account_code": "3110", "debit": 0, "credit": amount},
        ]
    return [
        {"account_code": "7110", "debit": amount, "credit": 0},
        {"account_code": "1310", "debit": 0, "credit": amount},
    ]


async def get_movements(tenant_id: str, item_id: Optional[int] = None,
                        movement_type: Optional[str] = None,
                        date_from: Optional[str] = None, date_to: Optional[str] = None,
                        limit: int = 50, offset: int = 0) -> dict:
    async with get_conn() as conn:
        params: list = [tenant_id]
        where = ["m.tenant_id = $1"]
        if item_id:
            params.append(item_id); where.append(f"m.item_id = ${len(params)}")
        if movement_type:
            params.append(movement_type); where.append(f"m.movement_type = ${len(params)}")
        if date_from:
            params.append(date_from); where.append(f"m.movement_date >= ${len(params)}")
        if date_to:
            params.append(date_to); where.append(f"m.movement_date <= ${len(params)}")

        where_sql = " AND ".join(where)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM stock_movements m WHERE {where_sql}", *params
        )

        params_page = params + [limit, offset]
        lim_p = len(params_page) - 1
        off_p = len(params_page)
        rows = await conn.fetch(f"""
            SELECT m.id, m.item_id, i.item_code, i.item_name,
                   m.movement_type, m.quantity, m.unit_cost,
                   m.quantity * m.unit_cost AS total_value,
                   m.reference_doc, m.movement_date, m.notes, m.created_at
            FROM stock_movements m
            JOIN inventory_items i ON i.id = m.item_id AND i.tenant_id = m.tenant_id
            WHERE {where_sql}
            ORDER BY m.movement_date DESC, m.id DESC
            LIMIT ${lim_p} OFFSET ${off_p}
        """, *params_page)

    return {
        "movements": [dict(r) for r in rows],
        "total": total,
    }


async def get_current_stock(tenant_id: str, item_id: int) -> float:
    async with get_conn() as conn:
        val = await conn.fetchval(_q("""
            SELECT COALESCE(SUM(CASE WHEN movement_type = 'in' THEN quantity
                                     WHEN movement_type = 'out' THEN -quantity
                                     ELSE 0 END), 0)
            FROM stock_movements
            WHERE tenant_id = %s AND item_id = %s
        """), tenant_id, item_id)
    return float(val or 0)


# ── Valuation ─────────────────────────────────────────────────────────────────

async def calculate_valuation(tenant_id: str, method: str = "fifo",
                              as_of_date: Optional[str] = None) -> dict:
    as_of = as_of_date or date.today().isoformat()
    async with get_conn() as conn:
        rows = await conn.fetch(_q(
            "SELECT id, item_code, item_name, unit_of_measure FROM inventory_items "
            "WHERE tenant_id = %s AND is_active = TRUE"
        ), tenant_id)
        items = [dict(r) for r in rows]

    valued = []
    for item in items:
        ins, outs = await _in_out_movements(tenant_id, item["id"], as_of)
        if method == "fifo":
            v = _fifo_value(ins, outs)
        elif method == "lifo":
            v = _lifo_value(ins, outs)
        else:
            v = _average_value(ins, outs)
        valued.append({**item, **v})

    total_value = sum(it["total_value"] for it in valued)
    total_qty   = sum(it["quantity"] for it in valued)
    return {"method": method, "as_of": as_of,
            "total_value": round(total_value, 2), "total_qty": total_qty,
            "items": [it for it in valued if it["quantity"] > 0]}


async def get_stock_report(tenant_id: str, low_stock_only: bool = False) -> dict:
    result = await list_items(tenant_id, low_stock=low_stock_only, limit=10000, offset=0)
    items = result.get("items", [])
    total_qty = sum(float(it.get("current_stock") or 0) for it in items)
    total_stock_value = sum(
        float(it.get("current_stock") or 0) * float(it.get("purchase_price") or 0)
        for it in items
    )
    return {
        "items": items,
        "total": result.get("total", 0),
        "reported_count": len(items),
        "low_stock_count": result.get("low_stock_count", 0),
        "total_qty": round(total_qty, 3),
        "total_stock_value": round(total_stock_value, 2),
    }


async def _in_out_movements(tenant_id: str, item_id: int, as_of: str):
    async with get_conn() as conn:
        rows = await conn.fetch(_q("""
            SELECT movement_type, quantity, unit_cost, movement_date
            FROM stock_movements
            WHERE tenant_id=%s AND item_id=%s AND movement_date <= %s
            ORDER BY movement_date, id
        """), tenant_id, item_id, as_of)

    ins  = [{"qty": float(r["quantity"]), "cost": float(r["unit_cost"]), "date": r["movement_date"]}
            for r in rows if r["movement_type"] in ("in",)]
    outs = [{"qty": float(r["quantity"])} for r in rows if r["movement_type"] == "out"]
    return ins, outs


def _fifo_value(ins: list, outs: list) -> dict:
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


def _lifo_value(ins: list, outs: list) -> dict:
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


def _average_value(ins: list, outs: list) -> dict:
    total_in   = sum(b["qty"] for b in ins)
    total_out  = sum(o["qty"] for o in outs)
    total_cost = sum(b["qty"] * b["cost"] for b in ins)
    avg_cost   = total_cost / total_in if total_in else 0
    qty        = max(0.0, total_in - total_out)
    return {"quantity": qty, "total_value": round(qty * avg_cost, 2),
            "avg_cost": round(avg_cost, 4)}


# ── Purchase Orders ───────────────────────────────────────────────────────────

async def create_purchase_order(tenant_id: str, data: dict) -> dict:
    async with get_conn() as conn:
        if not data.get("po_number"):
            n = await conn.fetchval(_q(
                "SELECT COUNT(*)+1 FROM purchase_orders WHERE tenant_id=%s"
            ), tenant_id)
            data["po_number"] = f"PO-{date.today().year}-{n:04d}"

        normalized_lines = []
        for line in data.get("lines", []):
            item_id = int(line["item_id"])
            qty = float(line["quantity"])
            price = float(line["unit_price"])
            if qty <= 0:
                raise ValueError("INVALID_QUANTITY")
            if price < 0:
                raise ValueError("INVALID_UNIT_PRICE")
            item_exists = await conn.fetchval(_q(
                "SELECT 1 FROM inventory_items WHERE id = %s AND tenant_id = %s AND is_active = TRUE"
            ), item_id, tenant_id)
            if not item_exists:
                raise ValueError("ITEM_NOT_FOUND")
            normalized_lines.append((item_id, qty, price, line.get("line_number"), line.get("notes")))

        row = await conn.fetchrow(_q("""
            INSERT INTO purchase_orders
                (tenant_id, po_number, supplier_name, supplier_inn,
                 po_date, expected_date, total_amount, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """), tenant_id, data["po_number"],
            data.get("supplier_name"), data.get("supplier_inn"),
            data.get("po_date") or date.today().isoformat(),
            data.get("expected_date"),
            data.get("total_amount", 0),
            data.get("notes"),
        )
        po_id = row["id"]

        for item_id, qty, price, line_number, notes in normalized_lines:
            await conn.execute(_q("""
                INSERT INTO purchase_order_lines
                    (po_id, item_id, quantity_ordered, unit_price, line_number, notes)
                VALUES (%s,%s,%s,%s,%s,%s)
            """), po_id, item_id, qty,
                price, line_number, notes,
            )
    return {**data, "id": po_id}


async def list_purchase_orders(tenant_id: str, status: Optional[str] = None,
                               limit: int = 50, offset: int = 0) -> dict:
    async with get_conn() as conn:
        params: list = [tenant_id]
        where = ["tenant_id = $1"]
        if status:
            params.append(status); where.append(f"status = ${len(params)}")
        where_sql = " AND ".join(where)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM purchase_orders WHERE {where_sql}", *params
        )
        params_page = params + [limit, offset]
        lim_p = len(params_page) - 1
        off_p = len(params_page)
        rows = await conn.fetch(f"""
            SELECT id, po_number, supplier_name, po_date, expected_date,
                   status, total_amount, notes, created_at
            FROM purchase_orders WHERE {where_sql}
            ORDER BY created_at DESC LIMIT ${lim_p} OFFSET ${off_p}
        """, *params_page)
    return {"orders": [dict(r) for r in rows], "total": total}


async def get_purchase_order(tenant_id: str, po_id: int) -> Optional[dict]:
    async with get_conn() as conn:
        order = await conn.fetchrow(_q("""
            SELECT id, tenant_id, po_number, supplier_name, supplier_inn,
                   po_date, expected_date, received_date, status,
                   subtotal, vat_amount, total_amount, notes, created_at, updated_at
            FROM purchase_orders
            WHERE id = %s AND tenant_id = %s
        """), po_id, tenant_id)
        if not order:
            return None
        lines = await conn.fetch(_q("""
            SELECT pol.id, pol.item_id, ii.item_code, ii.item_name,
                   pol.quantity_ordered, pol.quantity_received, pol.unit_price,
                   pol.line_number, pol.notes
            FROM purchase_order_lines pol
            JOIN purchase_orders po ON po.id = pol.po_id
            JOIN inventory_items ii ON ii.id = pol.item_id AND ii.tenant_id = po.tenant_id
            WHERE pol.po_id = %s AND po.tenant_id = %s
            ORDER BY COALESCE(pol.line_number, pol.id), pol.id
        """), po_id, tenant_id)

    result = dict(order)
    result["lines"] = [dict(r) for r in lines]
    return result


async def receive_purchase_order(tenant_id: str, po_id: int, lines_received: list) -> dict:
    received_count = 0
    draft_ids = []
    async with get_conn() as conn:
        for line in lines_received:
            line_id = line["line_id"]
            qty     = float(line["quantity_received"])
            cost    = float(line.get("unit_cost", 0))

            row = await conn.fetchrow(_q(
                "SELECT pol.item_id, pol.quantity_ordered, pol.quantity_received "
                "FROM purchase_order_lines pol "
                "JOIN purchase_orders po ON po.id = pol.po_id "
                "JOIN inventory_items ii ON ii.id = pol.item_id AND ii.tenant_id = po.tenant_id "
                "WHERE pol.id = %s AND po.tenant_id = %s"
            ), line_id, tenant_id)
            if not row:
                continue
            item_id = row["item_id"]
            qty = min(qty, float(row["quantity_ordered"]) - float(row["quantity_received"]))
            if qty <= 0:
                continue

            await conn.execute(_q(
                "UPDATE purchase_order_lines SET quantity_received = quantity_received + %s "
                "WHERE id = %s"
            ), qty, line_id)
            await conn.execute(_q("""
                INSERT INTO stock_movements
                    (tenant_id, item_id, movement_type, quantity, unit_cost,
                     reference_type, reference_doc, movement_date)
                VALUES (%s,%s,'in',%s,%s,'purchase_order',%s,CURRENT_DATE)
            """), tenant_id, item_id, qty, cost, f"PO-{po_id}")
            received_count += 1

            if qty > 0 and cost > 0:
                line_total = round(qty * cost, 2)
                draft = await create_journal_draft(
                    description=f"Purchase order {po_id} receipt for item {item_id}",
                    lines=[
                        {"account_code": "1310", "debit": line_total, "credit": 0},
                        {"account_code": "3110", "debit": 0, "credit": line_total},
                    ],
                    tenant_id=tenant_id,
                    partner="Inventory receipt",
                    source_document_id=po_id,
                )
                draft_ids.append(draft["id"])

        await conn.execute(_q("""
            UPDATE purchase_orders SET status = CASE
                WHEN (SELECT SUM(quantity_ordered - quantity_received) FROM purchase_order_lines WHERE po_id=%s) <= 0
                     THEN 'received'
                ELSE 'partial'
            END, updated_at=NOW()
            WHERE id=%s AND tenant_id=%s
        """), po_id, po_id, tenant_id)

    return {"po_id": po_id, "lines_received": received_count, "draft_ids": draft_ids}


# ── Warehouses & Categories ───────────────────────────────────────────────────

async def list_warehouses(tenant_id: str) -> list:
    async with get_conn() as conn:
        rows = await conn.fetch(_q(
            "SELECT id, code, name, address, is_default FROM warehouses "
            "WHERE tenant_id=%s AND is_active=TRUE ORDER BY is_default DESC, name"
        ), tenant_id)
    return [dict(r) for r in rows]


async def list_categories(tenant_id: str) -> list:
    async with get_conn() as conn:
        rows = await conn.fetch(_q(
            "SELECT id, code, name, parent_id FROM inventory_categories "
            "WHERE tenant_id=%s AND is_active=TRUE ORDER BY name"
        ), tenant_id)
    return [dict(r) for r in rows]


async def create_warehouse(tenant_id: str, data: dict) -> dict:
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "INSERT INTO warehouses (tenant_id, code, name, address, is_default) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id"
        ), tenant_id, data["code"], data["name"],
            data.get("address"), data.get("is_default", False))
    return {**data, "id": row["id"]}


async def create_category(tenant_id: str, data: dict) -> dict:
    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "INSERT INTO inventory_categories (tenant_id, code, name, parent_id) "
            "VALUES (%s,%s,%s,%s) RETURNING id"
        ), tenant_id, data["code"], data["name"], data.get("parent_id"))
    return {**data, "id": row["id"]}
