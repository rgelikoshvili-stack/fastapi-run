"""
app/policy/localization/georgia_pack.py
Bridge Hub — ქართული საბუღალტრო წესები
"""

VAT_RATE = 0.18
PAYG_RATE = 0.02
REPRESENTATIVE_EXPENSE_LIMIT = 0.01

TAX_ACCOUNTS = {
    "vat_output": "3310",
    "vat_input":  "3330",
    "income_tax": "3160",
    "payg":       "3150",
    "profit_tax": "3100",
}

ACCOUNT_KEYWORDS = {
    "7110": ["ხელფასი", "salary", "მივლინება"],
    "7210": ["ქირა", "rent", "იჯარა"],
    "7310": ["კომუნალური", "მაგთი", "სილქნეტი", "geocell", "beeline", "ელექტრო", "წყალი", "გაზი"],
    "7410": ["სატრანსპორტო", "taxi", "fuel", "საწვავი", "uber"],
    "7510": ["სარეკლამო", "marketing", "advertising"],
    "7610": ["საოფისე", "office", "კანცელარია"],
    "7710": ["წარმომადგენლობითი", "representative", "entertainment", "რესტორანი"],
    "7810": ["საბანკო", "bank fee", "საკომისიო", "commission"],
    "5010": ["შემოსავალი", "revenue", "გაყიდვა", "sale"],
}

def extract_vat(amount: float) -> float:
    return round(amount * VAT_RATE / (1 + VAT_RATE), 2)

def add_vat(amount: float) -> float:
    return round(amount * (1 + VAT_RATE), 2)

def split_vat_entry(draft: dict) -> list:
    amount = float(draft.get("amount", 0))
    vat    = extract_vat(amount)
    net    = round(amount - vat, 2)
    return [
        {**draft, "amount": net, "description": draft.get("description","") + " (წმინდა)"},
        {**draft, "amount": vat, "account_dr": TAX_ACCOUNTS["vat_input"],
         "description": "VAT 18% — " + draft.get("description","")},
    ]

def check_payg(draft: dict):
    desc = (draft.get("description") or "").lower()
    if not any(k in desc for k in ["ხელფასი", "salary"]):
        return None
    amount = float(draft.get("amount", 0))
    payg   = round(amount * PAYG_RATE, 2)
    return {
        "type":        "payg",
        "amount":      payg,
        "account_dr":  TAX_ACCOUNTS["payg"],
        "account_cr":  "1010",
        "description": f"PAYG 2% — {draft.get('description','')}",
    }

def check_representative_expense(amount: float, annual_revenue: float) -> dict:
    limit = round(annual_revenue * REPRESENTATIVE_EXPENSE_LIMIT, 2)
    over  = amount > limit
    return {
        "allowed": not over,
        "limit":   limit,
        "amount":  amount,
        "over_by": round(amount - limit, 2) if over else 0,
        "warning": f"ლიმიტი გადაცილებულია {round(amount-limit,2)} GEL-ით" if over else None,
    }

def suggest_account(description: str):
    desc_lower = description.lower()
    for account, keywords in ACCOUNT_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return account
    return None

def apply_rules(result: dict, tenant_id: str = "default") -> dict:
    desc   = result.get("description", "")
    amount = float(result.get("amount", 0))

    if amount > 100:
        result["vat_amount"]    = extract_vat(amount)
        result["vat_net"]       = round(amount - extract_vat(amount), 2)
        result["vat_suggested"] = True

    payg = check_payg({"description": desc, "amount": amount})
    if payg:
        result["payg_required"] = True
        result["payg_amount"]   = payg["amount"]

    suggested = suggest_account(desc)
    if suggested and not result.get("account_code"):
        result["account_code"]   = suggested
        result["account_source"] = "georgia_pack_keyword"

    return result

def get_tax_account(tax_type: str):
    return TAX_ACCOUNTS.get(tax_type)
