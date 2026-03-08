RULES = [
    # შემოსავალი
    (["payment","client","customer","invoice","revenue","sale","income","received"], "6100", "income"),
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
    (["tax","vat","rs.ge","revenue service","გადასახადი","დღგ"], "3100", "tax"),
    # სატრანსპორტო
    (["fuel","petrol","gas station","taxi","transport","საწვავი"], "7160", "transport"),
    # მარკეტინგი
    (["marketing","advertising","ads","facebook","google ads"], "7170", "marketing"),
    # საოფისე
    (["stationery","supplies","კანცელარია"], "7180", "office"),
    # კურიერი
    (["courier","delivery","shipping","მიტანა"], "7185", "delivery"),
]

def classify(description: str, paid_in=None, paid_out=None, partner: str = ""):
    desc = (description or "").lower()
    part = (partner or "").lower()
    combined = desc + " " + part

    matched_account = "7190"
    matched_reason = "default expense"
    confidence = 0.4
    matches = 0

    for keywords, account, reason in RULES:
        for kw in keywords:
            if kw.lower() in combined:
                matched_account = account
                matched_reason = reason
                matches += 1
                break

    if matches == 0 and paid_in and not paid_out:
        matched_account = "6100"
        matched_reason = "income (direction)"
        confidence = 0.5
    elif matches == 1:
        confidence = 0.75
    elif matches >= 2:
        confidence = 0.9

    review_required = confidence < 0.6

    return {
        "account_code": matched_account,
        "reason": matched_reason,
        "confidence": round(confidence, 2),
        "review_required": review_required,
    }
