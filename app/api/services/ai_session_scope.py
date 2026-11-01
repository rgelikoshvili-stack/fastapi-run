"""User+tenant scoped AI session identifiers (Chat177).

Existing DB chat rows are left untouched. New and cleared sessions use a
namespaced opaque key so user A cannot read or delete user B's chat by guessing
a public session_id. No migration or direct DB changes are performed here.
"""
from __future__ import annotations

import hashlib
import re

from fastapi import HTTPException, Request

from app.api.authz import require_signed_tenant_permission

_SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def scoped_ai_session(request: Request, session_id: str | None) -> tuple[str, str | None]:
    tenant_id = require_signed_tenant_permission(request, "chat:use")
    signed_user = getattr(request.state, "user_id", None)
    if not isinstance(signed_user, (str, int)) or not str(signed_user).strip():
        raise HTTPException(status_code=403, detail="Signed user identity required")

    if session_id is None:
        return tenant_id, None
    if not isinstance(session_id, str) or not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise HTTPException(status_code=422, detail="Invalid AI session ID")

    # Length-delimited input prevents ambiguity between tenant/user/session.
    fields = (tenant_id, str(signed_user), session_id)
    raw = "".join(f"{len(v)}:{v}" for v in fields).encode("utf-8")
    return tenant_id, "usr2_" + hashlib.sha256(raw).hexdigest()
