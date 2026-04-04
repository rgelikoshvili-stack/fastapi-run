from fastapi import APIRouter, Request
import psycopg2.extras
import json

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
from app.api.services.learning_service import get_learning_health_service
from app.api.services.pattern_decay_service import run_pattern_decay

router = APIRouter(prefix="/learning", tags=["learning"])


def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS learning_feedback (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT DEFAULT 'default',
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
        ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default'
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
            tenant_id TEXT DEFAULT 'default',
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
        ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default'
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
def submit_feedback(request: Request, payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        ensure_tables(cur)

        cur.execute(
            """
            INSERT INTO learning_feedback
            (
                tenant_id,
                run_id,
                feedback_type,
                original_account,
                corrected_account,
                original_amount,
                description,
                user_comment
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                tenant_id,
                payload.get("run_id"),
                payload.get("feedback_type", "CORRECTION"),
                payload.get("original_account") or payload.get("account_code"),
                payload.get("corrected_account") or payload.get("corrected_account_code"),
                payload.get("amount", 0),
                payload.get("description", ""),
                payload.get("comment", ""),
            ),
        )

        row = cur.fetchone()
        conn.commit()
        return ok_response("Feedback saved", {"tenant_id": tenant_id, "id": row["id"]})
    except Exception as e:
        conn.rollback()
        return error_response("Feedback save failed", "LEARNING_FEEDBACK_SAVE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/patterns")
def get_learned_patterns(request: Request):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        ensure_tables(cur)

        cur.execute(
            """
            SELECT
                COALESCE(corrected_account, original_account, 'unknown') AS learned_account_code,
                COUNT(*) AS frequency,
                AVG(original_amount) AS avg_amount,
                array_agg(DISTINCT description) AS descriptions
            FROM learning_feedback
            WHERE tenant_id = %s
              AND feedback_type = 'CORRECTION'
            GROUP BY COALESCE(corrected_account, original_account, 'unknown')
            ORDER BY frequency DESC
            LIMIT 20
            """,
            (tenant_id,),
        )
        rows = cur.fetchall()

        return ok_response(
            "Learned patterns",
            {
                "tenant_id": tenant_id,
                "items": [dict(r) for r in rows],
                "count": len(rows),
            },
        )
    except Exception as e:
        return error_response("Learning patterns failed", "LEARNING_PATTERNS_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/queue/add")
def queue_add(request: Request, payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        ensure_tables(cur)

        cur.execute(
            """
            INSERT INTO async_queue (tenant_id, task_type, payload, status)
            VALUES (%s, %s, %s, 'PENDING')
            RETURNING id
            """,
            (
                tenant_id,
                payload.get("task_type", "ANALYZE"),
                json.dumps(payload),
            ),
        )

        row = cur.fetchone()
        conn.commit()
        return ok_response(
            "Queue task added",
            {"tenant_id": tenant_id, "task_id": row["id"], "status": "PENDING"},
        )
    except Exception as e:
        conn.rollback()
        return error_response("Queue add failed", "LEARNING_QUEUE_ADD_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/queue/status")
def queue_status(request: Request):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        ensure_tables(cur)

        cur.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM async_queue
            WHERE tenant_id = %s
            GROUP BY status
            """,
            (tenant_id,),
        )
        breakdown = {r["status"]: r["count"] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT id, tenant_id, task_type, status, created_at, processed_at
            FROM async_queue
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (tenant_id,),
        )
        recent = [dict(r) for r in cur.fetchall()]

        return ok_response(
            "Queue status",
            {
                "tenant_id": tenant_id,
                "queue_breakdown": breakdown,
                "recent_tasks": recent,
            },
        )
    except Exception as e:
        return error_response("Queue status failed", "LEARNING_QUEUE_STATUS_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/stats")
def learning_stats(request: Request):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        ensure_tables(cur)

        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM learning_feedback
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        total = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT feedback_type, COUNT(*) AS count
            FROM learning_feedback
            WHERE tenant_id = %s
            GROUP BY feedback_type
            """,
            (tenant_id,),
        )
        by_type = {r["feedback_type"]: r["count"] for r in cur.fetchall()}

        return ok_response(
            "Learning stats",
            {
                "tenant_id": tenant_id,
                "total_feedback": total,
                "by_type": by_type,
                "learning_active": True,
            },
        )
    except Exception as e:
        return error_response("Learning stats failed", "LEARNING_STATS_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/health")
def learning_health(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = get_learning_health_service(tenant_id=tenant_id)
    if result.get("ok"):
        return ok_response("Learning health", result)
    return error_response(
        "Learning health failed",
        "LEARNING_HEALTH_ERROR",
        result.get("error", "unknown"),
    )


@router.get("/patterns/top")
def learning_patterns_top(request: Request):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        ensure_tables(cur)

        cur.execute(
            """
            SELECT
                id,
                tenant_id,
                pattern_type,
                pattern_value,
                account_code,
                reason,
                confidence_score,
                support_count,
                success_count,
                failure_count,
                status,
                COALESCE(autopilot_eligible, FALSE) AS autopilot_eligible,
                last_seen_at,
                last_confirmed_at,
                CASE
                    WHEN last_seen_at IS NULL THEN NULL
                    ELSE EXTRACT(DAY FROM (NOW() - last_seen_at))
                END AS days_since_seen
            FROM learning_patterns
            WHERE tenant_id = %s
            ORDER BY
                confidence_score DESC NULLS LAST,
                success_count DESC NULLS LAST,
                support_count DESC NULLS LAST
            LIMIT 10
            """,
            (tenant_id,),
        )
        top_rows = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT
                id,
                tenant_id,
                pattern_type,
                pattern_value,
                account_code,
                reason,
                confidence_score,
                support_count,
                success_count,
                failure_count,
                status,
                COALESCE(autopilot_eligible, FALSE) AS autopilot_eligible,
                last_seen_at,
                last_confirmed_at,
                CASE
                    WHEN last_seen_at IS NULL THEN NULL
                    ELSE EXTRACT(DAY FROM (NOW() - last_seen_at))
                END AS days_since_seen
            FROM learning_patterns
            WHERE tenant_id = %s
            ORDER BY
                failure_count DESC NULLS LAST,
                confidence_score ASC NULLS LAST,
                support_count DESC NULLS LAST
            LIMIT 10
            """,
            (tenant_id,),
        )
        weak_rows = [dict(r) for r in cur.fetchall()]

        return ok_response(
            "Top & Weak patterns",
            {
                "tenant_id": tenant_id,
                "top_patterns": top_rows,
                "weak_patterns": weak_rows,
            },
        )

    except Exception as e:
        return error_response(
            "Patterns top failed",
            "LEARNING_PATTERNS_TOP_ERROR",
            str(e),
        )
    finally:
        cur.close()
        conn.close()


@router.post("/decay")
def learning_decay(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = run_pattern_decay(tenant_id=tenant_id)
    if result.get("ok"):
        return ok_response("Decay applied", result)
    return error_response(
        "Pattern decay failed",
        "LEARNING_DECAY_ERROR",
        result.get("error", "unknown"),
    )


@router.get("/autopilot-check")
def autopilot_check(
    request: Request,
    confidence: float = 0.85,
    success_count: int = 5,
    support_count: int = 6,
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    success_rate = success_count / max(support_count, 1)
    eligible = confidence >= 0.90 and success_rate >= 0.80
    return ok_response(
        "Autopilot check",
        {
            "tenant_id": tenant_id,
            "eligible": eligible,
            "confidence": confidence,
            "success_rate": round(success_rate, 2),
            "thresholds": {"confidence": 0.90, "success_rate": 0.80},
        },
    )