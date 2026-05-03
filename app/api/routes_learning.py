from fastapi import APIRouter, Request
import json

from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
from app.api.services.learning_service import get_learning_health_service
from app.api.services.pattern_decay_service import run_pattern_decay

router = APIRouter(prefix="/learning", tags=["learning"])

_CREATE_FEEDBACK = """
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
"""

_CREATE_ASYNC_QUEUE = """
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
"""

_ALTER_FEEDBACK_COLS = [
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default'",
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS run_id VARCHAR(100)",
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS feedback_type VARCHAR(50)",
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS original_account VARCHAR(20)",
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS corrected_account VARCHAR(20)",
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS original_amount FLOAT",
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS user_comment TEXT",
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
]

_ALTER_QUEUE_COLS = [
    "ALTER TABLE async_queue ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default'",
    "ALTER TABLE async_queue ADD COLUMN IF NOT EXISTS task_type VARCHAR(50)",
    "ALTER TABLE async_queue ADD COLUMN IF NOT EXISTS payload JSONB",
    "ALTER TABLE async_queue ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'PENDING'",
    "ALTER TABLE async_queue ADD COLUMN IF NOT EXISTS result JSONB",
    "ALTER TABLE async_queue ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
    "ALTER TABLE async_queue ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP",
]


async def _ensure_tables(conn):
    await conn.execute(_CREATE_FEEDBACK)
    await conn.execute(_CREATE_ASYNC_QUEUE)
    for stmt in _ALTER_FEEDBACK_COLS + _ALTER_QUEUE_COLS:
        try:
            await conn.execute(stmt)
        except Exception:
            pass


@router.post("/feedback")
async def submit_feedback(request: Request, payload: dict):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            row = await conn.fetchrow(_q("""
                INSERT INTO learning_feedback
                (tenant_id, run_id, feedback_type, original_account, corrected_account,
                 original_amount, description, user_comment)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """), tenant_id,
                payload.get("run_id"),
                payload.get("feedback_type", "CORRECTION"),
                payload.get("original_account") or payload.get("account_code"),
                payload.get("corrected_account") or payload.get("corrected_account_code"),
                payload.get("amount", 0),
                payload.get("description", ""),
                payload.get("comment", ""))
        return ok_response("Feedback saved", {"tenant_id": tenant_id, "id": row["id"]})
    except Exception as e:
        return error_response("Feedback save failed", "LEARNING_FEEDBACK_SAVE_ERROR", str(e))


@router.get("/patterns")
async def get_learned_patterns(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            rows = [dict(r) for r in await conn.fetch(_q("""
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
            """), tenant_id)]
        return ok_response("Learned patterns", {
            "tenant_id": tenant_id,
            "items": rows,
            "count": len(rows),
        })
    except Exception as e:
        return error_response("Learning patterns failed", "LEARNING_PATTERNS_ERROR", str(e))


@router.post("/queue/add")
async def queue_add(request: Request, payload: dict):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            row = await conn.fetchrow(_q("""
                INSERT INTO async_queue (tenant_id, task_type, payload, status)
                VALUES (%s, %s, %s, 'PENDING')
                RETURNING id
            """), tenant_id, payload.get("task_type", "ANALYZE"), json.dumps(payload))
        return ok_response("Queue task added", {
            "tenant_id": tenant_id, "task_id": row["id"], "status": "PENDING"
        })
    except Exception as e:
        return error_response("Queue add failed", "LEARNING_QUEUE_ADD_ERROR", str(e))


@router.get("/queue/status")
async def queue_status(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            breakdown_rows = await conn.fetch(_q("""
                SELECT status, COUNT(*) AS count
                FROM async_queue WHERE tenant_id = %s GROUP BY status
            """), tenant_id)
            breakdown = {r["status"]: r["count"] for r in breakdown_rows}

            recent = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, tenant_id, task_type, status, created_at, processed_at
                FROM async_queue WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 10
            """), tenant_id)]

        return ok_response("Queue status", {
            "tenant_id": tenant_id,
            "queue_breakdown": breakdown,
            "recent_tasks": recent,
        })
    except Exception as e:
        return error_response("Queue status failed", "LEARNING_QUEUE_STATUS_ERROR", str(e))


@router.get("/stats")
async def learning_stats(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            total = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM learning_feedback WHERE tenant_id = %s"
            ), tenant_id) or 0
            type_rows = await conn.fetch(_q("""
                SELECT feedback_type, COUNT(*) AS count
                FROM learning_feedback WHERE tenant_id = %s GROUP BY feedback_type
            """), tenant_id)
            by_type = {r["feedback_type"]: r["count"] for r in type_rows}

        return ok_response("Learning stats", {
            "tenant_id": tenant_id,
            "total_feedback": total,
            "by_type": by_type,
            "learning_active": True,
        })
    except Exception as e:
        return error_response("Learning stats failed", "LEARNING_STATS_ERROR", str(e))


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
async def learning_patterns_top(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            await _ensure_tables(conn)
            top_rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT
                    id, tenant_id, pattern_type, pattern_value, account_code, reason,
                    confidence_score, support_count, success_count, failure_count, status,
                    COALESCE(autopilot_eligible, FALSE) AS autopilot_eligible,
                    last_seen_at, last_confirmed_at,
                    CASE WHEN last_seen_at IS NULL THEN NULL
                         ELSE EXTRACT(DAY FROM (NOW() - last_seen_at)) END AS days_since_seen
                FROM learning_patterns
                WHERE tenant_id = %s
                ORDER BY confidence_score DESC NULLS LAST,
                         success_count DESC NULLS LAST,
                         support_count DESC NULLS LAST
                LIMIT 10
            """), tenant_id)]

            weak_rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT
                    id, tenant_id, pattern_type, pattern_value, account_code, reason,
                    confidence_score, support_count, success_count, failure_count, status,
                    COALESCE(autopilot_eligible, FALSE) AS autopilot_eligible,
                    last_seen_at, last_confirmed_at,
                    CASE WHEN last_seen_at IS NULL THEN NULL
                         ELSE EXTRACT(DAY FROM (NOW() - last_seen_at)) END AS days_since_seen
                FROM learning_patterns
                WHERE tenant_id = %s
                ORDER BY failure_count DESC NULLS LAST,
                         confidence_score ASC NULLS LAST,
                         support_count DESC NULLS LAST
                LIMIT 10
            """), tenant_id)]

        return ok_response("Top & Weak patterns", {
            "tenant_id": tenant_id,
            "top_patterns": top_rows,
            "weak_patterns": weak_rows,
        })
    except Exception as e:
        return error_response("Patterns top failed", "LEARNING_PATTERNS_TOP_ERROR", str(e))


@router.post("/decay")
def learning_decay(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = run_pattern_decay(tenant_id=tenant_id)
    if result.get("ok"):
        return ok_response("Decay applied", result)
    return error_response("Pattern decay failed", "LEARNING_DECAY_ERROR", result.get("error", "unknown"))


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
    return ok_response("Autopilot check", {
        "tenant_id": tenant_id,
        "eligible": eligible,
        "confidence": confidence,
        "success_rate": round(success_rate, 2),
        "thresholds": {"confidence": 0.90, "success_rate": 0.80},
    })


@router.patch("/patterns/{pattern_id}")
async def update_pattern(pattern_id: int, payload: dict, request: Request):
    """Human correction of a learned pattern (account_code, reason, status)."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            async with conn.transaction():
                exists = await conn.fetchrow(_q(
                    "SELECT id FROM learning_patterns WHERE id = %s AND tenant_id = %s FOR UPDATE"
                ), pattern_id, tenant_id)
                if not exists:
                    return error_response("Pattern not found", "NOT_FOUND", f"pattern {pattern_id}")

                allowed = {"account_code", "reason", "status", "confidence_score"}
                updates = {k: v for k, v in payload.items() if k in allowed}
                if not updates:
                    return error_response("No valid fields", "NO_FIELDS",
                                         "Send account_code, reason, status, or confidence_score")

                set_clause = ", ".join(f"{k} = %s" for k in updates)
                values = list(updates.values()) + [pattern_id, tenant_id]
                row = await conn.fetchrow(_q(
                    f"UPDATE learning_patterns SET {set_clause}, last_confirmed_at = NOW() "
                    f"WHERE id = %s AND tenant_id = %s RETURNING *"
                ), *values)
        return ok_response("Pattern updated", {"pattern": dict(row)})
    except Exception as e:
        return error_response("Update failed", "UPDATE_ERROR", str(e))


@router.delete("/patterns/{pattern_id}")
async def delete_pattern(pattern_id: int, request: Request):
    """Soft-delete a pattern (sets status = 'archived')."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            st = await conn.execute(_q(
                "UPDATE learning_patterns SET status = 'archived', last_confirmed_at = NOW() "
                "WHERE id = %s AND tenant_id = %s AND status != 'archived'"
            ), pattern_id, tenant_id)
            if int(st.split()[-1]) == 0:
                return error_response("Not found or already archived", "NOT_FOUND", f"pattern {pattern_id}")
        return ok_response("Pattern archived", {"pattern_id": pattern_id})
    except Exception as e:
        return error_response("Delete failed", "DELETE_ERROR", str(e))
