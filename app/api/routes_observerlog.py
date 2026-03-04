from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import sqlite3, json, uuid, os
from datetime import datetime, timezone

router = APIRouter(prefix="/observerlog", tags=["observerlog"])

DB_PATH = os.getenv("OBSERVER_DB", "/tmp/observer_log.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS observations (
            observation_id TEXT PRIMARY KEY,
            case_id TEXT,
            raw_input TEXT,
            canonical_input TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ai_suggestions (
            ai_id TEXT PRIMARY KEY,
            case_id TEXT,
            draft TEXT,
            confidence REAL,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS human_decisions (
            human_id TEXT PRIMARY KEY,
            case_id TEXT,
            final_journal TEXT,
            comment TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS diffs (
            diff_id TEXT PRIMARY KEY,
            case_id TEXT,
            ai_id TEXT,
            human_id TEXT,
            changed_fields TEXT,
            error_tags TEXT,
            rule_tags TEXT,
            created_at TEXT
        );
    """)
    conn.commit()
    conn.close()

init_db()

class LogPayload(BaseModel):
    case_id: Optional[str] = None
    raw_input: Optional[Dict[str, Any]] = None
    canonical_input: Optional[Dict[str, Any]] = None
    ai_draft: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None

class DecisionPayload(BaseModel):
    case_id: str
    final_journal: Dict[str, Any]
    comment: Optional[str] = ""

def _compute_diff(ai_draft: dict, final_journal: dict) -> dict:
    changed_fields = []
    error_tags = []
    rule_tags = []
    for key in set(list(ai_draft.keys()) + list(final_journal.keys())):
        ai_val = ai_draft.get(key)
        hu_val = final_journal.get(key)
        if ai_val != hu_val:
            changed_fields.append({
                "field": key,
                "ai": ai_val,
                "human": hu_val
            })
            if key == "vat": error_tags.append("VAT_mismatch")
            if key == "account_code": error_tags.append("wrong_account")
            if key == "amount": error_tags.append("amount_mismatch")
            if key == "direction": error_tags.append("wrong_direction")
    return {
        "changed_fields": changed_fields,
        "error_tags": list(set(error_tags)),
        "rule_tags": rule_tags
    }

@router.get("/health")
def health():
    return {"ok": True, "db_path": DB_PATH}

@router.get("/cases/count")
def cases_count():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    conn.close()
    return {"ok": True, "count": count}

@router.post("/log")
def log_case(payload: LogPayload):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    case_id = payload.case_id or str(uuid.uuid4())
    conn.execute("INSERT OR IGNORE INTO cases VALUES (?,?)", (case_id, now))
    observation_id = str(uuid.uuid4())
    conn.execute("INSERT INTO observations VALUES (?,?,?,?,?)", (
        observation_id, case_id,
        json.dumps(payload.raw_input or {}, ensure_ascii=False),
        json.dumps(payload.canonical_input or {}, ensure_ascii=False),
        now
    ))
    ai_id = str(uuid.uuid4())
    conn.execute("INSERT INTO ai_suggestions VALUES (?,?,?,?,?)", (
        ai_id, case_id,
        json.dumps(payload.ai_draft or {}, ensure_ascii=False),
        payload.confidence or 0.0, now
    ))
    conn.commit()
    conn.close()
    return {"ok": True, "case_id": case_id, "observation_id": observation_id, "ai_id": ai_id}

@router.post("/decision")
def human_decision(payload: DecisionPayload):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        "SELECT * FROM ai_suggestions WHERE case_id=? ORDER BY created_at DESC LIMIT 1",
        (payload.case_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"No AI suggestion found for case_id={payload.case_id}")
    ai_draft = json.loads(row["draft"])
    human_id = str(uuid.uuid4())
    conn.execute("INSERT INTO human_decisions VALUES (?,?,?,?,?)", (
        human_id, payload.case_id,
        json.dumps(payload.final_journal, ensure_ascii=False),
        payload.comment, now
    ))
    diff = _compute_diff(ai_draft, payload.final_journal)
    diff_id = str(uuid.uuid4())
    conn.execute("INSERT INTO diffs VALUES (?,?,?,?,?,?,?,?)", (
        diff_id, payload.case_id, row["ai_id"], human_id,
        json.dumps(diff["changed_fields"], ensure_ascii=False),
        json.dumps(diff["error_tags"], ensure_ascii=False),
        json.dumps(diff["rule_tags"], ensure_ascii=False),
        now
    ))
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "human_id": human_id,
        "diff_id": diff_id,
        "diff": diff
    }

@router.get("/diffs/{case_id}")
def get_diffs(case_id: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM diffs WHERE case_id=? ORDER BY created_at DESC",
        (case_id,)
    ).fetchall()
    conn.close()
    return {"ok": True, "diffs": [dict(r) for r in rows]}

@router.get("/patterns")
def get_patterns():
    conn = get_db()
    rows = conn.execute("SELECT error_tags FROM diffs").fetchall()
    conn.close()
    counter = {}
    for row in rows:
        tags = json.loads(row["error_tags"] or "[]")
        for tag in tags:
            counter[tag] = counter.get(tag, 0) + 1
    return {"ok": True, "patterns": counter}