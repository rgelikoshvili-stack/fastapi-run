from decimal import Decimal
import hashlib
from datetime import datetime, timezone
from app.schemas.canonical import CanonicalBankTransaction, ControlIssue

ISSUES: list = []

def compute_dedup_hash(tx: CanonicalBankTransaction) -> str:
    key = f"{tx.date}|{tx.amount}|{tx.description[:50]}|{tx.currency}"
    return hashlib.sha256(key.encode()).hexdigest()

def check_duplicates(tx: CanonicalBankTransaction) -> list:
    issues = []
    h = compute_dedup_hash(tx)
    from app.storage.event_log import AUDIT_LOG
    hashes = [e.get("metadata", {}).get("hash") for e in AUDIT_LOG]
    if h in hashes:
        issues.append(ControlIssue(
            issue_type="duplicate", severity="HIGH",
            message=f"Duplicate: {tx.date} {tx.amount} {tx.description[:40]}",
            linked_object_id=tx.id, linked_object_type="transaction",
            suggested_action="Compare with existing transaction",
            created_at=datetime.now(timezone.utc).isoformat()
        ))
    return issues

def check_anomalies(tx: CanonicalBankTransaction) -> list:
    issues = []
    if tx.amount > Decimal("10000"):
        issues.append(ControlIssue(
            issue_type="threshold_breach", severity="HIGH",
            message=f"Large amount: {tx.amount} GEL",
            linked_object_id=tx.id, linked_object_type="transaction",
            suggested_action="Requires manager approval",
            created_at=datetime.now(timezone.utc).isoformat()
        ))
    if tx.amount % Decimal("1000") == 0 and tx.amount >= Decimal("5000"):
        issues.append(ControlIssue(
            issue_type="anomaly", severity="LOW",
            message=f"Round number: {tx.amount} GEL",
            linked_object_id=tx.id, linked_object_type="transaction",
            created_at=datetime.now(timezone.utc).isoformat()
        ))
    if hasattr(tx.date, "weekday") and tx.date.weekday() >= 5:
        issues.append(ControlIssue(
            issue_type="anomaly", severity="LOW",
            message=f"Weekend transaction: {tx.date}",
            linked_object_id=tx.id, linked_object_type="transaction",
            created_at=datetime.now(timezone.utc).isoformat()
        ))
    if not tx.description or len(tx.description.strip()) < 3:
        issues.append(ControlIssue(
            issue_type="anomaly", severity="MEDIUM",
            message="Missing or very short description",
            linked_object_id=tx.id, linked_object_type="transaction",
            created_at=datetime.now(timezone.utc).isoformat()
        ))
    return issues

def run_all_checks(tx: CanonicalBankTransaction) -> list:
    issues = []
    issues.extend(check_duplicates(tx))
    issues.extend(check_anomalies(tx))
    for issue in issues:
        ISSUES.append(issue.model_dump())
    return issues

def get_issues(severity: str = "") -> list:
    if severity:
        return [i for i in ISSUES if i["severity"] == severity]
    return ISSUES
