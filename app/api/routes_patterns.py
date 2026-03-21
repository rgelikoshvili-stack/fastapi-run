from fastapi import APIRouter
from app.api.db import get_db
from app.api.services.pattern_decay_service import run_pattern_decay

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.get("/learning-health")
def learning_health():
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE status = 'candidate') AS candidate_count,
                COUNT(*) FILTER (WHERE status = 'inactive') AS inactive_count,
                COUNT(*) FILTER (
                    WHERE status = 'active'
                      AND last_seen_at IS NOT NULL
                      AND last_seen_at < NOW() - INTERVAL '45 days'
                ) AS stale_active_count,
                COUNT(*) FILTER (
                    WHERE status = 'active'
                      AND success_count >= 3
                      AND failure_count = 0
                      AND support_count >= 5
                      AND last_seen_at IS NOT NULL
                      AND last_seen_at >= NOW() - INTERVAL '45 days'
                ) AS autopilot_ready_count
            FROM learning_patterns
            """
        )
        row = cur.fetchone()

        return {
            "ok": True,
            "data": {
                "total_patterns": row[0] or 0,
                "active_patterns": row[1] or 0,
                "candidate_patterns": row[2] or 0,
                "inactive_patterns": row[3] or 0,
                "stale_active_patterns": row[4] or 0,
                "autopilot_ready_patterns": row[5] or 0,
            },
        }
    finally:
        cur.close()
        conn.close()


@router.post("/decay/run")
def decay_run():
    result = run_pattern_decay()
    return {
        "ok": True,
        "data": result,
    }