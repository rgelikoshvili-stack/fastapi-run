from app.api.db import get_conn, _q
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

SIGNAL_WEIGHTS = {
    "approve": 1.0,
    "correct": 2.0,
    "reject": 1.5,
}


async def _feedback_exists(conn, draft_id: int, feedback_type: str, tenant_id: str) -> bool:
    row = await conn.fetchrow(_q("""
        SELECT COUNT(*) AS cnt FROM learning_feedback
        WHERE draft_id = %s AND feedback_type = %s AND tenant_id = %s
    """), draft_id, feedback_type, tenant_id)
    return bool(row and row["cnt"] > 0)


def _get_pattern_value_for_draft(draft: dict):
    matched_on = draft.get("pattern_matched_on")

    if matched_on in ("description_exact", "description_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("description")

    if matched_on in ("partner_exact", "partner_fuzzy"):
        return draft.get("pattern_value_used") or draft.get("partner")

    return None


def _mark_success_for_draft(draft: dict, tenant_id: str, weight: float = 1.0):
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value or not account_code:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_success("description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight)
    if matched_on == "partner_exact":
        return mark_pattern_success("partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight)
    if matched_on == "description_fuzzy":
        return mark_pattern_success("description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight)
    if matched_on == "partner_fuzzy":
        return mark_pattern_success("partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight)

    return {"updated": 0}


def _mark_failure_for_draft(draft: dict, tenant_id: str, weight: float = 1.5):
    matched_on = draft.get("pattern_matched_on")
    account_code = draft.get("account_code")
    pattern_value = _get_pattern_value_for_draft(draft)

    if not pattern_value or not account_code:
        return {"updated": 0}

    if matched_on == "description_exact":
        return mark_pattern_failure("description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight)
    if matched_on == "partner_exact":
        return mark_pattern_failure("partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight)
    if matched_on == "description_fuzzy":
        return mark_pattern_failure("description_exact", pattern_value, account_code, tenant_id=tenant_id, weight=weight)
    if matched_on == "partner_fuzzy":
        return mark_pattern_failure("partner", pattern_value, account_code, tenant_id=tenant_id, weight=weight)

    return {"updated": 0}


def _save_erp_memory_from_draft(draft: dict, account_code: str, tenant_id: str):
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
            tenant_id=tenant_id,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def apply_approve_learning(
    draft: dict,
    approved_by_mode: str = "manual_review",
    tenant_id: str = "default",
):
    memory_result = {"ok": False}
    erp_memory_result = {"ok": False}
    pattern_update_result = {"updated": 0}
    duplicate_skipped = False
    feedback_result = None
    weight = SIGNAL_WEIGHTS["approve"]

    try:
        async with get_conn() as conn:
            if await _feedback_exists(conn, draft["id"], "approve", tenant_id):
                duplicate_skipped = True
            else:
                feedback_result = save_feedback(
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
                    notes=f"run_id=draft:{draft.get('id')}; weight={weight}",
                    tenant_id=tenant_id,
                )

            memory_result = await save_transaction_memory(
                draft.get("description"),
                draft.get("partner"),
                draft.get("amount"),
                draft.get("account_code"),
                tenant_id=tenant_id,
            )

            erp_memory_result = _save_erp_memory_from_draft(
                draft, draft.get("account_code"), tenant_id=tenant_id,
            )

            generate_patterns_from_feedback(tenant_id=tenant_id)

    except Exception as e:
        return {"ok": False, "error": str(e)}

    if draft.get("classification_source") in PATTERN_SOURCES and not duplicate_skipped:
        pattern_update_result = _mark_success_for_draft(draft, tenant_id, weight=weight)

    log_event(
        "draft_approved_learning_applied",
        {
            "tenant_id": tenant_id,
            "draft_id": draft.get("id"),
            "duplicate_skipped": duplicate_skipped,
            "feedback_result": feedback_result,
            "classification_source": draft.get("classification_source"),
            "pattern_update_result": pattern_update_result,
            "memory_saved": bool(memory_result.get("ok")),
            "memory_result": memory_result,
            "erp_memory_saved": bool(erp_memory_result.get("ok")),
            "erp_memory_result": erp_memory_result,
            "signal_weight": weight,
        },
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "duplicate_skipped": duplicate_skipped,
        "feedback_result": feedback_result,
        "pattern_update_result": pattern_update_result,
        "memory_result": memory_result,
        "erp_memory_result": erp_memory_result,
        "signal_weight": weight,
    }


async def apply_reject_learning(draft: dict, reason: str = "", tenant_id: str = "default"):
    pattern_update_result = {"updated": 0}
    duplicate_skipped = False
    feedback_result = None
    weight = SIGNAL_WEIGHTS["reject"]

    try:
        async with get_conn() as conn:
            if await _feedback_exists(conn, draft["id"], "reject", tenant_id):
                duplicate_skipped = True
            else:
                feedback_result = save_feedback(
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
                    notes=f"run_id=draft:{draft.get('id')}; reason={reason}; weight={weight}",
                    tenant_id=tenant_id,
                )

            generate_patterns_from_feedback(tenant_id=tenant_id)

    except Exception as e:
        return {"ok": False, "error": str(e)}

    if draft.get("classification_source") in PATTERN_SOURCES and not duplicate_skipped:
        pattern_update_result = _mark_failure_for_draft(draft, tenant_id, weight=weight)

    log_event(
        "draft_rejected_learning_applied",
        {
            "tenant_id": tenant_id,
            "draft_id": draft.get("id"),
            "reason": reason,
            "duplicate_skipped": duplicate_skipped,
            "feedback_result": feedback_result,
            "classification_source": draft.get("classification_source"),
            "pattern_update_result": pattern_update_result,
            "signal_weight": weight,
        },
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "duplicate_skipped": duplicate_skipped,
        "feedback_result": feedback_result,
        "pattern_update_result": pattern_update_result,
        "signal_weight": weight,
    }


async def apply_correct_learning(
    draft: dict,
    corrected_account_code: str,
    corrected_reason: str = "manual_correction",
    corrected_by: str = "manual_review",
    notes: str = "",
    tenant_id: str = "default",
):
    memory_result = {"ok": False}
    erp_memory_result = {"ok": False}
    failure_result = {"updated": 0}
    success_result = {"updated": 0}
    duplicate_skipped = False
    feedback_result = None
    weight = SIGNAL_WEIGHTS["correct"]

    try:
        async with get_conn() as conn:
            if await _feedback_exists(conn, draft["id"], "correct", tenant_id):
                duplicate_skipped = True
            else:
                feedback_result = save_feedback(
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
                    notes=f"run_id=draft:{draft.get('id')}; weight={weight}; {notes}",
                    tenant_id=tenant_id,
                )

            memory_result = await save_transaction_memory(
                draft.get("description"),
                draft.get("partner"),
                draft.get("amount"),
                corrected_account_code,
                tenant_id=tenant_id,
            )

            corrected_draft = dict(draft)
            corrected_draft["account_code"] = corrected_account_code
            corrected_draft["reason"] = corrected_reason

            erp_memory_result = _save_erp_memory_from_draft(
                corrected_draft, corrected_account_code, tenant_id=tenant_id,
            )

            generate_patterns_from_feedback(tenant_id=tenant_id)

    except Exception as e:
        return {"ok": False, "error": str(e)}

    if draft.get("classification_source") in PATTERN_SOURCES and not duplicate_skipped:
        # ძველი ანგარიში — failure (AI შეცდა)
        failure_result = _mark_failure_for_draft(draft, tenant_id, weight=weight)

    if not duplicate_skipped:
        # სწორი ანგარიში — success weight=2.0 (ძლიერი სიგნალი)
        corrected_draft_for_learning = dict(draft)
        corrected_draft_for_learning["account_code"] = corrected_account_code
        success_result = _mark_success_for_draft(
            corrected_draft_for_learning, tenant_id, weight=weight
        )

    log_event(
        "draft_corrected_learning_applied",
        {
            "tenant_id": tenant_id,
            "draft_id": draft.get("id"),
            "corrected_account_code": corrected_account_code,
            "corrected_reason": corrected_reason,
            "duplicate_skipped": duplicate_skipped,
            "feedback_result": feedback_result,
            "memory_saved": bool(memory_result.get("ok")),
            "memory_result": memory_result,
            "erp_memory_saved": bool(erp_memory_result.get("ok")),
            "erp_memory_result": erp_memory_result,
            "pattern_failure_result": failure_result,
            "pattern_success_result": success_result,
            "signal_weight": weight,
        },
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "duplicate_skipped": duplicate_skipped,
        "feedback_result": feedback_result,
        "memory_result": memory_result,
        "erp_memory_result": erp_memory_result,
        "pattern_failure_result": failure_result,
        "pattern_success_result": success_result,
        "signal_weight": weight,
    }


async def get_learning_health_service(tenant_id: str = "default"):
    try:
        async with get_conn() as conn:
            total_feedback = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM learning_feedback WHERE tenant_id = %s"
            ), tenant_id)

            fb_rows = await conn.fetch(_q(
                "SELECT feedback_type, COUNT(*) AS count FROM learning_feedback "
                "WHERE tenant_id = %s GROUP BY feedback_type"
            ), tenant_id)
            feedback_by_type = {r["feedback_type"]: r["count"] for r in fb_rows}

            last_row = await conn.fetchrow(_q(
                "SELECT COALESCE(MAX(created_at), NOW()) AS last_feedback_at "
                "FROM learning_feedback WHERE tenant_id = %s"
            ), tenant_id)
            last_feedback_at = last_row["last_feedback_at"] if last_row else None

            active_patterns = candidate_patterns = inactive_patterns = 0
            try:
                pat_rows = await conn.fetch(_q(
                    "SELECT status, COUNT(*) AS count FROM learning_patterns "
                    "WHERE tenant_id = %s GROUP BY status"
                ), tenant_id)
                pattern_map = {r["status"]: r["count"] for r in pat_rows}
                active_patterns    = pattern_map.get("active", 0)
                candidate_patterns = pattern_map.get("candidate", 0)
                inactive_patterns  = pattern_map.get("inactive", 0)
            except Exception:
                pass

            auto_approved_count = manual_review_count = 0
            try:
                dr_row = await conn.fetchrow(_q("""
                    SELECT
                        SUM(CASE WHEN status='auto_approved' THEN 1 ELSE 0 END) AS auto_approved_count,
                        SUM(CASE WHEN status IN ('drafted','pending_approval') THEN 1 ELSE 0 END) AS manual_review_count
                    FROM journal_drafts WHERE tenant_id = %s
                """), tenant_id)
                auto_approved_count = dr_row.get("auto_approved_count") or 0 if dr_row else 0
                manual_review_count = dr_row.get("manual_review_count") or 0 if dr_row else 0
            except Exception:
                pass

        return {
            "ok": True, "tenant_id": tenant_id,
            "total_feedback": total_feedback,
            "feedback_by_type": feedback_by_type,
            "active_patterns": active_patterns,
            "candidate_patterns": candidate_patterns,
            "inactive_patterns": inactive_patterns,
            "auto_approved_count": auto_approved_count,
            "manual_review_count": manual_review_count,
            "last_feedback_at": str(last_feedback_at) if last_feedback_at else None,
            "learning_ok": True, "signal_weights": SIGNAL_WEIGHTS,
        }
    except Exception as e:
        return {"ok": False, "tenant_id": tenant_id, "error": str(e), "learning_ok": False}


def run_decay_service(tenant_id: str = "default"):
    try:
        from app.api.engines.pattern_engine import decay_old_patterns
        result = decay_old_patterns(tenant_id=tenant_id)
        return {"ok": True, "tenant_id": tenant_id, "decayed": result}
    except Exception as e:
        return {"ok": False, "tenant_id": tenant_id, "error": str(e)}