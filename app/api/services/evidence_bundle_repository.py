"""app/api/services/evidence_bundle_repository.py

Evidence Bundle Repository — thin data-access abstraction.

Provides mockable async methods for insert/update/get operations on
evidence_bundles and evidence_bundle_events.

Rules:
- No business logic here.
- No connector calls.
- No approval/posting behavior changes.
- No Balance.ge activation.
- All methods are async and accept an asyncpg connection.
- Unit tests mock this class entirely — no real DB required in tests.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


class EvidenceBundleRepository:
    """Data-access layer for evidence_bundles and evidence_bundle_events."""

    def __init__(self, conn: Any):
        self._conn = conn

    async def insert_bundle(self, bundle_data: dict) -> dict:
        """Insert a new evidence bundle row. Returns the inserted row as dict."""
        from app.api.db import _q
        row = await self._conn.fetchrow(
            _q("""
                INSERT INTO evidence_bundles
                    (tenant_id, source_type, source_id, source_file_id,
                     source_file_hash, bank_transaction_id, document_id,
                     ocr_result_id, journal_draft_id, journal_entry_id,
                     approval_event_id, posting_log_id, connector_provider,
                     connector_operation, payload_preview_hash,
                     ai_reasoning, extracted_fields, risk_flags,
                     confidence, status, created_by, updated_by)
                VALUES
                    (%s, %s, %s, %s,
                     %s, %s, %s,
                     %s, %s, %s,
                     %s, %s, %s,
                     %s, %s,
                     %s::jsonb, %s::jsonb, %s::jsonb,
                     %s, %s, %s, %s)
                RETURNING *
            """),
            bundle_data["tenant_id"],
            bundle_data["source_type"],
            bundle_data.get("source_id"),
            bundle_data.get("source_file_id"),
            bundle_data.get("source_file_hash"),
            bundle_data.get("bank_transaction_id"),
            bundle_data.get("document_id"),
            bundle_data.get("ocr_result_id"),
            bundle_data.get("journal_draft_id"),
            bundle_data.get("journal_entry_id"),
            bundle_data.get("approval_event_id"),
            bundle_data.get("posting_log_id"),
            bundle_data.get("connector_provider"),
            bundle_data.get("connector_operation"),
            bundle_data.get("payload_preview_hash"),
            json.dumps(bundle_data.get("ai_reasoning") or {}),
            json.dumps(bundle_data.get("extracted_fields") or {}),
            json.dumps(bundle_data.get("risk_flags") or []),
            bundle_data.get("confidence"),
            bundle_data.get("status", "draft"),
            bundle_data.get("created_by"),
            bundle_data.get("updated_by"),
        )
        return dict(row)

    async def update_bundle(self, bundle_id: str, tenant_id: str, updates: dict) -> Optional[dict]:
        """Apply partial updates to an evidence bundle. Returns updated row or None."""
        from app.api.db import _q
        allowed = {
            "journal_draft_id", "journal_entry_id", "approval_event_id",
            "posting_log_id", "connector_provider", "connector_operation",
            "payload_preview_hash", "ai_reasoning", "extracted_fields",
            "risk_flags", "confidence", "status", "updated_by",
            "source_file_hash", "bank_transaction_id", "document_id",
            "ocr_result_id",
        }
        safe_updates = {k: v for k, v in updates.items() if k in allowed}
        if not safe_updates:
            return None

        set_clauses = []
        params: list = []
        idx = 1
        jsonb_cols = {"ai_reasoning", "extracted_fields", "risk_flags"}
        for col, val in safe_updates.items():
            if col in jsonb_cols:
                set_clauses.append(f"{col} = ${idx}::jsonb")
                params.append(json.dumps(val))
            else:
                set_clauses.append(f"{col} = ${idx}")
                params.append(val)
            idx += 1

        set_clauses.append(f"updated_at = NOW()")
        params.extend([bundle_id, tenant_id])

        sql = (
            f"UPDATE evidence_bundles SET {', '.join(set_clauses)} "
            f"WHERE id = ${idx} AND tenant_id = ${idx + 1} RETURNING *"
        )
        row = await self._conn.fetchrow(sql, *params)
        return dict(row) if row else None

    async def insert_event(self, event_data: dict) -> dict:
        """Insert an evidence_bundle_events row."""
        from app.api.db import _q
        row = await self._conn.fetchrow(
            _q("""
                INSERT INTO evidence_bundle_events
                    (tenant_id, evidence_bundle_id, event_type,
                     actor, event_ref_type, event_ref_id, metadata)
                VALUES (%s, %s::uuid, %s, %s, %s, %s, %s::jsonb)
                RETURNING *
            """),
            event_data["tenant_id"],
            event_data["evidence_bundle_id"],
            event_data["event_type"],
            event_data.get("actor"),
            event_data.get("event_ref_type"),
            event_data.get("event_ref_id"),
            json.dumps(event_data.get("metadata") or {}),
        )
        return dict(row)

    async def get_bundle(self, bundle_id: str, tenant_id: str) -> Optional[dict]:
        """Fetch a single evidence bundle by id and tenant_id."""
        from app.api.db import _q
        row = await self._conn.fetchrow(
            _q("SELECT * FROM evidence_bundles WHERE id = %s::uuid AND tenant_id = %s"),
            bundle_id, tenant_id,
        )
        return dict(row) if row else None

    async def list_bundle_events(self, bundle_id: str, tenant_id: str) -> list[dict]:
        """List all events for an evidence bundle."""
        from app.api.db import _q
        rows = await self._conn.fetch(
            _q("""
                SELECT * FROM evidence_bundle_events
                WHERE evidence_bundle_id = %s::uuid AND tenant_id = %s
                ORDER BY created_at ASC
            """),
            bundle_id, tenant_id,
        )
        return [dict(r) for r in rows]
