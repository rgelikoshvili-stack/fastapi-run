from app.api.db import get_db
import json


PROMOTION_SUPPORT_THRESHOLD = 3
PROMOTION_SUCCESS_THRESHOLD = 3
DEMOTION_FAILURE_THRESHOLD = 2


def _decide_pattern_status(support_count: int, success_count: int, failure_count: int) -> str:
    if failure_count >= DEMOTION_FAILURE_THRESHOLD:
        return "inactive"

    if (
        support_count >= PROMOTION_SUPPORT_THRESHOLD
        and success_count >= PROMOTION_SUCCESS_THRESHOLD
        and failure_count == 0
    ):
        return "active"

    return "candidate"


def correct_draft(draft_id: int, payload: dict, user: str = "human"):
    conn = get_db()
    cur = conn.cursor()

    try:
        # 1. წამოვიღოთ არსებული draft
        cur.execute("""
            SELECT id, description, partner, account_code, reason,
                   debit_account, credit_account, amount, classification_source
            FROM journal_drafts
            WHERE id = %s
        """, (draft_id,))
        row = cur.fetchone()

        if not row:
            return {
                "ok": False,
                "message": "Draft not found",
                "data": None,
                "error": {"code": "NOT_FOUND", "details": f"Draft {draft_id} not found"},
            }

        original = {
            "account_code": row[3],
            "reason": row[4],
            "debit_account": row[5],
            "credit_account": row[6],
        }

        final = {
            "account_code": payload.get("account_code", original["account_code"]),
            "reason": payload.get("reason", original["reason"]),
            "debit_account": payload.get("debit_account", original["debit_account"]),
            "credit_account": payload.get("credit_account", original["credit_account"]),
        }

        # 2. ვნახოთ რეალურად რა შეიცვალა
        changed_fields = []
        delta_parts = []

        for key in original:
            if original[key] != final[key]:
                changed_fields.append(key)
                delta_parts.append(f"{key}: {original[key]} -> {final[key]}")

        delta_summary = ", ".join(delta_parts) if delta_parts else "no_change"

        # 3. განვაახლოთ draft
        cur.execute("""
            UPDATE journal_drafts
            SET account_code = %s,
                reason = %s,
                debit_account = %s,
                credit_account = %s,
                status = 'approved',
                approved_by_mode = 'human_correction',
                updated_at = NOW()
            WHERE id = %s
        """, (
            final["account_code"],
            final["reason"],
            final["debit_account"],
            final["credit_account"],
            draft_id
        ))

        # 4. human review log
        cur.execute("""
            INSERT INTO human_reviews (
                case_id,
                review_action,
                final_payload,
                final_account_code,
                final_reason,
                correction_summary,
                reviewed_by,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id
        """, (
            draft_id,
            "correct",
            json.dumps(final),
            final["account_code"],
            final["reason"],
            delta_summary,
            user
        ))

        review_id = cur.fetchone()[0]

        # 5. learning delta log
        cur.execute("""
            INSERT INTO learning_deltas (
                case_id,
                review_id,
                original_payload,
                final_payload,
                changed_fields,
                delta_summary,
                learning_label,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            draft_id,
            review_id,
            json.dumps(original),
            json.dumps(final),
            json.dumps(changed_fields),
            delta_summary,
            "corrected_mapping"
        ))

        # 6. Pattern learning update
        description = row[1]
        partner = row[2]

        # აქ შეგიძლია description-based learning
        if description:
            pattern_type = "description_exact"
            pattern_value = description.strip().lower()

            cur.execute("""
                SELECT id, support_count, success_count, failure_count
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND pattern_value = %s
                LIMIT 1
            """, (pattern_type, pattern_value))
            existing = cur.fetchone()

            if existing:
                pattern_id, support_count, success_count, failure_count = existing

                new_support = int(support_count or 0) + 1
                new_success = int(success_count or 0) + 1
                new_failure = int(failure_count or 0)

                new_status = _decide_pattern_status(new_support, new_success, new_failure)

                cur.execute("""
                    UPDATE learning_patterns
                    SET account_code = %s,
                        reason = %s,
                        support_count = %s,
                        success_count = %s,
                        failure_count = %s,
                        status = %s,
                        source = 'human_correction',
                        last_seen_at = NOW(),
                        last_confirmed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                """, (
                    final["account_code"],
                    final["reason"],
                    new_support,
                    new_success,
                    new_failure,
                    new_status,
                    pattern_id
                ))
            else:
                new_support = 1
                new_success = 1
                new_failure = 0
                new_status = _decide_pattern_status(new_support, new_success, new_failure)

                cur.execute("""
                    INSERT INTO learning_patterns (
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW(), NOW())
                """, (
                    pattern_type,
                    pattern_value,
                    final["account_code"],
                    final["reason"],
                    0.90,
                    new_support,
                    new_success,
                    new_failure,
                    new_status,
                    "human_correction"
                ))

        # 7. სურვილის შემთხვევაში partner-based learning-იც
        if partner:
            pattern_type = "partner"
            pattern_value = partner.strip()

            cur.execute("""
                SELECT id, support_count, success_count, failure_count
                FROM learning_patterns
                WHERE pattern_type = %s
                  AND pattern_value = %s
                LIMIT 1
            """, (pattern_type, pattern_value))
            existing = cur.fetchone()

            if existing:
                pattern_id, support_count, success_count, failure_count = existing

                new_support = int(support_count or 0) + 1
                new_success = int(success_count or 0) + 1
                new_failure = int(failure_count or 0)

                new_status = _decide_pattern_status(new_support, new_success, new_failure)

                cur.execute("""
                    UPDATE learning_patterns
                    SET account_code = %s,
                        reason = %s,
                        support_count = %s,
                        success_count = %s,
                        failure_count = %s,
                        status = %s,
                        source = 'human_correction',
                        last_seen_at = NOW(),
                        last_confirmed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                """, (
                    final["account_code"],
                    final["reason"],
                    new_support,
                    new_success,
                    new_failure,
                    new_status,
                    pattern_id
                ))
            else:
                new_support = 1
                new_success = 1
                new_failure = 0
                new_status = _decide_pattern_status(new_support, new_success, new_failure)

                cur.execute("""
                    INSERT INTO learning_patterns (
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW(), NOW())
                """, (
                    pattern_type,
                    pattern_value,
                    final["account_code"],
                    final["reason"],
                    0.90,
                    new_support,
                    new_success,
                    new_failure,
                    new_status,
                    "human_correction"
                ))

        conn.commit()

        return {
            "ok": True,
            "message": "Draft corrected and learning updated",
            "data": {
                "draft_id": draft_id,
                "review_id": review_id,
                "changed_fields": changed_fields,
                "delta_summary": delta_summary
            },
            "error": None
        }

    except Exception as e:
        conn.rollback()
        return {
            "ok": False,
            "message": "Internal server error",
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "details": str(e)
            }
        }

    finally:
        cur.close()
        conn.close()