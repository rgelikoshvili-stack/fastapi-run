from app.services.preview_service import build_draft_preview
from app.api.services.approval_service import approve_draft_service, reject_draft_service


def run_chat_action_workflow(payload: dict) -> dict:
    action = payload.get("action", {}) or {}
    action_name = action.get("action")
    mode = action.get("mode")

    if mode == "preview":
        return {
            "ok": True,
            "mode": "preview",
            "preview": build_draft_preview(payload),
        }

    if action_name == "approval.approve":
        draft_id = payload.get("draft_id")
        if draft_id is None:
            return {
                "ok": False,
                "mode": "execute",
                "message": "draft_id is required for approval",
                "error": "MISSING_DRAFT_ID",
            }

        tenant_id = payload.get("tenant_id", "default")
        return approve_draft_service(int(draft_id), tenant_id=tenant_id)

    if action_name == "approval.reject":
        draft_id = payload.get("draft_id")
        reason = payload.get("reason", "")

        if draft_id is None:
            return {
                "ok": False,
                "mode": "execute",
                "message": "draft_id is required for rejection",
                "error": "MISSING_DRAFT_ID",
            }

        tenant_id = payload.get("tenant_id", "default")
        return reject_draft_service(int(draft_id), reason, tenant_id=tenant_id)

    if action_name == "posting.apply":
        return {
            "ok": True,
            "mode": "execute",
            "message": "Posting execution route prepared",
            "data": {
                "action": "posting.apply",
                "status": "not_implemented_yet",
            },
            "error": None,
        }

    if action_name == "dashboard.show":
        return {
            "ok": True,
            "mode": "read",
            "message": "Dashboard view requested",
            "data": {
                "action": "dashboard.show",
            },
            "error": None,
        }

    return {
        "ok": True,
        "mode": "noop",
        "message": "No executable workflow matched",
        "data": {
            "action": action_name or "unknown",
        },
        "error": None,
    }