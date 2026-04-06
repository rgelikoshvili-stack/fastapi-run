"""
Bridge Hub — სრული ცოდნის ბაზა (Pure Python)
ყველა ქართული საგადასახადო წესი, ACCA სტანდარტი და GAAS კლასიფიკაცია
Python კოდში ჩაშენებული — JSON ფაილი არ სჭირდება
"""

# ══════════════════════════════════════════════════════════════
# 1. საქართველოს საგადასახადო სისტემა
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
        "examples": [
            {"gross": 5900, "net": 5000, "vat": 900},
            {"gross": 1180, "net": 1000, "vat": 180},
            {"gross": 2360, "net": 2000, "vat": 360},
        ]
    },
    "PIT": {
        "rate": 0.20,
        "description": "საშემოსავლო გადასახადი — 20%",
        "rules": [
            "PIT = ხელფასი × 0.20",
            "PAYG = ხელფასი × 0.02 (დამსაქმებელი იხდის)",
            "ნეტო = ხელფასი - PIT - PAYG (თუ PAYG თანამშრომელს ეკისრება)",
            "ნეტო = ხელფასი - PIT (ჩვეულებრივ)",
            "გატარება: Dr 7210 / Cr 2110 (ნეტო) + Cr 3320 (PIT) + Cr 3330 (PAYG)",
            "PIT-ის გადახდა: ყოველი თვის 15-მდე",
            "PAYG-ის გადახდა: ყოველი თვის 15-მდე",
            "RS.ge-ზე: ფორმა N4 (ხელფასების დეკლარაცია)",
        ],
        "examples": [
            {"gross": 3000, "pit": 600, "payg": 60, "net": 2340},
            {"gross": 2000, "pit": 400, "payg": 40, "net": 1560},
            {"gross": 5000, "pit": 1000, "payg": 100, "net": 3900},
        ]
    },
    "CIT": {
        "rate": 0.15,
        "description": "მოგების გადასახადი (ესტონური მოდელი) — 15%",
        "rules": [
            "CIT = დივიდენდი × 0.15 (გასაცემ თანხაზე)",
            "CIT = დივიდენდი × 0.15/0.85 (ნეტო-დან გამოთვლა)",
            "ესტონური მოდელი: გადასახადი მხოლოდ განაწილებულ მოგებაზე",
            "გატარება: Dr 3340 / Cr 1110",
            "გადახდა: დივიდენდის გაცემიდან 15 დღეში",
            "RS.ge-ზე: ფორმა N101",
        ]
    },
    "PROPERTY_TAX": {
        "rate_max": 0.01,
        "description": "ქონების გადასახადი — 1%-მდე",
        "rules": [
            "განაკვეთი: 0%-დან 1%-მდე (ადგილობრივი ორგანო განსაზღვრავს)",
            "ბაზა: ქონების საბაზრო ღირებულება",
            "გადახდა: წელიწადში ორჯერ",
        ]
    },
    "EXCISE": {
        "description": "აქციზი — სპეციფიკური საქონელი",
        "rules": [
            "ალკოჰოლი, თამბაქო, საწვავი — ფიქსირებული განაკვეთი",
            "RS.ge-ზე: ფორმა N6",
        ]
    }
}

# ══════════════════════════════════════════════════════════════
# 2. ანგარიშთა გეგმა (Chart of Accounts)
# ══════════════════════════════════════════════════════════════

CHART_OF_ACCOUNTS = {
    # 1xxx — აქტივები
    "1110": {"name": "სალარო / ნაღდი ფული", "type": "asset", "keywords": ["ნაღდი", "სალარო", "cash", "კასა"]},
    "1120": {"name": "საბანკო ანგარიში", "type": "asset", "keywords": ["ბანკი", "tbc", "bog", "bank", "გადარიცხვა"]},
    "1210": {"name": "მოთხოვნები მყიდველებზე", "type": "asset", "keywords": ["მოთხოვნა", "დებიტორი", "receivable"]},
    "1310": {"name": "სასაქონლო-მატერიალური მარაგები", "type": "asset", "keywords": ["საქონელი", "მარაგი", "inventory"]},
    "1410": {"name": "წინასწარ გადახდილი ხარჯები", "type": "asset", "keywords": ["წინასწარ", "prepaid", "ავანსი"]},
    "1510": {"name": "ძირითადი საშუალებები", "type": "asset", "keywords": ["ძირითადი", "fixed asset", "შენობა", "მანქანა"]},
    "1610": {"name": "არამატერიალური აქტივები", "type": "asset", "keywords": ["პატენტი", "ლიცენზია", "intangible"]},
    # 2xxx — ვალდებულებები
    "2110": {"name": "გასახდელი ხელფასი", "type": "liability", "keywords": ["ხელფასი", "salary", "payroll"]},
    "2210": {"name": "მოკლევადიანი სესხები", "type": "liability", "keywords": ["სესხი", "loan", "კრედიტი"]},
    "2310": {"name": "მიწოდებლებზე გადასახდელი", "type": "liability", "keywords": ["მიწოდებელი", "კრედიტორი", "payable"]},
    # 3xxx — გადასახადები
    "3310": {"name": "დღგ გადასახდელი", "type": "liability", "keywords": ["დღგ", "vat", "დამატებული ღირებულება"]},
    "3320": {"name": "PIT გადასახდელი", "type": "liability", "keywords": ["pit", "საშემოსავლო", "income tax"]},
    "3330": {"name": "PAYG გადასახდელი", "type": "liability", "keywords": ["payg", "pension", "საპენსიო"]},
    "3340": {"name": "CIT გადასახდელი", "type": "liability", "keywords": ["cit", "მოგება", "profit tax", "dividend"]},
    # 4xxx — კაპიტალი
    "4110": {"name": "საწესდებო კაპიტალი", "type": "equity", "keywords": ["კაპიტალი", "equity", "capital"]},
    "4210": {"name": "გაუნაწილებელი მოგება", "type": "equity", "keywords": ["მოგება", "retained earnings"]},
    # 5xxx — შემოსავლები
    "6110": {"name": "გაყიდვებიდან შემოსავალი", "type": "revenue", "keywords": ["გაყიდვა", "revenue", "income", "შემოსავალი", "ანაზღაურება"]},
    "6120": {"name": "მომსახურებიდან შემოსავალი", "type": "revenue", "keywords": ["მომსახურება", "service", "კონსულტაცია"]},
    # 6xxx — ხარჯები
    "7110": {"name": "გაყიდული საქონლის ღირებულება", "type": "expense", "keywords": ["COGS", "cost of goods", "ღირებულება"]},
    "7210": {"name": "ხელფასის ხარჯი", "type": "expense", "keywords": ["ხელფასი", "salary expense", "payroll"]},
    "7310": {"name": "ქირის ხარჯი", "type": "expense", "keywords": ["ქირა", "rent", "იჯარა", "ოფისი"]},
    "7410": {"name": "კომუნალური ხარჯი", "type": "expense", "keywords": ["კომუნალური", "utilities", "დენი", "წყალი", "გაზი"]},
    "7510": {"name": "საბანკო საკომისიო", "type": "expense", "keywords": ["საკომისიო", "commission", "bank fee", "tbc", "bog", "სერვის"]},
    "7610": {"name": "ამორტიზაცია", "type": "expense", "keywords": ["ამორტიზაცია", "depreciation"]},
    "7710": {"name": "სარეკლამო ხარჯი", "type": "expense", "keywords": ["რეკლამა", "marketing", "advertising"]},
    "7810": {"name": "სხვა ხარჯები", "type": "expense", "keywords": ["სხვა", "other", "miscellaneous"]},
    "7910": {"name": "პროცენტის ხარჯი", "type": "expense", "keywords": ["პროცენტი", "interest", "სარგებელი"]},
}

# ══════════════════════════════════════════════════════════════
# 3. GAAS v5.2 — AI კლასიფიკაციის წესები
# ══════════════════════════════════════════════════════════════

CLASSIFICATION_RULES = [
    # ბანკი
    {"keywords": ["tbc", "bog", "საკომისიო", "bank fee", "commission", "სერვის", "ბანკი"], "account": "7510", "confidence": 0.95},
    {"keywords": ["tbc transfer", "bog transfer", "გადარიცხვა", "transfer"], "account": "1120", "confidence": 0.90},
    # ხელფასი
    {"keywords": ["ხელფასი", "salary", "payroll", "მუშაკი", "თანამშრომელი"], "account": "7210", "confidence": 0.95},
    # ქირა
    {"keywords": ["ქირა", "rent", "იჯარა", "ოფისი", "office"], "account": "7310", "confidence": 0.92},
    # კომუნალური
    {"keywords": ["კომუნალური", "utilities", "დენი", "electricity", "წყალი", "water", "გაზი", "gas"], "account": "7410", "confidence": 0.93},
    # გაყიდვა
    {"keywords": ["გაყიდვა", "sale", "invoice", "ინვოისი", "მომსახურება", "service"], "account": "6110", "confidence": 0.88},
    # VAT
    {"keywords": ["დღგ", "vat", "დამატებული ღირებულება"], "account": "3310", "confidence": 0.97},
    # PIT
    {"keywords": ["pit", "საშემოსავლო", "income tax", "3320"], "account": "3320", "confidence": 0.97},
    # PAYG
    {"keywords": ["payg", "pension", "საპენსიო", "3330"], "account": "3330", "confidence": 0.97},
    # სარეკლამო
    {"keywords": ["რეკლამა", "marketing", "advertising", "facebook", "google ads"], "account": "7710", "confidence": 0.90},
    # პროცენტი
    {"keywords": ["პროცენტი", "interest", "სარგებელი", "loan interest"], "account": "7910", "confidence": 0.93},
    # ამორტიზაცია
    {"keywords": ["ამორტიზაცია", "depreciation", "amortization"], "account": "7610", "confidence": 0.95},
    # ნაღდი
    {"keywords": ["ნაღდი", "cash", "სალარო", "კასა"], "account": "1110", "confidence": 0.90},
]

# ══════════════════════════════════════════════════════════════
# 4. ACCA სტანდარტები — ძირითადი ცნებები
# ══════════════════════════════════════════════════════════════

ACCA_STANDARDS = {
    "F2_MANAGEMENT_ACCOUNTING": {
        "topics": [
            "Break-even = Fixed Costs ÷ Contribution per unit",
            "Contribution = Selling Price - Variable Cost",
            "Margin of Safety = (Actual Sales - Break-even Sales) ÷ Actual Sales × 100%",
            "Absorption Costing: Fixed overhead absorbed into product cost",
            "Marginal Costing: Fixed overhead treated as period cost",
            "Variance Analysis: Actual vs Budget",
            "Standard Costing: Predetermined costs for planning",
        ]
    },
    "F3_FINANCIAL_ACCOUNTING": {
        "topics": [
            "Double Entry: Every debit has equal credit",
            "Assets = Liabilities + Equity (Accounting Equation)",
            "Income Statement: Revenue - Expenses = Profit",
            "Balance Sheet: Assets = Liabilities + Equity",
            "Cash Flow Statement: Operating + Investing + Financing",
            "Accruals Concept: Record when earned/incurred not when cash received/paid",
            "Going Concern: Business will continue operating",
            "Depreciation: Straight-line = (Cost - Residual) ÷ Useful Life",
        ]
    },
    "F9_FINANCIAL_MANAGEMENT": {
        "topics": [
            "NPV = Σ (Cash Flow ÷ (1+r)^t) - Initial Investment",
            "IRR: Discount rate where NPV = 0",
            "Payback Period: Time to recover initial investment",
            "WACC = (E/V × Re) + (D/V × Rd × (1-T))",
            "Beta: Measure of systematic risk",
            "CAPM: Re = Rf + β × (Rm - Rf)",
            "Working Capital = Current Assets - Current Liabilities",
            "Current Ratio = Current Assets ÷ Current Liabilities",
            "Quick Ratio = (Current Assets - Inventory) ÷ Current Liabilities",
        ]
    },
    "IFRS_KEY": {
        "topics": [
            "IFRS 15: Revenue Recognition — 5-step model",
            "IFRS 16: Leases — Right-of-use asset",
            "IAS 2: Inventories — Lower of cost or NRV",
            "IAS 16: Property, Plant & Equipment",
            "IAS 36: Impairment of Assets",
            "IAS 37: Provisions, Contingent Liabilities",
            "IAS 38: Intangible Assets",
        ]
    }
}

# ══════════════════════════════════════════════════════════════
# 5. Bridge Hub — სისტემის ცოდნა
# ══════════════════════════════════════════════════════════════

BRIDGE_HUB_KNOWLEDGE = {
    "architecture": {
        "layers": [
            "Layer 1: API Gateway (FastAPI)",
            "Layer 2: Auth & RBAC (JWT + Roles)",
            "Layer 3: Tenant Middleware (Multi-tenant DB isolation)",
            "Layer 4: Rate Limiting (SlowAPI)",
            "Layer 5: Business Logic (Routes)",
            "Layer 6: AI Classification (GPT-4 + OpenRouter)",
            "Layer 7: Learning System (Pattern decay)",
            "Layer 8: Database (PostgreSQL)",
            "Layer 9: External APIs (Balance.ge, RS.ge, TBC, BOG)",
            "Layer 10: Cloud Run (Google Cloud)",
        ],
        "classification_chain": [
            "Step 1: Exact Match (patterns table)",
            "Step 2: Fuzzy Match (similarity > 0.85)",
            "Step 3: Rules Engine (keyword rules)",
            "Step 4: LLM (GPT-4 / Claude via OpenRouter)",
            "Step 5: Fallback (manual review)",
        ]
    },
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
        "classify": "POST /api/classify",
        "approve": "POST /api/approve",
        "export": "GET /api/export",
        "payroll": "POST /api/payroll/calculate",
        "ocr": "POST /api/ocr/upload",
        "bank_sync": "POST /api/bank-sync",
    }
}

# ══════════════════════════════════════════════════════════════
# 6. ქართული ბიზნეს სამართალი — ძირითადი ნორმები
# ══════════════════════════════════════════════════════════════

GEORGIAN_LAW = {
    "company_types": {
        "შ.პ.ს.": "შეზღუდული პასუხისმგებლობის საზოგადოება — მინ. კაპიტალი 1 ლარი",
        "ი.მ.": "ინდივიდუალური მეწარმე — პირადი პასუხისმგებლობა",
        "ს.ს.": "სააქციო საზოგადოება — აქციები, სამეთვალყურეო საბჭო",
        "კ.კ.": "კომანდიტური საზოგადოება",
    },
    "tax_registration": {
        "VAT": "სავალდებულო: ბრუნვა > 100,000₾/წელ; ნებაყოფლობითი: ნებისმიერ დროს",
        "PIT": "ყველა დამსაქმებელი ვალდებულია",
        "CIT": "ყველა კომპანია ვალდებულია (მოგების განაწილებისას)",
    },
    "deadlines": {
        "VAT_declaration": "კვარტლის მომდევნო თვის 15-მდე",
        "PIT_payment": "ყოველი თვის 15-მდე",
        "CIT_payment": "დივიდენდის გაცემიდან 15 დღეში",
        "annual_report": "წლის ბოლოდან 3 თვეში",
    }
}

# ══════════════════════════════════════════════════════════════
# 7. მთავარი ფუნქციები — Knowledge Base API
# ══════════════════════════════════════════════════════════════

def classify_transaction(description: str) -> dict:
    """ტრანზაქციის კლასიფიკაცია."""
    desc_lower = description.lower()
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
        return {
            "account": account_code,
            "name": account_info.get("name", "უცნობი"),
            "confidence": best_match["confidence"],
            "matched_keywords": best_score,
        }
    return {"account": "7810", "name": "სხვა ხარჯები", "confidence": 0.5, "matched_keywords": 0}


def calculate_vat(amount: float, inclusive: bool = True) -> dict:
    """VAT-ის გაანგარიშება."""
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
        "journal": f"Dr 1310 {net}₾ / Cr 6110 {net}₾, Cr 3310 {vat}₾"
    }


def calculate_payroll(gross: float) -> dict:
    """ხელფასის გაანგარიშება PIT + PAYG."""
    pit = round(gross * 0.20, 2)
    payg = round(gross * 0.02, 2)
    net = round(gross - pit, 2)
    return {
        "gross": gross,
        "pit": pit,
        "payg": payg,
        "net": net,
        "total_employer_cost": round(gross + payg, 2),
        "journal": f"Dr 7210 {gross}₾ / Cr 2110 {net}₾, Cr 3320 {pit}₾, Cr 3330 {payg}₾"
    }


def search_knowledge(query: str, top_k: int = 5) -> list:
    """ცოდნის ბაზაში ძიება."""
    query_lower = query.lower()
    results = []

    # საგადასახადო წესებში ძიება
    for tax_name, tax_data in TAX_RULES.items():
        for rule in tax_data.get("rules", []):
            if any(word in rule.lower() for word in query_lower.split()):
                results.append({
                    "category": "TAX",
                    "source": tax_name,
                    "text": rule,
                    "relevance": 0.9
                })

    # ანგარიშთა გეგმაში ძიება
    for code, account in CHART_OF_ACCOUNTS.items():
        if any(kw in query_lower for kw in account["keywords"]):
            results.append({
                "category": "COA",
                "source": f"ანგარიში {code}",
                "text": f"{code} — {account['name']}",
                "relevance": 0.85
            })

    # ACCA სტანდარტებში ძიება
    for std_name, std_data in ACCA_STANDARDS.items():
        for topic in std_data.get("topics", []):
            if any(word in topic.lower() for word in query_lower.split() if len(word) > 3):
                results.append({
                    "category": "ACCA",
                    "source": std_name,
                    "text": topic,
                    "relevance": 0.8
                })

    # Bridge Hub-ის ცოდნაში ძიება
    for endpoint, desc in BRIDGE_HUB_KNOWLEDGE["endpoints"].items():
        if endpoint in query_lower or any(w in desc.lower() for w in query_lower.split()):
            results.append({
                "category": "BRIDGE_HUB",
                "source": "endpoints",
                "text": f"{endpoint}: {desc}",
                "relevance": 0.75
            })

    # სორტირება relevance-ით და top_k-ის დაბრუნება
    results.sort(key=lambda x: x["relevance"], reverse=True)
    return results[:top_k]


def get_context_for_llm(query: str, max_chars: int = 3000) -> str:
    """LLM-ისთვის კონტექსტის მომზადება."""
    results = search_knowledge(query, top_k=10)
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
    return {
        "tax_rules": len(TAX_RULES),
        "accounts": len(CHART_OF_ACCOUNTS),
        "classification_rules": len(CLASSIFICATION_RULES),
        "acca_standards": len(ACCA_STANDARDS),
        "integrations": len(BRIDGE_HUB_KNOWLEDGE["integrations"]),
        "total_knowledge_items": (
            len(TAX_RULES) +
            len(CHART_OF_ACCOUNTS) +
            len(CLASSIFICATION_RULES) +
            sum(len(v.get("topics", [])) for v in ACCA_STANDARDS.values()) +
            sum(len(v.get("rules", [])) for v in TAX_RULES.values())
        )
    }


# ══════════════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🧪 Bridge Hub Knowledge Base — ტესტი\n")

    # VAT ტესტი
    vat = calculate_vat(5900, inclusive=True)
    print(f"✅ VAT (5900₾ ჩათვლილი): ნეტო={vat['net']}₾, VAT={vat['vat']}₾")
    print(f"   გატარება: {vat['journal']}\n")

    # Payroll ტესტი
    pay = calculate_payroll(3000)
    print(f"✅ Payroll (3000₾): PIT={pay['pit']}₾, PAYG={pay['payg']}₾, ნეტო={pay['net']}₾")
    print(f"   გატარება: {pay['journal']}\n")

    # კლასიფიკაციის ტესტი
    cls = classify_transaction("TBC საბანკო საკომისიო 45₾")
    print(f"✅ კლასიფიკაცია: {cls['account']} — {cls['name']} ({cls['confidence']*100:.0f}%)\n")

    # ძიების ტესტი
    results = search_knowledge("დღგ VAT 18%")
    print(f"✅ ძიება 'დღგ VAT 18%': {len(results)} შედეგი")
    for r in results[:3]:
        print(f"   [{r['category']}] {r['text'][:80]}")

    # სტატისტიკა
    stats = get_stats()
    print(f"\n📊 სტატისტიკა: {stats['total_knowledge_items']} ცოდნის ელემენტი")
