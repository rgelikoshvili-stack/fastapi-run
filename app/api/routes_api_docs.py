from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.api.response_utils import ok_response

router = APIRouter(prefix="/api-docs", tags=["api-docs"])

BASE = "https://fastapi-run-226875230147.us-central1.run.app"

POSTMAN_COLLECTION = {
    "info": {
        "name": "Bridge Hub API v1.0.0",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        "description": "Bridge Hub — Georgian Accounting & Bank Pipeline API"
    },
    "variable": [
        {"key": "base_url", "value": BASE},
        {"key": "admin_key", "value": "admin-key-2026"},
        {"key": "accountant_key", "value": "accountant-key-2026"},
    ],
    "item": [
        {
            "name": "🏥 Health",
            "item": [
                {"name": "Health Check", "request": {"method": "GET", "url": "{{base_url}}/health"}},
            ]
        },
        {
            "name": "🏦 Bank Pipeline",
            "item": [
                {"name": "Process Bank CSV", "request": {"method": "POST", "url": "{{base_url}}/bank-csv/process",
                    "header": [{"key": "Content-Type", "value": "multipart/form-data"}]}},
                {"name": "Approval Queue", "request": {"method": "GET", "url": "{{base_url}}/approval/queue"}},
                {"name": "Approve Draft", "request": {"method": "POST", "url": "{{base_url}}/approval/approve/1"}},
                {"name": "Reject Draft", "request": {"method": "POST", "url": "{{base_url}}/approval/reject/1"}},
                {"name": "Audit Log", "request": {"method": "GET", "url": "{{base_url}}/approval/audit"}},
            ]
        },
        {
            "name": "📒 Journal",
            "item": [
                {"name": "Export Excel", "request": {"method": "GET", "url": "{{base_url}}/export/journal/excel"}},
                {"name": "PDF Report", "request": {"method": "POST", "url": "{{base_url}}/reports/pdf",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"report_type":"journal","date_from":"2026-01-01"}'}}},
            ]
        },
        {
            "name": "🔄 Reconciliation",
            "item": [
                {"name": "Run Reconciliation", "request": {"method": "POST", "url": "{{base_url}}/reconcile/run",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"date_from":"2026-01-01","date_to":"2026-12-31"}'}}},
                {"name": "Summary", "request": {"method": "GET", "url": "{{base_url}}/reconcile/summary"}},
            ]
        },
        {
            "name": "💰 Balance.ge",
            "item": [
                {"name": "Test Connection", "request": {"method": "POST", "url": "{{base_url}}/balance-ge/test-connection",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"api_key":"your-key","company_id":"12345"}'}}},
                {"name": "Export Format", "request": {"method": "GET", "url": "{{base_url}}/balance-ge/export-format/1"}},
                {"name": "Post Journals", "request": {"method": "POST", "url": "{{base_url}}/balance-ge/post-journals",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"draft_ids":[1,2],"api_key":"your-key","company_id":"12345"}'}}},
            ]
        },
        {
            "name": "🔗 1C Connector",
            "item": [
                {"name": "Preview", "request": {"method": "GET", "url": "{{base_url}}/1c/preview/approved"}},
                {"name": "Export XML", "request": {"method": "POST", "url": "{{base_url}}/1c/export",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"status":"approved","format":"xml"}'}}},
                {"name": "Export CSV", "request": {"method": "POST", "url": "{{base_url}}/1c/export",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"status":"approved","format":"csv"}'}}},
            ]
        },
        {
            "name": "🔐 Auth & RBAC",
            "item": [
                {"name": "My Profile", "request": {"method": "GET", "url": "{{base_url}}/auth/me",
                    "header": [{"key": "X-Api-Key", "value": "{{admin_key}}"}]}},
                {"name": "List Users (Admin)", "request": {"method": "GET", "url": "{{base_url}}/auth/users",
                    "header": [{"key": "X-Api-Key", "value": "{{admin_key}}"}]}},
                {"name": "Roles", "request": {"method": "GET", "url": "{{base_url}}/auth/roles"}},
            ]
        },
        {
            "name": "👥 Tenants",
            "item": [
                {"name": "List Tenants", "request": {"method": "GET", "url": "{{base_url}}/tenants/list"}},
                {"name": "My Tenant", "request": {"method": "GET", "url": "{{base_url}}/tenants/me",
                    "header": [{"key": "X-Api-Key", "value": "alte-key-2026"}]}},
            ]
        },
        {
            "name": "🔔 Webhooks",
            "item": [
                {"name": "Events List", "request": {"method": "GET", "url": "{{base_url}}/webhooks/events"}},
                {"name": "Create Webhook", "request": {"method": "POST", "url": "{{base_url}}/webhooks/create",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"name":"My Hook","url":"https://your-site.com/webhook","events":["draft.approved"]}'}}},
                {"name": "Trigger", "request": {"method": "POST", "url": "{{base_url}}/webhooks/trigger",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"event":"draft.approved","payload":{"draft_id":1}}'}}},
                {"name": "Logs", "request": {"method": "GET", "url": "{{base_url}}/webhooks/logs"}},
            ]
        },
        {
            "name": "📊 Dashboard",
            "item": [
                {"name": "Dashboard v1", "request": {"method": "GET", "url": "{{base_url}}/ui/dashboard"}},
                {"name": "Dashboard v2 (Charts)", "request": {"method": "GET", "url": "{{base_url}}/ui/dashboard/v2"}},
            ]
        },
        {
            "name": "📧 Notifications",
            "item": [
                {"name": "Test Email", "request": {"method": "POST", "url": "{{base_url}}/notifications/test",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"to":"you@example.com","subject":"Test","message":"Hello"}'}}},
                {"name": "Review Required", "request": {"method": "POST", "url": "{{base_url}}/notifications/review-required",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": '{"to":"accountant@company.ge"}'}}},
            ]
        },
        {
            "name": "🗂 Docs Hub",
            "item": [
                {"name": "Sprint History", "request": {"method": "GET", "url": "{{base_url}}/docs-hub/sprints"}},
            ]
        },
    ]
}

@router.get("/postman", response_class=JSONResponse)
def get_postman_collection():
    return POSTMAN_COLLECTION

@router.get("/endpoints")
def list_all_endpoints():
    endpoints = []
    for folder in POSTMAN_COLLECTION["item"]:
        for req in folder.get("item", []):
            endpoints.append({
                "folder": folder["name"],
                "name": req["name"],
                "method": req["request"]["method"],
                "url": req["request"]["url"].replace("{{base_url}}", BASE),
            })
    return ok_response("All endpoints", {"count": len(endpoints), "endpoints": endpoints})
