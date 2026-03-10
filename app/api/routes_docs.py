from fastapi import APIRouter
from app.api.response_utils import ok_response

router = APIRouter(prefix="/docs-hub", tags=["docs"])

SPRINT_HISTORY = {
    "project": "Bridge Hub v1.0.0",
    "sprints": {
        "sprint_51_52": {
            "revision": "fastapi-run-00153-bht",
            "date": "2026-03-07",
            "summary": "Diagnostic fixes P1-P4",
            "completed": [
                "P1: /finance/kpi status→state",
                "P1: /search/query id→run_id fix",
                "P1: DB credentials → env vars",
                "P2: Global exception handler 404/422/500",
                "P2: ai-journal/list route",
                "P2: Response standardization",
                "P3: Timestamp TEXT→TIMESTAMPTZ migration",
                "P3: ::timestamp cast removal",
                "P3: duplicate app/api/app/ deleted",
                "P3: 12 inactive routes archived to _archive/",
                "P4: 82 backup main.py* files deleted",
                "Pydantic validation (JournalRequest)",
                "audit_events table created",
                "audit_service.log_event() added",
            ],
            "new_files": [
                "app/api/db.py",
                "app/api/audit_service.py",
                "app/api/response_utils.py",
            ],
            "git_commits": [
                "866c7aa — Fix all diagnostic issues",
                "49ef379 — timestamp migration",
                "6834c45 — archive 12 inactive routes",
                "d2c1a23 — Pydantic validation, business scenario tests",
                "974b3e5 — audit service + ai-journal/list fix",
            ],
        },
        "sprint_53": {
            "revision": "fastapi-run-00166-zmr",
            "date": "2026-03-08",
            "summary": "Bank Pipeline — ყველა 8 ეტაპი",
            "completed": [
                "ეტაპი 1: Parser universalization (CSV/XLSX/XML)",
                "ეტაპი 2: Amount logic + fallback columns",
                "ეტაპი 3: Rule Engine — 17 კატეგორია",
                "ეტაპი 4: Journal Draft Generator (Dr/Cr)",
                "ეტაპი 5: Debit/Credit posting logic",
                "ეტაპი 6: Confidence Scoring 4-factor",
                "ეტაპი 7: Approval/Review Queue",
                "ეტაპი 8: Audit Trail",
                "ეტაპი 9: Batch Processing /bank-csv/process",
                "ეტაპი 10: Export Excel",
                "ეტაპი 11: რეალური TBC Bank XLSX ტესტი (78-79% auto)",
                "ეტაპი 12: Invoice PDF Pipeline",
            ],
            "new_files": [
                "app/api/bank_statement_parser.py",
                "app/api/transaction_classifier.py",
                "app/api/journal_generator.py",
                "app/api/invoice_parser.py",
                "app/api/routes_bank_process.py",
                "app/api/routes_approval.py",
                "app/api/routes_export_journal.py",
                "app/api/routes_invoice.py",
            ],
            "new_endpoints": [
                "POST /bank-csv/process",
                "GET /approval/queue",
                "POST /approval/approve/{id}",
                "POST /approval/reject/{id}",
                "GET /approval/audit",
                "GET /export/journal/excel",
                "POST /invoice/parse",
            ],
            "db_tables": [
                "journal_drafts",
                "audit_events",
            ],
            "classifier_categories": [
                "6100 income", "7100 cost_of_goods", "7110 rent",
                "7120 salary", "7130 utility", "7140 software",
                "7150 bank_fee", "7160 transport", "7170 marketing",
                "7180 office", "7185 delivery", "7190 default",
                "7191 grocery", "7192 household", "1210 transfer",
                "1210 conversion", "3100 tax",
            ],
            "confidence_scoring": {
                "keyword_match": "+0.4",
                "partner_hint": "+0.2",
                "operation_code": "+0.2",
                "direction": "+0.2",
                "review_threshold": "< 0.6",
            },
            "tbc_bank_test": {
                "file1": "total=27 drafted=21 review=6 failed=0 (78% auto)",
                "file2": "total=14 drafted=11 review=3 failed=0 (79% auto)",
            },
            "git_commits": [
                "bdad5b1 — parser stabilization, rule engine x12, journal draft",
                "b6a9922 — batch processing /bank-csv/process",
                "d28c35a — approval queue, batch→DB save",
                "fd512b8 — audit trail on bank pipeline",
                "9b75d2d — Excel export",
                "4fab9c2 — real TBC Bank XLSX support, confidence fix",
                "d2ae768 — invoice PDF parser, all 8 etapi complete",
            ],
        },
    },
    "next_sprint_54": [
        "Balance.ge API integration",
        "1C connector (export)",
        "Frontend Dashboard (React/HTML)",
        "Multi-tenant support",
        "Georgian classifier keywords expansion",
    ],
}


@router.get("/sprints")
def get_all_sprints():
    return ok_response("Sprint history", SPRINT_HISTORY)


@router.get("/sprints/{sprint_id}")
def get_sprint(sprint_id: str):
    sprint = SPRINT_HISTORY["sprints"].get(sprint_id)
    if not sprint:
        keys = list(SPRINT_HISTORY["sprints"].keys())
        return ok_response("Available sprints", {"available": keys})
    return ok_response(f"Sprint {sprint_id}", sprint)