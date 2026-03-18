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
):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO learning_feedback (
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
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
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

    conn.commit()
    cur.close()
    conn.close()

    return {"status": "feedback_saved"}