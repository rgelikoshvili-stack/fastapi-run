from datetime import datetime, timezone
from difflib import SequenceMatcher
import math

from app.api.db import get_db
from app.api.engines.pattern_engine import (
    is_pattern_autopilot_eligible,
    mark_pattern_success,
    update_pattern_usage,
)
from app.api.services.expense_article_service import find_expense_article
from app.api.services.transaction_memory_service import find_memory_match
from app.api.services.erp_memory_service import find_erp_memory_match
from app.policy.localization import georgia_pack
import app.api.services.llm_service as llm_service


RULES = [
    # შემოსავლები — 6110=გ-ვ.შემ., 6120=მომ.შემ.
    (["ანაზღაურება", "თანხის მიღება", "გადახდა მიღებული", "შემოსული"], "6110", "income"),
    (["payment", "client", "customer", "revenue", "sale", "income", "received"], "6110", "income"),
    # ხელფასი — 7210=ხ.ხ., 3320=PIT, 3330=PAYG
    (["ხელფასი", "თანამშრომელი", "hr გადარიცხვა"], "7210", "salary"),
    (["salary", "payroll", "wage", "compensation"], "7210", "salary"),
    # ქირა — 7310=ქ.ხ. (7110=COGS — rent is NOT 7110)
    (["ქირის გადახდა", "იჯარა", "სასტუმრო"], "7310", "rent"),
    (["rent", "ქირა", "lease", "rental"], "7310", "rent"),
    # კომუნალური — 7410=კ.ხ.
    (["ელექტროენერგია", "წყალი", "გაზი", "მაგთიკომი", "სილქნეტი", "ველი", "gwp", "telasi"], "7410", "utility"),
    (["electricity", "power", "water", "gas", "utility", "komunaluri"], "7410", "utility"),
    # ინტერნეტი/მობილური — 7810=სხ.ა.ხ.
    (["ინტერნეტი", "მობილური", "internet", "mobile"], "7810", "software"),
    # პროგრამული — 7810=სხ.ა.ხ.
    (["software", "subscription", "hosting", "google", "microsoft", "adobe", "openai", "saas"], "7810", "software"),
    (["stationery", "supplies", "კანცელარია"], "7810", "office"),
    # საბანკო საკომისიო — 7510=სბ.სკ.
    (["მომსახურების საფასური", "ბარათის მომსახურება", "sms შეტყობინება", "ყოველთვიური საკომისიო"], "7510", "bank_fee"),
    (["bank fee", "commission", "service fee", "account maintenance", "საკომისიო"], "7510", "bank_fee"),
    # გადასახადები — სწორი ანგარიშები: 3320=PIT, 3330=PAYG, 3310=VAT, 3340=CIT
    (["საშემოსავლო გადასახადი", "pit", "income tax"], "3320", "pit"),
    (["საპენსიო", "pension", "payg"], "3330", "payg"),
    (["დღგ", "vat"], "3310", "vat_payable"),
    (["მოგების გადასახადი", "cit", "corporate tax"], "3340", "cit"),
    (["rs.ge", "revenue.mof.ge", "revenue service", "sagareo"], "3320", "tax"),
    # შიდა გადარიცხვა — 1120=საბანკო ანგ.
    (["საკუთარ ანგარიშზე", "სხვა ანგარიშზე გადარიცხვა", "შიდა გადარიცხვა"], "1120", "transfer"),
    (["transfer", "own account", "internal", "გადარიცხვა"], "1120", "transfer"),
    # სატრანსპორტო — 7730=სატ.ხ.
    (["fuel", "petrol", "gas station", "taxi", "transport", "საწვავი"], "7730", "transport"),
    (["courier", "delivery", "shipping", "მიტანა", "მიწოდება", "კურიერი", "glopal", "express post"], "7730", "transport"),
    # მარკეტინგი — 7710=რ.ხ.
    (["რეკლამა", "სარეკლამო", "პრომაცია"], "7710", "marketing"),
    (["marketing", "advertising", "ads", "facebook", "google ads"], "7710", "marketing"),
    # სხვა ხარჯი — 7910=სხვ.ხ.
    (["სუპერმარკეტი", "პროდუქტების მაღაზია", "agrohub", "goodwill", "ori nabiji", "smart", "europroduct"], "7910", "other"),
    (["grocery", "supermarket", "სასურსათო", "2nabiji", "carrefour", "nikora"], "7910", "other"),
    (["საყოფაცხოვრებო", "სახლის ხარჯი", "რემონტი", "სარემონტო"], "7910", "other"),
    (["საოჯახო", "household", "home expense"], "7910", "other"),
    # COGS — 7110=COGS
    (["cost of goods", "cost of service", "cogs"], "7110", "cost_of_goods"),
    # კონვერტაცია — 7920=გ.კ.ზ.
    (["კონვერტაცია", "conversion", "exchange"], "7920", "conversion"),
    # POS / სხვა — 7910=სხვ.ხ.
    (["pos -", "pos transaction"], "7910", "pos_expense"),
]


def similarity(a: str, b: str) -> float:
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def to_float(value):
    try:
        return float(value) if value is not None else None
    except Exception:
        return None


def safe_int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return default


def normalize_text(value: str) -> str:
    return (value or "").strip().lower()


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
    status = normalize_text(status) or "candidate"

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
            support_count, success_count, failure_count,
            last_seen_at=last_seen_at,
        )
        and is_recent_enough_for_autopilot(last_seen_at, max_days=45)
    )

    if autopilot_eligible:
        base = max(base, 0.99)

    penalty = recency_penalty_days(last_seen_at)
    base -= penalty

    if status == "active":
        floor, ceiling = 0.68, 0.99
    elif status == "candidate":
        floor, ceiling = 0.55, 0.84
    else:
        floor, ceiling = 0.30, 0.60

    return round(max(floor, min(base, ceiling)), 2)


def check_anomaly(
    amount: float | None,
    account_code: str | None,
    tenant_id: str = "default",
) -> dict:
    if not amount or not account_code:
        return {"anomaly_flag": False, "anomaly_reason": None}

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                AVG(amount) AS avg_amount,
                STDDEV(amount) AS std_amount,
                COUNT(*) AS tx_count
            FROM journal_drafts
            WHERE account_code = %s
              AND tenant_id = %s
              AND amount IS NOT NULL
              AND amount > 0
              AND created_at > NOW() - INTERVAL '90 days'
            """,
            (account_code, tenant_id),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row or not row[0] or int(row[2] or 0) < 5:
        return {"anomaly_flag": False, "anomaly_reason": "insufficient_history"}

    avg = float(row[0])
    std = float(row[1] or 0)

    if std == 0:
        return {"anomaly_flag": False, "anomaly_reason": None}

    z_score = abs(amount - avg) / std

    if z_score > 3.0:
        return {
            "anomaly_flag": True,
            "anomaly_reason": f"amount {amount} differs from baseline avg={round(avg, 2)} std={round(std, 2)} z={round(z_score, 2)}",
        }

    return {"anomaly_flag": False, "anomaly_reason": None}


def check_partner_memory(conn, partner: str, tenant_id: str = "default"):
    if not partner:
        return None
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT account_code, confidence
            FROM transaction_memory
            WHERE LOWER(partner) = LOWER(%s)
              AND tenant_id = %s
            ORDER BY confidence DESC
            LIMIT 1
            """,
            (partner, tenant_id),
        )
        row = cur.fetchone()
    finally:
        cur.close()
    if row:
        return {"account_code": row[0], "confidence": row[1], "source": "partner_memory"}
    return None


def get_exact_pattern_match(
    cur,
    pattern_type: str,
    value: str,
    tenant_id: str = "default",
    statuses=("active", "candidate"),
):
    cur.execute(
        """
        SELECT account_code, reason, support_count, success_count,
               failure_count, status, last_seen_at
        FROM learning_patterns
        WHERE pattern_type = %s
          AND pattern_value = %s
          AND tenant_id = %s
          AND status = ANY(%s)
        ORDER BY
            CASE WHEN status = 'active' THEN 0 ELSE 1 END,
            support_count DESC, success_count DESC, id DESC
        LIMIT 1
        """,
        (pattern_type, value, tenant_id, list(statuses)),
    )
    return cur.fetchone()


def get_fuzzy_pattern_match(
    cur,
    pattern_type: str,
    value: str,
    tenant_id: str = "default",
    min_ratio: float = 0.82,
    statuses=("active", "candidate"),
):
    cur.execute(
        """
        SELECT pattern_value, account_code, reason, support_count,
               success_count, failure_count, status, last_seen_at
        FROM learning_patterns
        WHERE pattern_type = %s
          AND tenant_id = %s
          AND status = ANY(%s)
        """,
        (pattern_type, tenant_id, list(statuses)),
    )
    rows = cur.fetchall()

    best = None
    best_ratio = 0.0

    for row in rows:
        pattern_value, account_code, reason, support_count, success_count, failure_count, status, last_seen_at = row
        pv = normalize_text(pattern_value)
        if not pv:
            continue
        ratio = similarity(value, pv)
        if value in pv or pv in value:
            ratio = max(ratio, 0.93)
        if ratio >= min_ratio and ratio > best_ratio:
            best_ratio = ratio
            best = (
                pattern_value, account_code, reason,
                safe_int(support_count, 1), safe_int(success_count, 0),
                safe_int(failure_count, 0), status, last_seen_at, ratio,
            )

    return best


def check_patterns(
    description: str = "",
    partner: str = "",
    tenant_id: str = "default",
):
    conn = get_db()
    cur = conn.cursor()

    try:
        desc = normalize_text(description)
        part = normalize_text(partner)

        if desc:
            row = get_exact_pattern_match(cur, "description_exact", desc, tenant_id)
            if row:
                account_code, reason, support_count, success_count, failure_count, status, last_seen_at = row
                support_count = safe_int(support_count, 1)
                success_count = safe_int(success_count, 0)
                failure_count = safe_int(failure_count, 0)
                update_pattern_usage("description_exact", desc, account_code, tenant_id=tenant_id)
                confidence = adaptive_pattern_confidence(
                    support_count, success_count, failure_count,
                    status=status, last_seen_at=last_seen_at,
                )
                return {
                    "account_code": account_code,
                    "reason": reason,
                    "confidence": float(confidence or 0.0),
                    "support_count": support_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "status": status,
                    "matched_on": "description_exact",
                    "source": "pattern_active" if status == "active" else "pattern_candidate",
                    "pattern_value_used": desc,
                    "pattern_days_since_seen": days_since(last_seen_at),
                    "pattern_recency_penalty": recency_penalty_days(last_seen_at),
                }

        if part:
            row = get_exact_pattern_match(cur, "partner", part, tenant_id)
            if row:
                account_code, reason, support_count, success_count, failure_count, status, last_seen_at = row
                support_count = safe_int(support_count, 1)
                success_count = safe_int(success_count, 0)
                failure_count = safe_int(failure_count, 0)
                update_pattern_usage("partner", part, account_code, tenant_id=tenant_id)
                confidence = adaptive_pattern_confidence(
                    support_count, success_count, failure_count,
                    status=status, last_seen_at=last_seen_at,
                )
                return {
                    "account_code": account_code,
                    "reason": reason,
                    "confidence": float(confidence or 0.0),
                    "support_count": support_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "status": status,
                    "matched_on": "partner_exact",
                    "source": "pattern_active" if status == "active" else "pattern_candidate",
                    "pattern_value_used": part,
                    "pattern_days_since_seen": days_since(last_seen_at),
                    "pattern_recency_penalty": recency_penalty_days(last_seen_at),
                }

        if desc:
            row = get_fuzzy_pattern_match(cur, "description_exact", desc, tenant_id, min_ratio=0.82)
            if row:
                matched_pattern_value, account_code, reason, support_count, success_count, failure_count, status, last_seen_at, ratio = row
                update_pattern_usage("description_exact", matched_pattern_value, account_code, tenant_id=tenant_id)
                confidence = adaptive_pattern_confidence(
                    support_count, success_count, failure_count,
                    fuzzy_ratio=ratio, status=status, last_seen_at=last_seen_at,
                )
                return {
                    "account_code": account_code,
                    "reason": reason,
                    "confidence": float(confidence or 0.0),
                    "support_count": support_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "status": status,
                    "matched_on": "description_fuzzy",
                    "source": "pattern_active_fuzzy" if status == "active" else "pattern_candidate_fuzzy",
                    "pattern_similarity": round(ratio, 2),
                    "pattern_value_used": matched_pattern_value,
                    "pattern_days_since_seen": days_since(last_seen_at),
                    "pattern_recency_penalty": recency_penalty_days(last_seen_at),
                }

        if part:
            row = get_fuzzy_pattern_match(cur, "partner", part, tenant_id, min_ratio=0.84)
            if row:
                matched_pattern_value, account_code, reason, support_count, success_count, failure_count, status, last_seen_at, ratio = row
                update_pattern_usage("partner", matched_pattern_value, account_code, tenant_id=tenant_id)
                confidence = adaptive_pattern_confidence(
                    support_count, success_count, failure_count,
                    fuzzy_ratio=ratio, status=status, last_seen_at=last_seen_at,
                )
                return {
                    "account_code": account_code,
                    "reason": reason,
                    "confidence": float(confidence or 0.0),
                    "support_count": support_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "status": status,
                    "matched_on": "partner_fuzzy",
                    "source": "pattern_active_fuzzy" if status == "active" else "pattern_candidate_fuzzy",
                    "pattern_similarity": round(ratio, 2),
                    "pattern_value_used": matched_pattern_value,
                    "pattern_days_since_seen": days_since(last_seen_at),
                    "pattern_recency_penalty": recency_penalty_days(last_seen_at),
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
    tenant_id: str = "default",
):
    desc = normalize_text(description)
    part = normalize_text(partner)
    op = normalize_text(operation_code)
    doc = normalize_text(doc_type)
    combined = f"{desc} {part}".strip()

    paid_in_value = to_float(paid_in)
    paid_out_value = to_float(paid_out)
    amount_for_history = paid_out_value if paid_out_value is not None else paid_in_value

    # 0. PARTNER MEMORY OVERRIDE
    conn = get_db()
    try:
        partner_override = check_partner_memory(conn, part, tenant_id=tenant_id)
    finally:
        conn.close()

    if partner_override:
        anomaly = check_anomaly(amount_for_history, partner_override["account_code"], tenant_id)
        return {
            "account_code": partner_override["account_code"],
            "reason": "partner_memory_override",
            "confidence": min(0.99, float(partner_override["confidence"] or 0.0)),
            "review_required": False,
            "status": "auto_approved",
            "source": "partner_memory",
            "pattern_support_count": None,
            "pattern_success_count": None,
            "pattern_failure_count": None,
            "pattern_matched_on": "partner_memory",
            "pattern_similarity": None,
            "pattern_value_used": part,
            "pattern_days_since_seen": None,
            "pattern_recency_penalty": None,
            "autopilot_eligible": True,
            "autopilot_reason": "partner_memory_override",
            "anomaly_flag": anomaly.get("anomaly_flag", False),
            "anomaly_reason": anomaly.get("anomaly_reason"),
        }

    # 1. EXPENSE ARTICLE
    article = find_expense_article(desc, part)
    if article:
        anomaly = check_anomaly(amount_for_history, article["linked_account_code"], tenant_id)
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
            "anomaly_flag": anomaly.get("anomaly_flag", False),
            "anomaly_reason": anomaly.get("anomaly_reason"),
        }

    # 2. TRANSACTION MEMORY
    memory = find_memory_match(desc, part, tenant_id=tenant_id)
    if memory:
        confidence = float(memory.get("confidence") or 0.0)
        usage_count = safe_int(memory.get("memory_usage_count"), 0)
        anomaly = check_anomaly(amount_for_history, memory["account_code"], tenant_id)
        return {
            "account_code": memory["account_code"],
            "reason": memory["reason"],
            "confidence": float(confidence or 0.0),
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
            "autopilot_eligible": confidence >= 0.90 and usage_count >= 3,
            "autopilot_reason": "memory_match" if confidence >= 0.90 and usage_count >= 3 else "memory_needs_review",
            "anomaly_flag": anomaly.get("anomaly_flag", False),
            "anomaly_reason": anomaly.get("anomaly_reason"),
        }

    # 3. ERP MEMORY
    erp_match = find_erp_memory_match(
        description=description,
        partner=partner,
        amount=amount_for_history,
        doc_type=doc_type,
        tenant_id=tenant_id,
    )
    if erp_match:
        confidence = min(float(erp_match.get("confidence") or 0.90), 0.94)
        auto_ok = confidence >= 0.93
        anomaly = check_anomaly(amount_for_history, erp_match.get("account_code"), tenant_id)
        return {
            "account_code": erp_match.get("account_code"),
            "reason": "erp_history_match",
            "confidence": float(confidence or 0.0),
            "review_required": not auto_ok,
            "status": "auto_approved" if auto_ok else "pending_approval",
            "source": "erp_history",
            "pattern_support_count": erp_match.get("evidence_count"),
            "pattern_success_count": None,
            "pattern_failure_count": None,
            "pattern_matched_on": "erp_posting_memory",
            "pattern_similarity": None,
            "pattern_value_used": erp_match.get("description"),
            "pattern_days_since_seen": None,
            "pattern_recency_penalty": None,
            "autopilot_eligible": auto_ok,
            "autopilot_reason": "erp_history_rule" if auto_ok else "erp_history_needs_review",
            "anomaly_flag": anomaly.get("anomaly_flag", False),
            "anomaly_reason": anomaly.get("anomaly_reason"),
        }

    # 4. LEARNING PATTERNS
    learned = check_patterns(desc, part, tenant_id=tenant_id)
    if learned:
        support_count = safe_int(learned.get("support_count"), 0)
        success_count = safe_int(learned.get("success_count"), 0)
        failure_count = safe_int(learned.get("failure_count"), 0)
        pattern_days = learned.get("pattern_days_since_seen")
        confidence = float(learned.get("confidence") or 0.0)
        learned_status = normalize_text(learned.get("status"))

        review_required = True
        status = "pending_approval"

        if learned_status == "active" and confidence >= 0.90:
            review_required = False
            status = "auto_approved"

        autopilot_reason = "not_eligible"
        if learned_status != "active":
            autopilot_reason = "status_not_active"
        elif (pattern_days if pattern_days is not None else 999999) > 45:
            autopilot_reason = "pattern_stale"
        elif failure_count > 0:
            autopilot_reason = "has_failures"
        elif support_count < 5:
            autopilot_reason = "support_below_threshold"
        elif success_count < 3:
            autopilot_reason = "success_below_threshold"
        elif confidence < 0.90:
            autopilot_reason = "confidence_below_autopilot_threshold"
        else:
            autopilot_reason = "eligible_for_autopilot"

        anomaly = check_anomaly(amount_for_history, learned["account_code"], tenant_id)
        return {
            "account_code": learned["account_code"],
            "reason": learned["reason"],
            "confidence": float(confidence or 0.0),
            "review_required": review_required,
            "status": status,
            "source": learned["source"],
            "pattern_support_count": support_count,
            "pattern_success_count": success_count,
            "pattern_failure_count": failure_count,
            "pattern_matched_on": learned.get("matched_on"),
            "pattern_similarity": learned.get("pattern_similarity"),
            "pattern_value_used": learned.get("pattern_value_used"),
            "pattern_days_since_seen": pattern_days,
            "pattern_recency_penalty": learned.get("pattern_recency_penalty"),
            "autopilot_eligible": status == "auto_approved",
            "autopilot_reason": autopilot_reason,
            "anomaly_flag": anomaly.get("anomaly_flag", False),
            "anomaly_reason": anomaly.get("anomaly_reason"),
        }

    # 5. FALLBACK RULES
    matched_account = "7910"
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
            confidence = min(float(confidence or 0.0) + 0.05, 0.95)
    if keyword_matched and part:
        confidence = min(float(confidence or 0.0) + 0.05, 0.95)
    if keyword_matched and op:
        if matched_reason in op or matched_account in op:
            confidence = min(float(confidence or 0.0) + 0.05, 1.0)

    if not keyword_matched:
        try:
            llm_result = llm_service.classify(
                description, {"partner": part, "amount": amount_for_history}, tenant_id
            )
            if llm_result.get("account_code") and float(llm_result.get("confidence") or 0.0) > 0.55:
                matched_account = llm_result["account_code"]
                matched_reason = "llm:gpt"
                confidence = float(llm_result.get("confidence") or 0.0)
                keyword_matched = True
            else:
                raise ValueError("low confidence")
        except Exception:
            if paid_in_value is not None and paid_out_value is None:
                matched_account = "6110"
                matched_reason = "income_direction"
                confidence = 0.65
            elif paid_out_value is not None and paid_in_value is None:
                matched_account = "7910"
                matched_reason = "expense_direction"
                confidence = 0.55
            else:
                matched_account = "7910"
                matched_reason = "default_expense"
                confidence = 0.4

    confidence = round(min(float(confidence or 0.0), 1.0), 2)
    review_required = confidence < 0.75
    anomaly = check_anomaly(amount_for_history, matched_account, tenant_id)
    georgia_enriched = georgia_pack.apply_rules(
        {
            "description": description,
            "amount": amount_for_history or 0,
            "account_code": matched_account,
        },
        tenant_id
    )

    return {
        "account_code": matched_account,
        "reason": matched_reason,
        "confidence": float(confidence or 0.0),
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
        "anomaly_flag": anomaly.get("anomaly_flag", False),
        "anomaly_reason": anomaly.get("anomaly_reason"),
        "vat_suggested": georgia_enriched.get("vat_suggested", False),
        "vat_amount": georgia_enriched.get("vat_amount"),
        "payg_required": georgia_enriched.get("payg_required", False),
        "payg_amount": georgia_enriched.get("payg_amount"),
    }