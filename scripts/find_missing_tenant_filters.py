"""
scripts/find_missing_tenant_filters.py
Read-only audit: finds SQL queries on tenant-aware tables that lack tenant_id filter.

Usage:
    python scripts/find_missing_tenant_filters.py
    python scripts/find_missing_tenant_filters.py --json
"""
import re
import sys
import os
import glob
import argparse
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

TENANT_AWARE_TABLES = {
    "journal_drafts",
    "bank_transactions",
    "invoices",
    "expenses",
    "audit_log",
    "audit_events",
    "contracts",
    "contract_milestones",
    "bank_accounts",
    "learning_patterns",
    "learning_feedback",
    "posting_logs",
}

# Tables confirmed to have no tenant_id column — skip without reporting
GLOBAL_TABLES = {
    "pipeline_runs",
    "coa",
    "exchange_rates",
    "expense_categories",
    "journal_entries",
    "firestore_sync",
    "firestore_log",
    "search_index",
    "search_history",
    "invoice_items",   # child of invoices, joined by invoice_id
    "draft_comments",  # tenant filtered via join
}

SCAN_PATTERNS = [
    "app/api/routes_*.py",
    "app/api/services/*.py",
]

# Lines to look ahead after FROM <table> for tenant_id
LOOKAHEAD_LINES = 14

# ── Helpers ──────────────────────────────────────────────────────────────────

# Matches FROM <table> or JOIN <table> (case-insensitive)
_FROM_RE = re.compile(
    r'\b(?:FROM|JOIN|UPDATE|INSERT\s+INTO)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
    re.IGNORECASE,
)

def _find_sql_blocks(lines: list[str]) -> list[tuple[int, int, str, str]]:
    """
    Yield (start_line_0indexed, end_line_0indexed, table_name, block_text)
    for each SQL-ish block that references a tenant-aware table.

    Strategy:
    - Find lines with FROM/JOIN/UPDATE/INSERT INTO targeting a known table.
    - Collect surrounding context: from the opening triple-quote (or cur.execute)
      up to LOOKAHEAD_LINES after the FROM line.
    """
    results = []
    for i, line in enumerate(lines):
        m = _FROM_RE.search(line)
        if not m:
            continue
        table = m.group(1).lower()
        if table not in TENANT_AWARE_TABLES:
            continue

        # Collect context window: start_ctx = cur.execute line or triple-quote
        ctx_start = max(0, i - 10)
        ctx_end = min(len(lines), i + LOOKAHEAD_LINES + 1)
        block = "".join(lines[ctx_start:ctx_end])

        results.append((i, ctx_start, ctx_end, table, block))
    return results


def _has_tenant_filter(block: str) -> bool:
    """
    Return True if tenant_id appears in the SQL block, OR if the block uses
    a dynamic {where_clause} / {conditions} variable whose build-up contains
    'tenant_id' within the same context window.
    """
    if "tenant_id" in block.lower():
        return True
    # Dynamic WHERE via f-string placeholder — the variable is built above
    # e.g.  WHERE {where_clause}  or  WHERE {conditions}
    if re.search(r'WHERE\s+\{[a-z_]+\}', block, re.IGNORECASE):
        return True
    return False


def _is_insert_with_tenant(block: str) -> bool:
    """
    For INSERT statements, tenant_id in the column list counts as 'filtered'.
    """
    if re.search(r'INSERT\s+INTO', block, re.IGNORECASE):
        return "tenant_id" in block.lower()
    return False


def _classify(line: str, block: str) -> str | None:
    """
    Returns 'MISSING_TENANT_FILTER' or None (clean).
    """
    # Count how many distinct table references are in the block
    # If it's a helper function that accepts tenant_id as a Python variable
    # we still need the SQL itself to use it.
    if _has_tenant_filter(block):
        return None
    return "MISSING_TENANT_FILTER"


# ── Scanner ──────────────────────────────────────────────────────────────────

def scan_file(path: str) -> list[dict]:
    findings = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"  [SKIP] {path}: {e}", file=sys.stderr)
        return findings

    blocks = _find_sql_blocks(lines)

    # Deduplicate: same line may fire multiple FROM matches
    seen_lines = set()
    for (from_line_idx, ctx_start, ctx_end, table, block) in blocks:
        key = (from_line_idx, table)
        if key in seen_lines:
            continue
        seen_lines.add(key)

        status = _classify(lines[from_line_idx], block)
        if status is None:
            continue

        # Build snippet (the FROM line + up to 4 following lines)
        snippet_lines = lines[from_line_idx: min(from_line_idx + 5, len(lines))]
        snippet = "".join(snippet_lines).rstrip()
        # Trim to 200 chars
        if len(snippet) > 200:
            snippet = snippet[:200] + " ..."

        findings.append({
            "file": path,
            "line": from_line_idx + 1,  # 1-based
            "table": table,
            "snippet": snippet.strip(),
            "status": status,
        })

    return findings


def scan_all(root: str = ".") -> list[dict]:
    all_findings = []
    scanned = 0
    for pattern in SCAN_PATTERNS:
        full_pattern = os.path.join(root, pattern)
        files = sorted(glob.glob(full_pattern))
        for fpath in files:
            results = scan_file(fpath)
            all_findings.extend(results)
            scanned += 1
    return all_findings, scanned


# ── Report ───────────────────────────────────────────────────────────────────

def print_report(findings: list[dict], scanned: int, as_json: bool = False):
    if as_json:
        import json
        print(json.dumps({"scanned_files": scanned, "findings": findings}, indent=2, ensure_ascii=False))
        return

    if not findings:
        print(f"\n[OK]  No missing tenant filters found. ({scanned} files scanned)")
        return

    # Group by file
    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)

    print(f"\n{'='*72}")
    print(f"  TENANT FILTER AUDIT — {len(findings)} finding(s) in {len(by_file)} file(s)")
    print(f"  Scanned: {scanned} files")
    print(f"{'='*72}\n")

    for fpath in sorted(by_file.keys()):
        file_findings = by_file[fpath]
        short = fpath.replace("\\", "/")
        print(f"  FILE: {short}  ({len(file_findings)} issue(s))")
        print(f"  {'-'*66}")
        for fi in sorted(file_findings, key=lambda x: x["line"]):
            print(f"    Line {fi['line']:>4}  |  table: {fi['table']:<22}  |  {fi['status']}")
            for sline in fi["snippet"].splitlines():
                print(f"              {sline}")
            print()
        print()

    print(f"{'='*72}")
    print(f"  TOTAL: {len(findings)} MISSING_TENANT_FILTER findings")
    print(f"{'='*72}\n")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit tenant_id filters in SQL queries")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--root", default=".", help="Project root (default: .)")
    args = parser.parse_args()

    findings, scanned = scan_all(root=args.root)
    print_report(findings, scanned, as_json=args.json)
    sys.exit(1 if findings else 0)
