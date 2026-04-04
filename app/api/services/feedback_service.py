from app.api.db import get_db


def save_feedback(
    draft_id,
    tx_fingerprint,
    source_type,
    description_raw,
    description_normalized,
    partner_raw,
    partner_normalized,
    amount,
    original_account_code,
    original_reason,
    original_confidence,
    final_account_code,
    final_reason,
    feedback_type,
    corrected_by=None,
    notes=None,
    tenant_id: str = "default",
):
    conn = get_db()
    cur = conn.cursor()

    try:
        # duplicate-safe by draft_id + tenant_id
        cur.execute(
            """
            SELECT id
            FROM learning_feedback
            WHERE draft_id = %s
              AND tenant_id = %s
              AND feedback_type = %s
            LIMIT 1
            """,
            (draft_id, tenant_id, feedback_type),
        )
        existing = cur.fetchone()

        if existing:
            return {
                "status": "duplicate_skipped",
                "feedback_id": existing[0],
                "tenant_id": tenant_id,
            }

        cur.execute(
            """
            INSERT INTO learning_feedback (
                tenant_id,
                draft_id,
                tx_fingerprint,
                source_type,
                description_raw,
                description_normalized,
                partner_raw,
                partner_normalized,
                amount,
                original_account_code,
                original_reason,
                original_confidence,
                final_account_code,
                final_reason,
                feedback_type,
                corrected_by,
                notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id,
                draft_id,
                tx_fingerprint,
                source_type,
                description_raw,
                description_normalized,
                partner_raw,
                partner_normalized,
                amount,
                original_account_code,
                original_reason,
                original_confidence,
                final_account_code,
                final_reason,
                feedback_type,
                corrected_by,
                notes,
            ),
        )

        feedback_id = cur.fetchone()[0]
        conn.commit()

        return {
            "status": "feedback_saved",
            "feedback_id": feedback_id,
            "tenant_id": tenant_id,
        }

    finally:
        cur.close()
        conn.close()