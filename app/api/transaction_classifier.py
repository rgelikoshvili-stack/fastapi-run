from difflib import SequenceMatcher

from app.api.db import get_db
from app.api.engines.pattern_engine import is_pattern_autopilot_eligible

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


def similarity(a: str, b: str) -> float:
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def adaptive_pattern_confidence(
    support_count: int,
    success_count: int,
    failure_count: int,
    fuzzy_ratio: float | None = None,
    status: str = "candidate",
) -> float:
    if status == "active":
        base = 0.93
    else:
        base = 0.78

    if support_count >= 5:
        base += 0.03
    elif support_count >= 3:
        base += 0.02
    elif support_count >= 2:
        base += 0.01

    total_feedback = success_count + failure_count
    if total_feedback > 0:
        success_rate = success_count / total_feedback
        if success_rate >= 0.90:
            base += 0.01
        elif success_rate < 0.40:
            base -= 0.06
        elif success_rate < 0.60:
            base -= 0.03

    if failure_count >= 3:
        base -= 0.06
    elif failure_count >= 1:
        base -= 0.03

    if fuzzy_ratio is not None:
        base = min(base, max(0.74, fuzzy_ratio))

    if is_pattern_autopilot_eligible(support_count, success_count, failure_count):
        base = max(base, 0.99)

    floor = 0.70 if status == "active" else 0.72
    ceiling = 0.99 if status == "active" else 0.84
    return round(max(floor, min(base, ceiling)), 2)


def get_exact_pattern_match(cur, pattern_type: str, value: str, statuses=("active", "candidate")):
    cur.execute(
        """
        SELECT
            account_code,
            reason,
            support_count,
            success_count,
            failure_count,
            status
        FROM learning_patterns
        WHERE pattern_type = %s
          AND pattern_value = %s
          AND status = ANY(%s)
        ORDER BY
            CASE WHEN status = 'active' THEN 0 ELSE 1 END,
            support_count DESC,
            success_count DESC,
            id DESC
        LIMIT 1
        """,
        (pattern_type, value, list(statuses)),
    )
    return cur.fetchone()


def get_fuzzy_pattern_match(cur, pattern_type: str, value: str, min_ratio: float = 0.82, statuses=("active", "candidate")):
    cur.execute(
        """
        SELECT
            pattern_value,
            account_code,
            reason,
            support_count,
            success_count,
            failure_count,
            status
        FROM learning_patterns
        WHERE pattern_type = %s
          AND status = ANY(%s)
        """,
        (pattern_type, list(statuses)),
    )
    rows = cur.fetchall()

    best = None
    best_ratio = 0.0

    for row in rows:
        pattern_value, account_code, reason, support_count, success_count, failure_count, status = row
        pv = (pattern_value or "").strip().lower()
        if not pv:
            continue

        ratio = similarity(value, pv)
        if value in pv or pv in value:
            ratio = max(ratio, 0.93)

        if ratio >= min_ratio and ratio > best_ratio:
            best_ratio = ratio
            best = (
                account_code,
                reason,
                int(support_count or 1),
                int(success_count or 0),
                int(failure_count or 0),
                status,
                ratio,
            )

    return best


def check_patterns(description: str = "", partner: str = ""):
    conn = get_db()
    cur = conn.cursor()

    try:
        desc = (description or "").strip().lower()
        part = (partner or "").strip()

        if desc:
            row = get_exact_pattern_match(cur, "description_exact", desc)
            if row:
                account_code, reason, support_count, success_count, failure_count, status = row
                confidence = adaptive_pattern_confidence(
                    int(support_count or 1),
                    int(success_count or 0),
                    int(failure_count or 0),
                    status=status,
                )
                return {
                    "account_code": account_code,
                    "reason": reason,
                    "confidence": confidence,
                    "support_count": int(support_count or 1),
                    "success_count": int(success_count or 0),
                    "failure_count": int(failure_count or 0),
                    "status": status,
                    "matched_on": "description_exact",
                    "source": "pattern_active" if status == "active" else "pattern_candidate",
                }

        if part:
            row = get_exact_pattern_match(cur, "partner", part)
            if row:
                account_code, reason, support_count, success_count, failure_count, status = row
                confidence = adaptive_pattern_confidence(
                    int(support_count or 1),
                    int(success_count or 0),
                    int(failure_count or 0),
                    status=status,
                )
                return {
                    "account_code": account_code,
                    "reason": reason,
                    "confidence": confidence,
                    "support_count": int(support_count or 1),
                    "success_count": int(success_count or 0),
                    "failure_count": int(failure_count or 0),
                    "status": status,
                    "matched_on": "partner_exact",
                    "source": "pattern_active" if status == "active" else "pattern_candidate",
                }

        if desc:
            row = get_fuzzy_pattern_match(cur, "description_exact", desc, min_ratio=0.82)
            if row:
                account_code, reason, support_count, success_count, failure_count, status, ratio = row
                confidence = adaptive_pattern_confidence(
                    support_count,
                    success_count,
                    failure_count,
                    fuzzy_ratio=ratio,
                    status=status,
                )
                return {
                    "account_code": account_code,
                    "reason": reason,
                    "confidence": confidence,
                    "support_count": support_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "status": status,
                    "matched_on": "description_fuzzy",
                    "source": "pattern_active_fuzzy" if status == "active" else "pattern_candidate_fuzzy",
                    "pattern_similarity": round(ratio, 2),
                }

        if part:
            row = get_fuzzy_pattern_match(cur, "partner", part, min_ratio=0.84)
            if row:
                account_code, reason, support_count, success_count, failure_count, status, ratio = row
                confidence = adaptive_pattern_confidence(
                    support_count,
                    success_count,
                    failure_count,
                    fuzzy_ratio=ratio,
                    status=status,
                )
                return {
                    "account_code": account_code,
                    "reason": reason,
                    "confidence": confidence,
                    "support_count": support_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "status": status,
                    "matched_on": "partner_fuzzy",
                    "source": "pattern_active_fuzzy" if status == "active" else "pattern_candidate_fuzzy",
                    "pattern_similarity": round(ratio, 2),
                }

        return None

    finally:
        cur.close()
        conn.close()


def classify(
    description: str,
    paid_in=None,
    paid_out=None,
    partner: str = "",
    operation_code: str = "",
):
    desc = (description or "").strip().lower()
    part = (partner or "").strip()
    op = (operation_code or "").strip().lower()
    combined = f"{desc} {part.lower()}".strip()

    learned = check_patterns(desc, part)
    if learned:
        is_candidate = learned["status"] == "candidate"
        is_active = learned["status"] == "active"

        review_required = True
        status = "pending_approval"

        if is_active and learned["confidence"] >= 0.90:
            review_required = False
            status = "auto_approved"
        elif is_candidate:
            review_required = True
            status = "pending_approval"

        return {
            "account_code": learned["account_code"],
            "reason": learned["reason"],
            "confidence": learned["confidence"],
            "review_required": review_required,
            "status": status,
            "source": learned["source"],
            "pattern_support_count": learned["support_count"],
            "pattern_success_count": learned["success_count"],
            "pattern_failure_count": learned["failure_count"],
            "pattern_matched_on": learned["matched_on"],
            "pattern_similarity": learned.get("pattern_similarity"),
        }

    matched_account = "7190"
    matched_reason = "default_expense"
    confidence = 0.0
    keyword_matched = False

    for keywords, account, reason in RULES:
        if any(kw.lower() in combined for kw in keywords):
            matched_account = account
            matched_reason = reason
            confidence = 0.8
            keyword_matched = True
            break

    if keyword_matched and part:
        confidence = min(confidence + 0.05, 0.95)

    if keyword_matched and op:
        if matched_reason in op or matched_account in op:
            confidence = min(confidence + 0.05, 1.0)

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
    review_required = confidence < 0.75

    return {
        "account_code": matched_account,
        "reason": matched_reason,
        "confidence": confidence,
        "review_required": review_required,
        "status": "drafted" if not review_required else "pending_approval",
        "source": "rules",
        "pattern_support_count": None,
        "pattern_success_count": None,
        "pattern_failure_count": None,
        "pattern_matched_on": None,
        "pattern_similarity": None,
    }