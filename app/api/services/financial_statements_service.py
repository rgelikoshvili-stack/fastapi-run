"""app/api/services/financial_statements_service.py
IAS 1-compliant P&L and Balance Sheet from posted journal entries only.
"""
from __future__ import annotations
import logging
import os
from typing import Optional
from datetime import date

from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response

log = logging.getLogger(__name__)

# ── Feature-flag helpers ───────────────────────────────────────────────────

STANDARD_NET_STATUSES = ("posted", "correction")
FORBIDDEN_STATUSES = frozenset({
    "draft", "approved", "auto_approved",
    "simulated_success", "mock_posting", "dry_run",
})


def _posted_ledger_reports_enabled() -> bool:
    """Return True only when POSTED_LEDGER_REPORTS_ENABLED is explicitly set."""
    return os.getenv("POSTED_LEDGER_REPORTS_ENABLED", "").lower() in ("1", "true", "yes")


def _require_tenant_id(tenant_id: str) -> None:
    """Raise ValueError when tenant_id is absent or empty (fail closed)."""
    if not tenant_id:
        raise ValueError("tenant_id is required and must not be empty")


def _assert_no_silent_fallback(sql: str) -> None:
    """Raise ValueError if the posted-ledger SQL references journal_drafts."""
    if "journal_drafts" in sql:
        raise ValueError(
            "Posted-ledger query must not reference journal_drafts — no silent fallback allowed"
        )


# ── Posted-ledger query builders (return SQL + params, never execute) ──────

def _build_pnl_posted_ledger_query(
    tenant_id: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[str, list]:
    """Return (sql, params) for P&L from journal_entry_headers + journal_entry_lines."""
    _require_tenant_id(tenant_id)
    params: list = [tenant_id, list(STANDARD_NET_STATUSES)]
    date_filter = ""
    if date_from:
        params.append(date_from)
        date_filter += f" AND jeh.entry_date >= ${len(params)}"
    if date_to:
        params.append(date_to)
        date_filter += f" AND jeh.entry_date <= ${len(params)}"
    sql = f"""
        SELECT jel.account_code,
               jel.account_type,
               SUM(jel.debit)  AS total_debit,
               SUM(jel.credit) AS total_credit,
               MAX(jeh.source_draft_id)    AS source_draft_id,
               MAX(jeh.posting_log_id)     AS posting_log_id,
               MAX(jeh.evidence_bundle_id) AS evidence_bundle_id
        FROM journal_entry_lines jel
        JOIN journal_entry_headers jeh ON jeh.id = jel.journal_entry_id
        WHERE jeh.tenant_id = $1
          AND jeh.status = ANY($2)
          AND jel.account_type IN ('income', 'expense')
          {date_filter}
        GROUP BY jel.account_code, jel.account_type
        ORDER BY jel.account_code
    """
    _assert_no_silent_fallback(sql)
    return sql, params


def _build_balance_sheet_posted_ledger_query(
    tenant_id: str,
    as_of: Optional[str],
) -> tuple[str, list]:
    """Return (sql, params) for Balance Sheet from journal_entry_headers + journal_entry_lines."""
    _require_tenant_id(tenant_id)
    params: list = [tenant_id, list(STANDARD_NET_STATUSES)]
    as_of_filter = ""
    if as_of:
        params.append(as_of)
        as_of_filter = f" AND jeh.entry_date <= ${len(params)}"
    sql = f"""
        SELECT jel.account_code,
               jel.account_type,
               SUM(jel.debit)  AS total_debit,
               SUM(jel.credit) AS total_credit
        FROM journal_entry_lines jel
        JOIN journal_entry_headers jeh ON jeh.id = jel.journal_entry_id
        WHERE jeh.tenant_id = $1
          AND jeh.status = ANY($2)
          AND jel.account_type IN ('asset', 'liability', 'equity')
          {as_of_filter}
        GROUP BY jel.account_code, jel.account_type
        ORDER BY jel.account_code
    """
    _assert_no_silent_fallback(sql)
    return sql, params


def _build_cashflow_posted_ledger_query(
    tenant_id: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[str, list]:
    """Return (sql, params) for Cashflow from journal_entry_headers + journal_entry_lines."""
    _require_tenant_id(tenant_id)
    params: list = [tenant_id, list(STANDARD_NET_STATUSES)]
    date_filter = ""
    if date_from:
        params.append(date_from)
        date_filter += f" AND jeh.entry_date >= ${len(params)}"
    if date_to:
        params.append(date_to)
        date_filter += f" AND jeh.entry_date <= ${len(params)}"
    sql = f"""
        SELECT jel.cashflow_category,
               SUM(jel.debit)  AS total_debit,
               SUM(jel.credit) AS total_credit
        FROM journal_entry_lines jel
        JOIN journal_entry_headers jeh ON jeh.id = jel.journal_entry_id
        WHERE jeh.tenant_id = $1
          AND jeh.status = ANY($2)
          AND jel.account_code LIKE '1%'
          {date_filter}
        GROUP BY jel.cashflow_category
        ORDER BY jel.cashflow_category
    """
    _assert_no_silent_fallback(sql)
    return sql, params

# ── Account classification map ─────────────────────────────────────────────
# Each account: net = debit - credit for assets/expenses; credit - debit for liabilities/equity/revenue

_BALANCE_SHEET = {
    # Current Assets
    "1110": ("assets", "current",     "ნაღდი / სალარო"),
    "1120": ("assets", "current",     "საბანკო ანგარიში"),
    "1130": ("assets", "current",     "სხვა ფულის ექვივალენტი"),
    "1210": ("assets", "current",     "მოთხოვნები კლიენტებზე"),
    "1220": ("assets", "current",     "საეჭვო მოთხოვნები"),
    "1310": ("assets", "current",     "მარაგები / საქონელი"),
    "1320": ("assets", "current",     "მზა პროდუქცია"),
    "1330": ("assets", "current",     "უდამთავრებელი წარმოება"),
    "1410": ("assets", "current",     "სხვა მოკლევადიანი მოთხოვნები"),
    "1420": ("assets", "current",     "გადახდილი ავანსები"),
    "1430": ("assets", "current",     "წინასწარ გადახდილი ხარჯები"),
    "1760": ("assets", "current",     "დღგ ჩათვლა (Input VAT)"),
    "3311": ("assets", "current",     "ჩათვლილი დღგ"),
    # Non-current Assets
    "1510": ("assets", "non_current", "ძირითადი საშუალებები"),
    "1520": ("assets", "non_current", "დარიცხული ამორტიზაცია (კ.)"),  # contra
    "1610": ("assets", "non_current", "არამატერიალური აქტივები"),
    "1620": ("assets", "non_current", "გრძელვადიანი ინვესტიცია"),
    "1710": ("assets", "non_current", "ROU აქტივი (IFRS 16)"),
    # Current Liabilities
    "3110": ("liabilities", "current",     "კრედიტორული დავალიანება"),
    "3120": ("liabilities", "current",     "მიღებული ავანსები"),
    "3130": ("liabilities", "current",     "გადასახდელი ხარჯები"),
    "3310": ("liabilities", "current",     "დღგ გადასახდელი"),
    "3320": ("liabilities", "current",     "PIT გადასახდელი"),
    "3330": ("liabilities", "current",     "დასაქმებულის საპენსიო"),
    "3335": ("liabilities", "current",     "დამქირავებლის საპენსიო"),
    "3340": ("liabilities", "current",     "CIT გადასახდელი"),
    "3350": ("liabilities", "current",     "Withholding გადასახდელი"),
    "3360": ("liabilities", "current",     "გადახდელი ხელფასი (net)"),
    "3370": ("liabilities", "current",     "გადასახდელი დივიდენდი"),
    "3380": ("liabilities", "current",     "სხვა გადასახადი"),
    # Non-current Liabilities
    "3410": ("liabilities", "non_current", "სასესხო ვალდებულება"),
    "3420": ("liabilities", "non_current", "გარანტია / თავდებობა"),
    "3430": ("liabilities", "non_current", "ფინ. იჯარა (IFRS 16)"),
    "3510": ("liabilities", "non_current", "გრძელვადიანი სასესხო ვალდ."),
    # Equity
    "4110": ("equity", "equity", "საწესდებო კაპიტალი"),
    "4120": ("equity", "equity", "დამატებითი კაპიტალი"),
    "4210": ("equity", "equity", "გაუნაწილებელი მოგება (RE)"),
    "4220": ("equity", "equity", "სარეზერვო კაპიტალი"),
}

_PNL = {
    # Revenue
    "6110": ("revenue", "გ-ვ. შემოსავალი"),
    "6120": ("revenue", "მომსახურების შემოსავალი"),
    "6130": ("revenue", "სხვა ოპ. შემოსავალი"),
    "6140": ("revenue", "პასიური შემოსავალი"),
    "6150": ("revenue", "სხვა შემოსავალი"),
    # COGS
    "7110": ("cogs",    "გაყიდული საქ. ღირებულება (COGS)"),
    "7120": ("cogs",    "პირდაპირი ხარჯი"),
    # Operating Expenses
    "7210": ("opex",    "ხელფასი და დანამატები"),
    "7220": ("opex",    "დამატებითი სამ. ხარჯი"),
    "7230": ("opex",    "სხვა შრ. ხარჯი"),
    "7310": ("opex",    "ქირა"),
    "7320": ("opex",    "ოფ. ლოჯ. ხარჯი"),
    "7410": ("opex",    "კომ. ხარჯი (utilities)"),
    "7510": ("opex",    "საბანკო საკომისიო"),
    "7520": ("opex",    "საბანკო პროცენტი"),
    "7610": ("opex",    "ამორტიზაცია"),
    "7710": ("opex",    "რეკლამა / მარკეტინგი"),
    "7720": ("opex",    "წარმომადგენლობითი ხარჯი"),
    "7730": ("opex",    "სატრანსპორტო ხარჯი"),
    "7810": ("opex",    "სხვა ადმინ. ხარჯი"),
    "7910": ("opex",    "სხვა ხარჯი"),
    "7920": ("opex",    "გაცვლითი კურსის ზარალი"),
}


async def _get_trial_balance(
    tenant_id: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> dict:
    """Return {account_code: net_balance} from posted journal entries only."""
    params: list = [tenant_id]
    date_filter = ""
    if date_from:
        date_filter += " AND jd.date >= %s"
        params.append(date_from)
    if date_to:
        date_filter += " AND jd.date <= %s"
        params.append(date_to)

    sql = _q(f"""
        SELECT
            COALESCE(entry->>'dr', entry->>'cr') AS account_code,
            CASE WHEN entry->>'dr' IS NOT NULL THEN 'debit' ELSE 'credit' END AS side,
            SUM(CAST(COALESCE(entry->>'amount', '0') AS NUMERIC)) AS total
        FROM journal_drafts jd
        CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
          {date_filter}
          AND (entry->>'dr' IS NOT NULL OR entry->>'cr' IS NOT NULL)
        GROUP BY COALESCE(entry->>'dr', entry->>'cr'),
                 CASE WHEN entry->>'dr' IS NOT NULL THEN 'debit' ELSE 'credit' END
    """)

    async with get_conn() as conn:
        rows = await conn.fetch(sql, *params)

    balances: dict[str, float] = {}
    for row in rows:
        code = row["account_code"]
        if not code:
            continue
        val = float(row["total"] or 0)
        if code not in balances:
            balances[code] = 0.0
        if row["side"] == "debit":
            balances[code] += val
        else:
            balances[code] -= val
    return balances  # positive = net debit balance


async def _build_pnl_from_posted_ledger(
    tenant_id: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> dict:
    """Execute posted-ledger P&L query; fail closed if tables unavailable."""
    _require_tenant_id(tenant_id)
    sql, params = _build_pnl_posted_ledger_query(tenant_id, date_from, date_to)
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(sql, *params)
    except Exception as e:
        log.error("Posted-ledger P&L unavailable: %s", e)
        return error_response("Posted-ledger P&L unavailable", "POSTED_LEDGER_UNAVAILABLE", str(e))

    revenue_lines, cogs_lines, opex_lines = [], [], []
    for row in rows:
        code = row["account_code"]
        acct_type = row.get("account_type", "")
        total_dr = float(row["total_debit"] or 0)
        total_cr = float(row["total_credit"] or 0)
        audit = {
            "source_draft_id": row.get("source_draft_id"),
            "posting_log_id": row.get("posting_log_id"),
            "evidence_bundle_id": row.get("evidence_bundle_id"),
        }
        pnl_meta = _PNL.get(code)
        if acct_type == "income":
            amount = round(total_cr - total_dr, 2)
            revenue_lines.append({"account_code": code,
                                   "label": pnl_meta[1] if pnl_meta else code,
                                   "amount": amount, **audit})
        elif acct_type == "expense":
            amount = round(total_dr - total_cr, 2)
            section = pnl_meta[0] if pnl_meta else "opex"
            label = pnl_meta[1] if pnl_meta else code
            line = {"account_code": code, "label": label, "amount": amount, **audit}
            (cogs_lines if section == "cogs" else opex_lines).append(line)

    total_revenue = round(sum(l["amount"] for l in revenue_lines), 2)
    total_cogs    = round(sum(l["amount"] for l in cogs_lines), 2)
    gross_profit  = round(total_revenue - total_cogs, 2)
    total_opex    = round(sum(l["amount"] for l in opex_lines), 2)
    ebit          = round(gross_profit - total_opex, 2)

    return ok_response("P&L built (posted ledger)", {
        "source": "posted_ledger",
        "period": {"from": date_from, "to": date_to},
        "revenue":      {"lines": revenue_lines, "total": total_revenue},
        "cogs":         {"lines": cogs_lines,    "total": total_cogs},
        "gross_profit": gross_profit,
        "opex":         {"lines": opex_lines,    "total": total_opex},
        "ebit":         ebit,
        "currency":     "GEL",
    })


async def build_profit_and_loss(
    tenant_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    if _posted_ledger_reports_enabled():
        return await _build_pnl_from_posted_ledger(tenant_id, date_from, date_to)

    try:
        tb = await _get_trial_balance(tenant_id, date_from, date_to)
    except Exception as e:
        log.error("P&L trial balance failed: %s", e)
        return error_response("P&L build failed", "DB_ERROR", str(e))

    revenue_lines, cogs_lines, opex_lines = [], [], []

    for code, (section, label) in _PNL.items():
        net = tb.get(code, 0.0)
        if net == 0.0:
            continue
        amount = -net if section == "revenue" else net
        line = {"account_code": code, "label": label, "amount": round(amount, 2)}
        if section == "revenue":
            revenue_lines.append(line)
        elif section == "cogs":
            cogs_lines.append(line)
        else:
            opex_lines.append(line)

    total_revenue = round(sum(l["amount"] for l in revenue_lines), 2)
    total_cogs    = round(sum(l["amount"] for l in cogs_lines), 2)
    gross_profit  = round(total_revenue - total_cogs, 2)
    total_opex    = round(sum(l["amount"] for l in opex_lines), 2)
    ebit          = round(gross_profit - total_opex, 2)

    return ok_response("P&L built", {
        "period": {"from": date_from, "to": date_to},
        "revenue":       {"lines": revenue_lines, "total": total_revenue},
        "cogs":          {"lines": cogs_lines,    "total": total_cogs},
        "gross_profit":  gross_profit,
        "opex":          {"lines": opex_lines,    "total": total_opex},
        "ebit":          ebit,
        "currency":      "GEL",
    })


async def _build_balance_sheet_from_posted_ledger(
    tenant_id: str,
    as_of: Optional[str],
) -> dict:
    """Execute posted-ledger Balance Sheet query; fail closed if tables unavailable."""
    _require_tenant_id(tenant_id)
    sql, params = _build_balance_sheet_posted_ledger_query(tenant_id, as_of)
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(sql, *params)
    except Exception as e:
        log.error("Posted-ledger Balance Sheet unavailable: %s", e)
        return error_response("Posted-ledger Balance Sheet unavailable",
                              "POSTED_LEDGER_UNAVAILABLE", str(e))

    sections: dict = {
        "assets":      {"current": [], "non_current": []},
        "liabilities": {"current": [], "non_current": []},
        "equity":      {"equity":  []},
    }
    for row in rows:
        code = row["account_code"]
        acct_type = row.get("account_type", "")
        total_dr = float(row["total_debit"] or 0)
        total_cr = float(row["total_credit"] or 0)
        bs_meta = _BALANCE_SHEET.get(code)
        group = acct_type if acct_type in sections else "assets"
        sub = bs_meta[1] if bs_meta else ("current" if group != "equity" else "equity")
        if group not in sections or sub not in sections.get(group, {}):
            continue
        amount = round((total_dr - total_cr) if group == "assets" else (total_cr - total_dr), 2)
        sections[group][sub].append({
            "account_code": code,
            "label": bs_meta[2] if bs_meta else code,
            "amount": amount,
        })

    total_current_assets    = round(sum(l["amount"] for l in sections["assets"]["current"]), 2)
    total_noncurrent_assets = round(sum(l["amount"] for l in sections["assets"]["non_current"]), 2)
    total_assets            = round(total_current_assets + total_noncurrent_assets, 2)
    total_current_liab      = round(sum(l["amount"] for l in sections["liabilities"]["current"]), 2)
    total_noncurrent_liab   = round(sum(l["amount"] for l in sections["liabilities"]["non_current"]), 2)
    total_liabilities       = round(total_current_liab + total_noncurrent_liab, 2)
    total_equity            = round(sum(l["amount"] for l in sections["equity"]["equity"]), 2)
    total_le                = round(total_liabilities + total_equity, 2)

    return ok_response("Balance Sheet built (posted ledger)", {
        "source": "posted_ledger",
        "as_of": as_of or date.today().isoformat(),
        "assets": {
            "current":     {"lines": sections["assets"]["current"],     "total": total_current_assets},
            "non_current": {"lines": sections["assets"]["non_current"], "total": total_noncurrent_assets},
            "total":       total_assets,
        },
        "liabilities": {
            "current":     {"lines": sections["liabilities"]["current"],     "total": total_current_liab},
            "non_current": {"lines": sections["liabilities"]["non_current"], "total": total_noncurrent_liab},
            "total":       total_liabilities,
        },
        "equity": {"lines": sections["equity"]["equity"], "total": total_equity},
        "total_liabilities_and_equity": total_le,
        "balanced": abs(total_assets - total_le) < 0.05,
        "currency": "GEL",
    })


async def build_cashflow_statement(
    tenant_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """IAS 7 — Statement of Cash Flows (direct method from posted journal lines).

    Reads all posted journal entry lines, identifies lines touching cash/bank
    accounts (1110, 1120), classifies each pair into operating/investing/financing,
    and sums up the totals.  Falls back gracefully when no DB is available.
    """
    from app.api.services.cashflow_classification_service import build_cashflow_direct
    _require_tenant_id(tenant_id)

    params: list = [tenant_id, list(STANDARD_NET_STATUSES)]
    date_filter = ""
    if date_from:
        params.append(date_from)
        date_filter += f" AND jeh.entry_date >= ${len(params)}"
    if date_to:
        params.append(date_to)
        date_filter += f" AND jeh.entry_date <= ${len(params)}"

    # Fetch all journal entry lines from posted headers in the period
    sql = f"""
        SELECT
            jel.account_code,
            jel.debit,
            jel.credit,
            jel.description,
            jel.account_type,
            jeh.id AS header_id
        FROM journal_entry_lines jel
        JOIN journal_entry_headers jeh ON jeh.id = jel.journal_entry_id
        WHERE jeh.tenant_id = $1
          AND jeh.status = ANY($2)
          {date_filter}
        ORDER BY jeh.id, jel.id
    """

    # Fall back to journal_drafts table when new schema unavailable
    fallback_sql = _q(f"""
        SELECT
            COALESCE(entry->>'dr', '')  AS dr_account,
            COALESCE(entry->>'cr', '')  AS cr_account,
            CAST(COALESCE(entry->>'amount', '0') AS NUMERIC) AS amount,
            COALESCE(entry->>'description', '') AS description
        FROM journal_drafts jd
        CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
        ORDER BY jd.id
    """)

    pairs: list[dict] = []
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(sql, *params)

        # Group lines by header_id to form DR/CR pairs
        from collections import defaultdict
        by_header: dict = defaultdict(list)
        for row in rows:
            by_header[row["header_id"]].append(row)

        for header_lines in by_header.values():
            debits  = [r for r in header_lines if float(r["debit"]  or 0) > 0]
            credits = [r for r in header_lines if float(r["credit"] or 0) > 0]
            # Emit each DR/CR combination as a potential cash movement pair
            for d in debits:
                for c in credits:
                    pairs.append({
                        "dr": d["account_code"],
                        "cr": c["account_code"],
                        "amount": float(d["debit"] or 0),
                        "description": d["description"] or "",
                    })

    except Exception as e:
        log.warning("journal_entry_lines unavailable (%s), trying journal_drafts", e)
        try:
            async with get_conn() as conn:
                fallback_params: list = [tenant_id]
                if date_from:
                    fallback_sql_with_date = fallback_sql.replace(
                        "jd.status = 'posted'",
                        f"jd.status = 'posted' AND jd.date >= %s"
                    )
                    fallback_params.append(date_from)
                    if date_to:
                        fallback_sql_with_date = fallback_sql_with_date.replace(
                            f"jd.date >= %s",
                            f"jd.date >= %s AND jd.date <= %s"
                        )
                        fallback_params.append(date_to)
                else:
                    fallback_sql_with_date = fallback_sql

                rows = await conn.fetch(fallback_sql_with_date, *fallback_params)
                for row in rows:
                    pairs.append({
                        "dr": row["dr_account"],
                        "cr": row["cr_account"],
                        "amount": float(row["amount"] or 0),
                        "description": row["description"] or "",
                    })
        except Exception as e2:
            log.error("Cashflow DB unavailable: %s", e2)
            return error_response("Cashflow statement unavailable", "DB_ERROR", str(e2))

    result = build_cashflow_direct(pairs)
    return ok_response("Cashflow statement built", {
        "period": {"from": date_from, "to": date_to},
        "method": "direct",
        "operating": result["operating"],
        "investing": result["investing"],
        "financing": result["financing"],
        "internal_transfers": result["internal_transfers"],
        "non_cash": {"count": len(result["non_cash"]["lines"])},
        "net_change_in_cash": result["net_change_in_cash"],
        "policy_notes": result["policy_notes"],
        "currency": "GEL",
    })


async def build_balance_sheet(tenant_id: str, as_of: Optional[str] = None) -> dict:
    if _posted_ledger_reports_enabled():
        return await _build_balance_sheet_from_posted_ledger(tenant_id, as_of)

    try:
        tb = await _get_trial_balance(tenant_id, None, as_of)
    except Exception as e:
        log.error("Balance Sheet trial balance failed: %s", e)
        return error_response("Balance Sheet build failed", "DB_ERROR", str(e))

    sections: dict = {
        "assets":      {"current": [], "non_current": []},
        "liabilities": {"current": [], "non_current": []},
        "equity":      {"equity":  []},
    }

    for code, (group, sub, label) in _BALANCE_SHEET.items():
        net = tb.get(code, 0.0)
        if net == 0.0:
            continue
        amount = net if group == "assets" else -net

        sections[group][sub].append({
            "account_code": code,
            "label": label,
            "amount": round(amount, 2),
        })

    total_current_assets    = round(sum(l["amount"] for l in sections["assets"]["current"]), 2)
    total_noncurrent_assets = round(sum(l["amount"] for l in sections["assets"]["non_current"]), 2)
    total_assets            = round(total_current_assets + total_noncurrent_assets, 2)

    total_current_liab    = round(sum(l["amount"] for l in sections["liabilities"]["current"]), 2)
    total_noncurrent_liab = round(sum(l["amount"] for l in sections["liabilities"]["non_current"]), 2)
    total_liabilities     = round(total_current_liab + total_noncurrent_liab, 2)

    total_equity = round(sum(l["amount"] for l in sections["equity"]["equity"]), 2)
    total_le     = round(total_liabilities + total_equity, 2)

    balanced = abs(total_assets - total_le) < 0.05

    return ok_response("Balance Sheet built", {
        "as_of": as_of or date.today().isoformat(),
        "assets": {
            "current":     {"lines": sections["assets"]["current"],     "total": total_current_assets},
            "non_current": {"lines": sections["assets"]["non_current"], "total": total_noncurrent_assets},
            "total":       total_assets,
        },
        "liabilities": {
            "current":     {"lines": sections["liabilities"]["current"],     "total": total_current_liab},
            "non_current": {"lines": sections["liabilities"]["non_current"], "total": total_noncurrent_liab},
            "total":       total_liabilities,
        },
        "equity": {
            "lines": sections["equity"]["equity"],
            "total": total_equity,
        },
        "total_liabilities_and_equity": total_le,
        "balanced": balanced,
        "currency": "GEL",
    })
