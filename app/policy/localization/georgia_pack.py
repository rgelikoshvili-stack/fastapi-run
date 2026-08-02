from decimal import Decimal, ROUND_HALF_UP


# ========== Georgia Tax Constants ==========

VAT_RATE = Decimal("0.18")          # დღგ 18%
PAYG_RATE = Decimal("0.02")         # საპენსიო 2%
PIT_RATE = Decimal("0.20")          # საშემოსავლო 20%
CIT_RATE = Decimal("0.15")          # კორპ. გადასახადი 15%
REPRESENTATION_LIMIT = Decimal("0.01")  # წარმომადგ. ხარჯი 1%

COUNTRY_CODE = "GE"
LOCALE = "ka_GE"
CURRENCY = "GEL"
TAX_YEAR_START = "01-01"
TAX_YEAR_END = "12-31"


# ========== Account Mapping ==========

ACCOUNT_MAP = {
    # შემოსავლები
    "income":              "6100",
    "sales":               "6100",
    "service_income":      "6110",

    # ხარჯები
    "salary":              "7210",
    "payroll":             "7210",
    "bank_fee":            "7150",
    "transport":           "7160",
    "travel":              "7160",
    "reservation":         "7160",
    "office":              "7180",
    "office_supplies":     "7180",
    "communication":       "7190",
    "internet":            "7190",
    "utilities":           "7170",
    "rent":                "7110",
    "cost_of_service":     "7100",
    "cost_of_goods":       "7100",
    "representation":      "7130",
    "tax":                 "3100",

    # ბანკი / ფული
    "bank":                "1210",
    "cash":                "1110",
    "transfer":            "1211",
    "currency_conversion": "1220",

    # კრედიტორები
    "accounts_payable":    "3310",
    "creditors":           "3310",

    # საგადასახადო
    "vat_payable":         "3310",
    "vat_receivable":      "2210",
    "income_tax":          "3320",
    "payg":                "3330",
    "cit_payable":         "3340",
    "withholding_payable": "3350",
    "dividend_payable":    "3370",
}


# ========== VAT Calculations ==========

def extract_vat(amount_with_vat: Decimal) -> dict:
    """
    თანხიდან დღგ-ის გამოყოფა (18% ჩათვლილი)
    მაგ: 118 ლარი → base=100, vat=18
    """
    base = (amount_with_vat / (1 + VAT_RATE)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    vat = (amount_with_vat - base).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {"base": float(base), "vat": float(vat), "total": float(amount_with_vat)}


def add_vat(base_amount: Decimal) -> dict:
    """
    თანხაზე დღგ-ის დამატება
    მაგ: 100 ლარი → base=100, vat=18, total=118
    """
    vat = (base_amount * VAT_RATE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total = base_amount + vat
    return {"base": float(base_amount), "vat": float(vat), "total": float(total)}


# ========== PAYG (საპენსიო) ==========

def calculate_payg(gross_salary: Decimal) -> dict:
    """
    საპენსიო ფონდის გამოთვლა (2%)
    """
    payg = (gross_salary * PAYG_RATE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    net = gross_salary - payg
    return {
        "gross": float(gross_salary),
        "payg": float(payg),
        "net": float(net),
    }


# ========== CIT (Corporate Income Tax — Estonian Model) ==========

WITHHOLDING_RATES = {
    "dividend": Decimal("0.05"),
    "interest": Decimal("0.05"),
    "royalty":  Decimal("0.10"),
    "services": Decimal("0.10"),
}
CIT_DIVISOR = Decimal("0.85")  # gross-up: tax_base = profit / 0.85


def calculate_cit(distributed_profit: Decimal) -> dict:
    """
    კორპ. გადასახადი ესტონური მოდელით (15%).
    ბაზა = განაცხადებული მოგება ÷ 0.85
    CIT  = ბაზა × 15%
    Dr 4210 / Cr 3370  — მოგების განაწილება
    Dr 3370 / Cr 3340 + Cr 1120  — გადახდა
    """
    profit = Decimal(str(distributed_profit))
    tax_base = (profit / CIT_DIVISOR).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cit = (tax_base * CIT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net_dividend = (profit - cit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "distributed_profit": float(profit),
        "tax_base": float(tax_base),
        "cit": float(cit),
        "net_dividend": float(net_dividend),
        "journal_step1": {"debit": "4210", "credit": "3370", "amount": float(profit)},
        "journal_step2": [
            {"debit": "3370", "credit": "3340", "amount": float(cit)},
            {"debit": "3370", "credit": "1120", "amount": float(net_dividend)},
        ],
        "deadline_days": 15,
        "form": "N101",
        "source": "საგ.კოდ.მ.97(3)",
    }


# ========== Withholding Tax ==========

def calculate_withholding(amount: Decimal, payment_type: str = "dividend", is_resident: bool = True) -> dict:
    """
    გადახდის წყაროსთან დაკავება.
    არარეზიდენტი — dividend:5%, interest:5%, royalty:10%, services:10%.
    რეზიდენტი — მხოლოდ royalty:10%, დანარჩენი 0%.
    Dr 3370 / Cr 3350  — tax დაკავება
    Dr 3350 / Cr 1120  — გადახდა RSA-ში
    """
    ptype = payment_type.lower().strip()
    if is_resident and ptype != "royalty":
        rate = Decimal("0")
    else:
        rate = WITHHOLDING_RATES.get(ptype, Decimal("0.10"))

    amt = Decimal(str(amount))
    tax = (amt * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = (amt - tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "amount": float(amt),
        "payment_type": ptype,
        "is_resident": is_resident,
        "rate_pct": int(rate * 100),
        "tax": float(tax),
        "net": float(net),
        "journal": {"debit": "3350", "credit": "1120", "amount": float(tax)} if tax else None,
        "deadline_days": 15,
        "source": "საგ.კოდ.მ.134",
    }


# ========== Dividend (full flow: accrual + CIT + withholding) ==========

def calculate_dividend(gross_profit: Decimal, recipient_is_resident: bool = True) -> dict:
    """
    დივიდენდის სრული ნაკადი:
      1. CIT on distribution (Estonian model)
      2. Withholding on net dividend paid to shareholder
    """
    cit_result = calculate_cit(gross_profit)
    net_after_cit = Decimal(str(cit_result["net_dividend"]))

    wth_result = calculate_withholding(
        net_after_cit,
        payment_type="dividend",
        is_resident=recipient_is_resident,
    )

    return {
        "gross_profit": float(gross_profit),
        "cit": cit_result["cit"],
        "net_after_cit": float(net_after_cit),
        "withholding_tax": wth_result["tax"],
        "net_to_shareholder": wth_result["net"],
        "total_tax": round(cit_result["cit"] + wth_result["tax"], 2),
        "effective_rate_pct": round(
            (cit_result["cit"] + wth_result["tax"]) / float(gross_profit) * 100, 2
        ) if float(gross_profit) else 0,
        "cit_detail": cit_result,
        "withholding_detail": wth_result,
    }


# ========== Account Resolution ==========

def get_account(category: str, fallback: str = "7190") -> str:
    """
    კატეგორიის მიხედვით ანგარიშის კოდის მიღება
    """
    return ACCOUNT_MAP.get(category.lower().strip(), fallback)


# ========== Localization Pack ==========

def get_localization_pack() -> dict:
    """
    სრული localization pack
    """
    return {
        "country": COUNTRY_CODE,
        "locale": LOCALE,
        "currency": CURRENCY,
        "vat_rate": float(VAT_RATE),
        "payg_rate": float(PAYG_RATE),
        "pit_rate": float(PIT_RATE),
        "cit_rate": float(CIT_RATE),
        "representation_limit": float(REPRESENTATION_LIMIT),
        "account_map": ACCOUNT_MAP,
        "tax_year": {
            "start": TAX_YEAR_START,
            "end": TAX_YEAR_END,
        },
    }


# ========== Validation ==========

def validate_vat_transaction(amount: float, has_invoice: bool) -> dict:
    """
    დღგ-ის ტრანზაქციის ვალიდაცია
    """
    issues = []
    if amount >= 1000 and not has_invoice:
        issues.append("1000 ლარზე მეტი ტრანზაქცია — დღგ-ის ფაქტურა სავალდებულოა")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


def validate_representation_expense(
    amount: float, total_revenue: float
) -> dict:
    """
    წარმომადგენლობითი ხარჯის ლიმიტის შემოწმება
    """
    limit = total_revenue * float(REPRESENTATION_LIMIT)
    ok = amount <= limit
    return {
        "valid": ok,
        "limit": round(limit, 2),
        "amount": amount,
        "issue": None if ok else f"ლიმიტი გადაჭარბებულია: {amount} > {limit:.2f}",
    }