from fastapi import APIRouter
import psycopg2, psycopg2.extras, json
from datetime import datetime, timezone
from collections import Counter
from app.api.db import get_db

router = APIRouter(prefix="/patterns", tags=["patterns"])

DB_URL = "postgresql://postgres:BridgeHub2026x@35.192.214.120/bridgehub"

def get_db():
    conn = psycopg2.connect(DB_URL)
    return conn

@router.get("/health")
def health():
    return {"ok": True, "service": "patterns", "db": "postgresql"}

@router.get("/errors")
def error_patterns():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT error_tags FROM diffs")
    rows = cur.fetchall()
    cur.close(); conn.close()
    counter = Counter()
    for row in rows:
        tags = json.loads(row[0] or "[]")
        for tag in tags:
            counter[tag] += 1
    return {
        "ok": True,
        "total_diffs": len(rows),
        "error_patterns": dict(counter.most_common())
    }

@router.get("/accounts")
def account_patterns():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT changed_fields FROM diffs")
    rows = cur.fetchall()
    cur.close(); conn.close()
    ai_accounts = Counter()
    human_accounts = Counter()
    for row in rows:
        fields = json.loads(row[0] or "[]")
        for f in fields:
            if f.get("field") == "account_code":
                ai_accounts[f.get("ai", "?")] += 1
                human_accounts[f.get("human", "?")] += 1
    return {
        "ok": True,
        "most_wrong_ai_accounts": dict(ai_accounts.most_common(10)),
        "most_correct_human_accounts": dict(human_accounts.most_common(10))
    }

@router.get("/weekly")
def weekly_report():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM diffs ORDER BY created_at DESC")
    diffs = cur.fetchall()
    cur.execute("SELECT * FROM human_decisions ORDER BY created_at DESC")
    decisions = cur.fetchall()
    cur.execute("SELECT state, COUNT(*) as cnt FROM approvals GROUP BY state")
    approvals = cur.fetchall()
    cur.close(); conn.close()

    error_counter = Counter()
    for row in diffs:
        tags = json.loads(row["error_tags"] or "[]")
        for tag in tags:
            error_counter[tag] += 1

    approval_stats = {row["state"]: row["cnt"] for row in approvals}

    return {
        "ok": True,
        "report_date": datetime.now(timezone.utc).isoformat(),
        "total_decisions": len(decisions),
        "total_diffs": len(diffs),
        "top_errors": dict(error_counter.most_common(5)),
        "approval_stats": approval_stats,
        "recommendation": _recommend(error_counter)
    }

def _recommend(counter):
    if not counter:
        return "სისტემა სწორად მუშაობს — შეცდომები არ არის!"
    top = counter.most_common(1)[0]
    tips = {
        "VAT_mismatch": "VAT გამოთვლა გადაამოწმე — 18% წესი",
        "wrong_account": "ანგარიშის კოდები გადაამოწმე COA-ში",
        "amount_mismatch": "თანხების შედარება საჭიროა",
        "wrong_direction": "Debit/Credit მიმართულება შეამოწმე"
    }
    return tips.get(top[0], f"ყველაზე ხშირი შეცდომა: {top[0]} ({top[1]} ჯერ)")