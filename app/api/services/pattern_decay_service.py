from app.api.db import get_db
from app.api.engines.pattern_engine import _decide_pattern_status


def run_pattern_decay(limit: int = 500):
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                id,
                pattern_type,
                pattern_value,
                support_count,
                success_count,
                failure_count,
                status,
                last_seen_at
            FROM learning_patterns
            ORDER BY updated_at ASC NULLS FIRST, id ASC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

        checked = 0
        changed = 0
        to_candidate = 0
        to_inactive = 0

        for row in rows:
            (
                pattern_id,
                pattern_type,
                pattern_value,
                support_count,
                success_count,
                failure_count,
                old_status,
                last_seen_at,
            ) = row

            new_status = _decide_pattern_status(
                int(support_count or 0),
                int(success_count or 0),
                int(failure_count or 0),
                last_seen_at=last_seen_at,
            )

            checked += 1

            if new_status != old_status:
                cur.execute(
                    """
                    UPDATE learning_patterns
                    SET
                        status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_status, pattern_id),
                )
                changed += 1

                if new_status == "candidate":
                    to_candidate += 1
                elif new_status == "inactive":
                    to_inactive += 1

        conn.commit()

        return {
            "checked": checked,
            "changed": changed,
            "to_candidate": to_candidate,
            "to_inactive": to_inactive,
        }

    finally:
        cur.close()
        conn.close()


def get_pattern_health_summary():
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_patterns,
                COUNT(*) FILTER (WHERE status = 'active') AS active_patterns,
                COUNT(*) FILTER (WHERE status = 'candidate') AS candidate_patterns,
                COUNT(*) FILTER (WHERE status = 'inactive') AS inactive_patterns,
                COUNT(*) FILTER (
                    WHERE status = 'active'
                      AND failure_count = 0
                      AND support_count >= 5
                      AND success_count >= 3
                      AND last_seen_at >= NOW() - INTERVAL '45 days'
                ) AS autopilot_eligible_patterns,
                COUNT(*) FILTER (
                    WHERE last_seen_at IS NULL
                       OR last_seen_at < NOW() - INTERVAL '45 days'
                ) AS stale_patterns
            FROM learning_patterns
            """
        )
        row = cur.fetchone()

        return {
            "total_patterns": int(row[0] or 0),
            "active_patterns": int(row[1] or 0),
            "candidate_patterns": int(row[2] or 0),
            "inactive_patterns": int(row[3] or 0),
            "autopilot_eligible_patterns": int(row[4] or 0),
            "stale_patterns": int(row[5] or 0),
        }

    finally:
        cur.close()
        conn.close()