"""
Bridge Hub — Accounting Rules & Formatting
app/api/services/accounting_rules.py

3 გაუმჯობესება:
  1. Dividend 2-step posting rule
  2. VAT debit account rule (paid vs unpaid)
  3. GEL currency formatting
"""

from typing import Optional


# ═══════════════════════════════════════════════════════
# 1. GEL FORMATTING
# ═══════════════════════════════════════════════════════

def format_gel(amount: float) -> str:
    """
    10000   → 10,000.00₾
    1500.5  → 1,500.50₾
    """
    return f"{amount:,.2f}₾"


# ═══════════════════════════════════════════════════════
# 2. VAT POSTING RULE
# ═══════════════════════════════════════════════════════

def build_vat_posting(
    gross_amount: float,
    vat_rate: float = 0.18,
    payment_status: str = "paid",  # "paid" | "unpaid"
    revenue_account: str = "6110",
    vat_account: str = "3310",
    bank_account: str = "1120",
    receivable_account: str = "1410",
) -> dict:
    """
    paid   → Dr 1120 Bank
    unpaid → Dr 1410 Accounts Receivable

    მაგ: gross=5900 → net=5000, vat=900
    """
    net = round(gross_amount / (1 + vat_rate), 2)
    vat = round(gross_amount - net, 2)

    debit_account = bank_account if payment_status == "paid" else receivable_account
    debit_label   = "Bank/Cash" if payment_status == "paid" else "Accounts Receivable"

    lines = [
        {"account_code": debit_account,    "label": debit_label,       "debit": gross_amount, "credit": 0.00},
        {"account_code": revenue_account,  "label": "Revenue",          "debit": 0.00,         "credit": net},
        {"account_code": vat_account,      "label": "VAT Payable",      "debit": 0.00,         "credit": vat},
    ]

    return {
        "type": "vat_sale",
        "payment_status": payment_status,
        "gross": gross_amount,
        "net": net,
        "vat": vat,
        "lines": lines,
        "human_readable": _format_lines(lines),
        "balance_ge_payload": _to_balance_ge(lines),
    }


# ═══════════════════════════════════════════════════════
# 3. DIVIDEND 2-STEP POSTING RULE
# ═══════════════════════════════════════════════════════

def build_dividend_posting(
    gross_amount: float,
    cit_rate: float = 0.15,
    retained_earnings_account: str = "4210",
    dividends_payable_account: str = "3320",
    cit_payable_account: str = "3340",
    bank_account: str = "1120",
) -> dict:
    """
    2-step dividend posting:

    Step 1 — Accrual:
      Dr 4210 Retained Earnings  10,000.00₾
      Cr 3320 Dividends Payable  10,000.00₾

    Step 2 — Payment + CIT:
      Dr 3320 Dividends Payable  10,000.00₾
      Cr 3340 CIT Payable         1,500.00₾
      Cr 1120 Bank/Cash           8,500.00₾
    """
    cit    = round(gross_amount * cit_rate, 2)
    net    = round(gross_amount - cit, 2)

    step1_lines = [
        {"account_code": retained_earnings_account, "label": "Retained Earnings",  "debit": gross_amount, "credit": 0.00},
        {"account_code": dividends_payable_account, "label": "Dividends Payable",  "debit": 0.00,         "credit": gross_amount},
    ]

    step2_lines = [
        {"account_code": dividends_payable_account, "label": "Dividends Payable",  "debit": gross_amount, "credit": 0.00},
        {"account_code": cit_payable_account,       "label": "CIT Payable (15%)",  "debit": 0.00,         "credit": cit},
        {"account_code": bank_account,              "label": "Bank/Cash",           "debit": 0.00,         "credit": net},
    ]

    return {
        "type": "dividend_2step",
        "gross": gross_amount,
        "cit": cit,
        "net_to_shareholder": net,
        "step1": {
            "description": "Dividend Accrual",
            "lines": step1_lines,
            "human_readable": _format_lines(step1_lines),
            "balance_ge_payload": _to_balance_ge(step1_lines, description="Dividend Accrual"),
        },
        "step2": {
            "description": "Dividend Payment + CIT",
            "lines": step2_lines,
            "human_readable": _format_lines(step2_lines),
            "balance_ge_payload": _to_balance_ge(step2_lines, description="Dividend Payment with CIT"),
        },
    }


# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════

def _format_lines(lines: list) -> str:
    """Human-readable journal output"""
    result = []
    for l in lines:
        if l["debit"] > 0:
            result.append(f"  Dr {l['account_code']} {l['label']:<30} {format_gel(l['debit']):>14}")
        else:
            result.append(f"  Cr {l['account_code']} {l['label']:<30} {format_gel(l['credit']):>14}")
    return "\n".join(result)


def _to_balance_ge(lines: list, description: str = "", date: Optional[str] = None) -> dict:
    """Balance.ge structured import payload"""
    from datetime import date as dt
    return {
        "journal_date": date or dt.today().isoformat(),
        "description": description,
        "lines": [
            {
                "account_code": l["account_code"],
                "debit":  round(l["debit"],  2),
                "credit": round(l["credit"], 2),
            }
            for l in lines
        ],
    }


# ═══════════════════════════════════════════════════════
# QUICK TEST
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("1. GEL FORMATTING")
    print("=" * 60)
    for v in [10000, 1500, 8500, 5900, 900.5]:
        print(f"  {v} → {format_gel(v)}")

    print()
    print("=" * 60)
    print("2. VAT POSTING — paid (bank)")
    print("=" * 60)
    vat = build_vat_posting(5900, payment_status="paid")
    print(vat["human_readable"])
    print("\nBalance.ge payload:")
    import json
    print(json.dumps(vat["balance_ge_payload"], indent=2, ensure_ascii=False))

    print()
    print("=" * 60)
    print("3. VAT POSTING — unpaid (receivable)")
    print("=" * 60)
    vat2 = build_vat_posting(5900, payment_status="unpaid")
    print(vat2["human_readable"])

    print()
    print("=" * 60)
    print("4. DIVIDEND 2-STEP POSTING")
    print("=" * 60)
    div = build_dividend_posting(10000)
    print("Step 1 — Accrual:")
    print(div["step1"]["human_readable"])
    print("\nStep 2 — Payment:")
    print(div["step2"]["human_readable"])
    print(f"\n  CIT: {format_gel(div['cit'])}")
    print(f"  Net to shareholder: {format_gel(div['net_to_shareholder'])}")
    print("\nBalance.ge Step 1:")
    print(json.dumps(div["step1"]["balance_ge_payload"], indent=2, ensure_ascii=False))
    print("\nBalance.ge Step 2:")
    print(json.dumps(div["step2"]["balance_ge_payload"], indent=2, ensure_ascii=False))
