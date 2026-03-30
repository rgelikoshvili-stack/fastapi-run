from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.api.db import get_db


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        try:
            normalized = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def _calculate_success_rate(success_count: int, failure_count: int) -> float:
    total = success_count + failure_count
    if total <= 0:
        return 0.0
    return round(success_count / total, 4)


def _calculate_failure_rate(success_count: int, failure_count: int) -> float:
    total = success_count + failure_count
    if total <= 0:
        return 0.0
    return round(failure_count / total, 4)


def _calculate_support_factor(support_count: int) -> float:
    if support_count <= 0:
        return 0.0
    if support_count >= 20:
        return 1.0
    return round(support_count / 20.0, 4)


def _calculate_recency_penalty(last_seen_at: Optional[str]) -> float:
    dt = _parse_dt(last_seen_at)
    if not dt:
        return 0.0

    now = datetime.now(timezone.utc)
    age_days = (now - dt).days

    if age_days <= 7:
        return 0.0
    if age_days <= 30:
        return 0.03
    if age_days <= 90:
        return 0.08
    return 0.15


def _build_reason(
    support_count: int,
    success_rate: float,
    confidence_score: float,
    autopilot_eligible: bool,
    min_support_required: int,
    min_success_rate_required: float,
    autopilot_threshold: float,
) -> str:
    reasons = []

    if support_count < min_support_required:
        reasons.append(f"support_count {support_count} < required {min_support_required}")

    if success_rate < min_success_rate_required:
        reasons.append(
            f"success_rate {success_rate:.2f} < required {min_success_rate_required:.2f}"
        )

    if confidence_score < autopilot_threshold:
        reasons.append(
            f"confidence_score {confidence_score:.2f} < threshold {autopilot_threshold:.2f}"
        )

    if autopilot_eligible and not reasons:
        return "Eligible for autopilot: all thresholds satisfied."

    if not reasons:
        return "Not eligible by current policy."

    return "Not eligible: " + "; ".join(reasons)


def explain_pattern(pattern_id: int) -> Dict[str, Any]:
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                id,
                pattern_type,
                pattern_value,
                account_code,
                confidence_score,
                support_count,
                success_count,
                failure_count,
                autopilot_eligible,
                status,
                created_at,
                updated_at,
                last_seen_at
            FROM learning_patterns
            WHERE id = %s
            """,
            (pattern_id,),
        )
        row = cur.fetchone()

        if not row:
            return {
                "ok": False,
                "message": f"Pattern not found: {pattern_id}",
                "data": None,
            }

        support_count = _safe_int(row[5])
        success_count = _safe_int(row[6])
        failure_count = _safe_int(row[7])
        confidence_score = _safe_float(row[4])
        autopilot_eligible = bool(row[8])

        success_rate = _calculate_success_rate(success_count, failure_count)
        failure_rate = _calculate_failure_rate(success_count, failure_count)
        support_factor = _calculate_support_factor(support_count)
        recency_penalty = _calculate_recency_penalty(row[12])

        final_confidence = round(confidence_score, 4)

        autopilot_threshold = 0.90
        min_support_required = 5
        min_success_rate_required = 0.80

        autopilot_reason = _build_reason(
            support_count=support_count,
            success_rate=success_rate,
            confidence_score=final_confidence,
            autopilot_eligible=autopilot_eligible,
            min_support_required=min_support_required,
            min_success_rate_required=min_success_rate_required,
            autopilot_threshold=autopilot_threshold,
        )

        return {
            "ok": True,
            "message": "Pattern explanation generated",
            "data": {
                "id": row[0],
                "pattern_type": row[1],
                "pattern_value": row[2],
                "account_code": row[3],
                "status": row[9],
                "support_count": support_count,
                "success_count": success_count,
                "failure_count": failure_count,
                "success_rate": success_rate,
                "failure_rate": failure_rate,
                "support_factor": support_factor,
                "recency_penalty": recency_penalty,
                "confidence_score": confidence_score,
                "final_confidence": final_confidence,
                "autopilot_eligible": autopilot_eligible,
                "autopilot_threshold": autopilot_threshold,
                "minimum_support_required": min_support_required,
                "minimum_success_rate_required": min_success_rate_required,
                "autopilot_reason": autopilot_reason,
                "created_at": row[10],
                "updated_at": row[11],
                "last_seen_at": row[12],
            },
        }
    finally:
        cur.close()
        conn.close()