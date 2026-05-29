"""app/api/services/inventory_costing_service.py — COGS costing engine (Task 12C).

Computes the Cost of Goods Sold for inventory dispatch (out) movements using
FIFO or Weighted Average Cost Group (WACG) methods.

Pure functions (fifo_cogs, wacg_cogs, compute_cogs) have no DB access and are
unit-testable in isolation.  The async entry-point compute_dispatch_cogs fetches
purchase history and delegates to the appropriate pure function.
"""
from __future__ import annotations

from typing import Any

from app.api.db import get_conn, _q


# ---------------------------------------------------------------------------
# Pure costing functions (no DB access)
# ---------------------------------------------------------------------------

def fifo_cogs(purchases: list[dict], dispatch_qty: float) -> dict[str, Any]:
    """Compute COGS for *dispatch_qty* units using FIFO.

    *purchases* must be ordered oldest-first.  Each entry:
        {"qty": float, "cost": float}

    Returns:
        {"cogs": float, "unit_cost": float, "layers_consumed": [...], "unmatched_qty": float}
    """
    remaining = dispatch_qty
    total_cost = 0.0
    layers = []

    for batch in purchases:
        if remaining <= 0:
            break
        take = min(batch["qty"], remaining)
        cost_taken = take * batch["cost"]
        total_cost += cost_taken
        remaining -= take
        layers.append({"qty": take, "cost_per_unit": batch["cost"], "total": round(cost_taken, 4)})

    unit_cost = round(total_cost / dispatch_qty, 4) if dispatch_qty else 0.0
    return {
        "cogs": round(total_cost, 2),
        "unit_cost": unit_cost,
        "layers_consumed": layers,
        "unmatched_qty": round(max(0.0, remaining), 6),
    }


def wacg_cogs(purchases: list[dict], dispatch_qty: float) -> dict[str, Any]:
    """Compute COGS for *dispatch_qty* units using Weighted Average Cost Group.

    Returns:
        {"cogs": float, "unit_cost": float, "avg_purchase_cost": float, "unmatched_qty": float}
    """
    total_qty  = sum(b["qty"] for b in purchases)
    total_cost = sum(b["qty"] * b["cost"] for b in purchases)
    avg_cost   = total_cost / total_qty if total_qty else 0.0

    matched_qty = min(dispatch_qty, total_qty)
    unmatched   = max(0.0, dispatch_qty - total_qty)
    cogs        = matched_qty * avg_cost

    return {
        "cogs": round(cogs, 2),
        "unit_cost": round(avg_cost, 4),
        "avg_purchase_cost": round(avg_cost, 4),
        "unmatched_qty": round(unmatched, 6),
    }


def compute_cogs(method: str, purchases: list[dict], dispatch_qty: float) -> dict[str, Any]:
    """Dispatch to the correct costing function.

    *method*: 'fifo' | 'average' (WACG) | 'lifo' (falls back to FIFO for simplicity)
    """
    if method == "average":
        result = wacg_cogs(purchases, dispatch_qty)
    else:
        result = fifo_cogs(purchases, dispatch_qty)
    result["method"] = method
    return result


# ---------------------------------------------------------------------------
# Async entry-point
# ---------------------------------------------------------------------------

async def compute_dispatch_cogs(
    tenant_id: str,
    item_id: int,
    dispatch_qty: float,
    as_of_date: str,
) -> dict[str, Any]:
    """Fetch purchase history and compute COGS for a dispatch of *dispatch_qty* units.

    Returns the result dict from compute_cogs plus:
        {"item_id": int, "dispatch_qty": float, "as_of_date": str, "costing_method": str}
    """
    async with get_conn() as conn:
        item = await conn.fetchrow(
            _q("SELECT costing_method FROM inventory_items WHERE id = %s AND tenant_id = %s"),
            item_id, tenant_id,
        )
        costing_method = (item["costing_method"] if item else None) or "fifo"

        rows = await conn.fetch(
            _q("""
                SELECT quantity, unit_cost
                FROM stock_movements
                WHERE tenant_id = %s AND item_id = %s
                  AND movement_type = 'in'
                  AND movement_date <= %s
                ORDER BY movement_date, id
            """),
            tenant_id, item_id, as_of_date,
        )

    purchases = [{"qty": float(r["quantity"]), "cost": float(r["unit_cost"])} for r in rows]
    result = compute_cogs(costing_method, purchases, dispatch_qty)
    result.update({
        "item_id": item_id,
        "dispatch_qty": dispatch_qty,
        "as_of_date": as_of_date,
        "costing_method": costing_method,
    })
    return result


def cogs_journal_lines(cogs_amount: float) -> list[dict]:
    """Return standard COGS debit / Inventory credit journal lines."""
    return [
        {"account_code": "7110", "label": "COGS", "debit": cogs_amount, "credit": 0.0},
        {"account_code": "1310", "label": "Inventory", "debit": 0.0, "credit": cogs_amount},
    ]
