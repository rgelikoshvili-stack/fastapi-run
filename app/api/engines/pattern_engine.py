from datetime import datetime, timezone

from app.api.db import get_db


PROMOTION_SUPPORT_THRESHOLD = 3
PROMOTION_SUCCESS_THRESHOLD = 3
DEMOTION_FAILURE_THRESHOLD = 2

AUTOPILOT_SUPPORT_THRESHOLD = 5
AUTOPILOT_SUCCESS_THRESHOLD = 3
AUTOPILOT_CONFIDENCE_THRESHOLD = 0.85

AUTOPILOT_MAX_PATTERN_AGE_DAYS = 45
STALE_CANDIDATE_AFTER_DAYS = 90
STALE_INACTIVE_AFTER_DAYS = 120


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _normalized_sql_expr(column_name: str) -> str:
    return f"LOWER(REGEXP_REPLACE(TRIM(COALESCE({column_name}, '')), '\\s+', ' ', 'g'))"


def _safe_parse_dt(value) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def _days_since(value) -> int | None:
    dt = _safe_parse_dt(value)
    if dt is None:
        return None
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _is_pattern_stale(last_seen_at, max_days: int = AUTOPILOT_MAX_PATTERN_AGE_DAYS) -> bool:
    days = _days_since(last_seen_at)
    if days is None:
        return True
    return days > max_days


def _calculate_confidence(success_count, failure_count) -> float:
    success = float(success_count or 0)
    failure = float(failure_count or 0)
    total = success + failure

    if total <= 0:
        return 0.50

    return max(0.0, min(1.0, success / total))


def calculate_pattern_confidence(
    support_count: int,
    success_count: int,
    failure_count: int,
    last_seen_at=None,
) -> float:
    support_count = int(support_count or 0)
    success_count = int(success_count or 0)
    failure_count = int(failure_count or 0)

    total = max(1, success_count + failure_count)
    success_rate = success_count / total

    confidence = 0.50

    if support_count >= 1:
        confidence += min(0.20, support_count * 0.02)

    confidence += success_rate * 0.25

    confidence -= min(0.25, failure_count * 0.08)

    days = _days_since(last_seen_at)
    if days is not None:
        if days > AUTOPILOT_MAX_PATTERN_AGE_DAYS:
            confidence -= 0.05
        if days >= STALE_CANDIDATE_AFTER_DAYS:
            confidence -= 0.05
        if days >= STALE_INACTIVE_AFTER_DAYS:
            confidence -= 0.10

    confidence = max(0.05, min(0.99, confidence))
    return round(confidence, 4)


def _decide_pattern_status(
    support_count: int,
    success_count: int,
    failure_count: int,
    last_seen_at=None,
) -> str:
    if failure_count >= DEMOTION_FAILURE_THRESHOLD:
        return "inactive"

    days = _days_since(last_seen_at)

    if days is not None and days >= STALE_INACTIVE_AFTER_DAYS and failure_count > 0:
        return "inactive"

    if (
        support_count >= PROMOTION_SUPPORT_THRESHOLD
        and success_count >= PROMOTION_SUCCESS_THRESHOLD
        and failure_count == 0
    ):
        if days is not None and days >= STALE_CANDIDATE_AFTER_DAYS:
            return "candidate"
        return "active"

    return "candidate"


def is_pattern_autopilot_eligible(
    support_count: int,
    success_count: int,
    failure_count: int,
    last_seen_at=None,
    confidence_score: float | None = None,
) -> bool:
    if failure_count > 0:
        return False
    if support_count < AUTOPILOT_SUPPORT_THRESHOLD:
        return False
    if success_count < AUTOPILOT_SUCCESS_THRESHOLD:
        return False

    confidence = (
        float(confidence_score)
        if confidence_score is not None
        else calculate_pattern_confidence(
            support_count=support_count,
            success_count=success_count,
            failure_count=failure_count,
            last_seen_at=last_seen_at,
        )
    )
    if confidence < AUTOPILOT_CONFIDENCE_THRESHOLD:
        return False

    if _is_pattern_stale(last_seen_at, AUTOPILOT_MAX_PATTERN_AGE_DAYS):
        return False

    return True


def recalculate_pattern_state(
    support_count: int,
    success_count: int,
    failure_count: int,
    last_seen_at=None,
):
    status = _decide_pattern_status(
        support_count=support_count,
        success_count=success_count,
        failure_count=failure_count,
        last_seen_at=last_seen_at,
    )
    confidence = calculate_pattern_confidence(
        support_count=support_count,
        success_count=success_count,
        failure_count=failure_count,
        last_seen_at=last_seen_at,
    )
    autopilot_eligible = is_pattern_autopilot_eligible(
        support_count=support_count,
        success_count=success_count,
        failure_count=failure_count,
        last_seen_at=last_seen_at,
        confidence_score=confidence,
    )

    return {
        "status": status,
        "confidence_score": confidence,
        "autopilot_eligible": autopilot_eligible,
    }


def generate_patterns_from_feedback():
    """
    Legacy/backfill helper.
    არ უნდა იყოს primary learning path.
    Primary learning ახლა ხდება approve/reject/correct flows-ით.
    """
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                description_normalized,
                partner_normalized,
                final_account_code,
                final_reason
            FROM learning_feedback
            WHERE final_account_code IS NOT NULL
            """
        )

        rows = cur.fetchall()
        inserted = 0
        updated = 0

        for row in rows:
            description = _normalize(row[0])
            partner = (row[1] or "").strip()
            account_code = row[2]
            reason = row[3]

            if description:
                cur.execute(
                    f"""
                    SELECT id, support_count, success_count, failure_count, last_seen_at
                    FROM learning_patterns
                    WHERE pattern_type = %s
                      AND {_normalized_sql_expr("pattern_value")} = %s
                    LIMIT 1
                    """,
                    ("description_exact", description),
                )
                existing = cur.fetchone()

                if existing:
                    pattern_id, support_count, success_count, failure_count, last_seen_at = existing

                    support_count = int(support_count or 0) + 1
                    success_count = int(success_count or 0)
                    failure_count = int(failure_count or 0)

                    state = recalculate_pattern_state(
                        support_count=support_count,
                        success_count=success_count,
                        failure_count=failure_count,
                        last_seen_at=last_seen_at,
                    )

                    cur.execute(
                        """
                        UPDATE learning_patterns
                        SET
                            account_code = %s,
                            reason = %s,
                            confidence_score = %s,
                            autopilot_eligible = %s,
                            support_count = %s,
                            status = %s,
                            source = 'feedback_learning',
                            last_seen_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            account_code,
                            reason,
                            state["confidence_score"],
                            state["autopilot_eligible"],
                            support_count,
                            state["status"],
                            pattern_id,
                        ),
                    )
                    updated += 1
                else:
                    support_count = 1
                    success_count = 0
                    failure_count = 0

                    state = recalculate_pattern_state(
                        support_count=support_count,
                        success_count=success_count,
                        failure_count=failure_count,
                        last_seen_at=None,
                    )

                    cur.execute(
                        """
                        INSERT INTO learning_patterns
                        (
                            pattern_type,
                            pattern_value,
                            account_code,
                            reason,
                            confidence_score,
                            autopilot_eligible,
                            support_count,
                            success_count,
                            failure_count,
                            status,
                            source,
                            last_seen_at,
                            last_confirmed_at,
                            created_at,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NULL, NOW(), NOW())
                        """,
                        (
                            "description_exact",
                            description,
                            account_code,
                            reason,
                            state["confidence_score"],
                            state["autopilot_eligible"],
                            support_count,
                            success_count,
                            failure_count,
                            state["status"],
                            "feedback_learning",
                        ),
                    )
                    inserted += 1

            if partner:
                cur.execute(
                    """
                    SELECT id, support_count, success_count, failure_count, last_seen_at
                    FROM learning_patterns
                    WHERE pattern_type = %s
                      AND pattern_value = %s
                    LIMIT 1
                    """,
                    ("partner", partner),
                )
                existing = cur.fetchone()

                if existing:
                    pattern_id, support_count, success_count, failure_count, last_seen_at = existing

                    support_count = int(support_count or 0) + 1
                    success_count = int(success_count or 0)
                    failure_count = int(failure_count or 0)

                    state = recalculate_pattern_state(
                        support_count=support_count,
                        success_count=success_count,
                        failure_count=failure_count,
                        last_seen_at=last_seen_at,
                    )

                    cur.execute(
                        """
                        UPDATE learning_patterns
                        SET
                            account_code = %s,
                            reason = %s,
                            confidence_score = %s,
                            autopilot_eligible = %s,
                            support_count = %s,
                            status = %s,
                            source = 'feedback_learning',
                            last_seen_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            account_code,
                            reason,
                            state["confidence_score"],
                            state["autopilot_eligible"],
                            support_count,
                            state["status"],
                            pattern_id,
                        ),
                    )
                    updated += 1
                else:
                    support_count = 1
                    success_count = 0
                    failure_count = 0

                    state = recalculate_pattern_state(
                        support_count=support_count,
                        success_count=success_count,
                        failure_count=failure_count,
                        last_seen_at=None,
                    )

                    cur.execute(
                        """
                        INSERT INTO learning_patterns
                        (
                            pattern_type,
                            pattern_value,
                            account_code,
                            reason,
                            confidence_score,
                            autopilot_eligible,
                            support_count,
                            success_count,
                            failure_count,
                            status,
                            source,
                            last_seen_at,
                            last_confirmed_at,
                            created_at,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NULL, NOW(), NOW())
                        """,
                        (
                            "partner",
                            partner,
                            account_code,
                            reason,
                            state["confidence_score"],
                            state["autopilot_eligible"],
                            support_count,
                            success_count,
                            failure_count,
                            state["status"],
                            "feedback_learning",
                        ),
                    )
                    inserted += 1

        conn.commit()

        return {
            "patterns_inserted": inserted,
            "patterns_updated": updated,
            "feedback_rows_seen": len(rows),
        }

    finally:
        cur.close()
        conn.close()


def mark_pattern_success(
    pattern_type: str,
    pattern_value: str,
    account_code: str | None = None,
):
    conn = get_db()
    cur = conn.cursor()

    try:
        value = _normalize(pattern_value) if pattern_type == "description_exact" else (pattern_value or "").strip()
        if not value:
            return {"updated": 0}

        if pattern_type == "description_exact":
            compare_sql = _normalized_sql_expr("pattern_value")
        else:
            compare_sql = "pattern_value"

        if account_code:
            cur.execute(
                f"""
                SELECT id, support_count, success_count, failure_count, last_seen_at
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND {compare_sql} = %s
                  AND account_code = %s
                LIMIT 1
                """,
                (pattern_type, value, account_code),
            )
        else:
            cur.execute(
                f"""
                SELECT id, support_count, success_count, failure_count, last_seen_at
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND {compare_sql} = %s
                LIMIT 1
                """,
                (pattern_type, value),
            )

        row = cur.fetchone()
        if not row:
            return {"updated": 0}

        pattern_id, support_count, success_count, failure_count, _last_seen_at = row
        support_count = int(support_count or 0) + 1
        success_count = int(success_count or 0) + 1
        failure_count = int(failure_count or 0)

        state = recalculate_pattern_state(
            support_count=support_count,
            success_count=success_count,
            failure_count=failure_count,
            last_seen_at=datetime.now(timezone.utc),
        )

        cur.execute(
            """
            UPDATE learning_patterns
            SET
                success_count = %s,
                support_count = %s,
                confidence_score = %s,
                autopilot_eligible = %s,
                status = %s,
                last_confirmed_at = NOW(),
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                success_count,
                support_count,
                state["confidence_score"],
                state["autopilot_eligible"],
                state["status"],
                pattern_id,
            ),
        )

        conn.commit()
        return {"updated": cur.rowcount}

    finally:
        cur.close()
        conn.close()


def mark_pattern_failure(
    pattern_type: str,
    pattern_value: str,
    account_code: str | None = None,
):
    conn = get_db()
    cur = conn.cursor()

    try:
        value = _normalize(pattern_value) if pattern_type == "description_exact" else (pattern_value or "").strip()
        if not value:
            return {"updated": 0}

        if pattern_type == "description_exact":
            compare_sql = _normalized_sql_expr("pattern_value")
        else:
            compare_sql = "pattern_value"

        if account_code:
            cur.execute(
                f"""
                SELECT id, support_count, success_count, failure_count, last_seen_at
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND {compare_sql} = %s
                  AND account_code = %s
                LIMIT 1
                """,
                (pattern_type, value, account_code),
            )
        else:
            cur.execute(
                f"""
                SELECT id, support_count, success_count, failure_count, last_seen_at
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND {compare_sql} = %s
                LIMIT 1
                """,
                (pattern_type, value),
            )

        row = cur.fetchone()
        if not row:
            return {"updated": 0}

        pattern_id, support_count, success_count, failure_count, last_seen_at = row
        support_count = int(support_count or 0) + 1
        success_count = int(success_count or 0)
        failure_count = int(failure_count or 0) + 1

        state = recalculate_pattern_state(
            support_count=support_count,
            success_count=success_count,
            failure_count=failure_count,
            last_seen_at=last_seen_at,
        )

        cur.execute(
            """
            UPDATE learning_patterns
            SET
                failure_count = %s,
                support_count = %s,
                confidence_score = %s,
                autopilot_eligible = %s,
                status = %s,
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                failure_count,
                support_count,
                state["confidence_score"],
                state["autopilot_eligible"],
                state["status"],
                pattern_id,
            ),
        )

        conn.commit()
        return {"updated": cur.rowcount}

    finally:
        cur.close()
        conn.close()