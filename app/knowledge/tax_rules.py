"""app/knowledge/tax_rules.py — Georgian tax rules + calculators"""
from app.knowledge.chart_of_accounts import (
    TAX_RATES, CHART_OF_ACCOUNTS, _journal, _fmt, _payload,
)

TAX_RULES = {
    "VAT": {
        "rate": 0.18,
        "threshold": 100000,
        "registration_days": 2,
        "description": "დამატებული ღირებულების გადასახადი — 18%",
        "rules": [
            "VAT = ნეტო × 0.18",
            "ნეტო = ბრუტო ÷ 1.18 (VAT-ჩათვლ.)",
            "ბრ. > 100,000₾ → 2 სამ. დღეში რეგ.",
            "Paid: Dr1120/Cr6110/Cr3310 | Unpaid: Dr1210/Cr6110/Cr3310",
            "დეკლ.: კვ. 15-ე",
        ],
        "exempt_no_credit": [
            "სამედ. მომს. და მედიკ.",
            "განათ. მომს.",
            "ფინ. მომს. (სესხი, დეპ., სადაზღ.)",
            "საც. ბინ. გაქ.",
        ],
        "exempt_with_credit": [
            "ექსპ. — 0% + ჩათვ. უფ.",
            "საერთ. სატრ. მომს.",
            "FIZ მიწ.",
        ],
        "reverse_charge": [
            "არარეზ. ელ. მომს. (Google/FB/Netflix) — Dr3310/Cr3310",
        ],
    },
    "PIT": {
        "rate": 0.20,
        "payg_employee": 0.02,
        "payg_employer": 0.02,
        "description": "საშემოსავლო — 20% + PAYG 2%",
        "rules": [
            "PIT = Gross × 20%",
            "EmpPension = Gross × 2% (თანამ.)",
            "EmplPension = Gross × 2% (კომ., თანამ. არ აკლდება)",
            "Net = Gross - PIT - EmpPension",
            "Gross-up: Gross = Net ÷ 0.78 (ON) / ÷ 0.80 (OFF)",
            "Dr7210/Cr3320/Cr3330/Cr3360 + Dr7220/Cr3335",
            "ვ.: თვ. 15-ე (ფ.N4)",
        ],
    },
    "CIT": {
        "rate": 0.15,
        "divisor": 0.85,
        "description": "მოგ. გადასახ. — ესტ. მოდ. 15%",
        "rules": [
            "მხ. განაწ. მოგ. (ესტ. მოდ.)",
            "ბაზა = განაც ÷ 0.85",
            "CIT = ბაზა × 15%",
            "Dr4210/Cr3370 → Dr3370/Cr3340/Cr1120",
            "ვ.: 15 დღე (ფ.N101)",
        ],
        "deemed": [
            "წარმ.ხ. > 1% შემ. — ზედ. ნაწ.",
            "არარეზ. პროც./Royalty",
        ],
    },
    "WITHHOLDING": {
        "rates": {"dividend": 0.05, "interest": 0.05, "royalty": 0.10, "services": 0.10},
        "description": "გადახდ. წ. გადასახ.",
        "rules": ["არარ.დივ.:5% | Royalty:10% | პროც.:5% | მომს.:10% | ვ.:15დ."],
    },
    "PROPERTY_TAX": {
        "rate_max": 0.01,
        "rules": ["მაქს.1% საბ.ღ-ბ. | ფიზ.: 40,000₾-გათ. | 15ივ.+15დეკ."],
    },
    "MICRO_SMALL": {
        "rules": ["მიკ.: <30,000₾→0% | მც.: <500,000₾→1% ან 3%"],
    },
}


def _load_files_if_needed():
    from app.knowledge.knowledge_loader import _load_files
    _load_files()


def calculate_vat(amount, inclusive=True, service_type="standard"):
    _load_files_if_needed()
    exempt = {
        "medical": "სამედ.გათ.",
        "education": "განათ.გათ.",
        "export": "ექსპ.0%+ჩათვ.",
        "financial": "ფინ.გათ.",
        "apartment": "ბინ.გათ.",
    }
    for k, note in exempt.items():
        if k in service_type.lower():
            return {
                "vat": 0, "net": amount, "gross": amount,
                "rate": "0%", "note": note, "source": "საგ.კოდ.მ.168-172",
            }

    r = TAX_RATES["vat"]
    if inclusive:
        net = round(amount / (1 + r), 2)
        vat = round(amount - net, 2)
        gross = amount
    else:
        net = amount
        vat = round(amount * r, 2)
        gross = round(amount + vat, 2)

    return {
        "net": net,
        "vat": vat,
        "gross": gross,
        "rate": 18,
        "journal_paid": _journal(("Dr", "1120", gross), ("Cr", "6110", net), ("Cr", "3310", vat)),
        "journal_unpaid": _journal(("Dr", "1210", gross), ("Cr", "6110", net), ("Cr", "3310", vat)),
        "balance_ge_paid": _payload("VAT sale", [("1120", gross, 0), ("6110", 0, net), ("3310", 0, vat)]),
        "note": f"{'ჩ-ვ' if inclusive else 'დ-ბ'}: net={_fmt(net)},vat={_fmt(vat)}",
        "deadline": "კვ.15-ე",
        "source": "საგ.კოდ.მ.160-172/ბუღ.ლ.4",
    }


def calculate_payroll(gross, include_pension=True, mode="gross"):
    _load_files_if_needed()
    ep = TAX_RATES["payg_employee"] if include_pension else 0.0
    erp = TAX_RATES["payg_employer"] if include_pension else 0.0
    p = TAX_RATES["pit"]

    if mode == "net":
        g = gross
        gross = round(g / (1 - p - ep), 2)

    pit = round(gross * p, 2)
    emp_p = round(gross * ep, 2)
    net = round(gross - pit - emp_p, 2)
    erp_a = round(gross * erp, 2)

    jl = [("Dr", "7210", gross), ("Cr", "3320", pit)]
    if emp_p:
        jl.append(("Cr", "3330", emp_p))
    jl.append(("Cr", "3360", net))

    j = _journal(*jl)
    if erp_a:
        j += "\n\n  — დამ.საპ. —\n" + _journal(("Dr", "7220", erp_a), ("Cr", "3335", erp_a))

    pl = [("7210", gross, 0), ("3320", 0, pit)]
    if emp_p:
        pl.append(("3330", 0, emp_p))
    pl.append(("3360", 0, net))

    return {
        "gross": gross,
        "pit": pit,
        "payg_employee": emp_p,
        "payg_employer": erp_a,
        "net": net,
        "total_employer_cost": round(gross + erp_a, 2),
        "journal": j,
        "balance_ge": _payload("Salary", pl),
        "deadline": "თვ.15-ე(N4)",
        "source": "საგ.კოდ.მ.154-155/ბუღ.",
    }


def calculate_cit(distributed_profit):
    _load_files_if_needed()
    tb = round(distributed_profit / TAX_RATES["cit_divisor"], 2)
    cit = round(tb * TAX_RATES["cit"], 2)
    nd = round(distributed_profit - cit, 2)

    j1 = _journal(("Dr", "4210", distributed_profit), ("Cr", "3370", distributed_profit))
    j2 = _journal(("Dr", "3370", distributed_profit), ("Cr", "3340", cit), ("Cr", "1120", nd))

    return {
        "distributed_profit": distributed_profit,
        "tax_base": tb,
        "cit": cit,
        "net_dividend": nd,
        "journal": f"ეტ.1:\n{j1}\n\nეტ.2:\n{j2}",
        "balance_ge_step1": _payload("Div.accrual", [("4210", distributed_profit, 0), ("3370", 0, distributed_profit)]),
        "balance_ge_step2": _payload("Div.payment", [("3370", distributed_profit, 0), ("3340", 0, cit), ("1120", 0, nd)]),
        "deadline": "15დ.",
        "source": "საგ.კოდ.მ.97(3)/ბუღ.ლ.6",
    }


def calculate_withholding(amount, payment_type="dividend", is_resident=True):
    _load_files_if_needed()
    rate = TAX_RATES.get(f"withholding_{payment_type}", 0.10)
    if is_resident and payment_type not in ["royalty"]:
        rate = 0
    tax = round(amount * rate, 2)
    net = round(amount - tax, 2)

    return {
        "amount": amount,
        "rate": int(rate * 100),
        "tax": tax,
        "net": net,
        "journal": _journal(("Dr", "3350", tax), ("Cr", "1120", tax)) if tax else "",
        "deadline": "15დ.",
        "source": "საგ.კოდ.მ.134",
    }


def calculate_depreciation(cost, residual, useful_life_years, method="straight_line"):
    _load_files_if_needed()
    annual = round((cost - residual) / useful_life_years, 2) if method == "straight_line" else round(cost * 0.20, 2)
    monthly = round(annual / 12, 2)

    return {
        "cost": cost,
        "residual": residual,
        "useful_life": useful_life_years,
        "method": method,
        "annual": annual,
        "monthly": monthly,
        "journal": _journal(("Dr", "7610", monthly), ("Cr", "1520", monthly)),
        "source": "IAS16/ბუღ.ლ.8",
    }


def calculate_inventory_shortage(shortage_amount, has_culprit=False):
    _load_files_if_needed()
    lines = [("Dr", "7110", shortage_amount), ("Cr", "1310", shortage_amount)]
    if has_culprit:
        lines += [("Dr", "1210", shortage_amount), ("Cr", "7110", shortage_amount)]

    return {
        "shortage": shortage_amount,
        "vat_liability": round(shortage_amount * TAX_RATES["vat"], 2),
        "journal": _journal(*lines),
        "note": "⚠️ VAT!" + (" + თ.ანაზ." if has_culprit else ""),
        "source": "IAS2/ბუღ.ლ.3/საგ.კოდ.",
    }
