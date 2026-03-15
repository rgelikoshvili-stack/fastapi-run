RULES = [
    (["ანაზღაურება", "თანხის მიღება", "გადახდა მიღებული", "შემოსული"], "6100", "income"),
    (["ხელფასი", "თანამშრომელი", "hr გადარიცხვა"], "7120", "salary"),
    (["ქირის გადახდა", "იჯარა", "სასტუმრო"], "7110", "rent"),
    (["ელექტროენერგია", "წყალი", "გაზი", "ინტერნეტი", "მობილური", "მაგთიკომი", "სილქნეტი", "ველი", "gwp", "telasi"], "7130", "utility"),
    (["მომსახურების საფასური", "ბარათის მომსახურება", "sms შეტყობინება", "ყოველთვიური საკომისიო"], "7150", "bank_fee"),
    (["საშემოსავლო", "მოგების გადასახადი", "სოციალური", "pension", "საპენსიო", "rs.ge", "revenue.mof.ge"], "3100", "tax"),
    (["საკუთარ ანგარიშზე", "სხვა ანგარიშზე გადარიცხვა", "შიდა გადარიცხვა"], "1210", "transfer"),
    (["სუპერმარკეტი", "პროდუქტების მაღაზია", "agrohub", "goodwill", "ori nabiji", "smart", "europroduct"], "7191", "grocery"),
    (["საყოფაცხოვრებო", "სახლის ხარჯი", "რემონტი", "სარემონტო"], "7192", "household"),
    (["რეკლამა", "სარეკლამო", "პრომაცია"], "7170", "marketing"),
    (["მიწოდება", "კურიერი", "glopal", "express post"], "7185", "delivery"),

    (["payment", "client", "customer", "revenue", "sale", "income", "received"], "6100", "income"),
    (["salary", "payroll", "wage", "ხელფასი", "compensation"], "7120", "salary"),
    (["rent", "ქირა", "lease", "rental"], "7110", "rent"),
    (["electricity", "power", "water", "gas", "internet", "mobile", "utility", "komunaluri"], "7130", "utility"),
    (["software", "subscription", "hosting", "google", "microsoft", "adobe", "openai", "saas"], "7140", "software"),
    (["bank fee", "commission", "service fee", "account maintenance", "საკომისიო"], "7150", "bank_fee"),
    (["transfer", "own account", "internal", "გადარიცხვა"], "1210", "transfer"),
    (["tax", "vat", "rs.ge", "revenue service", "გადასახადი", "დღგ", "sagareo"], "3100", "tax"),
    (["fuel", "petrol", "gas station", "taxi", "transport", "საწვავი"], "7160", "transport"),
    (["marketing", "advertising", "ads", "facebook", "google ads"], "7170", "marketing"),
    (["stationery", "supplies", "კანცელარია"], "7180", "office"),
    (["courier", "delivery", "shipping", "მიტანა"], "7185", "delivery"),
    (["grocery", "supermarket", "სასურსათო", "2nabiji", "carrefour", "nikora", "goodwill"], "7191", "grocery"),
    (["საოჯახო", "household", "home expense"], "7192", "household"),
    (["კონვერტაცია", "conversion", "exchange"], "1210", "conversion"),
    (["cost of goods", "cost of service", "cogs"], "7100", "cost_of_goods"),
    (["pos -", "pos transaction"], "7190", "pos_expense"),
]

INCOME_ACCOUNTS = {"6100"}
EXPENSE_ACCOUNTS = {
    "7100", "7110", "7120", "7130", "7140", "7150",
    "7160", "7170", "7180", "7185", "7190", "7191", "7192"
}


def classify(description: str, paid_in=None, paid_out=None, partner: str = "", operation_code: str = ""):
    desc = (description or "").strip().lower()
    part = (partner or "").strip().lower()
    op = (operation_code or "").strip().lower()
    combined = f"{desc} {part}".strip()

    matched_account = "7190"
    matched_reason = "default_expense"
    confidence = 0.0
    keyword_matched = False

    # 1. Keyword-based classification
    for keywords, account, reason in RULES:
        if any(kw.lower() in combined for kw in keywords):
            matched_account = account
            matched_reason = reason
            confidence = 0.8
            keyword_matched = True
            break

    # 2. Optional boosts
    if keyword_matched and part:
        confidence = min(confidence + 0.05, 0.95)

    if keyword_matched and op:
        if matched_reason in op or matched_account in op:
            confidence = min(confidence + 0.05, 1.0)

    # 3. Direction-based fallback
    if not keyword_matched:
        if paid_in is not None and paid_out is None:
            matched_account = "6100"
            matched_reason = "income_direction"
            confidence = 0.65
        elif paid_out is not None and paid_in is None:
            matched_account = "7190"
            matched_reason = "expense_direction"
            confidence = 0.55
        else:
            matched_account = "7190"
            matched_reason = "default_expense"
            confidence = 0.4

    confidence = round(min(confidence, 1.0), 2)

    # 4. Review rule
    review_required = confidence < 0.75

    return {
        "account_code": matched_account,
        "reason": matched_reason,
        "confidence": confidence,
        "review_required": review_required,
    }