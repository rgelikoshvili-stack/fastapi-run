"""
Bridge Hub — Accounting Rules & Formatting
app/api/services/accounting_rules.py

ფაილი დაფუძნებულია:
- დღგ 18% ლოგიკაზე
- რეალიზაციის გატარებებზე (1410 / 6110 / 3330)
- ესტონური მოდელის CIT ფორმულაზე (amount / 0.85 * 15%)
- დასაბეგრი ჩამოწერის / დანაკლისის VAT + CIT ლოგიკაზე
"""

from __future__ import annotations

from datetime import date as dt
from typing import Optional, List, Dict


# ═══════════════════════════════════════════════════════
# 1. FORMAT
# ═══════════════════════════════════════════════════════

def format_gel(amount: float) -> str:
    """10000 -> 10,000.00₾"""
    return f"{float(amount):,.2f}₾"


# ═══════════════════════════════════════════════════════
# 2. HELPERS
# ═══════════════════════════════════════════════════════

def _round2(value: float) -> float:
    return round(float(value), 2)


def _make_line(account_code: str, label: str, debit: float = 0.0, credit: float = 0.0) -> dict:
    return {
        "account_code": str(account_code),
        "label": label,
        "debit": _round2(debit),
        "credit": _round2(credit),
    }


def _format_lines(lines: List[dict]) -> str:
    rows = []
    for l in lines:
        if l["debit"] > 0:
            rows.append(f"  Dr {l['account_code']} {l['label']:<30} {format_gel(l['debit']):>14}")
        else:
            rows.append(f"  Cr {l['account_code']} {l['label']:<30} {format_gel(l['credit']):>14}")
    return "\n".join(rows)


def _to_balance_ge(lines: List[dict], description: str = "", journal_date: Optional[str] = None) -> dict:
    return {
        "journal_date": journal_date or dt.today().isoformat(),
        "description": description,
        "lines": [
            {
                "account_code": l["account_code"],
                "debit": _round2(l["debit"]),
                "credit": _round2(l["credit"]),
            }
            for l in lines
        ],
    }


# ═══════════════════════════════════════════════════════
# 3. TAX CALC HELPERS
# ═══════════════════════════════════════════════════════

def split_vat_from_gross(gross_amount: float, vat_rate: float = 0.18) -> dict:
    """
    gross -> net + vat
    მაგ: 5900 -> 5000 + 900
    """
    gross = _round2(gross_amount)
    net = _round2(gross / (1 + vat_rate))
    vat = _round2(gross - net)
    return {
        "gross": gross,
        "net": net,
        "vat": vat,
        "vat_rate": vat_rate,
    }


def add_vat_to_net(net_amount: float, vat_rate: float = 0.18) -> dict:
    """
    net -> gross
    """
    net = _round2(net_amount)
    vat = _round2(net * vat_rate)
    gross = _round2(net + vat)
    return {
        "gross": gross,
        "net": net,
        "vat": vat,
        "vat_rate": vat_rate,
    }


def estonian_cit_from_distributed_amount(amount: float, cit_rate: float = 0.15, divisor: float = 0.85) -> dict:
    """
    საქართველოს ესტონური მოდელი:
    დასაბეგრი თანხა = amount / 0.85
    CIT = დასაბეგრი თანხა * 15%
    """
    amount = _round2(amount)
    tax_base = _round2(amount / divisor)
    cit = _round2(tax_base * cit_rate)
    net_after_cit = _round2(amount - cit)

    return {
        "amount": amount,
        "tax_base": tax_base,
        "cit": cit,
        "net_after_cit": net_after_cit,
        "cit_rate": cit_rate,
        "divisor": divisor,
    }


# ═══════════════════════════════════════════════════════
# 4. VAT SALE POSTING
# ═══════════════════════════════════════════════════════

def build_vat_posting(
    gross_amount: float,
    vat_rate: float = 0.18,
    payment_status: str = "paid",   # paid | unpaid
    revenue_account: str = "6110",
    vat_account: str = "3330",
    bank_account: str = "1120",
    receivable_account: str = "1410",
) -> dict:
    """
    VAT-იანი გაყიდვა

    paid:
      Dr 1120 / Cr 6110 / Cr 3330

    unpaid:
      Dr 1410 / Cr 6110 / Cr 3330
    """
    calc = split_vat_from_gross(gross_amount, vat_rate=vat_rate)

    debit_account = bank_account if payment_status == "paid" else receivable_account
    debit_label = "Bank/Cash" if payment_status == "paid" else "Accounts Receivable"

    lines = [
        _make_line(debit_account, debit_label, debit=calc["gross"]),
        _make_line(revenue_account, "Revenue", credit=calc["net"]),
        _make_line(vat_account, "VAT Payable", credit=calc["vat"]),
    ]

    return {
        "type": "vat_sale",
        "payment_status": payment_status,
        **calc,
        "lines": lines,
        "human_readable": _format_lines(lines),
        "balance_ge_payload": _to_balance_ge(
            lines,
            description=f"VAT sale ({payment_status})"
        ),
    }


# ═══════════════════════════════════════════════════════
# 5. DIVIDEND 2-STEP POSTING (ESTONIAN MODEL)
# ═══════════════════════════════════════════════════════

def build_dividend_posting(
    gross_amount: float,
    cit_rate: float = 0.15,
    divisor: float = 0.85,
    retained_earnings_account: str = "4210",
    dividends_payable_account: str = "3320",
    cit_payable_account: str = "3340",
    bank_account: str = "1120",
) -> dict:
    """
    2-step dividend posting:

    Step 1 — Accrual:
      Dr 4210 Retained Earnings
      Cr 3320 Dividends Payable

    Step 2 — Payment + CIT:
      Dr 3320 Dividends Payable
      Cr 3340 CIT Payable
      Cr 1120 Bank/Cash

    CIT ითვლება:
      gross_amount / 0.85 * 15%
    """
    cit_calc = estonian_cit_from_distributed_amount(
        gross_amount,
        cit_rate=cit_rate,
        divisor=divisor,
    )

    gross = cit_calc["amount"]
    cit = cit_calc["cit"]
    tax_base = cit_calc["tax_base"]
    net_to_shareholder = cit_calc["net_after_cit"]

    step1_lines = [
        _make_line(retained_earnings_account, "Retained Earnings", debit=gross),
        _make_line(dividends_payable_account, "Dividends Payable", credit=gross),
    ]

    step2_lines = [
        _make_line(dividends_payable_account, "Dividends Payable", debit=gross),
        _make_line(cit_payable_account, "CIT Payable", credit=cit),
        _make_line(bank_account, "Bank/Cash", credit=net_to_shareholder),
    ]

    return {
        "type": "dividend_2step",
        "gross": gross,
        "tax_base": tax_base,
        "cit": cit,
        "net_to_shareholder": net_to_shareholder,
        "cit_rate": cit_rate,
        "divisor": divisor,
        "step1": {
            "description": "Dividend Accrual",
            "lines": step1_lines,
            "human_readable": _format_lines(step1_lines),
            "balance_ge_payload": _to_balance_ge(
                step1_lines,
                description="Dividend Accrual"
            ),
        },
        "step2": {
            "description": "Dividend Payment + CIT",
            "lines": step2_lines,
            "human_readable": _format_lines(step2_lines),
            "balance_ge_payload": _to_balance_ge(
                step2_lines,
                description="Dividend Payment + CIT"
            ),
        },
    }


# ═══════════════════════════════════════════════════════
# 6. TAXABLE WRITE-OFF / SHORTAGE / FREE SUPPLY
# ═══════════════════════════════════════════════════════

def build_taxable_writeoff_posting(
    net_amount: float,
    vat_rate: float = 0.18,
    cit_rate: float = 0.15,
    divisor: float = 0.85,
    expense_account: str = "7290",
    inventory_account: str = "1610",
    vat_payable_account: str = "3330",
    cit_expense_account: str = "9210",
    cit_payable_account: str = "3340",
) -> dict:
    """
    დასაბეგრი ჩამოწერა / დანაკლისი / უსასყიდლო მიწოდება

    ლოგიკა:
    - დღგ ითვლება საბაზო თანხიდან
    - მოგების გადასახადი ითვლება net / 0.85 * 15%
    """
    net_amount = _round2(net_amount)

    vat_calc = add_vat_to_net(net_amount, vat_rate=vat_rate)
    cit_calc = estonian_cit_from_distributed_amount(
        net_amount,
        cit_rate=cit_rate,
        divisor=divisor,
    )

    vat = vat_calc["vat"]
    cit = cit_calc["cit"]

    lines = [
        _make_line(expense_account, "Write-off / Shortage Expense", debit=net_amount),
        _make_line(inventory_account, "Inventory", credit=net_amount),
        _make_line(expense_account, "VAT Expense", debit=vat),
        _make_line(vat_payable_account, "VAT Payable", credit=vat),
        _make_line(cit_expense_account, "Profit Tax Expense", debit=cit),
        _make_line(cit_payable_account, "CIT Payable", credit=cit),
    ]

    return {
        "type": "taxable_writeoff",
        "net_amount": net_amount,
        "vat": vat,
        "cit_tax_base": cit_calc["tax_base"],
        "cit": cit,
        "gross_with_vat": vat_calc["gross"],
        "lines": lines,
        "human_readable": _format_lines(lines),
        "balance_ge_payload": _to_balance_ge(
            lines,
            description="Taxable Write-off / Shortage"
        ),
    }


# ═══════════════════════════════════════════════════════
# 7. SIMPLE NON-VAT SERVICE / REVENUE
# ═══════════════════════════════════════════════════════

def build_simple_revenue_posting(
    amount: float,
    payment_status: str = "paid",   # paid | unpaid
    revenue_account: str = "6110",
    bank_account: str = "1120",
    receivable_account: str = "1410",
) -> dict:
    """
    დღგ-ს გარეშე შემოსავლის გატარება
    """
    amount = _round2(amount)

    debit_account = bank_account if payment_status == "paid" else receivable_account
    debit_label = "Bank/Cash" if payment_status == "paid" else "Accounts Receivable"

    lines = [
        _make_line(debit_account, debit_label, debit=amount),
        _make_line(revenue_account, "Revenue", credit=amount),
    ]

    return {
        "type": "simple_revenue",
        "payment_status": payment_status,
        "amount": amount,
        "lines": lines,
        "human_readable": _format_lines(lines),
        "balance_ge_payload": _to_balance_ge(
            lines,
            description=f"Simple revenue ({payment_status})"
        ),
    }


# ═══════════════════════════════════════════════════════
# 8. QUICK TEST
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("1. GEL FORMAT")
    print("=" * 60)
    for v in [10000, 1500.5, 5900, 1764.71]:
        print(f"{v} -> {format_gel(v)}")

    print("\n" + "=" * 60)
    print("2. VAT SALE — PAID")
    print("=" * 60)
    vat_paid = build_vat_posting(5900, payment_status="paid")
    print(vat_paid["human_readable"])
    print(json.dumps(vat_paid["balance_ge_payload"], ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("3. VAT SALE — UNPAID")
    print("=" * 60)
    vat_unpaid = build_vat_posting(5900, payment_status="unpaid")
    print(vat_unpaid["human_readable"])

    print("\n" + "=" * 60)
    print("4. DIVIDEND 2-STEP")
    print("=" * 60)
    div = build_dividend_posting(10000)
    print("STEP 1")
    print(div["step1"]["human_readable"])
    print("\nSTEP 2")
    print(div["step2"]["human_readable"])
    print(f"\nTax base: {format_gel(div['tax_base'])}")
    print(f"CIT: {format_gel(div['cit'])}")
    print(f"Net to shareholder: {format_gel(div['net_to_shareholder'])}")

    print("\n" + "=" * 60)
    print("5. TAXABLE WRITE-OFF")
    print("=" * 60)
    wr = build_taxable_writeoff_posting(5000)
    print(wr["human_readable"])