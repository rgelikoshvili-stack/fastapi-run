from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.api.db import get_db
from app.api.engines.pattern_engine import is_pattern_autopilot_eligible
from app.api.services.expense_article_service import find_expense_article
from app.api.services.transaction_memory_service import find_memory_match
from app.api.services.erp_memory_service import find_erp_memory_match


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


def days_since(last_seen_at) -> int | None:
    if not last_seen_at:
        return None

    if isinstance(last_seen_at, str):
        try:
            last_seen_at = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
        except Exception:
            return None

    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    return max(0, (now - last_seen_at).days)


def is_recent_enough_for_autopilot(last_seen_at, max_days: int = 45) -> bool:
    days = days_since(last_seen_at)
    if days is None:
        return False
    return days <= max_days


def recency_penalty_days(last_seen_at) -> float:
    days = days_since(last_seen_at)

    if days is None:
        return 0.08
    if days <= 7:
        return 0.00
    if days <= 30:
        return 0.03
    if days <= 60:
        return 0.08
    if days <= 90:
        return 0.15
    if days <= 120:
        return 0.22
    return 0.35


def adaptive_pattern_confidence(
    support_count: int,
    success_count: int,
    failure_count: int,
    fuzzy_ratio: float | None = None,
    status: str = "candidate",
    last_seen_at=None,
) -> float:
    status = (status or "candidate").strip().lower()

    if status == "active":
        base = 0.93
    elif status == "candidate":
        base = 0.78
    else:
        base = 0.58

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

    autopilot_eligible = (
        status == "active"
        and is_pattern_autopilot_eligible(
            support_count,
            success_count,
            failure_count,
            last_seen_at=last_seen_at,
        )
        and is_recent_enough_for_autopilot(last_seen_at, max_days=45)
    )

    if autopilot_eligible:
        base = max(base, 0.99)

    penalty = recency_penalty_days(last_seen_at)
    base -= penalty

    if status == "active":
        floor = 0.68
        ceiling = 0.99
    elif status == "candidate":
        floor = 0.55
        ceiling = 0.84
    else:
        floor = 0.30
        ceiling = 0.60

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
            status,
            last_seen_at
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
            status,
            last_seen_at
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
        pattern_value, account_code, reason, support_count, success_count, failure_count, status, last_seen_at = row
        pv = (pattern_value or "").strip().lower()
        if not pv:
            continue

        ratio = similarity(value, pv)
        if value in pv or pv in value:
            ratio = max(ratio, 0.93)

        if ratio >= min_ratio and ratio > best_ratio:
            best_ratio = ratio
            best = (
                pattern_value,
                account_code,
                reason,
                int(support_count or 1),
                int(success_count or 0),
                int(failure_count or 0),
                status,
                last_seen_at,
                ratio,
            )

    return best


def check_patterns(description: str = "", partner: str = ""):
    conn = get_db()
    cur = conn.cursor()

    try:
        desc = (description or "").strip().lower()
        part = (partner or "").strip().lower()

        if desc:
            row = get_exact_pattern_match(cur, "description_exact", desc)
            if row:
                account_code, reason, support_count, success_count, failure_count, status, last_seen_at = row
                confidence = adaptive_pattern_confidence(
                    int(support_count or 1),
                    int(success_count or 0),
                    int(failure_count or 0),
                    status=status,
                    last_seen_at=last_seen_at,
                )
                pattern_days = days_since(last_seen_at)
                pattern_penalty = recency_penalty_days(last_seen_at)
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
                    "pattern_value_used": desc,
                    "pattern_days_since_seen": pattern_days,
                    "pattern_recency_penalty": pattern_penalty,
                }

        if part:
            row = get_exact_pattern_match(cur, "partner", part)
            if row:
                account_code, reason, support_count, success_count, failure_count, status, last_seen_at = row
                confidence = adaptive_pattern_confidence(
                    int(support_count or 1),
                    int(success_count or 0),
                    int(failure_count or 0),
                    status=status,
                    last_seen_at=last_seen_at,
                )
                pattern_days = days_since(last_seen_at)
                pattern_penalty = recency_penalty_days(last_seen_at)
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
                    "pattern_value_used": part,
                    "pattern_days_since_seen": pattern_days,
                    "pattern_recency_penalty": pattern_penalty,
                }

        if desc:
            row = get_fuzzy_pattern_match(cur, "description_exact", desc, min_ratio=0.82)
            if row:
                matched_pattern_value, account_code, reason, support_count, success_count, failure_count, status, last_seen_at, ratio = row
                confidence = adaptive_pattern_confidence(
                    support_count,
                    success_count,
                    failure_count,
                    fuzzy_ratio=ratio,
                    status=status,
                    last_seen_at=last_seen_at,
                )
                pattern_days = days_since(last_seen_at)
                pattern_penalty = recency_penalty_days(last_seen_at)
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
                    "pattern_value_used": matched_pattern_value,
                    "pattern_days_since_seen": pattern_days,
                    "pattern_recency_penalty": pattern_penalty,
                }

        if part:
            row = get_fuzzy_pattern_match(cur, "partner", part, min_ratio=0.84)
            if row:
                matched_pattern_value, account_code, reason, support_count, success_count, failure_count, status, last_seen_at, ratio = row
                confidence = adaptive_pattern_confidence(
                    support_count,
                    success_count,
                    failure_count,
                    fuzzy_ratio=ratio,
                    status=status,
                    last_seen_at=last_seen_at,
                )
                pattern_days = days_since(last_seen_at)
                pattern_penalty = recency_penalty_days(last_seen_at)
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
                    "pattern_value_used": matched_pattern_value,
                    "pattern_days_since_seen": pattern_days,
                    "pattern_recency_penalty": pattern_penalty,
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
    doc_type: str = "",
):
    desc = (description or "").strip().lower()
    part = (partner or "").strip().lower()
    op = (operation_code or "").strip().lower()
    doc = (doc_type or "").strip().lower()
    combined = f"{desc} {part}".strip()

    # 1. EXPENSE ARTICLES (highest priority)
    article = find_expense_article(desc, part)
    if article:
        return {
            "account_code": article["linked_account_code"],
            "reason": "expense_article",
            "confidence": 0.95,
            "review_required": False,
            "status": "auto_approved",
            "source": "expense_article",
            "pattern_support_count": None,
            "pattern_success_count": None,
            "pattern_failure_count": None,
            "pattern_matched_on": "expense_article",
            "pattern_similarity": None,
            "pattern_value_used": article.get("article_name"),
            "pattern_days_since_seen": None,
            "pattern_recency_penalty": None,
            "autopilot_eligible": True,
            "autopilot_reason": "expense_article_rule",
        }

    # 2. TRANSACTION MEMORY
    memory = find_memory_match(desc, part)
    if memory:
        return {
            "account_code": memory["account_code"],
            "reason": memory["reason"],
            "confidence": memory["confidence"],
            "review_required": memory["review_required"],
            "status": memory["status"],
            "source": memory["source"],
            "pattern_support_count": None,
            "pattern_success_count": None,
            "pattern_failure_count": None,
            "pattern_matched_on": "transaction_memory",
            "pattern_similarity": None,
            "pattern_value_used": None,
            "pattern_days_since_seen": None,
            "pattern_recency_penalty": None,
            "autopilot_eligible": memory["confidence"] >= 0.90 and memory.get("memory_usage_count", 0) >= 3,
            "autopilot_reason": "memory_match" if memory["confidence"] >= 0.90 else "memory_needs_review",
        }

    # 3. ERP HISTORY
    erp_match = find_erp_memory_match(
        description=description,
        partner=partner,
        amount=paid_out if paid_out is not None else paid_in,
        doc_type=doc_type,
    )
    if erp_match:
        confidence = min(float(erp_match.get("confidence") or 0.90), 0.94)

        return {
            "account_code": erp_match.get("account_code"),
            "reason": "erp_history_match",
            "confidence": confidence,
            "review_required": False if confidence >= 0.93 else True,
            "status": "auto_approved" if confidence >= 0.93 else "pending_approval",
            "source": "erp_history",
            "pattern_support_count": erp_match.get("evidence_count"),
            "pattern_success_count": None,
            "pattern_failure_count": None,
            "pattern_matched_on": "erp_posting_memory",
            "pattern_similarity": None,
            "pattern_value_used": erp_match.get("description"),
            "pattern_days_since_seen": None,
            "pattern_recency_penalty": None,
            "autopilot_eligible": True if confidence >= 0.93 else False,
            "autopilot_reason": "erp_history_rule" if confidence >= 0.93 else "erp_history_needs_review",
        }

    # 4. LEARNING PATTERNS
    learned = check_patterns(desc, part)
    if learned:
        review_required = True
        status = "pending_approval"

        if learned["status"] == "active" and learned["confidence"] >= 0.90:
            review_required = False
            status = "auto_approved"
        elif learned["status"] == "candidate":
            review_required = True
            status = "pending_approval"

        autopilot_reason = "not_eligible"

        if learned["status"] != "active":
            autopilot_reason = "status_not_active"
        elif (learned.get("pattern_days_since_seen") if learned.get("pattern_days_since_seen") is not None else 999999) > 45:
            autopilot_reason = "pattern_stale"
        elif learned["failure_count"] > 0:
            autopilot_reason = "has_failures"
        elif learned["support_count"] < 5:
            autopilot_reason = "support_below_threshold"
        elif learned["success_count"] < 3:
            autopilot_reason = "success_below_threshold"
        elif learned["confidence"] < 0.90:
            autopilot_reason = "confidence_below_autopilot_threshold"
        else:
            autopilot_reason = "eligible_for_autopilot"

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
            "pattern_value_used": learned.get("pattern_value_used"),
            "pattern_days_since_seen": learned.get("pattern_days_since_seen"),
            "pattern_recency_penalty": learned.get("pattern_recency_penalty"),
            "autopilot_eligible": status == "auto_approved",
            "autopilot_reason": autopilot_reason,
        }

    # 5. FALLBACK RULES
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

    if keyword_matched and doc:
        if matched_reason in doc or matched_account in doc:
            confidence = min(confidence + 0.05, 0.95)

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
        "pattern_value_used": None,
        "pattern_days_since_seen": None,
        "pattern_recency_penalty": None,
        "autopilot_eligible": False,
        "autopilot_reason": "rules_path",
    }