"""app/api/services/evidence_bundle_service.py

Evidence Bundle Service — business logic for creating and linking
verifiable audit metadata to approval and posting operations.

Rules:
- No connector calls.
- No Balance.ge activation.
- No approval/posting business logic changes.
- No raw secrets, api_key, password, or credential values in bundles.
- Payload preview is stored as a hash only — never the raw payload body.
- confidence must be in [0.0, 1.0].
- safe_response strips any secret-like keys before returning.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# Keys that must never appear in a safe evidence bundle response
_UNSAFE_KEYS: frozenset[str] = frozenset({
    "api_key",
    "password",
    "token",
    "secret",
    "encrypted_value",
    "raw_connector_payload",
    "raw_secret",
    "decrypted_value",
    "plaintext",
    "private_key",
})


def _strip_unsafe(obj: Any) -> Any:
    """Recursively remove unsafe keys from dicts."""
    if isinstance(obj, dict):
        return {
            k: _strip_unsafe(v)
            for k, v in obj.items()
            if k.lower() not in _UNSAFE_KEYS
        }
    if isinstance(obj, list):
        return [_strip_unsafe(item) for item in obj]
    return obj


class EvidenceBundleService:
    """Service for managing evidence bundle lifecycle."""

    def __init__(self, repository: Any):
        self._repo = repository

    async def create_bundle(
        self,
        tenant_id: str,
        source_type: str,
        source_id: Optional[str] = None,
        source_file_id: Optional[str] = None,
        source_file_hash: Optional[str] = None,
        bank_transaction_id: Optional[str] = None,
        document_id: Optional[str] = None,
        ocr_result_id: Optional[str] = None,
        actor: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a new evidence bundle in draft status."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not source_type or not source_type.strip():
            raise ValueError("source_type is required")

        bundle_data = {
            "tenant_id": tenant_id,
            "source_type": source_type,
            "source_id": source_id,
            "source_file_id": source_file_id,
            "source_file_hash": source_file_hash,
            "bank_transaction_id": bank_transaction_id,
            "document_id": document_id,
            "ocr_result_id": ocr_result_id,
            "ai_reasoning": {},
            "extracted_fields": {},
            "risk_flags": [],
            "confidence": None,
            "status": "draft",
            "created_by": actor,
            "updated_by": actor,
        }

        bundle = await self._repo.insert_bundle(bundle_data)
        await self._repo.insert_event({
            "tenant_id": tenant_id,
            "evidence_bundle_id": str(bundle["id"]),
            "event_type": "created",
            "actor": actor,
            "metadata": _strip_unsafe(metadata or {}),
        })
        return bundle

    async def attach_ai_reasoning(
        self,
        bundle_id: str,
        tenant_id: str,
        ai_reasoning: dict,
        confidence: Optional[float] = None,
        risk_flags: Optional[list] = None,
        actor: Optional[str] = None,
    ) -> Optional[dict]:
        """Attach AI reasoning, confidence, and risk flags to a bundle."""
        if confidence is not None:
            if not (0.0 <= confidence <= 1.0):
                raise ValueError(f"confidence must be between 0 and 1, got {confidence}")

        safe_reasoning = _strip_unsafe(ai_reasoning or {})
        safe_flags = list(risk_flags or [])

        updates: dict = {
            "ai_reasoning": safe_reasoning,
            "risk_flags": safe_flags,
            "updated_by": actor,
        }
        if confidence is not None:
            updates["confidence"] = confidence

        bundle = await self._repo.update_bundle(bundle_id, tenant_id, updates)
        if bundle:
            await self._repo.insert_event({
                "tenant_id": tenant_id,
                "evidence_bundle_id": bundle_id,
                "event_type": "ai_attached",
                "actor": actor,
                "metadata": {"confidence": confidence, "risk_flags_count": len(safe_flags)},
            })
        return bundle

    async def attach_extracted_fields(
        self,
        bundle_id: str,
        tenant_id: str,
        extracted_fields: dict,
        actor: Optional[str] = None,
    ) -> Optional[dict]:
        """Store OCR/extraction output fields in the bundle."""
        safe_fields = _strip_unsafe(extracted_fields or {})
        bundle = await self._repo.update_bundle(bundle_id, tenant_id, {
            "extracted_fields": safe_fields,
            "updated_by": actor,
        })
        if bundle:
            await self._repo.insert_event({
                "tenant_id": tenant_id,
                "evidence_bundle_id": bundle_id,
                "event_type": "fields_attached",
                "actor": actor,
                "metadata": {"fields_count": len(safe_fields)},
            })
        return bundle

    async def link_approval(
        self,
        bundle_id: str,
        tenant_id: str,
        approval_event_id: str,
        journal_draft_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Optional[dict]:
        """Link an approval event and optionally a journal draft to the bundle."""
        updates: dict = {
            "approval_event_id": str(approval_event_id),
            "updated_by": actor,
        }
        if journal_draft_id is not None:
            updates["journal_draft_id"] = str(journal_draft_id)

        bundle = await self._repo.update_bundle(bundle_id, tenant_id, updates)
        if bundle:
            await self._repo.insert_event({
                "tenant_id": tenant_id,
                "evidence_bundle_id": bundle_id,
                "event_type": "approval_linked",
                "actor": actor,
                "event_ref_type": "approval_event",
                "event_ref_id": str(approval_event_id),
                "metadata": {"journal_draft_id": journal_draft_id},
            })
        return bundle

    async def link_posting(
        self,
        bundle_id: str,
        tenant_id: str,
        posting_log_id: str,
        payload_preview_hash: Optional[str] = None,
        connector_provider: Optional[str] = None,
        connector_operation: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Optional[dict]:
        """Link posting log and payload hash to the bundle.

        Only the hash of the payload preview is stored — never the raw payload.
        No connector call is made here.
        """
        updates: dict = {
            "posting_log_id": str(posting_log_id),
            "updated_by": actor,
        }
        if payload_preview_hash is not None:
            updates["payload_preview_hash"] = payload_preview_hash
        if connector_provider is not None:
            updates["connector_provider"] = connector_provider
        if connector_operation is not None:
            updates["connector_operation"] = connector_operation

        bundle = await self._repo.update_bundle(bundle_id, tenant_id, updates)
        if bundle:
            await self._repo.insert_event({
                "tenant_id": tenant_id,
                "evidence_bundle_id": bundle_id,
                "event_type": "posting_linked",
                "actor": actor,
                "event_ref_type": "posting_log",
                "event_ref_id": str(posting_log_id),
                "metadata": {
                    "connector_provider": connector_provider,
                    "connector_operation": connector_operation,
                    "has_payload_hash": payload_preview_hash is not None,
                },
            })
        return bundle

    async def link_journal_entry(
        self,
        bundle_id: str,
        tenant_id: str,
        journal_entry_id: str,
        actor: Optional[str] = None,
    ) -> Optional[dict]:
        """Link a posted journal entry to the bundle."""
        bundle = await self._repo.update_bundle(bundle_id, tenant_id, {
            "journal_entry_id": str(journal_entry_id),
            "updated_by": actor,
        })
        if bundle:
            await self._repo.insert_event({
                "tenant_id": tenant_id,
                "evidence_bundle_id": bundle_id,
                "event_type": "entry_linked",
                "actor": actor,
                "event_ref_type": "journal_entry",
                "event_ref_id": str(journal_entry_id),
                "metadata": {},
            })
        return bundle

    async def get_bundle(self, bundle_id: str, tenant_id: str) -> Optional[dict]:
        """Fetch a bundle by id scoped to tenant."""
        return await self._repo.get_bundle(bundle_id, tenant_id)

    def build_safe_response(self, bundle: dict) -> dict:
        """Return a safe dict that never includes secret-like keys."""
        include = {
            "id", "tenant_id", "source_type", "source_id",
            "source_file_id", "source_file_hash",
            "bank_transaction_id", "document_id", "ocr_result_id",
            "journal_draft_id", "journal_entry_id",
            "approval_event_id", "posting_log_id",
            "connector_provider", "connector_operation",
            "payload_preview_hash",
            "ai_reasoning", "extracted_fields", "risk_flags",
            "confidence", "status",
            "created_at", "updated_at", "created_by", "updated_by",
        }
        safe: dict = {}
        for key in include:
            if key in bundle:
                val = bundle[key]
                # Strip unsafe nested keys from JSONB fields
                if isinstance(val, (dict, list)):
                    val = _strip_unsafe(val)
                safe[key] = val

        # Final guard: remove any unsafe key that snuck in
        for unsafe_key in list(safe.keys()):
            if unsafe_key.lower() in _UNSAFE_KEYS:
                del safe[unsafe_key]

        return safe
