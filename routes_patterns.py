from fastapi import APIRouter
import sqlite3, json, os
from datetime import datetime, timezone
from collections import Counter

router = APIRouter(prefix="/patterns", tags=["patterns"])

OBS_DB = os.getenv("OBSERVER_DB", "/tmp/observer_log.db")
APP_DB = os.getenv("APPROVAL_DB", "/tmp/approval.db")

def get_obs_db():
    conn = sqlite3.connect(OBS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_app_db():
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    return conn

@router.get("/health")
def health():
    return {"ok": True, "service": "patterns"}

@router.get("/errors")
def error_patterns():
    conn = get_obs_db()
    rows = conn.execute("SELECT error_tags FROM diffs").fetchall()
    conn.close()
    counter = Counter()
    for row in rows:
        tags = json.loads(row["error_tags"] or "[]")
        for tag in tags:
            counter[tag] += 1
    return {
        "ok": True,
        "total_diffs": len(rows),
        "error_patterns": dict(counter.most_common())
    }

@router.get("/accounts")
def account_patterns():
    conn = get_obs_db()
    rows = conn.execute("SELECT changed_fields FROM diffs").fetchall()
    conn.close()
    ai_accounts = Counter()
    human_accounts = Counter()
    for row in rows:
        fields = json.loads(row["changed_fields"] or "[]")
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
    conn = get_obs_db()
    diffs = conn.execute("SELECT * FROM diffs ORDER BY created_at DESC").fetchall()
    decisions = conn.execute("SELECT * FROM human_decisions ORDER BY created_at DESC").fetchall()
    conn.close()

    app_conn = get_app_db()
    approvals = app_conn.execute("SELECT state, COUNT(*) as cnt FROM approvals GROUP BY state").fetchall()
    app_conn.close()

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