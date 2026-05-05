"""Bulk-add require_permission import + call to route files missing it."""
import re
import os

PERM_MAP = {
    "routes_bank_process.py":      "bank:upload",
    "routes_collaboration.py":     "approval:write",
    "routes_expense_articles.py":  "reports:read",
    "routes_invoices.py":          "reports:read",
    "routes_invoice.py":           "approval:write",
    "routes_learning.py":          "patterns:manage",
    "routes_learning_explain.py":  "patterns:view",
    "routes_outgoing.py":          "approval:write",
    "routes_patterns.py":          "patterns:manage",
    "routes_pdf_report.py":        "reports:read",
    "routes_qa.py":                "reports:read",
    "routes_search.py":            "search:read",
    "routes_security.py":          "settings:write",
    "routes_tax.py":               "reports:read",
    "routes_transaction_memory.py": "reports:read",
    "routes_notifications.py":     "notifications:write",
    "routes_ai_chat.py":           "chat:use",
    "routes_ai_journal.py":        "approval:write",
    "routes_ai_recommend.py":      "approval:write",
    "routes_audit.py":             "audit:read",
    "routes_audit_engine.py":      "audit:read",
    "routes_audit_log.py":         "audit:read",
    "routes_chat.py":              "chat:use",
    "routes_claude_chat.py":       "chat:use",
    "routes_client_portal.py":     "reports:read",
    "routes_dashboard.py":         "dashboard:view",
    "routes_dashboard_live.py":    "dashboard:view",
    "routes_email_inbound.py":     "settings:write",
    "routes_email_invoice.py":     "approval:write",
    "routes_rbac.py":              "tenants:manage",
    "routes_rsge_credentials.py":  "settings:write",
    "routes_system.py":            "dashboard:admin",
    "routes_tenants.py":           "tenants:manage",
    "routes_transaction_ai.py":    "approval:write",
    "routes_2fa.py":               "settings:write",
    "routes_worker.py":            "dashboard:admin",
}

IMPORT_LINE = "from app.api.authz import require_permission\n"
BASE = "app/api"

updated = []
skipped = []

for filename, default_perm in PERM_MAP.items():
    fpath = os.path.join(BASE, filename)
    if not os.path.exists(fpath):
        skipped.append(f"NOT FOUND: {fpath}")
        continue
    with open(fpath, encoding="utf-8") as f:
        original = f.read()
    if "require_permission" in original:
        skipped.append(f"ALREADY DONE: {filename}")
        continue

    lines = original.splitlines(keepends=True)

    # Step 1: find best import insertion point (after last top-level import)
    insert_at = 0
    for i, line in enumerate(lines):
        if (line.startswith("from ") or line.startswith("import ")) and not line.startswith("from __future__"):
            insert_at = i + 1
    lines.insert(insert_at, IMPORT_LINE)

    # Step 2: after every endpoint function def, inject require_permission
    # before the first real statement in the body
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        result.append(line)

        # detect "async def" or "def" that is an endpoint (indented 0 or 4 spaces)
        m = re.match(r'^( {0,4})(async def |def )(\w+)\s*\(', line)
        if m:
            fn_name = m.group(3)
            fn_indent = m.group(1) + "    "  # body indent

            # skip lines that are part of the function signature (multi-line args)
            j = i + 1
            while j < len(lines) and ":" not in lines[j - 1]:
                result.append(lines[j])
                j += 1

            # skip optional docstring
            if j < len(lines):
                stripped = lines[j].strip()
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    quote = stripped[:3]
                    result.append(lines[j])
                    j += 1
                    # multi-line docstring
                    while j < len(lines) and quote not in lines[j]:
                        result.append(lines[j])
                        j += 1
                    if j < len(lines):
                        result.append(lines[j])
                        j += 1

            # now inject require_permission before the first real statement
            if j < len(lines) and lines[j].strip():
                perm = default_perm
                result.append(f"{fn_indent}require_permission(request, \"{perm}\")\n")

            i = j
            continue

        i += 1

    content = "".join(result)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    updated.append(filename)

print(f"\nUpdated ({len(updated)}):")
for f in updated:
    print(f"  + {f}")
print(f"\nSkipped ({len(skipped)}):")
for f in skipped:
    print(f"  - {f}")
