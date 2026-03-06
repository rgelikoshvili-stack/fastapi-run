from fastapi import APIRouter
import psycopg2, psycopg2.extras, json
from datetime import datetime

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

def get_db():
    return psycopg2.connect(host="35.192.214.120", dbname="bridgehub", user="postgres", password="BridgeHub2026x")

@router.get("/run")
def run_reconciliation():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Bank transactions
    cur.execute("SELECT id, date, amount, description FROM bank_transactions ORDER BY created_at DESC LIMIT 200")
    bank_txs = [dict(r) for r in cur.fetchall()]
    
    # Journal entries
    cur.execute("SELECT id, created_at, amount, description FROM journal_entries ORDER BY created_at DESC LIMIT 200")
    journal_txs = [dict(r) for r in cur.fetchall()]
    
    matched = []
    unmatched_bank = []
    unmatched_journal = []
    used_journal_ids = set()

    for btx in bank_txs:
        found = False
        for jtx in journal_txs:
            if jtx["id"] in used_journal_ids:
                continue
            b_amount = float(btx.get("amount") or 0)
            j_amount = float(jtx.get("amount") or 0)
            if abs(b_amount - j_amount) < 0.01:
                matched.append({
                    "bank_id": btx["id"],
                    "journal_id": jtx["id"],
                    "amount": b_amount,
                    "status": "MATCHED"
                })
                used_journal_ids.add(jtx["id"])
                found = True
                break
        if not found:
            unmatched_bank.append({
                "bank_id": btx["id"],
                "amount": btx.get("amount"),
                "description": btx.get("description"),
                "status": "UNMATCHED_BANK"
            })

    for jtx in journal_txs:
        if jtx["id"] not in used_journal_ids:
            unmatched_journal.append({
                "journal_id": jtx["id"],
                "amount": jtx.get("amount"),
                "status": "UNMATCHED_JOURNAL"
            })

    cur.close(); conn.close()
    
    total = len(bank_txs)
    match_rate = round(len(matched) / total * 100, 1) if total > 0 else 0
    
    return {
        "ok": True,
        "summary": {
            "bank_transactions": len(bank_txs),
            "journal_entries": len(journal_txs),
            "matched": len(matched),
            "unmatched_bank": len(unmatched_bank),
            "unmatched_journal": len(unmatched_journal),
            "match_rate_percent": match_rate
        },
        "matched": matched[:20],
        "unmatched_bank": unmatched_bank[:20],
        "unmatched_journal": unmatched_journal[:20]
    }

@router.get("/status")
def reconciliation_status():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as bank_count FROM bank_transactions")
    bank_count = cur.fetchone()["bank_count"]
    cur.execute("SELECT COUNT(*) as journal_count FROM journal_entries")
    journal_count = cur.fetchone()["journal_count"]
    cur.close(); conn.close()
    return {
        "ok": True,
        "bank_transactions": bank_count,
        "journal_entries": journal_count,
        "ready": bank_count > 0 and journal_count > 0
    }