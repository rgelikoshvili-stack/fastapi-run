"""Chat198 FIN-12: one-shot OFFLINE fence proposal, never a dispatch lease.

Unregistered service, no router/worker/connector/network/ledger write.
The database candidate is an UNAPPLIED Draft. A fence proposal is an
audit-only observation of a PREPARED intent and never vendor idempotency
certification, ownership of an external lease, or permission to send/retry.

The caller must supply authenticated tenant context, a trusted JWT-subject
mapping from a separately reviewed boundary, and a transaction-scoped
connection. Role strings passed by public clients must not be trusted.
"""
from __future__ import annotations

import re
from uuid import UUID

from app.api.authz import has_role_permission
from app.api.db import _q, require_current_tenant_id

_TARGETS = frozenset(("balance", "onec", "oris"))
_SHA = re.compile(r"^[0-9a-f]{64}$")


class FenceProposalUnavailable(ValueError):
    """Fail closed: no dispatch, lease reuse, or ERP effect may be inferred."""


def _deny(code: str):
    raise FenceProposalUnavailable(code)


def fence_proposal_decision(state, *, expired=False, epoch=None):
    """Even a claimed expired lease or fresh epoch cannot allow ERP delivery."""
    return {
        "next_action": (
            "VENDOR_CONTRACT_HOLD"
            if isinstance(state, str) and state == "prepared"
            else "NOT_ELIGIBLE"
        ),
        "dispatch_allowed": False,
        "retry_allowed": False,
        "confirm_allowed": False,
        "ledger_write_allowed": False,
        "lease_authoritative": False,
        "provider_idempotency_certified": False,
    }


def _scope(conn, tenant_id, outbox_id):
    try:
        require_current_tenant_id(tenant_id)
    except (TypeError, ValueError):
        _deny("FIN12_FENCE_TENANT_UNAUTHORIZED")
    if conn.is_in_transaction() is not True:
        _deny("FIN12_FENCE_TRANSACTION_REQUIRED")
    if not isinstance(outbox_id, (str, UUID)):
        _deny("FIN12_FENCE_ID_INVALID")
    try:
        uid = UUID(str(outbox_id))
    except (ValueError, TypeError, AttributeError):
        _deny("FIN12_FENCE_ID_INVALID")
    if str(uid) != str(outbox_id):
        _deny("FIN12_FENCE_ID_INVALID")
    return uid


def _owner(subject, role):
    if (not isinstance(subject, str) or not 1 <= len(subject) <= 200
            or subject != subject.strip()
            or subject.casefold() in ("anon", "anonymous", "system",
                                      "human", "default")
            or any(ord(ch) <= 32 or ord(ch) == 127 for ch in subject)):
        _deny("FIN12_FENCE_TRUSTED_OWNER_REQUIRED")
    if role not in ("accountant", "admin") or not has_role_permission(role, "approval:write"):
        _deny("FIN12_FENCE_ROLE_FORBIDDEN")
    return subject


async def prepare_fence_proposal(conn, *, tenant_id, outbox_id,
                                 owner_subject, owner_role):
    """One-shot evidence record with an epoch fixed at ONE. Not a real lease.

    SELECT ... FOR UPDATE serializes proposal creation with SQL updates to the
    source intent on this connection. Unique (tenant,outbox) blocks concurrent
    owners/reclaims. Even after a hypothetical expiration there is NO reissue,
    retry, or vendor dispatch. Never commit a proposal from a failed transaction.
    """
    uid = _scope(conn, tenant_id, outbox_id)
    subject = _owner(owner_subject, owner_role)
    source = await conn.fetchrow(_q("""
        SELECT id,tenant_id,state,source_type,source_id,target_system,
               idempotency_key,payload_sha256,
               provider_receipt_id,provider_verified_at
          FROM posting_outbox_intents
         WHERE id=%s AND tenant_id=%s FOR UPDATE
    """), uid, tenant_id)
    if source is None:
        _deny("FIN12_FENCE_SOURCE_NOT_FOUND")
    row = dict(source)
    if row["state"] != "prepared":
        _deny("FIN12_FENCE_SOURCE_NOT_PREPARED")
    if (row["tenant_id"] != tenant_id
            or row["source_type"] != "journal_draft"
            or not isinstance(row["source_id"], str)
            or not 1 <= len(row["source_id"].strip()) <= 256
            or row["target_system"] not in _TARGETS
            or not isinstance(row["idempotency_key"], str)
            or not _SHA.fullmatch(row["idempotency_key"])
            or not isinstance(row["payload_sha256"], str)
            or not _SHA.fullmatch(row["payload_sha256"])
            or row["provider_receipt_id"] is not None
            or row["provider_verified_at"] is not None):
        _deny("FIN12_FENCE_SOURCE_INTEGRITY_UNAVAILABLE")

    record = await conn.fetchrow(_q("""
        INSERT INTO posting_outbox_fence_proposals(
            tenant_id,outbox_id,source_id,target_system,idempotency_key,
            payload_sha256,owner_subject,owner_role
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id,outbox_id) DO NOTHING
        RETURNING id,fence_epoch
    """), tenant_id, uid, row["source_id"], row["target_system"],
        row["idempotency_key"], row["payload_sha256"],
        subject, owner_role)
    if record is None:
        _deny("FIN12_FENCE_ALREADY_PROPOSED")
    if record["fence_epoch"] != 1:
        _deny("FIN12_FENCE_EPOCH_UNAUTHORIZED")
    return {
        "proposal_id": str(record["id"]),
        "intent_id": str(uid),
        "fence_epoch": record["fence_epoch"],
        **fence_proposal_decision("prepared"),
    }
