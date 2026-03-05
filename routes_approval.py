from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3, uuid, os, json
from datetime import datetime, timezone

router = APIRouter(prefix="/approval", tags=["approval"])

DB_PATH = os.getenv("APPROVAL_DB", "/tmp/approval.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            case_id TEXT,
            state TEXT,
            entries TEXT,
            submitted_by TEXT,
            approved_by TEXT,
            comment TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    conn.commit()
    conn.close()

init_db()

class SubmitPayload(BaseModel):
    case_id: Optional[str] = None
    entries: list
    submitted_by: Optional[str] = "user"

class ActionPayload(BaseModel):
    approved_by: Optional[str] = "manager"
    comment: Optional[str] = ""

@router.post("/submit")
def submit(payload: SubmitPayload):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    approval_id = str(uuid.uuid4())
    case_id = payload.case_id or str(uuid.uuid4())
    conn.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?)", (
        approval_id, case_id, "PENDING_APPROVAL",
        json.dumps(payload.entries, ensure_ascii=False),
        payload.submitted_by, None, None, now, now
    ))
    conn.commit()
    conn.close()
    return {"ok": True, "approval_id": approval_id, "case_id": case_id, "state": "PENDING_APPROVAL"}

@router.get("/pending")
def pending():
    conn = get_db()
    rows = conn.execute("SELECT * FROM approvals WHERE state='PENDING_APPROVAL' ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"ok": True, "pending": [dict(r) for r in rows]}

@router.post("/approve/{approval_id}")
def approve(approval_id: str, payload: ActionPayload):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"Not found: {approval_id}")
    if row["state"] != "PENDING_APPROVAL":
        conn.close()
        raise HTTPException(400, f"Cannot approve — state is {row['state']}")
    conn.execute("UPDATE approvals SET state='APPROVED', approved_by=?, comment=?, updated_at=? WHERE approval_id=?",
                 (payload.approved_by, payload.comment, now, approval_id))
    conn.commit()
    conn.close()
    return {"ok": True, "approval_id": approval_id, "state": "APPROVED"}

@router.post("/reject/{approval_id}")
def reject(approval_id: str, payload: ActionPayload):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, f"Not found: {approval_id}")
    conn.execute("UPDATE approvals SET state='REJECTED', approved_by=?, comment=?, updated_at=? WHERE approval_id=?",
                 (payload.approved_by, payload.comment, now, approval_id))
    conn.commit()
    conn.close()
    return {"ok": True, "approval_id": approval_id, "state": "REJECTED"}

@router.get("/status/{approval_id}")
def status(approval_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Not found: {approval_id}")
    return {"ok": True, "approval": dict(row)}

@router.get("/health")
def health():
    return {"ok": True, "service": "approval", "db_path": DB_PATH}