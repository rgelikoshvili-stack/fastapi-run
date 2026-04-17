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
    "salary":              "7120",
    "payroll":             "7120",
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

    # საგადასახადო
    "vat_payable":         "3310",
    "vat_receivable":      "2210",
    "income_tax":          "3320",
    "payg":                "3120",
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