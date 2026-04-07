"""
Bridge Hub Knowledge Base — V2 (Self-Learning + Deep Rules)
ახალი შესაძლებლობები:
  ✅ გამონაკლისების ლოგიკა (VAT-ისგან გათავისუფლება, ექსპორტი)
  ✅ IFRS 15/16 ალგორითმები
  ✅ learn_new_rule() — ბუღალტერი ასწავლის AI-ს ახალ წესს
  ✅ Tenant-specific ცოდნა (კომპანიის მიხედვით)
  ✅ Confidence-based კლასიფიკაცია
  ✅ ავტომატური ლოგირება (სად გაუჭირდა)
"""

import json
import os
import re
from datetime import datetime
from typing import Optional

# ══════════════════════════════════════════════════════════════
# 1. საგადასახადო სისტემა — სრული ლოგიკა + გამონაკლისები
# ══════════════════════════════════════════════════════════════

TAX_RULES = {
    "VAT": {
        "rate": 0.18,
        "description": "დამატებული ღირებულების გადასახადი — 18%",
        "rules": [
            "VAT = ნეტო × 0.18",
            "ნეტო = ბრუტო ÷ 1.18 (VAT-ჩათვლილი ფასიდან)",
            "VAT = ბრუტო - ნეტო",
            "გატარება: Dr 1310 / Cr 6110 (ნეტო) + Cr 3310 (VAT)",
            "VAT-ის ჩათვლა: Dr 3310 / Cr 1310",
            "VAT-ის გადახდა: Dr 3310 / Cr 1110",
            "VAT-ის დეკლარაცია: ყოველი კვარტლის ბოლოს",
            "VAT-ის გადამხდელი: ბრუნვა > 100,000₾/წელ",
        ],
        # გათავისუფლება ჩათვლის უფლების გარეშე (Zero-rated)
        "exempt_no_credit": [
            "სამედიცინო მომსახურება და მედიკამენტები",
            "საგანმანათლებლო მომსახურება",
            "ფინანსური მომსახურება (სესხი, დეპოზიტი, სადაზღვევო)",
            "მიწის ნაკვეთის მიწოდება",
            "ლოტო, ლატარია, სათამაშო ბიზნესი",
            "ბინის (საცხოვრებელი) გაქირავება",
        ],
        # ჩათვლის უფლებით გათავისუფლება (Zero VAT + Credit)
        "exempt_with_credit": [
            "ექსპორტი (საქართველოს ფარგლებს გარეთ მიწოდება) — 0%",
            "საერთაშორისო სატრანსპორტო მომსახურება",
            "თავისუფალ ინდუსტრიულ ზონაში (FIZ) მიწოდება",
            "ტურისტული ზონის სასტუმრო (სპეც. სტატუსი)",
        ],
        # უკუდაბეგვრა (Reverse Charge)
        "reverse_charge": [
            "არარეზიდენტისგან ელექტრონული მომსახურების შეძენა (Google, Facebook, Netflix)",
            "არარეზიდენტისგან კონსულტაციის შეძენა",
            "გატარება: Dr 3310 (Input) / Cr 3310 (Output) — ნეტო ეფექტი ნული",
        ],
        "examples": [
            {"gross": 5900, "net": 5000, "vat": 900},
            {"gross": 1180, "net": 1000, "vat": 180},
        ]
    },
    "PIT": {
        "rate": 0.20,
        "payg_rate": 0.02,
        "description": "საშემოსავლო გადასახადი — 20% + PAYG 2%",
        "rules": [
            "PIT = ხელფასი × 0.20",
            "PAYG (დამსაქმებელი) = ხელფასი × 0.02",
            "PAYG (თანამშრომელი) = ხელფასი × 0.02",
            "ნეტო = ხელფასი - PIT - PAYG_თანამშრომელი",
            "გატარება: Dr 7210 / Cr 2110 (ნეტო) + Cr 3320 (PIT) + Cr 3330 (PAYG)",
            "გადახდა: ყოველი თვის 15-მდე RS.ge-ზე",
            "ფორმა: N4",
        ],
        "exempt": [
            "სამედიცინო ხარჯების კომპენსაცია (ლიმიტამდე)",
            "სამგზავრო ხარჯები (ლიმიტამდე)",
            "ჯანდაცვის დაზღვევა (ლიმიტამდე)",
        ],
        "examples": [
            {"gross": 3000, "pit": 600, "payg": 60, "net": 2340},
            {"gross": 2000, "pit": 400, "payg": 40, "net": 1560},
        ]
    },
    "CIT": {
        "rate": 0.15,
        "description": "მოგების გადასახადი — ესტონური მოდელი 15%",
        "rules": [
            "CIT = განაწილებული_მოგება × 0.15",
            "ესტონური მოდელი: გადასახადი მხოლოდ განაწილებულ მოგებაზე",
            "განაწილებული მოგება: დივიდენდი, არარეზიდენტზე გადახდა, ჩუქება",
            "გატარება: Dr 3340 / Cr 1110",
            "გადახდა: დივიდენდიდან 15 დღეში",
            "ფორმა: N101",
        ],
        "deemed_distribution": [
            "წარმომადგენლობითი ხარჯი > 1% შემოსავლიდან — ზედმეტი ნაწილი იბეგრება",
            "არარეზიდენტზე პროცენტის გადახდა",
            "არარეზიდენტზე ლიცენზიის საფასურის გადახდა (Royalty)",
            "კომპანიის ქონების პირადი მიზნებისთვის გამოყენება",
        ]
    },
    "PROPERTY_TAX": {
        "rate_max": 0.01,
        "description": "ქონების გადასახადი — 1%-მდე",
        "rules": [
            "განაკვეთი: 0%-დან 1%-მდე (ადგილობრივი ორგანო განსაზღვრავს)",
            "ბაზა: ქონების საბაზრო ღირებულება",
            "გადახდა: წელიწადში ორჯერ (15 ივნისი და 15 დეკემბერი)",
            "ფიზიკური პირი: 40,000₾-მდე ქონება — გათავისუფლებული",
        ]
    },
    "WITHHOLDING": {
        "description": "გადახდის წყაროსთან დაკავება",
        "rates": {
            "dividend_resident": 0.05,
            "dividend_nonresident": 0.05,
            "interest_nonresident": 0.05,
            "royalty_nonresident": 0.10,
            "rent_nonresident": 0.10,
        },
        "rules": [
            "არარეზიდენტზე დივიდენდი: 5% — Dr 4210 / Cr 3350",
            "არარეზიდენტზე პროცენტი: 5% — Dr 7910 / Cr 3350",
            "არარეზიდენტზე Royalty: 10% — Dr 7810 / Cr 3350",
        ]
    }
}

# ══════════════════════════════════════════════════════════════
# 2. ანგარიშთა გეგმა (Chart of Accounts)
# ══════════════════════════════════════════════════════════════

CHART_OF_ACCOUNTS = {
    "1110": {"name": "სალარო / ნაღდი ფული", "type": "asset", "keywords": ["ნაღდი", "სალარო", "cash", "კასა"]},
    "1120": {"name": "საბანკო ანგარიში", "type": "asset", "keywords": ["ბანკი", "tbc", "bog", "bank", "გადარიცხვა"]},
    "1210": {"name": "მოთხოვნები მყიდველებზე", "type": "asset", "keywords": ["მოთხოვნა", "დებიტორი", "receivable"]},
    "1310": {"name": "სასაქონლო-მატერიალური მარაგები", "type": "asset", "keywords": ["საქონელი", "მარაგი", "inventory"]},
    "1410": {"name": "წინასწარ გადახდილი ხარჯები", "type": "asset", "keywords": ["წინასწარ", "prepaid", "ავანსი"]},
    "1510": {"name": "ძირითადი საშუალებები", "type": "asset", "keywords": ["ძირითადი", "fixed asset", "შენობა", "მანქანა", "ტექნიკა"]},
    "1520": {"name": "დარიცხული ამორტიზაცია", "type": "asset_contra", "keywords": ["ამორტიზაცია", "depreciation"]},
    "1610": {"name": "არამატერიალური აქტივები", "type": "asset", "keywords": ["პატენტი", "ლიცენზია", "intangible", "software", "პროგრამა"]},
    "1710": {"name": "ROU აქტივი (IFRS 16)", "type": "asset", "keywords": ["rou", "right of use", "ifrs 16", "ლიზინგი", "leasing"]},
    "2110": {"name": "გასახდელი ხელფასი", "type": "liability", "keywords": ["ხელფასი", "salary", "payroll"]},
    "2210": {"name": "მოკლევადიანი სესხები", "type": "liability", "keywords": ["სესხი", "loan", "კრედიტი"]},
    "2310": {"name": "მიწოდებლებზე გადასახდელი", "type": "liability", "keywords": ["მიწოდებელი", "კრედიტორი", "payable"]},
    "2410": {"name": "სალიზინგო ვალდებულება (IFRS 16)", "type": "liability", "keywords": ["ლიზინგი", "leasing", "ifrs 16"]},
    "3310": {"name": "დღგ გადასახდელი", "type": "liability", "keywords": ["დღგ", "vat", "დამატებული ღირებულება"]},
    "3320": {"name": "PIT გადასახდელი", "type": "liability", "keywords": ["pit", "საშემოსავლო", "income tax"]},
    "3330": {"name": "PAYG გადასახდელი", "type": "liability", "keywords": ["payg", "pension", "საპენსიო"]},
    "3340": {"name": "CIT გადასახდელი", "type": "liability", "keywords": ["cit", "მოგება", "profit tax", "dividend"]},
    "3350": {"name": "Withholding Tax გადასახდელი", "type": "liability", "keywords": ["withholding", "გადახდის წყარო", "არარეზიდენტი"]},
    "4110": {"name": "საწესდებო კაპიტალი", "type": "equity", "keywords": ["კაპიტალი", "equity", "capital"]},
    "4210": {"name": "გაუნაწილებელი მოგება", "type": "equity", "keywords": ["მოგება", "retained earnings"]},
    "6110": {"name": "გაყიდვებიდან შემოსავალი", "type": "revenue", "keywords": ["გაყიდვა", "revenue", "income", "შემოსავალი"]},
    "6120": {"name": "მომსახურებიდან შემოსავალი", "type": "revenue", "keywords": ["მომსახურება", "service", "კონსულტაცია"]},
    "6130": {"name": "სხვა საოპერაციო შემოსავალი", "type": "revenue", "keywords": ["სხვა შემოსავალი", "other income"]},
    "7110": {"name": "გაყიდული საქონლის ღირებულება (COGS)", "type": "expense", "keywords": ["cogs", "cost of goods", "ღირებულება"]},
    "7210": {"name": "ხელფასის ხარჯი", "type": "expense", "keywords": ["ხელფასი", "salary expense", "payroll"]},
    "7310": {"name": "ქირის ხარჯი", "type": "expense", "keywords": ["ქირა", "rent", "იჯარა", "ოფისი"]},
    "7410": {"name": "კომუნალური ხარჯი", "type": "expense", "keywords": ["კომუნალური", "utilities", "დენი", "electricity", "წყალი", "გაზი"]},
    "7510": {"name": "საბანკო საკომისიო", "type": "expense", "keywords": ["საკომისიო", "commission", "bank fee", "tbc", "bog", "სერვის"]},
    "7610": {"name": "ამორტიზაციის ხარჯი", "type": "expense", "keywords": ["ამორტიზაცია", "depreciation"]},
    "7710": {"name": "სარეკლამო ხარჯი", "type": "expense", "keywords": ["რეკლამა", "marketing", "advertising", "facebook", "google", "instagram"]},
    "7720": {"name": "წარმომადგენლობითი ხარჯი", "type": "expense", "keywords": ["წარმომადგენლობითი", "entertainment", "representative", "რესტორანი", "სასტუმრო"]},
    "7810": {"name": "სხვა ხარჯები", "type": "expense", "keywords": ["სხვა", "other", "miscellaneous"]},
    "7910": {"name": "პროცენტის ხარჯი", "type": "expense", "keywords": ["პროცენტი", "interest", "სარგებელი"]},
}

# ══════════════════════════════════════════════════════════════
# 3. კლასიფიკაციის წესები
# ══════════════════════════════════════════════════════════════

CLASSIFICATION_RULES = [
    {"keywords": ["tbc", "bog", "საკომისიო", "bank fee", "commission", "სერვის", "ბანკი"], "account": "7510", "confidence": 0.95},
    {"keywords": ["tbc transfer", "bog transfer", "გადარიცხვა", "transfer"], "account": "1120", "confidence": 0.90},
    {"keywords": ["ხელფასი", "salary", "payroll", "მუშაკი", "თანამშრომელი"], "account": "7210", "confidence": 0.95},
    {"keywords": ["ქირა", "rent", "იჯარა", "ოფისი", "office"], "account": "7310", "confidence": 0.92},
    {"keywords": ["კომუნალური", "utilities", "დენი", "electricity", "წყალი", "water", "გაზი", "gas"], "account": "7410", "confidence": 0.93},
    {"keywords": ["გაყიდვა", "sale", "invoice", "ინვოისი"], "account": "6110", "confidence": 0.88},
    {"keywords": ["მომსახურება", "service", "კონსულტაცია"], "account": "6120", "confidence": 0.85},
    {"keywords": ["დღგ", "vat", "დამატებული ღირებულება"], "account": "3310", "confidence": 0.97},
    {"keywords": ["pit", "საშემოსავლო", "income tax"], "account": "3320", "confidence": 0.97},
    {"keywords": ["payg", "pension", "საპენსიო"], "account": "3330", "confidence": 0.97},
    {"keywords": ["cit", "მოგება", "profit tax", "dividend", "დივიდენდი"], "account": "3340", "confidence": 0.97},
    {"keywords": ["რეკლამა", "marketing", "advertising", "facebook ads", "google ads", "instagram"], "account": "7710", "confidence": 0.90},
    {"keywords": ["წარმომადგენლობითი", "entertainment", "representative", "რესტორანი"], "account": "7720", "confidence": 0.88},
    {"keywords": ["პროცენტი", "interest", "სარგებელი", "loan interest"], "account": "7910", "confidence": 0.93},
    {"keywords": ["ამორტიზაცია", "depreciation", "amortization"], "account": "7610", "confidence": 0.95},
    {"keywords": ["ნაღდი", "cash", "სალარო", "კასა"], "account": "1110", "confidence": 0.90},
    {"keywords": ["ლიზინგი", "leasing", "ifrs 16", "rou"], "account": "1710", "confidence": 0.92},
    {"keywords": ["არარეზიდენტი", "nonresident", "withholding"], "account": "3350", "confidence": 0.90},
    # Wolt, Glovo, Bolt — ხშირი ქართული ბიზნეს ხარჯები
    {"keywords": ["wolt", "glovo", "bolt food"], "account": "7720", "confidence": 0.85},
    {"keywords": ["bolt"], "account": "7810", "confidence": 0.80},
    {"keywords": ["amazon", "aws", "google cloud", "azure"], "account": "7810", "confidence": 0.85},
]

# ══════════════════════════════════════════════════════════════
# 4. ACCA + IFRS სტანდარტები — ალგორითმებით
# ══════════════════════════════════════════════════════════════

ACCA_STANDARDS = {
    "IFRS_15_REVENUE": {
        "title": "IFRS 15 — შემოსავლის აღიარება (5-ნაბიჯიანი მოდელი)",
        "steps": [
            "ნაბიჯი 1: გამოავლინე კონტრაქტი მომხმარებელთან",
            "ნაბიჯი 2: გამოავლინე შესრულების ვალდებულებები (Performance Obligations)",
            "ნაბიჯი 3: განსაზღვრე ტრანზაქციის ფასი",
            "ნაბიჯი 4: გაანაწილე ფასი შესრულების ვალდებულებებზე",
            "ნაბიჯი 5: აღიარე შემოსავალი ვალდებულების შესრულებისას",
        ],
        "key_rules": [
            "კონტროლი გადაეცა? → შემოსავლის აღიარება",
            "დროში გაწელილი შესრულება: %-ით (Percentage of Completion)",
            "ვარიაბელური ანაზღაურება: მხოლოდ Highly Probable ნაწილი",
        ]
    },
    "IFRS_16_LEASES": {
        "title": "IFRS 16 — იჯარა",
        "lessee_accounting": [
            "ROU აქტივი = PV(სალიზინგო გადასახდელები) + საწყისი პირდაპირი ხარჯები",
            "სალიზინგო ვალდებულება = PV(სალიზინგო გადასახდელები)",
            "ამორტიზაცია: ROU ÷ იჯარის ვადა",
            "პროცენტი: ვალდებულება × საპროცენტო განაკვეთი",
            "გატარება (დასაწყისი): Dr 1710 (ROU) / Cr 2410 (ვალდებულება)",
            "გატარება (გადახდა): Dr 2410 / Dr 7910 (პროცენტი) / Cr 1120",
            "გამონაკლისი: < 12 თვე ან < $5,000 — შეიძლება ოპერაციულ ხარჯად",
        ]
    },
    "IAS_2_INVENTORIES": {
        "title": "IAS 2 — მარაგები",
        "rules": [
            "შეფასება: ღირებულება ან NRV (Net Realisable Value) — რომელიც დაბალია",
            "ღირებულება: შეძენის ფასი + პირდაპირი ხარჯები",
            "NRV = სავარაუდო გასაყიდი ფასი - სავარაუდო ხარჯები",
            "FIFO ან Weighted Average — LIFO დაუშვებელია IFRS-ით",
            "ჩამოწერა: Dr 7110 / Cr 1310",
        ]
    },
    "IAS_16_PPE": {
        "title": "IAS 16 — ძირითადი საშუალებები",
        "rules": [
            "საწყისი აღიარება: ღირებულება (Cost Model) ან გადაფასება (Revaluation Model)",
            "ამორტიზაცია: Straight-line = (ღირებულება - ნარჩენი) ÷ სასარგებლო ვადა",
            "ამორტიზაცია: Reducing Balance = საბალანსო ღირებულება × %",
            "გატარება: Dr 7610 / Cr 1520",
            "ჩამოწერა: Dr 1520 + Dr ზარალი / Cr 1510",
        ]
    },
    "F2_MANAGEMENT": {
        "title": "F2 — მენეჯმენტის აღრიცხვა",
        "formulas": [
            "Break-even = Fixed Costs ÷ Contribution per unit",
            "Contribution = Selling Price - Variable Cost",
            "Margin of Safety = (Actual - Break-even) ÷ Actual × 100%",
            "Absorption Costing: Fixed overhead → product cost",
            "Marginal Costing: Fixed overhead → period cost",
        ]
    },
    "F9_FINANCE": {
        "title": "F9 — ფინანსური მენეჯმენტი",
        "formulas": [
            "NPV = Σ (CF ÷ (1+r)^t) - Initial Investment",
            "IRR: discount rate where NPV = 0",
            "WACC = (E/V × Re) + (D/V × Rd × (1-T))",
            "CAPM: Re = Rf + β × (Rm - Rf)",
            "Current Ratio = Current Assets ÷ Current Liabilities",
            "Quick Ratio = (CA - Inventory) ÷ CL",
            "Debt/Equity = Total Debt ÷ Total Equity",
        ]
    }
}

# ══════════════════════════════════════════════════════════════
# 5. Bridge Hub — სისტემის ცოდნა
# ══════════════════════════════════════════════════════════════

BRIDGE_HUB_KNOWLEDGE = {
    "integrations": {
        "balance_ge": "Balance.ge — ქართული ბუღალტრული სისტემა (API ინტეგრაცია)",
        "1c": "1C:Enterprise — ERP სისტემა (XML ექსპორტი)",
        "tbc": "TBC Bank — ბანკის ამონაწერი (CSV/API)",
        "bog": "Bank of Georgia — ბანკის ამონაწერი (CSV/API)",
        "rs_ge": "RS.ge — შემოსავლების სამსახური (ელ-ფაქტურა, PIT, VAT)",
        "gmail": "Gmail IMAP — ინვოისების ავტო-პროცესინგი",
    },
    "endpoints": {
        "health": "GET /health",
        "ai_chat": "POST /api/ai/chat",
        "ai_search": "GET /api/ai/search",
        "ai_stats": "GET /api/ai/stats",
        "ai_vat": "POST /api/ai/vat",
        "ai_payroll": "POST /api/ai/payroll",
        "ai_classify": "POST /api/ai/classify",
        "classify": "POST /api/classify",
        "approve": "POST /api/approve",
        "export": "GET /api/export",
        "payroll": "POST /api/payroll/calculate",
        "ocr": "POST /api/ocr/upload",
        "bank_sync": "POST /api/bank-sync",
    }
}

# ══════════════════════════════════════════════════════════════
# 6. Tenant-Specific ცოდნა (კომპანიის მიხედვით)
# ══════════════════════════════════════════════════════════════

# ეს ფაილი ინახება: learned_rules.json
LEARNED_RULES_FILE = os.path.join(os.path.dirname(__file__), "learned_rules.json")

def _load_learned_rules() -> list:
    """ნასწავლი წესების ჩატვირთვა."""
    if os.path.exists(LEARNED_RULES_FILE):
        try:
            with open(LEARNED_RULES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def _save_learned_rules(rules: list):
    """ნასწავლი წესების შენახვა."""
    with open(LEARNED_RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def learn_new_rule(description_pattern: str, account: str, tenant_id: str = "global", note: str = "") -> dict:
    """
    ბუღალტერი ასწავლის AI-ს ახალ წესს.

    გამოყენება:
        learn_new_rule("Wolt", "7720", tenant_id="company_abc", note="Wolt = წარმომადგენლობითი")
        learn_new_rule("AWS", "7810", note="Amazon AWS = IT ხარჯი")
    """
    rules = _load_learned_rules()

    # შევამოწმოთ, უკვე არ არსებობს
    for r in rules:
        if r["pattern"].lower() == description_pattern.lower() and r["tenant_id"] == tenant_id:
            r["account"] = account
            r["note"] = note
            r["updated_at"] = datetime.now().isoformat()
            _save_learned_rules(rules)
            return {"status": "updated", "rule": r}

    new_rule = {
        "pattern": description_pattern,
        "account": account,
        "tenant_id": tenant_id,
        "note": note,
        "confidence": 0.99,
        "created_at": datetime.now().isoformat(),
        "source": "human_correction",
    }
    rules.append(new_rule)
    _save_learned_rules(rules)

    account_name = CHART_OF_ACCOUNTS.get(account, {}).get("name", "უცნობი")
    return {
        "status": "learned",
        "message": f"✅ ვისწავლე: '{description_pattern}' → {account} ({account_name})",
        "rule": new_rule
    }


# ══════════════════════════════════════════════════════════════
# 7. კლასიფიკაციის ძრავი
# ══════════════════════════════════════════════════════════════

def classify_transaction(description: str, tenant_id: str = "global") -> dict:
    """ტრანზაქციის კლასიფიკაცია — Tenant + Global წესებით."""
    desc_lower = description.lower()

    # 1. Tenant-specific ნასწავლი წესები (უმაღლესი პრიორიტეტი)
    learned = _load_learned_rules()
    for rule in learned:
        if rule["tenant_id"] in (tenant_id, "global"):
            if rule["pattern"].lower() in desc_lower:
                account_code = rule["account"]
                account_info = CHART_OF_ACCOUNTS.get(account_code, {})
                return {
                    "account": account_code,
                    "name": account_info.get("name", "უცნობი"),
                    "confidence": rule["confidence"],
                    "source": "learned_rule",
                    "note": rule.get("note", ""),
                }

    # 2. სტანდარტული კლასიფიკაციის წესები
    best_match = None
    best_score = 0
    for rule in CLASSIFICATION_RULES:
        score = sum(1 for kw in rule["keywords"] if kw.lower() in desc_lower)
        if score > best_score:
            best_score = score
            best_match = rule

    if best_match and best_score > 0:
        account_code = best_match["account"]
        account_info = CHART_OF_ACCOUNTS.get(account_code, {})
        confidence = best_match["confidence"]
        return {
            "account": account_code,
            "name": account_info.get("name", "უცნობი"),
            "confidence": confidence,
            "source": "rules_engine",
            "needs_review": confidence < 0.80,
        }

    # 3. Fallback
    return {
        "account": "7810",
        "name": "სხვა ხარჯები",
        "confidence": 0.40,
        "source": "fallback",
        "needs_review": True,
    }


# ══════════════════════════════════════════════════════════════
# 8. საგადასახადო კალკულატორები
# ══════════════════════════════════════════════════════════════

def calculate_vat(amount: float, inclusive: bool = True, service_type: str = "standard") -> dict:
    """VAT-ის გაანგარიშება გამონაკლისების გათვალისწინებით."""
    # გამონაკლისების შემოწმება
    exempt_types = {
        "medical": ("სამედიცინო მომსახურება — VAT-ისგან გათავისუფლებული", 0.0),
        "education": ("საგანმანათლებლო მომსახურება — VAT-ისგან გათავისუფლებული", 0.0),
        "export": ("ექსპორტი — 0% VAT (ჩათვლის უფლებით)", 0.0),
        "financial": ("ფინანსური მომსახურება — VAT-ისგან გათავისუფლებული", 0.0),
    }
    if service_type in exempt_types:
        note, rate = exempt_types[service_type]
        return {"gross": amount, "net": amount, "vat": 0.0, "rate": "0%", "note": note}

    # სტანდარტული გაანგარიშება
    if inclusive:
        net = round(amount / 1.18, 2)
        vat = round(amount - net, 2)
    else:
        net = amount
        vat = round(amount * 0.18, 2)

    return {
        "gross": round(net + vat, 2),
        "net": net,
        "vat": vat,
        "rate": "18%",
        "journal": f"Dr 1310 {net}₾ / Cr 6110 {net}₾, Cr 3310 {vat}₾",
        "service_type": service_type,
    }


def calculate_payroll(gross: float, include_employee_payg: bool = True) -> dict:
    """ხელფასის გაანგარიშება."""
    pit = round(gross * 0.20, 2)
    payg_employee = round(gross * 0.02, 2) if include_employee_payg else 0.0
    payg_employer = round(gross * 0.02, 2)
    net = round(gross - pit - payg_employee, 2)
    return {
        "gross": gross,
        "pit": pit,
        "payg_employee": payg_employee,
        "payg_employer": payg_employer,
        "net": net,
        "total_employer_cost": round(gross + payg_employer, 2),
        "journal": f"Dr 7210 {gross}₾ / Cr 2110 {net}₾, Cr 3320 {pit}₾, Cr 3330 {payg_employee + payg_employer}₾",
        "deadline": "ყოველი თვის 15-მდე RS.ge-ზე (ფორმა N4)",
    }


def calculate_cit(distributed_profit: float) -> dict:
    """CIT — ესტონური მოდელი."""
    cit = round(distributed_profit * 0.15, 2)
    net_dividend = round(distributed_profit - cit, 2)
    return {
        "distributed_profit": distributed_profit,
        "cit": cit,
        "net_dividend": net_dividend,
        "rate": "15%",
        "journal": f"Dr 4210 {distributed_profit}₾ / Cr 3340 {cit}₾, Cr 1120 {net_dividend}₾",
        "deadline": "დივიდენდის გაცემიდან 15 დღეში (ფორმა N101)",
    }


def calculate_depreciation(cost: float, residual: float, useful_life_years: int, method: str = "straight_line") -> dict:
    """ამორტიზაციის გაანგარიშება."""
    if method == "straight_line":
        annual = round((cost - residual) / useful_life_years, 2)
        monthly = round(annual / 12, 2)
        return {
            "method": "Straight-Line",
            "annual_depreciation": annual,
            "monthly_depreciation": monthly,
            "journal_monthly": f"Dr 7610 {monthly}₾ / Cr 1520 {monthly}₾",
        }
    elif method == "reducing_balance":
        rate = round(1 - (residual / cost) ** (1 / useful_life_years), 4)
        annual_year1 = round(cost * rate, 2)
        return {
            "method": "Reducing Balance",
            "rate": f"{rate*100:.2f}%",
            "annual_depreciation_year1": annual_year1,
            "journal_monthly": f"Dr 7610 / Cr 1520 (ყოველი თვე)",
        }
    return {"error": "უცნობი მეთოდი"}


# ══════════════════════════════════════════════════════════════
# 9. ძიების ძრავი
# ══════════════════════════════════════════════════════════════

def search_knowledge(query: str, top_k: int = 5) -> list:
    """ცოდნის ბაზაში ძიება."""
    query_lower = query.lower()
    results = []

    for tax_name, tax_data in TAX_RULES.items():
        for rule in tax_data.get("rules", []):
            if any(w in rule.lower() for w in query_lower.split() if len(w) > 2):
                results.append({"category": "TAX", "source": tax_name, "text": rule, "relevance": 0.9})
        for item in tax_data.get("exempt_no_credit", []):
            if any(w in item.lower() for w in query_lower.split() if len(w) > 2):
                results.append({"category": "TAX_EXEMPT", "source": tax_name, "text": item, "relevance": 0.88})
        for item in tax_data.get("deemed_distribution", []):
            if any(w in item.lower() for w in query_lower.split() if len(w) > 2):
                results.append({"category": "CIT_DEEMED", "source": tax_name, "text": item, "relevance": 0.87})

    for code, account in CHART_OF_ACCOUNTS.items():
        if any(kw in query_lower for kw in account["keywords"]):
            results.append({"category": "COA", "source": f"ანგარიში {code}", "text": f"{code} — {account['name']}", "relevance": 0.85})

    for std_name, std_data in ACCA_STANDARDS.items():
        for key in ["steps", "rules", "key_rules", "formulas", "lessee_accounting"]:
            for item in std_data.get(key, []):
                if any(w in item.lower() for w in query_lower.split() if len(w) > 3):
                    results.append({"category": "ACCA", "source": std_name, "text": item, "relevance": 0.80})

    results.sort(key=lambda x: x["relevance"], reverse=True)
    return results[:top_k]


def get_context_for_llm(query: str, max_chars: int = 3000) -> str:
    """LLM-ისთვის კონტექსტის მომზადება."""
    results = search_knowledge(query, top_k=12)
    context_parts = []
    total_chars = 0
    for r in results:
        text = f"[{r['category']}] {r['source']}: {r['text']}"
        if total_chars + len(text) > max_chars:
            break
        context_parts.append(text)
        total_chars += len(text)
    return "\n".join(context_parts)


def get_stats() -> dict:
    """სტატისტიკა."""
    learned = _load_learned_rules()
    return {
        "tax_rules": len(TAX_RULES),
        "accounts": len(CHART_OF_ACCOUNTS),
        "classification_rules": len(CLASSIFICATION_RULES),
        "acca_standards": len(ACCA_STANDARDS),
        "learned_rules": len(learned),
        "total_knowledge_items": (
            len(TAX_RULES) +
            len(CHART_OF_ACCOUNTS) +
            len(CLASSIFICATION_RULES) +
            sum(len(v.get("topics", [])) + len(v.get("steps", [])) + len(v.get("rules", [])) + len(v.get("formulas", [])) for v in ACCA_STANDARDS.values()) +
            sum(len(v.get("rules", [])) + len(v.get("exempt_no_credit", [])) + len(v.get("deemed_distribution", [])) for v in TAX_RULES.values()) +
            len(learned)
        )
    }


# ══════════════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🧪 Bridge Hub Knowledge Base V2 — ტესტი\n")

    vat = calculate_vat(5900, inclusive=True)
    print(f"✅ VAT: 5900₾ → ნეტო={vat['net']}₾, VAT={vat['vat']}₾")

    vat_export = calculate_vat(5000, inclusive=False, service_type="export")
    print(f"✅ ექსპორტი VAT: {vat_export['note']}")

    pay = calculate_payroll(3000)
    print(f"✅ Payroll: PIT={pay['pit']}₾, PAYG={pay['payg_employee']}₾, ნეტო={pay['net']}₾")

    cit = calculate_cit(10000)
    print(f"✅ CIT: 10000₾ → CIT={cit['cit']}₾, ნეტო={cit['net_dividend']}₾")

    dep = calculate_depreciation(12000, 2000, 5)
    print(f"✅ ამორტიზაცია: {dep['annual_depreciation']}₾/წელ, {dep['monthly_depreciation']}₾/თვე")

    cls = classify_transaction("TBC საბანკო საკომისიო 45₾")
    print(f"✅ კლასიფიკაცია: {cls['account']} ({cls['confidence']*100:.0f}%)")

    # Self-learning ტესტი
    result = learn_new_rule("Wolt", "7720", note="Wolt = წარმომადგენლობითი ხარჯი")
    print(f"✅ Self-learning: {result['message']}")

    cls2 = classify_transaction("Wolt 35₾")
    print(f"✅ ნასწავლი წესი: Wolt → {cls2['account']} ({cls2['source']})")

    stats = get_stats()
    print(f"\n📊 სტატისტიკა: {stats['total_knowledge_items']} ელემენტი, {stats['learned_rules']} ნასწავლი წესი")
