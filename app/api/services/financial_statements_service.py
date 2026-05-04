"""app/api/services/financial_statements_service.py
IAS 1-compliant P&L and Balance Sheet from posted journal entries only.
"""
from __future__ import annotations
import logging
from typing import Optional
from datetime import date

from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response

log = logging.getLogger(__name__)

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


async def build_profit_and_loss(
    tenant_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
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


async def build_balance_sheet(tenant_id: str, as_of: Optional[str] = None) -> dict:
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
