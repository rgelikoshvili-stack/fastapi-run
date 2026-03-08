RULES = [
    # === ქართული საბანკო ტერმინები (TBC/BOG/Credo) ===
    # შემოსავალი
    (["ანაზღაურება","თანხის მიღება","გადახდა მიღებული","შემოსული"], "6100", "income"),
    # ხელფასი
    (["სახელფასო","თანამშრომელი","hr გადარიცხვა"], "7120", "salary"),
    # ქირა
    (["ქირის გადახდა","იჯარა","სასტუმრო"], "7110", "rent"),
    # კომუნალური
    (["ელექტროენერგია","წყალი","გაზი","ინტერნეტი","მობილური","მაგთიკომი","სილქნეტი","ვეოლია","gwp","telasi"], "7130", "utility"),
    # ბანკის საკომისიო
    (["მომსახურების საფასური","ბარათის მომსახურება","sms შეტყობინება","ყოველთვიური საკომისიო"], "7150", "bank_fee"),
    # გადასახადი
    (["საშემოსავლო","მოგების გადასახადი","სოციალური","pension","საპენსიო","rs.ge","revenue.mof.ge"], "3100", "tax"),
    # ტრანსფერი
    (["საკუთარ ანგარიშზე","სხვა ანგარიშზე გადარიცხვა","შიდა გადარიცხვა"], "1210", "transfer"),
    # სასურსათო
    (["სუპერმარკეტი","პროდუქტების მაღაზია","agrohub","goodwill","ori nabiji","smart","europroduct"], "7191", "grocery"),
    # საოჯახო
    (["საყოფაცხოვრებო","სახლის ხარჯი","remонтი","სარემონტო"], "7192", "household"),
    # მარკეტინგი
    (["რეკლამა","სარეკლამო","პრომოცია"], "7170", "marketing"),
    # კურიერი
    (["მიწოდება","კურიერი","glopal","express post"], "7185", "delivery"),
    # შემოსავალი
    (["payment","client","customer","revenue","sale","income","received"], "6100", "income"),
    # ხელფასი
    (["salary","payroll","wage","ხელფასი","compensation"], "7120", "salary"),
    # ქირა
    (["rent","ქირა","lease","rental"], "7110", "rent"),
    # კომუნალური
    (["electricity","power","water","gas","internet","mobile","utility","komunaluri"], "7130", "utility"),
    # პროგრამული
    (["software","subscription","hosting","google","microsoft","adobe","openai","saas"], "7140", "software"),
    # ბანკის საკომისიო
    (["bank fee","commission","service fee","account maintenance","საკომისიო"], "7150", "bank_fee"),
    # ტრანსფერი
    (["transfer","own account","internal","გადარიცხვა"], "1210", "transfer"),
    # გადასახადები
    (["tax","vat","rs.ge","revenue service","გადასახადი","დღგ","sagareo"], "3100", "tax"),
    # სატრანსპორტო
    (["fuel","petrol","gas station","taxi","transport","საწვავი"], "7160", "transport"),
    # მარკეტინგი
    (["marketing","advertising","ads","facebook","google ads"], "7170", "marketing"),
    # საოფისე
    (["stationery","supplies","კანცელარია"], "7180", "office"),
    # კურიერი
    (["courier","delivery","shipping","მიტანა"], "7185", "delivery"),
    # სასურსათო
    (["grocery","supermarket","სასურსათო","2nabiji","carrefour","nikora","goodwill"], "7191", "grocery"),
    # საოჯახო ხარჯი
    (["საოჯახო","household","home expense"], "7192", "household"),
    # კონვერტაცია
    (["კონვერტაცია","conversion","exchange"], "1210", "conversion"),
    # Cost of goods/services
    (["cost of goods","cost of service","cogs"], "7100", "cost_of_goods"),
    # POS ტრანზაქცია
    (["pos -","pos transaction"], "7190", "pos_expense"),
]

INCOME_ACCOUNTS = {"6100"}
EXPENSE_ACCOUNTS = {"7100","7110","7120","7130","7140","7150","7160","7170","7180","7185","7190","7191","7192"}

def classify(description: str, paid_in=None, paid_out=None, partner: str = "", operation_code: str = ""):
    desc = (description or "").lower()
    part = (partner or "").lower()
    op   = (operation_code or "").lower()
    combined = desc + " " + part

    matched_account = "7190"
    matched_reason  = "default expense"
    confidence      = 0.0
    keyword_matched = False

    # 1. keyword match +0.3
    for keywords, account, reason in RULES:
        for kw in keywords:
            if kw.lower() in combined:
                matched_account = account
                matched_reason  = reason
                confidence     += 0.4
                keyword_matched = True
                break
        if keyword_matched:
            break

    # 2. partner hint +0.2
    if part and keyword_matched:
        confidence += 0.2

    # 3. operation code match +0.2
    if op and any(kw in op for kw in [matched_reason, matched_account]):
        confidence += 0.2

    # 4. direction consistency +0.2
    if paid_in is not None and paid_out is None:
        if matched_account in INCOME_ACCOUNTS:
            confidence += 0.2
        elif not keyword_matched:
            matched_account = "6100"
            matched_reason  = "income (direction)"
            confidence      = 0.5
    elif paid_out is not None and paid_in is None:
        if matched_account in EXPENSE_ACCOUNTS or matched_account in {"1210","3100"}:
            confidence += 0.2

    # fallback
    if not keyword_matched and not (paid_in and not paid_out):
        confidence = 0.4

    confidence = round(min(confidence, 1.0), 2)
    review_required = confidence < 0.6

    return {
        "account_code": matched_account,
        "reason": matched_reason,
        "confidence": confidence,
        "review_required": review_required,
    }
