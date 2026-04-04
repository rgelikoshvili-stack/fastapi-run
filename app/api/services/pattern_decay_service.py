from app.api.db import get_db
from app.api.engines.pattern_engine import recalculate_pattern_state


def _get_decay_threshold_days(usage_count: int) -> int:
    """usage_count-ზე დამოკიდებული decay სიჩქარე"""
    if usage_count >= 50:
        return 180  # ძალიან ხშირი → ნელი decay
    if usage_count >= 20:
        return 90   # ხშირი → საშუალო decay
    if usage_count >= 5:
        return 60   # საშუალო → ნორმალური decay
    return 45       # იშვიათი → სწრაფი decay


def run_pattern_decay(limit: int = 500, tenant_id: str = "default"):
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                id,
                pattern_type,
                pattern_value,
                account_code,
                support_count,
                success_count,
                failure_count,
                status,
                confidence_score,
                COALESCE(autopilot_eligible, FALSE),
                last_seen_at,
                COALESCE(usage_count, 0)
            FROM learning_patterns
            WHERE tenant_id = %s
            ORDER BY updated_at ASC NULLS FIRST, id ASC
            LIMIT %s
            """,
            (tenant_id, limit),
        )
        rows = cur.fetchall()

        checked = 0
        changed = 0
        to_candidate = 0
        to_inactive = 0
        to_active = 0
        autopilot_true = 0
        autopilot_false = 0
        smart_decayed = 0

        details = []

        for row in rows:
            (
                pattern_id,
                pattern_type,
                pattern_value,
                account_code,
                support_count,
                success_count,
                failure_count,
                old_status,
                old_confidence,
                old_autopilot,
                last_seen_at,
                usage_count,
            ) = row

            support_count = int(support_count or 0)
            success_count = int(success_count or 0)
            failure_count = int(failure_count or 0)
            usage_count = int(usage_count or 0)
            old_confidence = float(old_confidence or 0)
            old_autopilot = bool(old_autopilot)

            # Smart Decay threshold — usage_count-ზე დამოკიდებული
            decay_threshold = _get_decay_threshold_days(usage_count)

            state = recalculate_pattern_state(
                support_count=support_count,
                success_count=success_count,
                failure_count=failure_count,
                last_seen_at=last_seen_at,
            )

            new_status = state["status"]
            new_confidence = state["confidence_score"]
            new_autopilot = state["autopilot_eligible"]

            # Smart Decay: თუ last_seen_at > threshold და status active/candidate
            if old_status in ("active", "candidate") and last_seen_at is not None:
                cur.execute(
                    """
                    SELECT
                        EXTRACT(DAY FROM NOW() - %s::timestamp) AS days_ago
                    """,
                    (last_seen_at,),
                )
                age_row = cur.fetchone()
                days_ago = int(age_row[0] or 0) if age_row else 0

                if days_ago > decay_threshold:
                    new_status = "inactive"
                    new_confidence = max(0.05, new_confidence - 0.15)
                    new_autopilot = False
                    smart_decayed += 1

            checked += 1

            is_changed = (
                new_status != old_status
                or round(new_confidence, 4) != round(old_confidence, 4)
                or new_autopilot != old_autopilot
            )

            if is_changed:
                cur.execute(
                    """
                    UPDATE learning_patterns
                    SET
                        status = %s,
                        confidence_score = %s,
                        autopilot_eligible = %s,
                        updated_at = NOW()
                    WHERE id = %s
                      AND tenant_id = %s
                    """,
                    (new_status, new_confidence, new_autopilot, pattern_id, tenant_id),
                )
                changed += 1

                if new_status == "candidate":
                    to_candidate += 1
                elif new_status == "inactive":
                    to_inactive += 1
                elif new_status == "active":
                    to_active += 1

                if new_autopilot:
                    autopilot_true += 1
                else:
                    autopilot_false += 1

                details.append({
                    "tenant_id": tenant_id,
                    "id": pattern_id,
                    "pattern_type": pattern_type,
                    "pattern_value": pattern_value,
                    "account_code": account_code,
                    "old_status": old_status,
                    "new_status": new_status,
                    "old_confidence": old_confidence,
                    "new_confidence": new_confidence,
                    "old_autopilot": old_autopilot,
                    "new_autopilot": new_autopilot,
                    "usage_count": usage_count,
                    "decay_threshold_days": decay_threshold,
                })

        conn.commit()

        return {
            "ok": True,
            "tenant_id": tenant_id,
            "checked": checked,
            "changed": changed,
            "to_active": to_active,
            "to_candidate": to_candidate,
            "to_inactive": to_inactive,
            "smart_decayed": smart_decayed,
            "autopilot_true": autopilot_true,
            "autopilot_false": autopilot_false,
            "details": details[:50],
        }

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "tenant_id": tenant_id,
            "error": str(e),
        }

    finally:
        cur.close()
        conn.close()


def get_pattern_health_summary(tenant_id: str = "default"):
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
                    WHERE COALESCE(autopilot_eligible, FALSE) = TRUE
                ) AS autopilot_eligible_patterns,
                COUNT(*) FILTER (
                    WHERE last_seen_at IS NULL
                       OR last_seen_at < NOW() - INTERVAL '45 days'
                ) AS stale_patterns,
                AVG(COALESCE(usage_count, 0)) AS avg_usage_count,
                MAX(COALESCE(usage_count, 0)) AS max_usage_count
            FROM learning_patterns
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        row = cur.fetchone()

        return {
            "tenant_id": tenant_id,
            "total_patterns": int(row[0] or 0),
            "active_patterns": int(row[1] or 0),
            "candidate_patterns": int(row[2] or 0),
            "inactive_patterns": int(row[3] or 0),
            "autopilot_eligible_patterns": int(row[4] or 0),
            "stale_patterns": int(row[5] or 0),
            "avg_usage_count": round(float(row[6] or 0), 1),
            "max_usage_count": int(row[7] or 0),
            "decay_thresholds": {
                "usage_lt_5": "45 days",
                "usage_5_to_20": "60 days",
                "usage_20_to_50": "90 days",
                "usage_gt_50": "180 days",
            },
        }

    finally:
        cur.close()
        conn.close()