from app.api.db import get_db


PROMOTION_SUPPORT_THRESHOLD = 3
PROMOTION_SUCCESS_THRESHOLD = 3
DEMOTION_FAILURE_THRESHOLD = 2
AUTOPILOT_SUPPORT_THRESHOLD = 5
AUTOPILOT_SUCCESS_THRESHOLD = 3


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _decide_pattern_status(
    support_count: int,
    success_count: int,
    failure_count: int,
) -> str:
    if failure_count >= DEMOTION_FAILURE_THRESHOLD:
        return "inactive"

    if (
        support_count >= PROMOTION_SUPPORT_THRESHOLD
        and success_count >= PROMOTION_SUCCESS_THRESHOLD
        and failure_count == 0
    ):
        return "active"

    return "candidate"


def is_pattern_autopilot_eligible(
    support_count: int,
    success_count: int,
    failure_count: int,
) -> bool:
    if failure_count > 0:
        return False
    if support_count < AUTOPILOT_SUPPORT_THRESHOLD:
        return False
    if success_count < AUTOPILOT_SUCCESS_THRESHOLD:
        return False
    return True


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
                    """
                    SELECT id, support_count, success_count, failure_count
                    FROM learning_patterns
                    WHERE pattern_type = %s
                      AND pattern_value = %s
                    LIMIT 1
                    """,
                    ("description_exact", description),
                )
                existing = cur.fetchone()

                if existing:
                    pattern_id, support_count, success_count, failure_count = existing

                    support_count = int(support_count or 0) + 1
                    success_count = int(success_count or 0)
                    failure_count = int(failure_count or 0)
                    status = _decide_pattern_status(support_count, success_count, failure_count)

                    cur.execute(
                        """
                        UPDATE learning_patterns
                        SET
                            account_code = %s,
                            reason = %s,
                            support_count = %s,
                            status = %s,
                            source = 'feedback_learning',
                            last_seen_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (account_code, reason, support_count, status, pattern_id),
                    )
                    updated += 1
                else:
                    support_count = 1
                    success_count = 0
                    failure_count = 0
                    status = _decide_pattern_status(support_count, success_count, failure_count)

                    cur.execute(
                        """
                        INSERT INTO learning_patterns
                        (
                            pattern_type,
                            pattern_value,
                            account_code,
                            reason,
                            confidence_score,
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
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NULL, NOW(), NOW())
                        """,
                        (
                            "description_exact",
                            description,
                            account_code,
                            reason,
                            0.90,
                            support_count,
                            success_count,
                            failure_count,
                            status,
                            "feedback_learning",
                        ),
                    )
                    inserted += 1

            if partner:
                cur.execute(
                    """
                    SELECT id, support_count, success_count, failure_count
                    FROM learning_patterns
                    WHERE pattern_type = %s
                      AND pattern_value = %s
                    LIMIT 1
                    """,
                    ("partner", partner),
                )
                existing = cur.fetchone()

                if existing:
                    pattern_id, support_count, success_count, failure_count = existing

                    support_count = int(support_count or 0) + 1
                    success_count = int(success_count or 0)
                    failure_count = int(failure_count or 0)
                    status = _decide_pattern_status(support_count, success_count, failure_count)

                    cur.execute(
                        """
                        UPDATE learning_patterns
                        SET
                            account_code = %s,
                            reason = %s,
                            support_count = %s,
                            status = %s,
                            source = 'feedback_learning',
                            last_seen_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (account_code, reason, support_count, status, pattern_id),
                    )
                    updated += 1
                else:
                    support_count = 1
                    success_count = 0
                    failure_count = 0
                    status = _decide_pattern_status(support_count, success_count, failure_count)

                    cur.execute(
                        """
                        INSERT INTO learning_patterns
                        (
                            pattern_type,
                            pattern_value,
                            account_code,
                            reason,
                            confidence_score,
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
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NULL, NOW(), NOW())
                        """,
                        (
                            "partner",
                            partner,
                            account_code,
                            reason,
                            0.90,
                            support_count,
                            success_count,
                            failure_count,
                            status,
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

        if account_code:
            cur.execute(
                """
                SELECT id, support_count, success_count, failure_count
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND pattern_value = %s
                  AND account_code = %s
                LIMIT 1
                """,
                (pattern_type, value, account_code),
            )
        else:
            cur.execute(
                """
                SELECT id, support_count, success_count, failure_count
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND pattern_value = %s
                LIMIT 1
                """,
                (pattern_type, value),
            )

        row = cur.fetchone()
        if not row:
            return {"updated": 0}

        pattern_id, support_count, success_count, failure_count = row
        support_count = int(support_count or 0)
        success_count = int(success_count or 0) + 1
        failure_count = int(failure_count or 0)
        status = _decide_pattern_status(support_count, success_count, failure_count)

        cur.execute(
            """
            UPDATE learning_patterns
            SET
                success_count = %s,
                status = %s,
                last_confirmed_at = NOW(),
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (success_count, status, pattern_id),
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

        if account_code:
            cur.execute(
                """
                SELECT id, support_count, success_count, failure_count
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND pattern_value = %s
                  AND account_code = %s
                LIMIT 1
                """,
                (pattern_type, value, account_code),
            )
        else:
            cur.execute(
                """
                SELECT id, support_count, success_count, failure_count
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND pattern_value = %s
                LIMIT 1
                """,
                (pattern_type, value),
            )

        row = cur.fetchone()
        if not row:
            return {"updated": 0}

        pattern_id, support_count, success_count, failure_count = row
        support_count = int(support_count or 0)
        success_count = int(success_count or 0)
        failure_count = int(failure_count or 0) + 1
        status = _decide_pattern_status(support_count, success_count, failure_count)

        cur.execute(
            """
            UPDATE learning_patterns
            SET
                failure_count = %s,
                status = %s,
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (failure_count, status, pattern_id),
        )

        conn.commit()
        return {"updated": cur.rowcount}

    finally:
        cur.close()
        conn.close()