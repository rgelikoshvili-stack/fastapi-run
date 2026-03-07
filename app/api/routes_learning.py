from fastapi import APIRouter
import psycopg2, psycopg2.extras, json
from datetime import datetime
from app.api.db import get_db

router = APIRouter(prefix="/learning", tags=["learning"])



def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS learning_feedback (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(100),
            feedback_type VARCHAR(50),
            original_account VARCHAR(20),
            corrected_account VARCHAR(20),
            original_amount FLOAT,
            description TEXT,
            user_comment TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS async_queue (
            id SERIAL PRIMARY KEY,
            task_type VARCHAR(50),
            payload JSONB,
            status VARCHAR(20) DEFAULT 'PENDING',
            result JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            processed_at TIMESTAMP
        )
    """)

@router.post("/feedback")
def submit_feedback(payload: dict):
    conn = get_db()
    cur = conn.cursor()
    ensure_tables(cur)
    cur.execute("""
        INSERT INTO learning_feedback 
        (run_id, feedback_type, original_account, corrected_account, original_amount, description, user_comment)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (
        payload.get("run_id"),
        payload.get("feedback_type", "CORRECTION"),
        payload.get("original_account"),
        payload.get("corrected_account"),
        payload.get("amount", 0),
        payload.get("description", ""),
        payload.get("comment", "")
    ))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "message": "Feedback saved — AI will learn from this"}

@router.get("/patterns")
def get_learned_patterns():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    cur.execute("""
        SELECT corrected_account, COUNT(*) as frequency, 
               AVG(original_amount) as avg_amount,
               array_agg(DISTINCT description) as descriptions
        FROM learning_feedback
        WHERE feedback_type='CORRECTION'
        GROUP BY corrected_account
        ORDER BY frequency DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "learned_patterns": [dict(r) for r in rows]}

@router.post("/queue/add")
def queue_add(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    cur.execute("""
        INSERT INTO async_queue (task_type, payload, status)
        VALUES (%s,%s,'PENDING') RETURNING id
    """, (payload.get("task_type", "ANALYZE"), json.dumps(payload)))
    task_id = cur.fetchone()["id"]
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "task_id": task_id, "status": "PENDING"}

@router.get("/queue/status")
def queue_status():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    cur.execute("SELECT status, COUNT(*) as count FROM async_queue GROUP BY status")
    breakdown = {r["status"]: r["count"] for r in cur.fetchall()}
    cur.execute("SELECT * FROM async_queue ORDER BY created_at DESC LIMIT 10")
    recent = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "queue_breakdown": breakdown, "recent_tasks": recent}

@router.get("/stats")
def learning_stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    cur.execute("SELECT COUNT(*) as total FROM learning_feedback")
    total = cur.fetchone()["total"]
    cur.execute("SELECT feedback_type, COUNT(*) as count FROM learning_feedback GROUP BY feedback_type")
    by_type = {r["feedback_type"]: r["count"] for r in cur.fetchall()}
    cur.close(); conn.close()
    return {"ok": True, "total_feedback": total, "by_type": by_type, "learning_active": True}