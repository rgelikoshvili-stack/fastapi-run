"""app/api/services/cfo_dashboard_service.py
CFO Financial Dashboard — aggregates key metrics across all financial domains.

Two entry points:
  build_cfo_dashboard_from_data(...)  — pure function, accepts pre-fetched data dicts,
                                        fully testable without DB.
  build_cfo_dashboard(conn, tenant_id, as_of, date_from, date_to)
                                      — DB-backed async function that fetches data and
                                        delegates to the pure function.

Dashboard sections:
  cash_position    — 1110 + 1120 balances and net cashflow
  profitability    — revenue, COGS, gross profit/margin, OPEX, net P&L, net margin
  vat_position     — input VAT (3311), output VAT (3310), net VAT receivable/payable
  ar_status        — total AR, overdue AR, aging bucket summary
  ap_status        — total AP, overdue AP, aging bucket summary
  inventory        — total inventory value and quantity (from trial balance)
  rsge_summary     — document count, waybill count, mismatch/risk counts
  workflow         — unapproved drafts, pending approvals, posted entries
  fixed_assets     — cost (1510), accum depreciation (1520), NBV, monthly depreciation
  payroll          — gross, PIT, PAYG, net payable
  period_lock      — current period lock status
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── Forbidden fields — must never appear in dashboard output ──────────────────
_FORBIDDEN_FIELDS = frozenset({
    "access_token", "pin_token", "Authorization", "password",
    "JWT_SECRET", "DATABASE_URL", "ANTHROPIC_API_KEY",
    "BALANCE_API_KEY", "VAULT_ENCRYPTION_KEY", "rsge_password",
})

# ── Account codes used in metric calculations ─────────────────────────────────
_CASH_ACCOUNTS   = ("1110", "1120")
_INPUT_VAT       = "3311"
_OUTPUT_VAT      = "3310"
_FA_COST         = "1510"
_FA_DEPR         = "1520"
_INVENTORY       = "1310"

# ── Aging bucket names (must match routes_aging.py _BUCKETS) ─────────────────
AGING_BUCKETS = ("current_0_30", "31_60", "61_90", "91_120", "over_120")


def _safe(d: dict, *keys) -> Any:
    """Safe nested dict access, returns None if any key is missing."""
    v = d
    for k in keys:
        if not isinstance(v, dict):
            return None
        v = v.get(k)
    return v


def _pct(numerator: float, denominator: float) -> Optional[float]:
    if not denominator:
        return None
    return round(numerator / denominator * 100, 2)


def _strip_forbidden(d: dict) -> dict:
    """Recursively remove any key that matches a forbidden field name."""
    cleaned = {}
    for k, v in d.items():
        if k in _FORBIDDEN_FIELDS:
            continue
        if isinstance(v, dict):
            cleaned[k] = _strip_forbidden(v)
        else:
            cleaned[k] = v
    return cleaned


# ── Pure aggregation function ─────────────────────────────────────────────────

def build_cfo_dashboard_from_data(
    trial_balance: dict[str, float],
    pnl: dict[str, Any],
    cashflow: dict[str, Any] | None = None,
    ar_aging: dict[str, Any] | None = None,
    ap_aging: dict[str, Any] | None = None,
    rsge_summary: dict[str, Any] | None = None,
    draft_counts: dict[str, Any] | None = None,
    fixed_asset_data: dict[str, Any] | None = None,
    payroll_data: dict[str, Any] | None = None,
    period_lock: dict[str, Any] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Build CFO dashboard from pre-fetched domain data.

    All arguments are optional dicts — missing sections report partial data.
    This function is pure (no DB, no IO), fully testable.

    Args:
        trial_balance: {account_code: net_balance} (positive=debit for assets/expenses)
        pnl: P&L response data dict (from build_profit_and_loss)
        cashflow: Cashflow response data dict (from build_cashflow_statement)
        ar_aging: AR aging summary dict (from routes_aging)
        ap_aging: AP aging summary dict (from routes_aging)
        rsge_summary: RS.ge mismatch/document summary dict
        draft_counts: {drafted, awaiting_cfo, approved, posted, rejected, total}
        fixed_asset_data: {cost, accum_depreciation, monthly_depreciation}
        payroll_data: {gross, pit, payg_employee, payg_employer, net_payable}
        period_lock: {locked: bool, period: str}
        as_of: reporting date string

    Returns:
        CFO dashboard dict with all sections.
    """
    tb = trial_balance or {}

    # ── Cash position ─────────────────────────────────────────────────────────
    cash_1110 = round(float(tb.get("1110", 0.0)), 2)
    bank_1120 = round(float(tb.get("1120", 0.0)), 2)
    total_liquid = round(cash_1110 + bank_1120, 2)

    cf_operating  = 0.0
    cf_investing  = 0.0
    cf_financing  = 0.0
    cf_net_change = 0.0
    if cashflow:
        cf_operating  = round(float(_safe(cashflow, "operating",  "net") or 0), 2)
        cf_investing  = round(float(_safe(cashflow, "investing",  "net") or 0), 2)
        cf_financing  = round(float(_safe(cashflow, "financing",  "net") or 0), 2)
        cf_net_change = round(float(cashflow.get("net_change_in_cash") or 0), 2)

    cash_position = {
        "cash_1110":       cash_1110,
        "bank_1120":       bank_1120,
        "total_liquid":    total_liquid,
        "net_cashflow":    cf_net_change,
        "operating_cf":    cf_operating,
        "investing_cf":    cf_investing,
        "financing_cf":    cf_financing,
    }

    # ── Profitability ─────────────────────────────────────────────────────────
    revenue     = round(float(_safe(pnl, "revenue",  "total") or 0), 2)
    cogs        = round(float(_safe(pnl, "cogs",     "total") or 0), 2)
    gross_profit = round(float(pnl.get("gross_profit") or 0), 2)
    opex        = round(float(_safe(pnl, "opex",     "total") or 0), 2)
    ebit        = round(float(pnl.get("ebit") or 0), 2)

    profitability = {
        "revenue":         revenue,
        "cogs":            cogs,
        "gross_profit":    gross_profit,
        "gross_margin_pct": _pct(gross_profit, revenue),
        "opex":            opex,
        "net_profit_loss": ebit,
        "net_margin_pct":  _pct(ebit, revenue),
    }

    # ── VAT position ─────────────────────────────────────────────────────────
    input_vat  = round(float(tb.get(_INPUT_VAT,  0.0)), 2)
    output_vat = round(float(tb.get(_OUTPUT_VAT, 0.0)), 2)
    # For 3311 (input VAT asset): positive debit = receivable from tax authority
    # For 3310 (output VAT liability): positive credit = payable to tax authority
    # net > 0 = receivable; net < 0 = payable
    net_vat = round(input_vat - output_vat, 2)
    vat_label = "vat_receivable" if net_vat >= 0 else "vat_payable"

    vat_position = {
        "input_vat":   input_vat,
        "output_vat":  output_vat,
        "net_vat":     net_vat,
        "label":       vat_label,
    }

    # ── AR status ─────────────────────────────────────────────────────────────
    ar_total   = 0.0
    ar_overdue = 0.0
    ar_buckets: dict[str, float] = {b: 0.0 for b in AGING_BUCKETS}
    if ar_aging:
        for bucket_key in AGING_BUCKETS:
            bucket_data = ar_aging.get(bucket_key) or {}
            amount = float(bucket_data.get("amount") or 0)
            ar_buckets[bucket_key] = round(amount, 2)
            ar_total += amount
        ar_overdue = round(
            ar_buckets["31_60"] + ar_buckets["61_90"] +
            ar_buckets["91_120"] + ar_buckets["over_120"],
            2,
        )
        ar_total = round(ar_total, 2)

    ar_status = {
        "total_ar":   ar_total,
        "overdue_ar": ar_overdue,
        "buckets":    ar_buckets,
    }

    # ── AP status ─────────────────────────────────────────────────────────────
    ap_total   = 0.0
    ap_overdue = 0.0
    ap_buckets: dict[str, float] = {b: 0.0 for b in AGING_BUCKETS}
    if ap_aging:
        for bucket_key in AGING_BUCKETS:
            bucket_data = ap_aging.get(bucket_key) or {}
            amount = float(bucket_data.get("amount") or 0)
            ap_buckets[bucket_key] = round(amount, 2)
            ap_total += amount
        ap_overdue = round(
            ap_buckets["31_60"] + ap_buckets["61_90"] +
            ap_buckets["91_120"] + ap_buckets["over_120"],
            2,
        )
        ap_total = round(ap_total, 2)

    ap_status = {
        "total_ap":   ap_total,
        "overdue_ap": ap_overdue,
        "buckets":    ap_buckets,
    }

    # ── Inventory ─────────────────────────────────────────────────────────────
    inventory_value = round(float(tb.get(_INVENTORY, 0.0)), 2)
    low_stock_count = 0
    low_stock_note  = "low-stock rules not implemented; count reported as 0"
    if isinstance(fixed_asset_data, dict) and "low_stock" in (fixed_asset_data or {}):
        low_stock_count = int(fixed_asset_data.get("low_stock", 0))
        low_stock_note  = ""

    inventory_metrics = {
        "total_inventory_value": inventory_value,
        "low_stock_count":       low_stock_count,
        "low_stock_note":        low_stock_note,
    }

    # ── RS.ge summary ─────────────────────────────────────────────────────────
    rs = rsge_summary or {}
    rsge_metrics = {
        "synced_documents":    int(rs.get("synced_documents",    0)),
        "synced_waybills":     int(rs.get("synced_waybills",     0)),
        "total_mismatches":    int(rs.get("total_mismatches",    0)),
        "high_risk_mismatches":int(rs.get("high_risk_mismatches",0)),
        "unlinked_waybills":   int(rs.get("unlinked_waybills",   0)),
    }

    # ── Workflow / approvals ──────────────────────────────────────────────────
    dc = draft_counts or {}
    workflow = {
        "unapproved_drafts":  int(dc.get("drafted", 0)),
        "awaiting_cfo":       int(dc.get("awaiting_cfo", 0)),
        "posted_entries":     int(dc.get("posted", 0)),
        "rejected":           int(dc.get("rejected", 0)),
        "total_drafts":       int(dc.get("total", 0)),
    }

    # ── Fixed assets ──────────────────────────────────────────────────────────
    fa_cost  = round(float(tb.get(_FA_COST, 0.0)), 2)
    fa_depr  = round(abs(float(tb.get(_FA_DEPR, 0.0))), 2)  # 1520 credit balance → positive
    fa_nbv   = round(fa_cost - fa_depr, 2)
    fa_monthly_depr = 0.0
    if isinstance(fixed_asset_data, dict):
        fa_monthly_depr = round(float(fixed_asset_data.get("monthly_depreciation", 0.0)), 2)

    fixed_assets = {
        "cost":                 fa_cost,
        "accumulated_depr":     fa_depr,
        "net_book_value":       fa_nbv,
        "monthly_depreciation": fa_monthly_depr,
    }

    # ── Payroll ───────────────────────────────────────────────────────────────
    pr = payroll_data or {}
    payroll = {
        "gross":       round(float(pr.get("gross",       0.0)), 2),
        "pit":         round(float(pr.get("pit",         0.0)), 2),
        "payg_employee": round(float(pr.get("payg_employee", 0.0)), 2),
        "payg_employer": round(float(pr.get("payg_employer", 0.0)), 2),
        "net_payable": round(float(pr.get("net_payable",  0.0)), 2),
    }

    # ── Period lock ───────────────────────────────────────────────────────────
    pl = period_lock or {}
    period_lock_status = {
        "locked":  bool(pl.get("locked", False)),
        "period":  pl.get("period", ""),
    }

    dashboard = {
        "as_of":           as_of,
        "cash_position":   cash_position,
        "profitability":   profitability,
        "vat_position":    vat_position,
        "ar_status":       ar_status,
        "ap_status":       ap_status,
        "inventory":       inventory_metrics,
        "rsge_summary":    rsge_metrics,
        "workflow":        workflow,
        "fixed_assets":    fixed_assets,
        "payroll":         payroll,
        "period_lock":     period_lock_status,
    }

    # Final safety: strip any forbidden fields that may have crept in
    return _strip_forbidden(dashboard)


# ── DB-backed async function ──────────────────────────────────────────────────

async def build_cfo_dashboard(
    tenant_id: str,
    as_of: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict[str, Any]:
    """Build CFO dashboard from live DB data.

    Calls financial_statements_service, routing_aging, and other services,
    then delegates to build_cfo_dashboard_from_data().
    """
    from app.api.db import get_conn, _q
    from app.api.services.financial_statements_service import (
        _get_trial_balance,
        build_profit_and_loss,
        build_cashflow_statement,
    )

    try:
        tb = await _get_trial_balance(tenant_id, date_from, date_to)
    except Exception as e:
        log.warning("CFO dashboard: trial balance unavailable: %s", e)
        tb = {}

    pnl_resp = await build_profit_and_loss(tenant_id, date_from, date_to)
    pnl_data = (pnl_resp.get("data") or {}) if pnl_resp.get("ok") else {}

    cf_resp = await build_cashflow_statement(tenant_id, date_from, date_to)
    cf_data = (cf_resp.get("data") or {}) if cf_resp.get("ok") else None

    # Draft counts
    draft_counts: dict[str, Any] = {}
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(
                _q("""
                    SELECT status, COUNT(*) AS cnt
                    FROM journal_drafts
                    WHERE tenant_id = %s
                    GROUP BY status
                """),
                tenant_id,
            )
            draft_counts = {r["status"]: int(r["cnt"]) for r in rows}
            draft_counts["total"] = sum(draft_counts.values())
    except Exception as e:
        log.warning("CFO dashboard: draft counts unavailable: %s", e)

    # RS.ge summary
    rsge_summary: dict[str, Any] = {}
    try:
        async with get_conn() as conn:
            doc_count = await conn.fetchval(
                _q("SELECT COUNT(*) FROM rsge_documents WHERE tenant_id = %s"),
                tenant_id,
            ) or 0
            wb_count = await conn.fetchval(
                _q("SELECT COUNT(*) FROM rsge_waybills WHERE tenant_id = %s"),
                tenant_id,
            ) or 0
            mismatch_count = await conn.fetchval(
                _q("""
                    SELECT COUNT(*) FROM rsge_documents
                    WHERE tenant_id = %s AND mismatch_type IS NOT NULL
                """),
                tenant_id,
            ) or 0
            high_risk_count = await conn.fetchval(
                _q("""
                    SELECT COUNT(*) FROM rsge_documents
                    WHERE tenant_id = %s AND risk_level = 'high'
                """),
                tenant_id,
            ) or 0
            unlinked_wb = await conn.fetchval(
                _q("""
                    SELECT COUNT(*) FROM rsge_waybills
                    WHERE tenant_id = %s AND linked_invoice_id IS NULL
                """),
                tenant_id,
            ) or 0
        rsge_summary = {
            "synced_documents":    int(doc_count),
            "synced_waybills":     int(wb_count),
            "total_mismatches":    int(mismatch_count),
            "high_risk_mismatches":int(high_risk_count),
            "unlinked_waybills":   int(unlinked_wb),
        }
    except Exception as e:
        log.warning("CFO dashboard: RS.ge summary unavailable: %s", e)

    # Fixed asset monthly depreciation (latest posted entry for 7610)
    fixed_asset_data: dict[str, Any] = {}
    try:
        async with get_conn() as conn:
            depr_row = await conn.fetchrow(
                _q("""
                    SELECT COALESCE(SUM(CAST(entry->>'amount' AS NUMERIC)), 0) AS monthly_depr
                    FROM journal_drafts jd
                    CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
                    WHERE jd.tenant_id = %s
                      AND jd.status = 'posted'
                      AND COALESCE(entry->>'dr', '') = '7610'
                """),
                tenant_id,
            )
            fixed_asset_data["monthly_depreciation"] = float(depr_row["monthly_depr"] or 0)
    except Exception as e:
        log.warning("CFO dashboard: fixed asset depreciation unavailable: %s", e)

    # Period lock status
    period_lock_status: dict[str, Any] = {"locked": False, "period": as_of or ""}
    try:
        async with get_conn() as conn:
            period_key = (as_of or "")[:7]  # YYYY-MM
            locked = await conn.fetchval(
                _q("""
                    SELECT COUNT(*) > 0 FROM period_locks
                    WHERE tenant_id = %s AND period_key = %s
                """),
                tenant_id, period_key,
            )
            period_lock_status = {"locked": bool(locked), "period": period_key}
    except Exception as e:
        log.warning("CFO dashboard: period lock unavailable: %s", e)

    result = build_cfo_dashboard_from_data(
        trial_balance=tb,
        pnl=pnl_data,
        cashflow=cf_data,
        rsge_summary=rsge_summary,
        draft_counts=draft_counts,
        fixed_asset_data=fixed_asset_data,
        period_lock=period_lock_status,
        as_of=as_of,
    )
    return result
