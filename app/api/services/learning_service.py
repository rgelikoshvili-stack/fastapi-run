import psycopg2.extras

from app.api.db import get_db
from app.api.audit_service import log_event
from app.api.services.feedback_service import save_feedback
from app.api.services.transaction_memory_service import save_transaction_memory
from app.api.services.erp_memory_service import upsert_erp_posting_memory
from app.api.engines.pattern_engine import (
    generate_patterns_from_feedback,
    mark_pattern_success,
    mark_pattern_failure,
)


PATTERN_SOURCES = {
    "pattern_active",
    "pattern_active_fuzzy",
    "pattern_candidate",
    "pattern_candidate_fuzzy",
}


def _feedback_exists(cur, draft_id: int, feedback_type: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM learning_feedback
        WHERE run_id = %s
          AND feedback_type = %s
        LIMIT 1
        """,
        (f"draft:{draft_id}", feedback_type),
    )
    return cur.fetchone() is not None


def _get_pattern_value_for_draft(draft: dict):
    matched_on = draft.get("pattern_matched_on")

    if matched_on in ("description_exact", "description_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("description")

    if matched_on in ("partner_exact", "partner_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("partner")

    return None


def _mark_success_for_draft(draft: dict):
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value or not account_code:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_success("description_exact", pattern_value, account_code)
    if matched_on == "partner_exact":
        return mark_pattern_success("partner", pattern_value, account_code)
    if matched_on == "description_fuzzy":
        return mark_pattern_success("description_exact", pattern_value, account_code)
    if matched_on == "partner_fuzzy":
        return mark_pattern_success("partner", pattern_value, account_code)

    return {"updated": 0}


def _mark_failure_for_draft(draft: dict):
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value or not account_code:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_failure("description_exact", pattern_value, account_code)
    if matched_on == "partner_exact":
        return mark_pattern_failure("partner", pattern_value, account_code)
    if matched_on == "description_fuzzy":
        return mark_pattern_failure("description_exact", pattern_value, account_code)
    if matched_on == "partner_fuzzy":
        return mark_pattern_failure("partner", pattern_value, account_code)

    return {"updated": 0}


def _save_erp_memory_from_draft(draft: dict, account_code: str):
    try:
        debit_account = draft.get("debit_account")
        credit_account = draft.get("credit_account")
        direction = None

        if credit_account == account_code:
            direction = "in"
        elif debit_account == account_code:
            direction = "out"

        return upsert_erp_posting_memory(
            source_system=draft.get("source_type") or "manual",
            external_entry_id=str(draft.get("id")),
            external_doc_id=None,
            doc_type=draft.get("source_type") or "manual",
            description=draft.get("description"),
            partner=draft.get("partner"),
            amount=draft.get("amount"),
            currency="GEL",
            debit_account=debit_account,
            credit_account=credit_account,
            account_code=account_code,
            direction=direction,
            posting_date=str(draft.get("date")) if draft.get("date") is not None else None,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}


def apply_approve_learning(draft: dict, approved_by_mode: str = "manual_review"):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    memory_result = {"ok": False}
    erp_memory_result = {"ok": False}
    pattern_update_result = {"updated": 0}
    duplicate_skipped = False

    try:
        if _feedback_exists(cur, draft["id"], "approve"):
            duplicate_skipped = True
        else:
            save_feedback(
                draft_id=draft.get("id"),
                tx_fingerprint=draft.get("tx_fingerprint"),
                source_type=draft.get("source_type"),
                description_raw=draft.get("description"),
                description_normalized=draft.get("normalized_description") or draft.get("description"),
                partner_raw=draft.get("partner"),
                partner_normalized=draft.get("partner"),
                amount=draft.get("amount"),
                original_account_code=draft.get("account_code"),
                original_reason=draft.get("reason"),
                original_confidence=draft.get("confidence"),
                final_account_code=draft.get("account_code"),
                final_reason=draft.get("reason"),
                feedback_type="approve",
                corrected_by=approved_by_mode,
                notes=f"run_id=draft:{draft.get('id')}",
            )

            memory_result = save_transaction_memory(
                draft.get("description"),
                draft.get("partner"),
                draft.get("amount"),
                draft.get("account_code"),
            )

            erp_memory_result = _save_erp_memory_from_draft(
                draft,
                draft.get("account_code"),
            )

            generate_patterns_from_feedback()

        conn.commit()

    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

    if draft.get("classification_source") in PATTERN_SOURCES and not duplicate_skipped:
        pattern_update_result = _mark_success_for_draft(draft)

    log_event(
        "draft_approved_learning_applied",
        {
            "draft_id": draft.get("id"),
            "duplicate_skipped": duplicate_skipped,
            "classification_source": draft.get("classification_source"),
            "pattern_update_result": pattern_update_result,
            "memory_saved": bool(memory_result.get("ok")),
            "memory_result": memory_result,
            "erp_memory_saved": bool(erp_memory_result.get("ok")),
            "erp_memory_result": erp_memory_result,
        },
    )

    return {
        "ok": True,
        "duplicate_skipped": duplicate_skipped,
        "pattern_update_result": pattern_update_result,
        "memory_result": memory_result,
        "erp_memory_result": erp_memory_result,
    }


def apply_reject_learning(draft: dict, reason: str = ""):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    pattern_update_result = {"updated": 0}
    duplicate_skipped = False

    try:
        if _feedback_exists(cur, draft["id"], "reject"):
            duplicate_skipped = True
        else:
            save_feedback(
                draft_id=draft.get("id"),
                tx_fingerprint=draft.get("tx_fingerprint"),
                source_type=draft.get("source_type"),
                description_raw=draft.get("description"),
                description_normalized=draft.get("normalized_description") or draft.get("description"),
                partner_raw=draft.get("partner"),
                partner_normalized=draft.get("partner"),
                amount=draft.get("amount"),
                original_account_code=draft.get("account_code"),
                original_reason=draft.get("reason"),
                original_confidence=draft.get("confidence"),
                final_account_code=None,
                final_reason=None,
                feedback_type="reject",
                corrected_by="manual_review",
                notes=f"run_id=draft:{draft.get('id')}; reason={reason}",
            )

            generate_patterns_from_feedback()

        conn.commit()

    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

    if draft.get("classification_source") in PATTERN_SOURCES and not duplicate_skipped:
        pattern_update_result = _mark_failure_for_draft(draft)

    log_event(
        "draft_rejected_learning_applied",
        {
            "draft_id": draft.get("id"),
            "reason": reason,
            "duplicate_skipped": duplicate_skipped,
            "classification_source": draft.get("classification_source"),
            "pattern_update_result": pattern_update_result,
        },
    )

    return {
        "ok": True,
        "duplicate_skipped": duplicate_skipped,
        "pattern_update_result": pattern_update_result,
    }


def apply_correct_learning(
    draft: dict,
    corrected_account_code: str,
    corrected_reason: str = "manual_correction",
    corrected_by: str = "manual_review",
    notes: str = "",
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    memory_result = {"ok": False}
    erp_memory_result = {"ok": False}
    failure_result = {"updated": 0}
    duplicate_skipped = False

    try:
        if _feedback_exists(cur, draft["id"], "correct"):
            duplicate_skipped = True
        else:
            save_feedback(
                draft_id=draft.get("id"),
                tx_fingerprint=draft.get("tx_fingerprint"),
                source_type=draft.get("source_type"),
                description_raw=draft.get("description"),
                description_normalized=draft.get("normalized_description") or draft.get("description"),
                partner_raw=draft.get("partner"),
                partner_normalized=draft.get("partner"),
                amount=draft.get("amount"),
                original_account_code=draft.get("account_code"),
                original_reason=draft.get("reason"),
                original_confidence=draft.get("confidence"),
                final_account_code=corrected_account_code,
                final_reason=corrected_reason,
                feedback_type="correct",
                corrected_by=corrected_by,
                notes=f"run_id=draft:{draft.get('id')}; {notes}",
            )

            memory_result = save_transaction_memory(
                draft.get("description"),
                draft.get("partner"),
                draft.get("amount"),
                corrected_account_code,
            )

            corrected_draft = dict(draft)
            corrected_draft["account_code"] = corrected_account_code

            erp_memory_result = _save_erp_memory_from_draft(
                corrected_draft,
                corrected_account_code,
            )

            generate_patterns_from_feedback()

        conn.commit()

    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

    if draft.get("classification_source") in PATTERN_SOURCES and not duplicate_skipped:
        failure_result = _mark_failure_for_draft(draft)

    log_event(
        "draft_corrected_learning_applied",
        {
            "draft_id": draft.get("id"),
            "corrected_account_code": corrected_account_code,
            "duplicate_skipped": duplicate_skipped,
            "memory_saved": bool(memory_result.get("ok")),
            "memory_result": memory_result,
            "erp_memory_saved": bool(erp_memory_result.get("ok")),
            "erp_memory_result": erp_memory_result,
            "pattern_failure_result": failure_result,
        },
    )

    return {
        "ok": True,
        "duplicate_skipped": duplicate_skipped,
        "memory_result": memory_result,
        "erp_memory_result": erp_memory_result,
        "pattern_failure_result": failure_result,
    }


def get_learning_health_service():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT COUNT(*) AS total_feedback FROM learning_feedback")
        total_feedback = cur.fetchone()["total_feedback"]

        cur.execute(
            """
            SELECT feedback_type, COUNT(*) AS count
            FROM learning_feedback
            GROUP BY feedback_type
            """
        )
        feedback_by_type = {r["feedback_type"]: r["count"] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT COALESCE(MAX(created_at), NOW()) AS last_feedback_at
            FROM learning_feedback
            """
        )
        last_feedback_at = cur.fetchone()["last_feedback_at"]

        active_patterns = 0
        candidate_patterns = 0
        inactive_patterns = 0

        try:
            cur.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM learning_patterns
                GROUP BY status
                """
            )
            pattern_rows = cur.fetchall()
            pattern_map = {r["status"]: r["count"] for r in pattern_rows}
            active_patterns = pattern_map.get("active", 0)
            candidate_patterns = pattern_map.get("candidate", 0)
            inactive_patterns = pattern_map.get("inactive", 0)
        except Exception:
            pass

        auto_approved_count = 0
        manual_review_count = 0

        try:
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'auto_approved' THEN 1 ELSE 0 END) AS auto_approved_count,
                    SUM(CASE WHEN status IN ('drafted', 'pending_approval') THEN 1 ELSE 0 END) AS manual_review_count
                FROM journal_drafts
                """
            )
            row = cur.fetchone()
            auto_approved_count = row.get("auto_approved_count") or 0
            manual_review_count = row.get("manual_review_count") or 0
        except Exception:
            pass

        return {
            "ok": True,
            "total_feedback": total_feedback,
            "feedback_by_type": feedback_by_type,
            "active_patterns": active_patterns,
            "candidate_patterns": candidate_patterns,
            "inactive_patterns": inactive_patterns,
            "auto_approved_count": auto_approved_count,
            "manual_review_count": manual_review_count,
            "last_feedback_at": str(last_feedback_at) if last_feedback_at else None,
            "learning_ok": True,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "learning_ok": False,
        }
    finally:
        cur.close()
        conn.close()