import json
import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit_service import log_event
from app.api.services.retry_service import run_with_retry
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

BLOCKING_POST_STATUSES = {"posted"}


def _fetch_draft(cur, draft_id: int, tenant_id: str):
    cur.execute(
        """
        SELECT
            id, tenant_id, date, description, partner, amount,
            debit_account, credit_account, account_code,
            reason, confidence, review_required, status,
            source_type, bank_file_id, created_at
        FROM journal_drafts
        WHERE id = %s
          AND tenant_id = %s
        """,
        (draft_id, tenant_id),
    )
    return cur.fetchone()


def _validate_approved_draft(draft, draft_id: int, tenant_id: str):
    if not draft:
        return error_response(
            "Draft not found",
            "DRAFT_NOT_FOUND",
            f"journal_drafts id={draft_id} does not exist for tenant {tenant_id}",
        )
    if draft["status"] != "approved":
        return error_response(
            "Draft is not approved",
            "DRAFT_NOT_APPROVED",
            f"journal_drafts id={draft_id} has status={draft['status']} for tenant {tenant_id}",
        )
    return None


def _build_generic_payload(draft):
    return {
        "draft_id": draft["id"],
        "tenant_id": draft["tenant_id"],
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


def _insert_posting_log(cur, tenant_id, draft_id, target_system, payload, response, status, error_message):
    cur.execute(
        """
        INSERT INTO posting_logs
        (tenant_id, draft_id, target_system, payload_json, response_json, status, error_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            tenant_id,
            draft_id,
            target_system,
            json.dumps(payload, ensure_ascii=False),
            json.dumps(response, ensure_ascii=False),
            status,
            error_message,
        ),
    )
    return cur.fetchone()["id"]


def _find_successful_post(cur, tenant_id: str, draft_id: int, target_system: str):
    cur.execute(
        """
        SELECT id, status
        FROM posting_logs
        WHERE tenant_id = %s
          AND draft_id = %s
          AND target_system = %s
          AND status = ANY(%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (tenant_id, draft_id, target_system, list(BLOCKING_POST_STATUSES)),
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


def _get_connector_readiness(target_normalized: str, tenant_id: str) -> dict:
    if target_normalized == "mock":
        return {
            "target": "mock",
            "ready": True,
            "status": {"ok": True, "mode": "mock", "tenant_id": tenant_id},
        }

    if target_normalized == "balance":
        status = balance_config_status()
        return {
            "target": "balance",
            "ready": _is_connector_ready(status),
            "status": {"tenant_id": tenant_id, **status},
        }

    if target_normalized == "1c":
        status = onec_config_status()
        return {
            "target": "1c",
            "ready": _is_connector_ready(status),
            "status": {"tenant_id": tenant_id, **status},
        }

    if target_normalized == "oris":
        status = oris_config_status()
        return {
            "target": "oris",
            "ready": _is_connector_ready(status),
            "status": {"tenant_id": tenant_id, **status},
        }

    return {
        "target": target_normalized,
        "ready": False,
        "status": {"error": "unsupported_target", "tenant_id": tenant_id},
    }


def _get_connector_executor(target_normalized: str):
    connectors = {
        "mock": {
            "target_system": "mock",
            "payload_builder": lambda draft: _build_generic_payload(draft),
            "executor": lambda payload, draft: {
                "ok": True,
                "target_system": "mock",
                "status": "posted",
                "message": "Mock posting completed successfully",
                "posted_draft_id": draft["id"],
                "tenant_id": draft["tenant_id"],
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


def _execute_with_retry(connector: dict, payload: dict, draft) -> dict:
    def operation():
        return connector["executor"](payload, draft)

    return run_with_retry(
        operation,
        max_attempts=3,
        delay_seconds=1,
    )


def get_approved_drafts_service(limit: int, offset: int, tenant_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM journal_drafts
            WHERE status = 'approved'
              AND tenant_id = %s
            """,
            (tenant_id,),
        )
        total = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT
                id, tenant_id, date, description, partner, amount,
                debit_account, credit_account, account_code,
                reason, confidence, review_required, status,
                source_type, bank_file_id, created_at
            FROM journal_drafts
            WHERE status = 'approved'
              AND tenant_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, limit, offset),
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
            "tenant_id": tenant_id,
            "limit": limit,
            "offset": offset,
            "items": items,
        },
    )


def get_posting_payload_service(draft_id: int, tenant_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        draft = _fetch_draft(cur, draft_id, tenant_id)
        err = _validate_approved_draft(draft, draft_id, tenant_id)
        if err:
            return err

        payload = _build_generic_payload(draft)

    except Exception as e:
        return error_response("Posting payload build failed", "POSTING_PAYLOAD_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Posting payload preview",
        {"tenant_id": tenant_id, "draft": dict(draft), "payload": payload},
    )


def get_posting_logs_service(limit: int, offset: int, tenant_id: str, target_system: str | None = None, draft_id: int | None = None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        where_clauses = ["tenant_id = %s"]
        params = [tenant_id]

        if target_system:
            where_clauses.append("target_system = %s")
            params.append(target_system)

        if draft_id is not None:
            where_clauses.append("draft_id = %s")
            params.append(draft_id)

        where_sql = "WHERE " + " AND ".join(where_clauses)

        cur.execute(f"SELECT COUNT(*) AS total FROM posting_logs {where_sql}", tuple(params))
        total = cur.fetchone()["total"]

        cur.execute(
            f"""
            SELECT
                id, tenant_id, draft_id, target_system, payload_json,
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
            "tenant_id": tenant_id,
            "limit": limit,
            "offset": offset,
            "filters": {"target_system": target_system, "draft_id": draft_id},
            "items": items,
        },
    )


def get_posting_log_detail_service(log_id: int, tenant_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT
                id, tenant_id, draft_id, target_system, payload_json,
                response_json, status, error_message, created_at
            FROM posting_logs
            WHERE id = %s
              AND tenant_id = %s
            """,
            (log_id, tenant_id),
        )
        row = cur.fetchone()

        if not row:
            return error_response(
                "Posting log not found",
                "POSTING_LOG_NOT_FOUND",
                f"posting_logs id={log_id} does not exist for tenant {tenant_id}",
            )

    except Exception as e:
        return error_response("Posting log detail failed", "POSTING_LOG_DETAIL_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response("Posting log detail", dict(row))


def _run_posting_attempt(draft_id: int, target_normalized: str, tenant_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        draft = _fetch_draft(cur, draft_id, tenant_id)
        err = _validate_approved_draft(draft, draft_id, tenant_id)
        if err:
            return err

        connector = _get_connector_executor(target_normalized)
        if not connector:
            return error_response(
                "Unsupported target system",
                "UNSUPPORTED_TARGET",
                f"target={target_normalized} is not supported. Use mock, balance, 1c, oris",
            )

        log_target = connector["target_system"]

        existing_post = _find_successful_post(cur, tenant_id, draft["id"], log_target)
        if existing_post:
            log_event(
                "posting_duplicate_blocked",
                {
                    "tenant_id": tenant_id,
                    "draft_id": draft["id"],
                    "target": log_target,
                    "existing_log_id": existing_post["id"],
                },
            )
            return error_response(
                "Draft already posted",
                "ALREADY_POSTED",
                f"draft_id={draft['id']} was already posted to {log_target} for tenant {tenant_id} (log_id={existing_post['id']})",
            )

        readiness = _get_connector_readiness(target_normalized, tenant_id)
        if not readiness["ready"]:
            log_event(
                "connector_not_ready",
                {
                    "tenant_id": tenant_id,
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
                        "tenant_id": tenant_id,
                        "draft_id": draft["id"],
                        "target": log_target,
                        "readiness": readiness["status"],
                    },
                    ensure_ascii=False,
                ),
            )

        log_event(
            "posting_attempt_started",
            {"tenant_id": tenant_id, "draft_id": draft["id"], "target": log_target},
        )

        payload = connector["payload_builder"](draft)
        result = _execute_with_retry(connector, payload, draft)

        posting_status = result.get("status", result.get("result", "unknown"))
        posting_log_id = _insert_posting_log(
            cur,
            tenant_id,
            draft["id"],
            log_target,
            payload,
            result,
            posting_status,
            result.get("error"),
        )
        conn.commit()

        log_event(
            "posting_retry_info",
            {
                "tenant_id": tenant_id,
                "draft_id": draft["id"],
                "target": log_target,
                "attempts": result.get("attempts_used"),
                "retry_used": result.get("retry_applied"),
            },
        )

        log_event(
            "posting_attempt_finished",
            {
                "tenant_id": tenant_id,
                "draft_id": draft["id"],
                "target": log_target,
                "posting_log_id": posting_log_id,
                "status": posting_status,
            },
        )

        return ok_response(
            f"{log_target} posting attempt completed",
            {
                "tenant_id": tenant_id,
                "posting_log_id": posting_log_id,
                "draft_id": draft["id"],
                "target": log_target,
                "payload": payload,
                "result": result,
            },
        )

    except Exception as e:
        conn.rollback()
        log_event(
            "posting_attempt_failed",
            {"tenant_id": tenant_id, "draft_id": draft_id, "target": target_normalized, "error": str(e)},
        )
        return error_response(
            "Posting failed",
            "POSTING_EXECUTION_ERROR",
            str(e),
        )
    finally:
        cur.close()
        conn.close()


def mock_posting_service(draft_id: int, tenant_id: str):
    return _run_posting_attempt(draft_id, "mock", tenant_id)


def get_balance_status_service(tenant_id: str):
    try:
        return ok_response(
            "Balance status",
            {"tenant_id": tenant_id, "config": balance_config_status(), "ping": balance_ping()},
        )
    except Exception as e:
        return error_response("Balance status check failed", "BALANCE_STATUS_ERROR", str(e))


def post_draft_to_balance_service(draft_id: int, tenant_id: str):
    return _run_posting_attempt(draft_id, "balance", tenant_id)


def get_onec_status_service(tenant_id: str):
    try:
        return ok_response(
            "1C status",
            {"tenant_id": tenant_id, "config": onec_config_status(), "ping": onec_ping()},
        )
    except Exception as e:
        return error_response("1C status check failed", "ONEC_STATUS_ERROR", str(e))


def post_draft_to_onec_service(draft_id: int, tenant_id: str):
    return _run_posting_attempt(draft_id, "1c", tenant_id)


def get_oris_status_service(tenant_id: str):
    try:
        return ok_response(
            "ORIS status",
            {"tenant_id": tenant_id, "config": oris_config_status(), "ping": oris_ping()},
        )
    except Exception as e:
        return error_response("ORIS status check failed", "ORIS_STATUS_ERROR", str(e))


def post_draft_to_oris_service(draft_id: int, tenant_id: str):
    return _run_posting_attempt(draft_id, "oris", tenant_id)


def apply_posting_service(draft_id: int, target: str, tenant_id: str):
    target_normalized = (target or "").strip().lower()
    return _run_posting_attempt(draft_id, target_normalized, tenant_id)