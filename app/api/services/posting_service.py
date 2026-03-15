import json
import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event
from app.api.balance_connector import (
    balance_config_status,
    balance_ping,
    build_balance_payload,
    post_to_balance,
)
from app.api.onec_connector import (
    onec_config_status,
    onec_ping,
    build_onec_payload,
    post_to_onec,
)
from app.api.oris_connector import (
    oris_config_status,
    oris_ping,
    build_oris_payload,
    post_to_oris,
)


def _fetch_draft(cur, draft_id: int):
    cur.execute(
        """
        SELECT
            id, date, description, partner, amount,
            debit_account, credit_account, account_code,
            reason, confidence, review_required, status,
            source_type, bank_file_id, created_at
        FROM journal_drafts
        WHERE id = %s
        """,
        (draft_id,),
    )
    return cur.fetchone()


def _validate_approved_draft(draft, draft_id: int):
    if not draft:
        return error_response(
            "Draft not found",
            "DRAFT_NOT_FOUND",
            f"journal_drafts id={draft_id} does not exist",
        )
    if draft["status"] != "approved":
        return error_response(
            "Draft is not approved",
            "DRAFT_NOT_APPROVED",
            f"journal_drafts id={draft_id} has status={draft['status']}",
        )
    return None


def _build_generic_payload(draft):
    return {
        "draft_id": draft["id"],
        "transaction_date": str(draft["date"]) if draft["date"] is not None else None,
        "description": draft["description"],
        "partner": draft["partner"],
        "amount": float(draft["amount"]) if draft["amount"] is not None else 0.0,
        "debit_account": draft["debit_account"],
        "credit_account": draft["credit_account"],
        "account_code": draft["account_code"],
        "reason": draft["reason"],
        "source_type": draft["source_type"],
        "bank_file_id": draft["bank_file_id"],
        "metadata": {
            "confidence": float(draft["confidence"]) if draft["confidence"] is not None else None,
            "review_required": draft["review_required"],
            "created_at": str(draft["created_at"]) if draft["created_at"] is not None else None,
        },
    }


def _insert_posting_log(cur, draft_id, target_system, payload, response, status, error_message):
    cur.execute(
        """
        INSERT INTO posting_logs
        (draft_id, target_system, payload_json, response_json, status, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            draft_id,
            target_system,
            json.dumps(payload, ensure_ascii=False),
            json.dumps(response, ensure_ascii=False),
            status,
            error_message,
        ),
    )
    return cur.fetchone()["id"]


def _find_successful_post(cur, draft_id: int, target_system: str):
    cur.execute(
        """
        SELECT id, status
        FROM posting_logs
        WHERE draft_id = %s
          AND target_system = %s
          AND status NOT IN ('failed', 'config_missing', 'dry_run_only')
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (draft_id, target_system),
    )
    return cur.fetchone()


def _is_connector_ready(status: dict) -> bool:
    if not isinstance(status, dict):
        return False

    if status.get("ok") is True:
        return True

    if status.get("ready") is True:
        return True

    if status.get("configured") is True:
        return True

    if "base_url" in status or "api_key_configured" in status or "company_id" in status:
        return bool(status.get("base_url")) and bool(status.get("api_key_configured")) and bool(status.get("company_id"))

    return False


def _get_connector_readiness(target_normalized: str) -> dict:
    if target_normalized == "mock":
        return {
            "target": "mock",
            "ready": True,
            "status": {"ok": True, "mode": "mock"},
        }

    if target_normalized == "balance":
        status = balance_config_status()
        return {
            "target": "balance",
            "ready": _is_connector_ready(status),
            "status": status,
        }

    if target_normalized == "1c":
        status = onec_config_status()
        return {
            "target": "1c",
            "ready": _is_connector_ready(status),
            "status": status,
        }

    if target_normalized == "oris":
        status = oris_config_status()
        return {
            "target": "oris",
            "ready": _is_connector_ready(status),
            "status": status,
        }

    return {
        "target": target_normalized,
        "ready": False,
        "status": {"error": "unsupported_target"},
    }


def _get_connector_executor(target_normalized: str):
    connectors = {
        "mock": {
            "target_system": "mock",
            "payload_builder": lambda draft: _build_generic_payload(draft),
            "executor": lambda payload, draft: {
                "target_system": "mock",
                "result": "simulated_success",
                "message": "Mock posting completed successfully",
                "posted_draft_id": draft["id"],
            },
        },
        "balance": {
            "target_system": "balance",
            "payload_builder": lambda draft: build_balance_payload(dict(draft)),
            "executor": lambda payload, draft: post_to_balance(payload),
        },
        "1c": {
            "target_system": "1c",
            "payload_builder": lambda draft: build_onec_payload(dict(draft)),
            "executor": lambda payload, draft: post_to_onec(payload),
        },
        "oris": {
            "target_system": "oris",
            "payload_builder": lambda draft: build_oris_payload(dict(draft)),
            "executor": lambda payload, draft: post_to_oris(payload),
        },
    }
    return connectors.get(target_normalized)


def get_approved_drafts_service(limit: int, offset: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT COUNT(*) AS total FROM journal_drafts WHERE status = 'approved'")
        total = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT
                id, date, description, partner, amount,
                debit_account, credit_account, account_code,
                reason, confidence, review_required, status,
                source_type, bank_file_id, created_at
            FROM journal_drafts
            WHERE status = 'approved'
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        items = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response(
            "Approved drafts retrieval failed",
            "APPROVED_DRAFTS_ERROR",
            str(e),
        )
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Approved drafts",
        {
            "count": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        },
    )


def get_posting_payload_service(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        draft = _fetch_draft(cur, draft_id)
        err = _validate_approved_draft(draft, draft_id)
        if err:
            return err

        payload = _build_generic_payload(draft)

    except Exception as e:
        return error_response("Posting payload build failed", "POSTING_PAYLOAD_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("Posting payload preview", {"draft": dict(draft), "payload": payload})


def mock_posting_service(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        draft = _fetch_draft(cur, draft_id)
        err = _validate_approved_draft(draft, draft_id)
        if err:
            return err

        existing_post = _find_successful_post(cur, draft["id"], "mock")
        if existing_post:
            log_event(
                "posting_duplicate_blocked",
                {
                    "draft_id": draft["id"],
                    "target": "mock",
                    "existing_log_id": existing_post["id"],
                },
            )
            return error_response(
                "Draft already posted",
                "ALREADY_POSTED",
                f"draft_id={draft['id']} was already posted to mock (log_id={existing_post['id']})",
            )

        log_event(
            "posting_attempt_started",
            {"draft_id": draft["id"], "target": "mock"},
        )

        payload = _build_generic_payload(draft)
        mock_response = {
            "target_system": "mock",
            "result": "simulated_success",
            "message": "Mock posting completed successfully",
            "posted_draft_id": draft["id"],
        }

        posting_log_id = _insert_posting_log(
            cur,
            draft["id"],
            "mock",
            payload,
            mock_response,
            "simulated_success",
            None,
        )
        conn.commit()

        log_event(
            "posting_attempt_finished",
            {
                "draft_id": draft["id"],
                "target": "mock",
                "posting_log_id": posting_log_id,
                "status": "simulated_success",
            },
        )

    except Exception as e:
        conn.rollback()
        log_event(
            "posting_attempt_failed",
            {"draft_id": draft_id, "target": "mock", "error": str(e)},
        )
        return error_response("Mock posting failed", "MOCK_POSTING_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Mock posting completed",
        {
            "posting_log_id": posting_log_id,
            "draft_id": draft["id"],
            "payload": payload,
            "response": mock_response,
        },
    )


def get_posting_logs_service(limit: int, offset: int, target_system: str | None = None, draft_id: int | None = None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        where_clauses = []
        params = []

        if target_system:
            where_clauses.append("target_system = %s")
            params.append(target_system)

        if draft_id is not None:
            where_clauses.append("draft_id = %s")
            params.append(draft_id)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        cur.execute(f"SELECT COUNT(*) AS total FROM posting_logs {where_sql}", tuple(params))
        total = cur.fetchone()["total"]

        cur.execute(
            f"""
            SELECT
                id, draft_id, target_system, payload_json,
                response_json, status, error_message, created_at
            FROM posting_logs
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [limit, offset]),
        )
        items = [dict(r) for r in cur.fetchall()]

    except Exception as e:
        return error_response("Posting logs retrieval failed", "POSTING_LOGS_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Posting logs",
        {
            "count": total,
            "limit": limit,
            "offset": offset,
            "filters": {"target_system": target_system, "draft_id": draft_id},
            "items": items,
        },
    )


def get_posting_log_detail_service(log_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT
                id, draft_id, target_system, payload_json,
                response_json, status, error_message, created_at
            FROM posting_logs
            WHERE id = %s
            """,
            (log_id,),
        )
        row = cur.fetchone()

        if not row:
            return error_response(
                "Posting log not found",
                "POSTING_LOG_NOT_FOUND",
                f"posting_logs id={log_id} does not exist",
            )

    except Exception as e:
        return error_response("Posting log detail failed", "POSTING_LOG_DETAIL_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("Posting log detail", dict(row))


def get_balance_status_service():
    try:
        return ok_response("Balance status", {"config": balance_config_status(), "ping": balance_ping()})
    except Exception as e:
        return error_response("Balance status check failed", "BALANCE_STATUS_ERROR", str(e))


def post_draft_to_balance_service(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        draft = _fetch_draft(cur, draft_id)
        err = _validate_approved_draft(draft, draft_id)
        if err:
            return err

        existing_post = _find_successful_post(cur, draft["id"], "balance")
        if existing_post:
            log_event(
                "posting_duplicate_blocked",
                {
                    "draft_id": draft["id"],
                    "target": "balance",
                    "existing_log_id": existing_post["id"],
                },
            )
            return error_response(
                "Draft already posted",
                "ALREADY_POSTED",
                f"draft_id={draft['id']} was already posted to balance (log_id={existing_post['id']})",
            )

        log_event(
            "posting_attempt_started",
            {"draft_id": draft["id"], "target": "balance"},
        )

        payload = build_balance_payload(dict(draft))
        balance_result = post_to_balance(payload)

        posting_log_id = _insert_posting_log(
            cur,
            draft["id"],
            "balance",
            payload,
            balance_result,
            balance_result.get("status", "unknown"),
            balance_result.get("error"),
        )
        conn.commit()

        log_event(
            "posting_attempt_finished",
            {
                "draft_id": draft["id"],
                "target": "balance",
                "posting_log_id": posting_log_id,
                "status": balance_result.get("status", "unknown"),
            },
        )

    except Exception as e:
        conn.rollback()
        log_event(
            "posting_attempt_failed",
            {"draft_id": draft_id, "target": "balance", "error": str(e)},
        )
        return error_response("Balance posting failed", "BALANCE_POSTING_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Balance posting attempt completed",
        {
            "posting_log_id": posting_log_id,
            "draft_id": draft["id"],
            "payload": payload,
            "balance_result": balance_result,
        },
    )


def get_onec_status_service():
    try:
        return ok_response("1C status", {"config": onec_config_status(), "ping": onec_ping()})
    except Exception as e:
        return error_response("1C status check failed", "ONEC_STATUS_ERROR", str(e))


def post_draft_to_onec_service(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        draft = _fetch_draft(cur, draft_id)
        err = _validate_approved_draft(draft, draft_id)
        if err:
            return err

        existing_post = _find_successful_post(cur, draft["id"], "1c")
        if existing_post:
            log_event(
                "posting_duplicate_blocked",
                {
                    "draft_id": draft["id"],
                    "target": "1c",
                    "existing_log_id": existing_post["id"],
                },
            )
            return error_response(
                "Draft already posted",
                "ALREADY_POSTED",
                f"draft_id={draft['id']} was already posted to 1c (log_id={existing_post['id']})",
            )

        log_event(
            "posting_attempt_started",
            {"draft_id": draft["id"], "target": "1c"},
        )

        payload = build_onec_payload(dict(draft))
        onec_result = post_to_onec(payload)

        posting_log_id = _insert_posting_log(
            cur,
            draft["id"],
            "1c",
            payload,
            onec_result,
            onec_result.get("status", "unknown"),
            onec_result.get("error"),
        )
        conn.commit()

        log_event(
            "posting_attempt_finished",
            {
                "draft_id": draft["id"],
                "target": "1c",
                "posting_log_id": posting_log_id,
                "status": onec_result.get("status", "unknown"),
            },
        )

    except Exception as e:
        conn.rollback()
        log_event(
            "posting_attempt_failed",
            {"draft_id": draft_id, "target": "1c", "error": str(e)},
        )
        return error_response("1C posting failed", "ONEC_POSTING_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "1C posting attempt completed",
        {
            "posting_log_id": posting_log_id,
            "draft_id": draft["id"],
            "payload": payload,
            "onec_result": onec_result,
        },
    )


def get_oris_status_service():
    try:
        return ok_response("ORIS status", {"config": oris_config_status(), "ping": oris_ping()})
    except Exception as e:
        return error_response("ORIS status check failed", "ORIS_STATUS_ERROR", str(e))


def post_draft_to_oris_service(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        draft = _fetch_draft(cur, draft_id)
        err = _validate_approved_draft(draft, draft_id)
        if err:
            return err

        existing_post = _find_successful_post(cur, draft["id"], "oris")
        if existing_post:
            log_event(
                "posting_duplicate_blocked",
                {
                    "draft_id": draft["id"],
                    "target": "oris",
                    "existing_log_id": existing_post["id"],
                },
            )
            return error_response(
                "Draft already posted",
                "ALREADY_POSTED",
                f"draft_id={draft['id']} was already posted to oris (log_id={existing_post['id']})",
            )

        log_event(
            "posting_attempt_started",
            {"draft_id": draft["id"], "target": "oris"},
        )

        payload = build_oris_payload(dict(draft))
        oris_result = post_to_oris(payload)

        posting_log_id = _insert_posting_log(
            cur,
            draft["id"],
            "oris",
            payload,
            oris_result,
            oris_result.get("status", "unknown"),
            oris_result.get("error"),
        )
        conn.commit()

        log_event(
            "posting_attempt_finished",
            {
                "draft_id": draft["id"],
                "target": "oris",
                "posting_log_id": posting_log_id,
                "status": oris_result.get("status", "unknown"),
            },
        )

    except Exception as e:
        conn.rollback()
        log_event(
            "posting_attempt_failed",
            {"draft_id": draft_id, "target": "oris", "error": str(e)},
        )
        return error_response("ORIS posting failed", "ORIS_POSTING_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "ORIS posting attempt completed",
        {
            "posting_log_id": posting_log_id,
            "draft_id": draft["id"],
            "payload": payload,
            "oris_result": oris_result,
        },
    )


def apply_posting_service(draft_id: int, target: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        draft = _fetch_draft(cur, draft_id)
        err = _validate_approved_draft(draft, draft_id)
        if err:
            return err

        target_normalized = (target or "").strip().lower()
        connector = _get_connector_executor(target_normalized)
        if not connector:
            return error_response(
                "Unsupported target system",
                "UNSUPPORTED_TARGET",
                f"target={target} is not supported. Use mock, balance, 1c, oris",
            )

        log_target = connector["target_system"]

        existing_post = _find_successful_post(cur, draft["id"], log_target)
        if existing_post:
            log_event(
                "posting_duplicate_blocked",
                {
                    "draft_id": draft["id"],
                    "target": log_target,
                    "existing_log_id": existing_post["id"],
                },
            )
            return error_response(
                "Draft already posted",
                "ALREADY_POSTED",
                f"draft_id={draft['id']} was already posted to {log_target} (log_id={existing_post['id']})",
            )

        readiness = _get_connector_readiness(target_normalized)
        if not readiness["ready"]:
            log_event(
                "connector_not_ready",
                {
                    "draft_id": draft["id"],
                    "target": log_target,
                    "readiness": readiness["status"],
                },
            )
            return error_response(
                "Connector not ready",
                "CONNECTOR_NOT_READY",
                json.dumps(
                    {
                        "draft_id": draft["id"],
                        "target": log_target,
                        "readiness": readiness["status"],
                    },
                    ensure_ascii=False,
                ),
            )

        log_event(
            "posting_attempt_started",
            {"draft_id": draft["id"], "target": log_target},
        )

        payload = connector["payload_builder"](draft)
        result = connector["executor"](payload, draft)

        posting_log_id = _insert_posting_log(
            cur,
            draft["id"],
            log_target,
            payload,
            result,
            result.get("status", result.get("result", "unknown")),
            result.get("error"),
        )
        conn.commit()

        log_event(
            "posting_attempt_finished",
            {
                "draft_id": draft["id"],
                "target": log_target,
                "posting_log_id": posting_log_id,
                "status": result.get("status", result.get("result", "unknown")),
            },
        )

    except Exception as e:
        conn.rollback()
        log_event(
            "posting_attempt_failed",
            {"draft_id": draft_id, "target": target, "error": str(e)},
        )
        return error_response("Unified posting apply failed", "POSTING_APPLY_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Posting apply completed",
        {
            "posting_log_id": posting_log_id,
            "draft_id": draft["id"],
            "target": log_target,
            "payload": payload,
            "result": result,
        },
    )