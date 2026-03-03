from decimal import Decimal

POLICY_RULES = {
    "max_single_payment_without_approval": Decimal("2000"),
    "max_daily_spend_per_vendor":          Decimal("10000"),
    "restricted_categories":               ["gambling", "personal", "unclassified"],
    "require_doc_above":                   Decimal("500"),
    "cfo_approval_above":                  Decimal("10000"),
}

def check_policy(tx, draft_category: str = "") -> list:
    from app.schemas.canonical import ControlIssue
    from datetime import datetime, timezone
    issues = []
    rules = POLICY_RULES
    amount = tx.amount if hasattr(tx, "amount") else Decimal(str(tx.get("amount", 0)))

    if amount > rules["max_single_payment_without_approval"]:
        issues.append(ControlIssue(
            issue_type="policy_violation", severity="HIGH",
            message=f"Payment {amount} GEL exceeds approval threshold {rules['max_single_payment_without_approval']} GEL",
            linked_object_id=tx.id if hasattr(tx, "id") else tx.get("id",""),
            linked_object_type="transaction",
            suggested_action="Requires manager approval before posting.",
            created_at=datetime.now(timezone.utc).isoformat()
        ))

    if amount > rules["require_doc_above"]:
        issues.append(ControlIssue(
            issue_type="missing_document", severity="MEDIUM",
            message=f"Payment {amount} GEL requires supporting document (invoice/receipt)",
            linked_object_id=tx.id if hasattr(tx, "id") else tx.get("id",""),
            linked_object_type="transaction",
            suggested_action="Attach invoice or receipt.",
            created_at=datetime.now(timezone.utc).isoformat()
        ))

    if amount > rules["cfo_approval_above"]:
        issues.append(ControlIssue(
            issue_type="threshold_breach", severity="CRITICAL",
            message=f"Payment {amount} GEL requires CFO approval",
            linked_object_id=tx.id if hasattr(tx, "id") else tx.get("id",""),
            linked_object_type="transaction",
            suggested_action="Escalate to CFO for approval.",
            created_at=datetime.now(timezone.utc).isoformat()
        ))

    return issues
