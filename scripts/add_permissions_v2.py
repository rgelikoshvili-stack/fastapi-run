"""Safe bulk-add of require_permission to route files.

Strategy:
  1. Parse with ast to verify valid Python before and after
  2. Only add import after the LAST top-level import statement (not inside parentheses)
  3. Only inject require_permission as first statement INSIDE function body,
     after the colon on the def line (and after any docstring)
  4. Only inject if the function already has 'request' in its parameters
"""
import ast
import re
import os

PERM_MAP = {
    "routes_ai_chat.py":           "chat:use",
    "routes_ai_recommend.py":      "approval:write",
    "routes_audit.py":             "audit:read",
    "routes_audit_log.py":         "audit:read",
    "routes_chat.py":              "chat:use",
    "routes_claude_chat.py":       "chat:use",
    "routes_client_portal.py":     "reports:read",
    "routes_email_inbound.py":     "settings:write",
    "routes_expense_articles.py":  "reports:read",
    "routes_learning.py":          "patterns:manage",
    "routes_notifications.py":     "notifications:write",
    "routes_outgoing.py":          "approval:write",
    "routes_search.py":            "search:read",
    "routes_tenants.py":           "tenants:manage",
    "routes_transaction_memory.py": "reports:read",
}

IMPORT_LINE = "from app.api.authz import require_permission"
BASE = "app/api"


def has_request_param(func_node):
    """Check if function has a 'request' parameter."""
    for arg in func_node.args.args:
        if arg.arg == "request":
            return True
    return False


def process_file(fpath, default_perm):
    with open(fpath, encoding="utf-8") as f:
        original = f.read()

    # Verify it parses cleanly
    try:
        ast.parse(original)
    except SyntaxError as e:
        print(f"SKIP {fpath}: already has syntax error at line {e.lineno}")
        return False

    if "require_permission" in original:
        print(f"SKIP {fpath}: already has require_permission")
        return False

    lines = original.splitlines()

    # Step 1: find last top-level import line (not inside parentheses)
    last_import_line = 0
    paren_depth = 0
    for i, line in enumerate(lines):
        paren_depth += line.count("(") - line.count(")")
        if paren_depth == 0:
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("import "):
                last_import_line = i

    # Insert import after last import
    lines.insert(last_import_line + 1, IMPORT_LINE)

    # Step 2: parse AST to find endpoint functions and their body start lines
    # (after inserting the import, line numbers shift by 1 — we'll work on the new content)
    new_content = "\n".join(lines)
    try:
        tree = ast.parse(new_content)
    except SyntaxError as e:
        print(f"SKIP {fpath}: import insertion broke syntax at line {e.lineno}")
        return False

    # Collect injection points: (line_number_1indexed, indent, permission)
    injections = []  # list of (line_idx_0based, indent_str, perm)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not has_request_param(node):
            continue
        # Find the first statement in the body
        if not node.body:
            continue
        first_stmt = node.body[0]
        # If first statement is a docstring (Expr with Constant), skip to next
        if (isinstance(first_stmt, ast.Expr) and
                isinstance(first_stmt.value, ast.Constant) and
                isinstance(first_stmt.value.value, str)):
            if len(node.body) > 1:
                inject_line = node.body[1].lineno - 1  # 0-based
            else:
                inject_line = first_stmt.end_lineno  # after docstring
        else:
            inject_line = first_stmt.lineno - 1  # 0-based

        # Determine indentation from the inject line
        target_line = lines[inject_line] if inject_line < len(lines) else ""
        indent = re.match(r"^(\s*)", target_line).group(1)
        injections.append((inject_line, indent, default_perm))

    # Apply injections in reverse order so line numbers stay valid
    injections.sort(key=lambda x: x[0], reverse=True)
    for inject_line, indent, perm in injections:
        lines.insert(inject_line, f'{indent}require_permission(request, "{perm}")')

    final_content = "\n".join(lines)

    # Verify final content parses cleanly
    try:
        ast.parse(final_content)
    except SyntaxError as e:
        print(f"SKIP {fpath}: final content has syntax error at line {e.lineno}")
        return False

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(final_content)
    return True


updated = []
skipped = []

for filename, perm in PERM_MAP.items():
    fpath = os.path.join(BASE, filename)
    if not os.path.exists(fpath):
        skipped.append(f"NOT FOUND: {filename}")
        continue
    if process_file(fpath, perm):
        updated.append(filename)
    else:
        skipped.append(filename)

print(f"\nUpdated ({len(updated)}): {updated}")
print(f"Skipped ({len(skipped)}): {skipped}")
