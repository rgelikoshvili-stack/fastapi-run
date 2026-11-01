"""FIN-04: reviewed tenant-specific classifications for NEW Bridge-authority writes.

This module never creates a COA mapping from a draft or an ERP payload.
Only privileged, independently reviewed mapping rows may be read. Migration
is a separate, unapplied Draft; missing storage/privileges fail closed.
Historical posted-ledger account_type values are not rewritten.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

from app.api.db import _q, get_conn, require_current_tenant_id, _validate_tenant_id
from app.api.services.posted_ledger_reporting import (
    UnclassifiedLedgerAccount, canonical_account_type, classify_ledger_lines,
)

_CLASS_TYPES = frozenset({"asset", "liability", "equity", "income", "expense"})
_SOURCE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[^\s\x00-\x1f]{1,80}$")


def _enabled() -> bool:
    return os.getenv("TENANT_COA_MAPPINGS_ENABLED", "").lower() in {"1", "true", "yes"}


def _deny() -> None:
    raise UnclassifiedLedgerAccount("LEDGER_ACCOUNT_UNCLASSIFIED: approved tenant COA mapping required")


def _posting_date(value) -> date:
    try:
        if isinstance(value, datetime):
            raise ValueError("datetime is not an accounting date")
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise ValueError("missing accounting date")
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        _deny()


def _verified_row(row, tenant_id: str, requested: set[str], day: date):
    """Validate returned evidence, not just a query WHERE clause."""
    try:
        item = dict(row)
        code = item["account_code"]
        start = item["effective_from"]
        end = item.get("effective_until")
        kind = item["account_type"]
        if (
            item["tenant_id"] != tenant_id
            or not isinstance(code, str) or code not in requested
            or not _CODE.fullmatch(code) or canonical_account_type(code) is not None
            or kind not in _CLASS_TYPES
            or not isinstance(start, date) or isinstance(start, datetime)
            or (end is not None and (not isinstance(end, date) or isinstance(end, datetime)))
            or start > day or (end is not None and (end < day or end < start))
            or not isinstance(item.get("approved_at"), datetime)
            or not isinstance(item.get("approved_by"), str) or not item["approved_by"].strip()
            or not isinstance(item.get("source_system"), str) or not item["source_system"].strip()
            or not isinstance(item.get("source_revision"), str) or not item["source_revision"].strip()
            or not isinstance(item.get("source_sha256"), str)
            or not _SOURCE_SHA256.fullmatch(item["source_sha256"])
        ):
            _deny()
        return code, kind
    except (KeyError, TypeError, AttributeError, ValueError):
        _deny()


async def _fetch_verified(conn, tenant_id: str, unknown: set[str], day: date) -> dict[str, str]:
    # Rows are approved only if persisted by a privileged, reviewed ingest.
    # No latest-version guess: overlapping effective rows are ambiguous and fail.
    try:
        rows = await conn.fetch(_q("""
            SELECT tenant_id, account_code, account_type, effective_from,
                   effective_until, source_system, source_revision, source_sha256,
                   approved_by, approved_at
            FROM tenant_coa_mappings
            WHERE tenant_id = %s AND account_code = ANY(%s::text[])
              AND effective_from <= %s
              AND (effective_until IS NULL OR effective_until >= %s)
        """), tenant_id, sorted(unknown), day, day)
    except Exception:
        _deny()
    found: dict[str, str] = {}
    for row in rows:
        code, kind = _verified_row(row, tenant_id, unknown, day)
        if code in found:
            _deny()
        found[code] = kind
    if set(found) != unknown:
        _deny()
    return found


async def classify_tenant_ledger_lines(lines, tenant_id, entry_date, *, conn=None):
    """Never allow caller account_type hints to override canonical/reviewed data.

    Standard accounts retain their long-standing static code mapping without
    database queries. Custom codes require explicit rollout, authorized tenant
    context and a complete reviewed mapping set, BEFORE connector dispatch.
    """
    unknown = {
        str(line.get("account_code", "")).strip() for line in lines
        if canonical_account_type(line.get("account_code", "")) is None
    }
    if not unknown:
        return classify_ledger_lines(lines)
    if not _enabled():
        _deny()
    try:
        _validate_tenant_id(tenant_id)
        require_current_tenant_id(tenant_id)
    except ValueError:
        _deny()
    if any(not _CODE.fullmatch(code) for code in unknown):
        _deny()
    day = _posting_date(entry_date)
    if conn is not None:
        approved = await _fetch_verified(conn, tenant_id, unknown, day)
    else:
        try:
            async with get_conn() as scoped_conn:
                approved = await _fetch_verified(scoped_conn, tenant_id, unknown, day)
        except UnclassifiedLedgerAccount:
            raise
        except Exception:
            _deny()
    result = []
    for line in lines:
        code = str(line.get("account_code", "")).strip()
        kind = canonical_account_type(code) or approved.get(code)
        if kind is None:
            _deny()
        result.append(dict(line, account_type=kind))
    return result
