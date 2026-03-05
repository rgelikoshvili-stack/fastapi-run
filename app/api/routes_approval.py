from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import psycopg2, psycopg2.extras, json, uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/approval", tags=["approval"])

DB_URL = "postgresql://postgres:BridgeHub2026x@35.192.214.120/bridgehub"

def get_db():
    conn = psycopg2.connect(DB_URL)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
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
    cur.close()
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
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    approval_id = str(uuid.uuid4())
    case_id = payload.case_id or str(uuid.uuid4())
    cur.execute("INSERT INTO approvals VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
        approval_id, case_id, "PENDING_APPROVAL",
        json.dumps(payload.entries), payload.submitted_by,
        None, None, now, now))
    conn.commit(); cur.close(); conn.close()
    return {"ok": True, "approval_id": approval_id, "case_id": case_id, "state": "PENDING_APPROVAL"}

@router.get("/pending")
def pending():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM approvals WHERE state='PENDING_APPROVAL' ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "pending": [dict(r) for r in rows]}

@router.post("/approve/{approval_id}")
def approve(approval_id: str, payload: ActionPayload):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("SELECT * FROM approvals WHERE approval_id=%s", (approval_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        raise HTTPException(404, f"Not found: {approval_id}")
    if row["state"] != "PENDING_APPROVAL":
        cur.close(); conn.close()
        raise HTTPException(400, f"Cannot approve — state is {row['state']}")
    cur.execute("UPDATE approvals SET state='APPROVED', approved_by=%s, comment=%s, updated_at=%s WHERE approval_id=%s",
                (payload.approved_by, payload.comment, now, approval_id))
    conn.commit(); cur.close(); conn.close()
    return {"ok": True, "approval_id": approval_id, "state": "APPROVED"}

@router.post("/reject/{approval_id}")
def reject(approval_id: str, payload: ActionPayload):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("SELECT * FROM approvals WHERE approval_id=%s", (approval_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        raise HTTPException(404, f"Not found: {approval_id}")
    cur.execute("UPDATE approvals SET state='REJECTED', approved_by=%s, comment=%s, updated_at=%s WHERE approval_id=%s",
                (payload.approved_by, payload.comment, now, approval_id))
    conn.commit(); cur.close(); conn.close()
    return {"ok": True, "approval_id": approval_id, "state": "REJECTED"}

@router.get("/status/{approval_id}")
def status(approval_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM approvals WHERE approval_id=%s", (approval_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        raise HTTPException(404, f"Not found: {approval_id}")
    return {"ok": True, "approval": dict(row)}

@router.get("/health")
def health():
    return {"ok": True, "service": "approval", "db": "postgresql"}