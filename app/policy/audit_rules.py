# Audit Risk Rules — based on:
# 1. Georgian Tax Code (Codex R4)
# 2. USAID/Deloitte Tax Disputes Analysis 2016
# 3. GAAS v5.2 Control Framework

AUDIT_RISK_RULES = [
    # --- HIGH RISK ---
    {
        "rule_id":   "AR.CASH.LARGE",
        "severity":  "HIGH",
        "issue_type":"threshold_breach",
        "condition": lambda tx: tx.get("amount", 0) > 10000,
        "message":   "ნაღდი/ტრანზაქცია 10,000+ GEL — საგადასახადო სამსახურის ყურადღება",
        "action":    "Attach supporting documents. Verify VAT invoice exists.",
    },
    {
        "rule_id":   "AR.VAT.MISSING_INVOICE",
        "severity":  "HIGH",
        "issue_type":"missing_document",
        "condition": lambda tx: tx.get("amount", 0) > 500 and not tx.get("doc_ref"),
        "message":   "500+ GEL ოპერაციაზე ანგარიშფაქტურა არ არის (Tax Code მუხლი 167)",
        "action":    "Request VAT invoice from supplier.",
    },
    {
        "rule_id":   "AR.ROUND.SUSPICIOUS",
        "severity":  "MEDIUM",
        "issue_type":"anomaly",
        "condition": lambda tx: tx.get("amount", 0) >= 5000 and tx.get("amount", 0) % 1000 == 0,
        "message":   "მრგვალი რიცხვი 5,000+ GEL — Deloitte: დამახასიათებელი ოფშო სქემებისთვის",
        "action":    "Verify business purpose and counterparty.",
    },
    {
        "rule_id":   "AR.WEEKEND.TX",
        "severity":  "LOW",
        "issue_type":"anomaly",
        "condition": lambda tx: tx.get("weekday", 0) >= 5,
        "message":   "შაბათ-კვირის ტრანზაქცია — Deloitte: დამახასიათებელი",
        "action":    "Confirm operational necessity.",
    },
    {
        "rule_id":   "AR.CFO.APPROVAL",
        "severity":  "CRITICAL",
        "issue_type":"policy_violation",
        "condition": lambda tx: tx.get("amount", 0) > 10000,
        "message":   "CFO-ს დასტური საჭიროა 10,000+ GEL-ზე",
        "action":    "Escalate to CFO before posting.",
    },
    {
        "rule_id":   "AR.UNCLASSIFIED",
        "severity":  "MEDIUM",
        "issue_type":"classification_missing",
        "condition": lambda tx: tx.get("rule_id","") == "F3.UNCLASSIFIED",
        "message":   "ტრანზაქცია კლასიფიცირებული არ არის — მანუალური განხილვა",
        "action":    "Assign correct account code manually.",
    },
    {
        "rule_id":   "AR.GOOD_FAITH",
        "severity":  "LOW",
        "issue_type":"good_faith_notice",
        "condition": lambda tx: tx.get("confidence", 1.0) < 0.70,
        "message":   "დაბალი confidence — კეთილსინდისიერი გადამხდელის პრინციპი გამოიყენება",
        "action":    "Document intent. USAID/Deloitte: good faith defense available.",
    },
]

def run_audit_rules(tx: dict) -> list:
    """Run all audit risk rules on a transaction dict."""
    import uuid
    from datetime import datetime, timezone
    issues = []
    for rule in AUDIT_RISK_RULES:
        try:
            if rule["condition"](tx):
                issues.append({
                    "id":          str(uuid.uuid4()),
                    "rule_id":     rule["rule_id"],
                    "severity":    rule["severity"],
                    "issue_type":  rule["issue_type"],
                    "message":     rule["message"],
                    "suggested_action": rule["action"],
                    "tx_id":       tx.get("id",""),
                    "status":      "open",
                    "created_at":  datetime.now(timezone.utc).isoformat(),
                })
        except:
            continue
    return issues
