from datetime import datetime, timezone

from app.api.db import get_db

PROMOTION_SUPPORT_THRESHOLD = 3
PROMOTION_SUCCESS_THRESHOLD = 3
DEMOTION_FAILURE_THRESHOLD = 2

AUTOPILOT_SUPPORT_THRESHOLD = 5
AUTOPILOT_SUCCESS_THRESHOLD = 4
AUTOPILOT_CONFIDENCE_THRESHOLD = 0.88

AUTOPILOT_MAX_PATTERN_AGE_DAYS = 45
STALE_CANDIDATE_AFTER_DAYS = 90
STALE_INACTIVE_AFTER_DAYS = 120


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _normalized_sql_expr(column_name: str) -> str:
    return f"LOWER(REGEXP_REPLACE(TRIM(COALESCE({column_name}, '')), '\\s+', ' ', 'g'))"


def _normalize_pattern_value(pattern_type: str, pattern_value: str | None) -> str:
    if pattern_type in ("description_exact", "partner"):
        return _normalize(pattern_value)
    return (pattern_value or "").strip()


def _compare_sql_for_pattern_type(pattern_type: str) -> str:
    if pattern_type in ("description_exact", "partner"):
        return _normalized_sql_expr("pattern_value")
    return "pattern_value"


def _safe_parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _days_since(value) -> int | None:
    dt = _safe_parse_dt(value)
    if dt is None:
        return None
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _is_pattern_stale(last_seen_at, max_days: int = AUTOPILOT_MAX_PATTERN_AGE_DAYS) -> bool:
    days = _days_since(last_seen_at)
    if days is None:
        return True
    return days > max_days


def calculate_pattern_confidence(
    support_count: int,
    success_count: int,
    failure_count: int,
    last_seen_at=None,
    weighted_success_score: float = 0.0,
    weighted_failure_score: float = 0.0,
) -> float:
    support_count = int(support_count or 0)
    success_count = int(success_count or 0)
    failure_count = int(failure_count or 0)
    weighted_success_score = float(weighted_success_score or 0.0)
    weighted_failure_score = float(weighted_failure_score or 0.0)

    total_outcomes = success_count + failure_count
    success_rate = (success_count / total_outcomes) if total_outcomes > 0 else 0.0

    confidence = 0.20
    confidence += min(0.15, support_count * 0.01)
    confidence += min(0.30, success_count * 0.05)
    confidence += success_rate * 0.30
    confidence -= min(0.35, failure_count * 0.12)

    total_weighted = weighted_success_score + weighted_failure_score
    if total_weighted > 0:
        weighted_ratio = weighted_success_score / total_weighted
        confidence += (weighted_ratio - 0.5) * 0.10

    days = _days_since(last_seen_at)
    if days is not None:
        if days > AUTOPILOT_MAX_PATTERN_AGE_DAYS:
            confidence -= 0.05
        if days >= STALE_CANDIDATE_AFTER_DAYS:
            confidence -= 0.05
        if days >= STALE_INACTIVE_AFTER_DAYS:
            confidence -= 0.10

    return round(max(0.05, min(0.99, confidence)), 4)


def _decide_pattern_status(
    support_count: int,
    success_count: int,
    failure_count: int,
    last_seen_at=None,
) -> str:
    support_count = int(support_count or 0)
    success_count = int(success_count or 0)
    failure_count = int(failure_count or 0)

    if failure_count >= DEMOTION_FAILURE_THRESHOLD:
        return "inactive"

    days = _days_since(last_seen_at)

    if days is not None and days >= STALE_INACTIVE_AFTER_DAYS and failure_count > 0:
        return "inactive"

    if (
        support_count >= PROMOTION_SUPPORT_THRESHOLD
        and success_count >= PROMOTION_SUCCESS_THRESHOLD
        and failure_count == 0
    ):
        if days is not None and days >= STALE_CANDIDATE_AFTER_DAYS:
            return "candidate"
        return "active"

    return "candidate"


def is_pattern_autopilot_eligible(
    support_count: int,
    success_count: int,
    failure_count: int,
    last_seen_at=None,
    confidence_score: float | None = None,
    usage_count: int = 0,
) -> bool:
    support_count = int(support_count or 0)
    success_count = int(success_count or 0)
    failure_count = int(failure_count or 0)
    usage_count = int(usage_count or 0)

    total_outcomes = success_count + failure_count
    success_rate = (success_count / total_outcomes) if total_outcomes > 0 else 0.0

    if failure_count > 0:
        return False
    if support_count < AUTOPILOT_SUPPORT_THRESHOLD:
        return False
    if success_count < AUTOPILOT_SUCCESS_THRESHOLD:
        return False
    if success_rate < 0.90:
        return False
    if usage_count < 5:
        return False

    confidence = (
        float(confidence_score)
        if confidence_score is not None
        else calculate_pattern_confidence(
            support_count=support_count,
            success_count=success_count,
            failure_count=failure_count,
            last_seen_at=last_seen_at,
        )
    )

    if confidence < AUTOPILOT_CONFIDENCE_THRESHOLD:
        return False

    if _is_pattern_stale(last_seen_at, AUTOPILOT_MAX_PATTERN_AGE_DAYS):
        return False

    return True


def recalculate_pattern_state(
    support_count: int,
    success_count: int,
    failure_count: int,
    last_seen_at=None,
    weighted_success_score: float = 0.0,
    weighted_failure_score: float = 0.0,
    usage_count: int = 0,
):
    status = _decide_pattern_status(
        support_count=support_count,
        success_count=success_count,
        failure_count=failure_count,
        last_seen_at=last_seen_at,
    )
    confidence = calculate_pattern_confidence(
        support_count=support_count,
        success_count=success_count,
        failure_count=failure_count,
        last_seen_at=last_seen_at,
        weighted_success_score=weighted_success_score,
        weighted_failure_score=weighted_failure_score,
    )
    autopilot_eligible = is_pattern_autopilot_eligible(
        support_count=support_count,
        success_count=success_count,
        failure_count=failure_count,
        last_seen_at=last_seen_at,
        confidence_score=confidence,
        usage_count=usage_count,
    )
    return {
        "status": status,
        "confidence_score": confidence,
        "autopilot_eligible": autopilot_eligible,
    }


def generate_patterns_from_feedback(tenant_id: str = "default"):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT description_normalized, partner_normalized,
                   final_account_code, final_reason
            FROM learning_feedback
            WHERE tenant_id = %s
              AND final_account_code IS NOT NULL
            """,
            (tenant_id,),
        )
        rows = cur.fetchall()
        inserted = 0
        updated = 0

        for row in rows:
            description = _normalize(row[0])
            partner = _normalize(row[1])
            account_code = row[2]
            reason = row[3]

            if description:
                cur.execute(
                    f"""
                    SELECT id, support_count, success_count, failure_count,
                           last_seen_at, weighted_success_score, weighted_failure_score,
                           usage_count
                    FROM learning_patterns
                    WHERE tenant_id = %s
                      AND pattern_type = %s
                      AND {_normalized_sql_expr("pattern_value")} = %s
                    LIMIT 1
                    """,
                    (tenant_id, "description_exact", description),
                )
                existing = cur.fetchone()

                if existing:
                    pid, sc, suc, fc, lsa, wss, wfs, uc = existing
                    sc = int(sc or 0) + 1
                    suc = int(suc or 0)
                    fc = int(fc or 0)
                    wss = float(wss or 0.0)
                    wfs = float(wfs or 0.0)
                    uc = int(uc or 0)
                    state = recalculate_pattern_state(sc, suc, fc, lsa, wss, wfs, uc)

                    cur.execute(
                        """
                        UPDATE learning_patterns
                        SET account_code = %s,
                            reason = %s,
                            confidence_score = %s,
                            autopilot_eligible = %s,
                            support_count = %s,
                            status = %s,
                            source = 'feedback_learning',
                            last_seen_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s AND tenant_id = %s
                        """,
                        (
                            account_code,
                            reason,
                            state["confidence_score"],
                            state["autopilot_eligible"],
                            sc,
                            state["status"],
                            pid,
                            tenant_id,
                        ),
                    )
                    updated += 1
                else:
                    state = recalculate_pattern_state(1, 0, 0, None)
                    cur.execute(
                        """
                        INSERT INTO learning_patterns
                          (tenant_id, pattern_type, pattern_value, account_code, reason,
                           confidence_score, autopilot_eligible, support_count,
                           success_count, failure_count, status, source,
                           last_seen_at, last_confirmed_at, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NULL, NOW(), NOW())
                        """,
                        (
                            tenant_id,
                            "description_exact",
                            description,
                            account_code,
                            reason,
                            state["confidence_score"],
                            state["autopilot_eligible"],
                            1,
                            0,
                            0,
                            state["status"],
                            "feedback_learning",
                        ),
                    )
                    inserted += 1

            if partner:
                cur.execute(
                    f"""
                    SELECT id, support_count, success_count, failure_count,
                           last_seen_at, weighted_success_score, weighted_failure_score,
                           usage_count
                    FROM learning_patterns
                    WHERE tenant_id = %s
                      AND pattern_type = %s
                      AND {_normalized_sql_expr("pattern_value")} = %s
                    LIMIT 1
                    """,
                    (tenant_id, "partner", partner),
                )
                existing = cur.fetchone()

                if existing:
                    pid, sc, suc, fc, lsa, wss, wfs, uc = existing
                    sc = int(sc or 0) + 1
                    suc = int(suc or 0)
                    fc = int(fc or 0)
                    wss = float(wss or 0.0)
                    wfs = float(wfs or 0.0)
                    uc = int(uc or 0)
                    state = recalculate_pattern_state(sc, suc, fc, lsa, wss, wfs, uc)

                    cur.execute(
                        """
                        UPDATE learning_patterns
                        SET account_code = %s,
                            reason = %s,
                            confidence_score = %s,
                            autopilot_eligible = %s,
                            support_count = %s,
                            status = %s,
                            source = 'feedback_learning',
                            last_seen_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s AND tenant_id = %s
                        """,
                        (
                            account_code,
                            reason,
                            state["confidence_score"],
                            state["autopilot_eligible"],
                            sc,
                            state["status"],
                            pid,
                            tenant_id,
                        ),
                    )
                    updated += 1
                else:
                    state = recalculate_pattern_state(1, 0, 0, None)
                    cur.execute(
                        """
                        INSERT INTO learning_patterns
                          (tenant_id, pattern_type, pattern_value, account_code, reason,
                           confidence_score, autopilot_eligible, support_count,
                           success_count, failure_count, status, source,
                           last_seen_at, last_confirmed_at, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NULL, NOW(), NOW())
                        """,
                        (
                            tenant_id,
                            "partner",
                            partner,
                            account_code,
                            reason,
                            state["confidence_score"],
                            state["autopilot_eligible"],
                            1,
                            0,
                            0,
                            state["status"],
                            "feedback_learning",
                        ),
                    )
                    inserted += 1

        conn.commit()
        return {
            "tenant_id": tenant_id,
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
    tenant_id: str = "default",
    weight: float = 1.0,
):
    conn = get_db()
    cur = conn.cursor()
    try:
        value = _normalize_pattern_value(pattern_type, pattern_value)
        if not value:
            return {"updated": 0}

        compare_sql = _compare_sql_for_pattern_type(pattern_type)

        if account_code:
            cur.execute(
                f"""
                SELECT id, support_count, success_count, failure_count,
                       last_seen_at, weighted_success_score, weighted_failure_score,
                       usage_count
                FROM learning_patterns
                WHERE tenant_id = %s
                  AND pattern_type = %s
                  AND {compare_sql} = %s
                  AND account_code = %s
                LIMIT 1
                """,
                (tenant_id, pattern_type, value, account_code),
            )
        else:
            cur.execute(
                f"""
                SELECT id, support_count, success_count, failure_count,
                       last_seen_at, weighted_success_score, weighted_failure_score,
                       usage_count
                FROM learning_patterns
                WHERE tenant_id = %s
                  AND pattern_type = %s
                  AND {compare_sql} = %s
                LIMIT 1
                """,
                (tenant_id, pattern_type, value),
            )

        row = cur.fetchone()
        if not row:
            return {"updated": 0}

        pid, sc, suc, fc, _, wss, wfs, uc = row
        sc = int(sc or 0) + 1
        suc = int(suc or 0) + 1
        fc = int(fc or 0)
        wss = float(wss or 0.0) + weight
        wfs = float(wfs or 0.0)
        uc = int(uc or 0) + 1

        state = recalculate_pattern_state(sc, suc, fc, datetime.now(timezone.utc), wss, wfs, uc)

        cur.execute(
            """
            UPDATE learning_patterns
            SET success_count = %s,
                support_count = %s,
                confidence_score = %s,
                autopilot_eligible = %s,
                status = %s,
                weighted_success_score = %s,
                usage_count = %s,
                last_confirmed_at = NOW(),
                last_seen_at = NOW(),
                last_used_at = NOW(),
                updated_at = NOW()
            WHERE id = %s AND tenant_id = %s
            """,
            (
                suc,
                sc,
                state["confidence_score"],
                state["autopilot_eligible"],
                state["status"],
                wss,
                uc,
                pid,
                tenant_id,
            ),
        )
        conn.commit()
        return {"updated": cur.rowcount, "weight_applied": weight}
    finally:
        cur.close()
        conn.close()


def mark_pattern_failure(
    pattern_type: str,
    pattern_value: str,
    account_code: str | None = None,
    tenant_id: str = "default",
    weight: float = 1.5,
):
    conn = get_db()
    cur = conn.cursor()
    try:
        value = _normalize_pattern_value(pattern_type, pattern_value)
        if not value:
            return {"updated": 0}

        compare_sql = _compare_sql_for_pattern_type(pattern_type)

        if account_code:
            cur.execute(
                f"""
                SELECT id, support_count, success_count, failure_count,
                       last_seen_at, weighted_success_score, weighted_failure_score,
                       usage_count
                FROM learning_patterns
                WHERE tenant_id = %s
                  AND pattern_type = %s
                  AND {compare_sql} = %s
                  AND account_code = %s
                LIMIT 1
                """,
                (tenant_id, pattern_type, value, account_code),
            )
        else:
            cur.execute(
                f"""
                SELECT id, support_count, success_count, failure_count,
                       last_seen_at, weighted_success_score, weighted_failure_score,
                       usage_count
                FROM learning_patterns
                WHERE tenant_id = %s
                  AND pattern_type = %s
                  AND {compare_sql} = %s
                LIMIT 1
                """,
                (tenant_id, pattern_type, value),
            )

        row = cur.fetchone()
        if not row:
            return {"updated": 0}

        pid, sc, suc, fc, lsa, wss, wfs, uc = row
        sc = int(sc or 0) + 1
        suc = int(suc or 0)
        fc = int(fc or 0) + 1
        wss = float(wss or 0.0)
        wfs = float(wfs or 0.0) + weight
        uc = int(uc or 0) + 1

        state = recalculate_pattern_state(sc, suc, fc, lsa, wss, wfs, uc)

        cur.execute(
            """
            UPDATE learning_patterns
            SET failure_count = %s,
                support_count = %s,
                confidence_score = %s,
                autopilot_eligible = %s,
                status = %s,
                weighted_failure_score = %s,
                usage_count = %s,
                last_seen_at = NOW(),
                last_used_at = NOW(),
                updated_at = NOW()
            WHERE id = %s AND tenant_id = %s
            """,
            (
                fc,
                sc,
                state["confidence_score"],
                state["autopilot_eligible"],
                state["status"],
                wfs,
                uc,
                pid,
                tenant_id,
            ),
        )
        conn.commit()
        return {"updated": cur.rowcount, "weight_applied": weight}
    finally:
        cur.close()
        conn.close()


def decay_old_patterns(tenant_id: str = "default"):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE learning_patterns
            SET status = 'inactive',
                updated_at = NOW()
            WHERE tenant_id = %s
              AND status IN ('active', 'candidate')
              AND updated_at < NOW() - INTERVAL '45 days'
            """,
            (tenant_id,),
        )
        decayed = cur.rowcount
        conn.commit()
        return {"tenant_id": tenant_id, "decayed": decayed}
    except Exception as e:
        conn.rollback()
        return {"tenant_id": tenant_id, "decayed": 0, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def update_pattern_usage(
    pattern_type: str,
    pattern_value: str,
    account_code: str | None = None,
    tenant_id: str = "default",
):
    conn = get_db()
    cur = conn.cursor()
    try:
        value = _normalize_pattern_value(pattern_type, pattern_value)
        if not value:
            return {"updated": 0}

        compare_sql = _compare_sql_for_pattern_type(pattern_type)

        if account_code:
            cur.execute(
                f"""
                UPDATE learning_patterns
                SET usage_count = COALESCE(usage_count, 0) + 1,
                    last_used_at = NOW(),
                    updated_at = NOW()
                WHERE tenant_id = %s
                  AND pattern_type = %s
                  AND {compare_sql} = %s
                  AND account_code = %s
                """,
                (tenant_id, pattern_type, value, account_code),
            )
        else:
            cur.execute(
                f"""
                UPDATE learning_patterns
                SET usage_count = COALESCE(usage_count, 0) + 1,
                    last_used_at = NOW(),
                    updated_at = NOW()
                WHERE tenant_id = %s
                  AND pattern_type = %s
                  AND {compare_sql} = %s
                """,
                (tenant_id, pattern_type, value),
            )

        conn.commit()
        return {"updated": cur.rowcount}
    finally:
        cur.close()
        conn.close()