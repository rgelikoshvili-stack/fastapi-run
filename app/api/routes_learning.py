from fastapi import APIRouter
import psycopg2.extras
import json

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.services.learning_service import get_learning_health_service

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
        ALTER TABLE learning_feedback
        ADD COLUMN IF NOT EXISTS run_id VARCHAR(100)
    """)
    cur.execute("""
        ALTER TABLE learning_feedback
        ADD COLUMN IF NOT EXISTS feedback_type VARCHAR(50)
    """)
    cur.execute("""
        ALTER TABLE learning_feedback
        ADD COLUMN IF NOT EXISTS original_account VARCHAR(20)
    """)
    cur.execute("""
        ALTER TABLE learning_feedback
        ADD COLUMN IF NOT EXISTS corrected_account VARCHAR(20)
    """)
    cur.execute("""
        ALTER TABLE learning_feedback
        ADD COLUMN IF NOT EXISTS original_amount FLOAT
    """)
    cur.execute("""
        ALTER TABLE learning_feedback
        ADD COLUMN IF NOT EXISTS description TEXT
    """)
    cur.execute("""
        ALTER TABLE learning_feedback
        ADD COLUMN IF NOT EXISTS user_comment TEXT
    """)
    cur.execute("""
        ALTER TABLE learning_feedback
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()
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

    cur.execute("""
        ALTER TABLE async_queue
        ADD COLUMN IF NOT EXISTS task_type VARCHAR(50)
    """)
    cur.execute("""
        ALTER TABLE async_queue
        ADD COLUMN IF NOT EXISTS payload JSONB
    """)
    cur.execute("""
        ALTER TABLE async_queue
        ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'PENDING'
    """)
    cur.execute("""
        ALTER TABLE async_queue
        ADD COLUMN IF NOT EXISTS result JSONB
    """)
    cur.execute("""
        ALTER TABLE async_queue
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()
    """)
    cur.execute("""
        ALTER TABLE async_queue
        ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP
    """)

    cur.connection.commit()


@router.post("/feedback")
def submit_feedback(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_tables(cur)

        cur.execute("""
            INSERT INTO learning_feedback
            (
                run_id,
                feedback_type,
                original_account,
                corrected_account,
                original_amount,
                description,
                user_comment
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            payload.get("run_id"),
            payload.get("feedback_type", "CORRECTION"),
            payload.get("original_account") or payload.get("account_code"),
            payload.get("corrected_account") or payload.get("corrected_account_code"),
            payload.get("amount", 0),
            payload.get("description", ""),
            payload.get("comment", ""),
        ))

        row = cur.fetchone()
        conn.commit()
        return ok_response("Feedback saved", {"id": row["id"]})
    except Exception as e:
        conn.rollback()
        return error_response("Feedback save failed", "LEARNING_FEEDBACK_SAVE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/patterns")
def get_learned_patterns():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_tables(cur)

        cur.execute("""
            SELECT
                COALESCE(corrected_account, original_account, 'unknown') AS learned_account_code,
                COUNT(*) AS frequency,
                AVG(original_amount) AS avg_amount,
                array_agg(DISTINCT description) AS descriptions
            FROM learning_feedback
            WHERE feedback_type = 'CORRECTION'
            GROUP BY COALESCE(corrected_account, original_account, 'unknown')
            ORDER BY frequency DESC
            LIMIT 20
        """)
        rows = cur.fetchall()

        return ok_response(
            "Learned patterns",
            {"items": [dict(r) for r in rows], "count": len(rows)}
        )
    except Exception as e:
        return error_response("Learning patterns failed", "LEARNING_PATTERNS_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/queue/add")
def queue_add(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_tables(cur)

        cur.execute("""
            INSERT INTO async_queue (task_type, payload, status)
            VALUES (%s, %s, 'PENDING')
            RETURNING id
        """, (
            payload.get("task_type", "ANALYZE"),
            json.dumps(payload),
        ))

        row = cur.fetchone()
        conn.commit()
        return ok_response("Queue task added", {"task_id": row["id"], "status": "PENDING"})
    except Exception as e:
        conn.rollback()
        return error_response("Queue add failed", "LEARNING_QUEUE_ADD_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/queue/status")
def queue_status():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_tables(cur)

        cur.execute("SELECT status, COUNT(*) AS count FROM async_queue GROUP BY status")
        breakdown = {r["status"]: r["count"] for r in cur.fetchall()}

        cur.execute("""
            SELECT id, task_type, status, created_at, processed_at
            FROM async_queue
            ORDER BY created_at DESC
            LIMIT 10
        """)
        recent = [dict(r) for r in cur.fetchall()]

        return ok_response("Queue status", {
            "queue_breakdown": breakdown,
            "recent_tasks": recent,
        })
    except Exception as e:
        return error_response("Queue status failed", "LEARNING_QUEUE_STATUS_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/stats")
def learning_stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_tables(cur)

        cur.execute("SELECT COUNT(*) AS total FROM learning_feedback")
        total = cur.fetchone()["total"]

        cur.execute("""
            SELECT feedback_type, COUNT(*) AS count
            FROM learning_feedback
            GROUP BY feedback_type
        """)
        by_type = {r["feedback_type"]: r["count"] for r in cur.fetchall()}

        return ok_response("Learning stats", {
            "total_feedback": total,
            "by_type": by_type,
            "learning_active": True,
        })
    except Exception as e:
        return error_response("Learning stats failed", "LEARNING_STATS_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/health")
def learning_health():
    result = get_learning_health_service()
    if result.get("ok"):
        return ok_response("Learning health", result)
    return error_response(
        "Learning health failed",
        "LEARNING_HEALTH_ERROR",
        result.get("error", "unknown"),
    )