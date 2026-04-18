"""app/knowledge/chart_of_accounts.py — Static data: COA, ACCA, TAX_RATES + formatting helpers"""
from datetime import date

TAX_RATES = {
    "vat": 0.18,
    "vat_threshold": 100000,
    "vat_registration_days": 2,
    "pit": 0.20,
    "payg_employee": 0.02,
    "payg_employer": 0.02,
    "cit": 0.15,
    "cit_divisor": 0.85,
    "withholding_dividend": 0.05,
    "withholding_royalty": 0.10,
    "withholding_interest": 0.05,
    "withholding_services": 0.10,
    "property_max": 0.01,
    "micro_business": 0.01,
    "small_business": 0.03,
}

CHART_OF_ACCOUNTS = {
    "1110": {"name": "სალარო (ნაღდი)", "type": "asset", "keywords": ["ნაღდი", "სალარო", "cash", "კასა"]},
    "1120": {"name": "საბანკო ანგ.", "type": "asset", "keywords": ["საბ.ანგ", "გადარ", "bank account"]},
    "1130": {"name": "სხვა ფ.ეკვ.", "type": "asset", "keywords": []},
    "1210": {"name": "მოთხ. კლ-ზე", "type": "asset", "keywords": ["მოთხ", "დებ", "receivable"]},
    "1220": {"name": "სათ. მოთხ.", "type": "asset", "keywords": []},
    "1310": {"name": "მარ. / საქ.", "type": "asset", "keywords": ["საქ", "მარ", "inventory", "stock", "product"]},
    "1320": {"name": "მზა პროდ.", "type": "asset", "keywords": []},
    "1330": {"name": "უდ. წარმ.", "type": "asset", "keywords": []},
    "1410": {"name": "სხვ. მოკლ. მოთხ.", "type": "asset", "keywords": ["წინ", "prepaid"]},
    "1420": {"name": "გადახ. ავ.", "type": "asset", "keywords": ["ავანს", "advance", "prepay"]},
    "1430": {"name": "წინ. გადახ. ხ.", "type": "asset", "keywords": []},
    "1510": {"name": "ძირ. საშ.", "type": "asset", "keywords": ["ძირ", "fixed", "შენ", "მანქ", "ტექ", "equipment"]},
    "1520": {"name": "დარ. ამ. (კ.)", "type": "contra_asset", "keywords": ["ამ", "depreciation"]},
    "1610": {"name": "არ. აქტ.", "type": "asset", "keywords": ["პატ", "ლიც", "intangible", "software", "პრ"]},
    "1620": {"name": "გრ.ვ.ინვ.", "type": "asset", "keywords": []},
    "1710": {"name": "ROU (IFRS16)", "type": "asset", "keywords": ["rou", "ifrs 16", "ლიზ", "leasing"]},
    "3110": {"name": "კრ. დავ.", "type": "liability", "keywords": ["მიწ", "კრედ", "payable", "AP"]},
    "3120": {"name": "მიღ. ავ.", "type": "liability", "keywords": ["ავ", "advance"]},
    "3130": {"name": "გად. ხ.", "type": "liability", "keywords": []},
    "3310": {"name": "დღგ გად.", "type": "liability", "keywords": ["დღგ", "vat", "დამ.ღ"]},
    "3311": {"name": "ჩათვ. დღგ", "type": "asset", "keywords": ["vat input", "ჩათ.დღგ", "3311"]},
    "3320": {"name": "PIT / საშ.", "type": "liability", "keywords": ["pit", "საშ", "income tax"]},
    "3330": {"name": "დასაქ. საპ.", "type": "liability", "keywords": ["payg", "pension", "საპ"]},
    "3335": {"name": "დამ. საპ.", "type": "liability", "keywords": []},
    "3340": {"name": "CIT / მოგ.", "type": "liability", "keywords": ["cit", "მოგ", "profit tax"]},
    "3350": {"name": "Withholding", "type": "liability", "keywords": ["withholding", "არარ", "nonres"]},
    "3360": {"name": "გად.ხ.Net", "type": "liability", "keywords": []},
    "3370": {"name": "გად. დივ.", "type": "liability", "keywords": ["დივ", "dividend"]},
    "3380": {"name": "ქ.გ. გად.", "type": "liability", "keywords": []},
    "3410": {"name": "სასეხ.ვ.მ.", "type": "liability", "keywords": ["სესხ", "loan", "კრ"]},
    "3420": {"name": "გ.თ.", "type": "liability", "keywords": []},
    "3430": {"name": "ფ.იჯ.(IFRS16)", "type": "liability", "keywords": ["ლიზ", "ifrs 16"]},
    "3510": {"name": "გ.ვ.სესხ.ვ.", "type": "liability", "keywords": []},
    "4110": {"name": "საწ.კაპ.", "type": "equity", "keywords": ["კაპ", "equity", "capital", "საწ"]},
    "4120": {"name": "დამ.კაპ.", "type": "equity", "keywords": []},
    "4210": {"name": "გ.მ.(RE)", "type": "equity", "keywords": ["მოგ", "retained", "RE"]},
    "4220": {"name": "სარ.კაპ.", "type": "equity", "keywords": []},
    "6110": {"name": "გ-ვ. შემ.", "type": "revenue", "keywords": ["გ-ვ", "revenue", "income", "შემ", "invoice", "ინვ", "sale"]},
    "6120": {"name": "მომ. შემ.", "type": "revenue", "keywords": ["მომსახურება", "კონსულტაცია", "revenue service"]},
    "6130": {"name": "სხვ.ო.შ.", "type": "revenue", "keywords": []},
    "6140": {"name": "პ.შ.", "type": "revenue", "keywords": []},
    "6150": {"name": "სხვ.შ.", "type": "revenue", "keywords": []},
    "7110": {"name": "COGS", "type": "expense", "keywords": ["cogs", "cost of goods", "ღ-ბ"]},
    "7120": {"name": "პ.ხ.", "type": "expense", "keywords": []},
    "7210": {"name": "ხ.ხ.", "type": "expense", "keywords": ["ხელფ", "salary", "payroll", "მუშ", "თანამ"]},
    "7220": {"name": "დ.სპ.ხ.", "type": "expense", "keywords": []},
    "7230": {"name": "სხ.შ.ხ.", "type": "expense", "keywords": []},
    "7310": {"name": "ქ.ხ.", "type": "expense", "keywords": ["ქ-ა", "rent", "იჯ", "ოფ", "office"]},
    "7320": {"name": "ო.ლ.ხ.", "type": "expense", "keywords": []},
    "7410": {"name": "კ.ხ.", "type": "expense", "keywords": ["კომ", "utilities", "electric", "წყ", "გ", "gas"]},
    "7510": {
        "name": "სბ.სკ.",
        "type": "expense",
        "keywords": [
            "საბ. საკ", "commission", "bank fee", "tbc", "bog",
            "tbc bank", "bank of georgia", "საკომისიო", "სბ.სკ", "სრვ",
        ],
    },
    "7520": {"name": "სბ.პ.", "type": "expense", "keywords": ["პ", "interest", "სარგ"]},
    "7610": {"name": "ამ.ხ.", "type": "expense", "keywords": ["ამ", "depreciation"]},
    "7710": {"name": "რ.ხ.", "type": "expense", "keywords": ["რ", "marketing", "advertising", "facebook", "google ad", "instagram"]},
    "7720": {"name": "წ.ხ.", "type": "expense", "keywords": ["წ", "entertainment", "representative", "რ-ნ", "wolt", "glovo"]},
    "7730": {"name": "ს.ხ.", "type": "expense", "keywords": ["სატ", "transport", "taxi", "bolt"]},
    "7810": {"name": "სხ.ა.ხ.", "type": "expense", "keywords": ["aws", "amazon", "azure", "cloud", "software"]},
    "7910": {"name": "სხვ.ხ.", "type": "expense", "keywords": ["სხვ", "other", "misc"]},
    "7920": {"name": "გ.კ.ზ.", "type": "expense", "keywords": ["გ-ვ", "exchange"]},
}

ACCA_STANDARDS = {
    "IFRS_15": {"title": "IFRS 15 — შემ. აღ. (5-ნ.)", "steps": ["1.კ-ტ", "2.PO", "3.ფ-ი", "4.გ-ა", "5.შ.ვ."]},
    "IFRS_16": {
        "title": "IFRS 16 — იჯ.",
        "lessee_accounting": [
            "ROU=PV(გ-ბ)+საწ. Dr1710/Cr3430",
            "ამ: Dr7610/Cr1520. პ: Dr7520/Cr3430",
            "<12თ/<$5k→ოპ.ხ.",
        ],
    },
    "IAS_2": {"title": "IAS 2 — მარ.", "rules": ["ღ. ან NRV", "FIFO/WAvg (LIFO დ.)", "ჩ: Dr7110/Cr1310"]},
    "IAS_16": {"title": "IAS 16 — ძ.საშ.", "rules": ["SL=(Cost-Res)÷Life", "DB=BV×%", "Dr7610/Cr1520"]},
    "F2": {"title": "F2 Mgmt", "formulas": ["BE=Fix÷Contrib/u", "Contrib=SP-VC"]},
    "F9": {"title": "F9 Finance", "formulas": ["NPV=Σ(CF÷(1+r)^t)-I0", "WACC=E/V×Re+D/V×Rd×(1-T)", "CAPM:Re=Rf+β×(Rm-Rf)"]},
}


# ── Formatting helpers ───────────────────────────────────────────────────────

def _fmt(a):
    return f"{a:,.2f}₾"


def _jl(side, acc, amount):
    name = CHART_OF_ACCOUNTS.get(acc, {}).get("name", acc)
    left = f"{side} {acc} {name}"
    return f"  {left}{' ' * max(0, 34 - len(left))} {_fmt(amount)}"


def _journal(*lines):
    return "\n".join(_jl(s, a, v) for s, a, v in lines)


def _payload(desc, lines, dt=None):
    return {
        "journal_date": dt or date.today().isoformat(),
        "description": desc,
        "lines": [{"account_code": a, "debit": dr, "credit": cr} for a, dr, cr in lines],
    }
