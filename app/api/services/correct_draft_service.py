import json
import logging

import psycopg2.errors

from app.api.db import get_db
from app.api.audit_service import log_event
from app.api.services.learning_service import apply_correct_learning
from app.api.services.transaction_memory_service import save_transaction_memory
from app.api.metrics import APPROVAL_ACTIONS

log = logging.getLogger(__name__)


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


def correct_draft(draft_id: int, payload: dict, user: str = "human", tenant_id: str = "default"):
    conn = get_db()
    cur = conn.cursor()

    try:
        try:
            cur.execute(
                """
                SELECT id, description, partner, account_code, reason,
                       debit_account, credit_account, amount, classification_source
                FROM journal_drafts
                WHERE id = %s
                  AND tenant_id = %s
                FOR UPDATE NOWAIT
                """,
                (draft_id, tenant_id),
            )
        except psycopg2.errors.LockNotAvailable:
            conn.rollback()
            return {
                "ok": False,
                "error": {"code": "DRAFT_LOCKED", "details": "Draft is being processed by another request. Try again in a moment."},
                "status_code": 409,
            }

        row = cur.fetchone()

        if not row:
            return {
                "ok": False,
                "message": "Draft not found",
                "data": None,
                "error": {
                    "code": "NOT_FOUND",
                    "details": f"Draft {draft_id} not found for tenant {tenant_id}",
                },
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

        changed_fields = []
        delta_parts = []

        for key in original:
            if original[key] != final[key]:
                changed_fields.append(key)
                delta_parts.append(f"{key}: {original[key]} -> {final[key]}")

        delta_summary = ", ".join(delta_parts) if delta_parts else "no_change"

        # 🔒 UPDATE tenant-ით
        cur.execute(
            """
            UPDATE journal_drafts
            SET account_code = %s,
                reason = %s,
                debit_account = %s,
                credit_account = %s,
                status = 'approved',
                approved_by_mode = 'human_correction',
                updated_at = NOW()
            WHERE id = %s
              AND tenant_id = %s
            """,
            (
                final["account_code"],
                final["reason"],
                final["debit_account"],
                final["credit_account"],
                draft_id,
                tenant_id,
            ),
        )

        cur.execute(
            """
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
            """,
            (
                draft_id,
                "correct",
                json.dumps(final),
                final["account_code"],
                final["reason"],
                delta_summary,
                user,
            ),
        )

        review_id = cur.fetchone()[0]

        cur.execute(
            """
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
            """,
            (
                draft_id,
                review_id,
                json.dumps(original),
                json.dumps(final),
                json.dumps(changed_fields),
                delta_summary,
                "corrected_mapping",
            ),
        )

        conn.commit()

        try:
            log_event(
                "draft_corrected",
                {
                    "draft_id": draft_id,
                    "changed_fields": changed_fields,
                    "delta_summary": delta_summary,
                    "review_id": review_id,
                    "original": original,
                    "final": final,
                },
                actor=user,
                tenant_id=tenant_id,
            )
        except Exception as _e:
            log.error("audit log failed for draft_corrected draft_id=%s: %s", draft_id, _e)

        learning_result = apply_correct_learning(
            draft={
                "id": draft_id,
                "description": row[1],
                "partner": row[2],
                "account_code": original["account_code"],
                "reason": original["reason"],
                "debit_account": original["debit_account"],
                "credit_account": original["credit_account"],
                "amount": row[7],
                "classification_source": row[8],
            },
            corrected_account_code=final["account_code"],
            corrected_reason=final["reason"],
            corrected_by=user,
            notes=f"review_id={review_id}",
        )

        memory_result = save_transaction_memory(
            row[1],
            row[2],
            row[7],
            final["account_code"]
        )

        # AI pattern suggestion — best-effort, never blocks the correction
        ai_suggestion = None
        try:
            from app.ai_systems.learning_ai import _ai_suggest_pattern
            ai_suggestion = _ai_suggest_pattern(
                {
                    "description": row[1],
                    "partner": row[2],
                    "amount": row[7],
                    "debit_account": original["debit_account"],
                    "credit_account": original["credit_account"],
                },
                {
                    "debit_account": final["debit_account"],
                    "credit_account": final["credit_account"],
                },
                tenant_id,
            )
        except Exception as _ae:
            log.debug("ai_suggest_pattern skipped: %s", _ae)

        APPROVAL_ACTIONS.labels(action="correct", tenant=tenant_id).inc()
        return {
            "ok": True,
            "message": "Draft corrected and learning updated",
            "data": {
                "draft_id": draft_id,
                "review_id": review_id,
                "tenant_id": tenant_id,
                "changed_fields": changed_fields,
                "delta_summary": delta_summary,
                "learning_result": learning_result,
                "memory_result": memory_result,
                "ai_suggestion": ai_suggestion,
            },
            "error": None,
        }

    except Exception as e:
        conn.rollback()
        log.error("correct_draft failed draft_id=%s tenant=%s: %s", draft_id, tenant_id, e)
        return {
            "ok": False,
            "message": "Internal server error",
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "details": str(e),
            },
        }

    finally:
        cur.close()
        conn.close()