from decimal import Decimal
from typing import Optional, List, Dict, Any

from app.api.db import get_db
from app.api.services.normalization_service import normalize_text


def upsert_erp_posting_memory(
    source_system: str = "balance",
    external_entry_id: Optional[str] = None,
    external_doc_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    description: Optional[str] = None,
    partner: Optional[str] = None,
    amount: Optional[float] = None,
    currency: str = "GEL",
    debit_account: Optional[str] = None,
    credit_account: Optional[str] = None,
    account_code: Optional[str] = None,
    direction: Optional[str] = None,
    posting_date: Optional[str] = None,
) -> Dict[str, Any]:
    conn = get_db()
    cur = conn.cursor()

    normalized_description = normalize_text(description)
    normalized_partner = normalize_text(partner)

    cur.execute(
        """
        SELECT id, evidence_count
        FROM erp_posting_memory
        WHERE source_system = %s
          AND COALESCE(external_entry_id, '') = COALESCE(%s, '')
          AND COALESCE(external_doc_id, '') = COALESCE(%s, '')
          AND COALESCE(account_code, '') = COALESCE(%s, '')
        LIMIT 1
        """,
        (source_system, external_entry_id, external_doc_id, account_code),
    )
    existing = cur.fetchone()

    if existing:
        row_id, evidence_count = existing
        cur.execute(
            """
            UPDATE erp_posting_memory
            SET description = %s,
                normalized_description = %s,
                partner = %s,
                normalized_partner = %s,
                amount = %s,
                currency = %s,
                debit_account = %s,
                credit_account = %s,
                doc_type = %s,
                direction = %s,
                posting_date = %s,
                evidence_count = %s,
                updated_at = NOW(),
                last_seen_at = NOW()
            WHERE id = %s
            RETURNING id, source_system, account_code, evidence_count
            """,
            (
                description,
                normalized_description,
                partner,
                normalized_partner,
                amount,
                currency,
                debit_account,
                credit_account,
                doc_type,
                direction,
                posting_date,
                int(evidence_count or 0) + 1,
                row_id,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO erp_posting_memory (
                source_system,
                external_entry_id,
                external_doc_id,
                doc_type,
                description,
                normalized_description,
                partner,
                normalized_partner,
                amount,
                currency,
                debit_account,
                credit_account,
                account_code,
                direction,
                posting_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, source_system, account_code, evidence_count
            """,
            (
                source_system,
                external_entry_id,
                external_doc_id,
                doc_type,
                description,
                normalized_description,
                partner,
                normalized_partner,
                amount,
                currency,
                debit_account,
                credit_account,
                account_code,
                direction,
                posting_date,
            ),
        )

    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return {
        "ok": True,
        "memory": {
            "id": row[0],
            "source_system": row[1],
            "account_code": row[2],
            "evidence_count": row[3],
        },
    }


def find_erp_memory_match(
    description: Optional[str] = None,
    partner: Optional[str] = None,
    amount: Optional[float] = None,
    doc_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cur = conn.cursor()

    normalized_description = normalize_text(description)
    normalized_partner = normalize_text(partner)

    # priority:
    # 1) same partner + same normalized desc
    # 2) same desc
    # 3) same partner
    # 4) nearest amount tolerance

    cur.execute(
        """
        SELECT id, account_code, debit_account, credit_account,
               description, partner, amount, doc_type, evidence_count, confidence
        FROM erp_posting_memory
        WHERE normalized_partner = %s
          AND normalized_description = %s
        ORDER BY evidence_count DESC, updated_at DESC
        LIMIT 1
        """,
        (normalized_partner, normalized_description),
    )
    row = cur.fetchone()

    if not row and normalized_description:
        cur.execute(
            """
            SELECT id, account_code, debit_account, credit_account,
                   description, partner, amount, doc_type, evidence_count, confidence
            FROM erp_posting_memory
            WHERE normalized_description = %s
            ORDER BY evidence_count DESC, updated_at DESC
            LIMIT 1
            """,
            (normalized_description,),
        )
        row = cur.fetchone()

    if not row and normalized_partner:
        cur.execute(
            """
            SELECT id, account_code, debit_account, credit_account,
                   description, partner, amount, doc_type, evidence_count, confidence
            FROM erp_posting_memory
            WHERE normalized_partner = %s
            ORDER BY evidence_count DESC, updated_at DESC
            LIMIT 1
            """,
            (normalized_partner,),
        )
        row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "account_code": row[1],
        "debit_account": row[2],
        "credit_account": row[3],
        "description": row[4],
        "partner": row[5],
        "amount": float(row[6]) if row[6] is not None else None,
        "doc_type": row[7],
        "evidence_count": row[8],
        "confidence": float(row[9]) if row[9] is not None else 0.90,
        "source": "erp_history",
    }


def list_erp_posting_memory(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, source_system, description, partner, amount, account_code,
               debit_account, credit_account, evidence_count, last_seen_at
        FROM erp_posting_memory
        ORDER BY id DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()

    cur.close()
    conn.close()

    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "source_system": r[1],
            "description": r[2],
            "partner": r[3],
            "amount": float(r[4]) if r[4] is not None else None,
            "account_code": r[5],
            "debit_account": r[6],
            "credit_account": r[7],
            "evidence_count": r[8],
            "last_seen_at": r[9].isoformat() if r[9] else None,
        })

    return items