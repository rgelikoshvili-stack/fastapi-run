"""
H53 — Local-only synthetic fixture loader + report snapshot capture.

SAFETY CONTRACT:
- Requires H53_LOCAL_DRY_RUN=1 env var. Will abort otherwise.
- Requires DATABASE_URL pointing to 127.0.0.1:55433 only (H53 local port).
- Verifies fixture SHA-256 before inserting a single row.
- Does NOT import FastAPI, app startup, or any runtime service.
- Does NOT call external APIs or read production .env.
- Loads only: journal_entry_headers, journal_entry_lines, journal_entry_sources.
- Captures local SQL report snapshots after load.
- All data is synthetic — no real PII, no production data.

Usage:
  H53_LOCAL_DRY_RUN=1 \
  DATABASE_URL=postgresql://bridge_hub_h53:<local-disposable-password>@127.0.0.1:55433/bridge_hub_h53 \
  POSTED_LEDGER_REPORTS_ENABLED= \
  python scripts/capture_h53_local_report_snapshots.py
"""

import hashlib
import json
import os
import sys
import urllib.parse

import psycopg2
import psycopg2.extras

FIXTURE_PATH = "tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json"
EXPECTED_SHA256 = "1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299"
ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
REQUIRED_GUARD_VAR = "H53_LOCAL_DRY_RUN"
REQUIRED_GUARD_VALUE = "1"
REQUIRED_PORT = 55433

HEADER_DB_COLS = [
    "id", "tenant_id", "source_draft_id", "posting_log_id", "evidence_bundle_id",
    "entry_date", "posting_date", "period", "status", "source_type",
    "currency", "exchange_rate", "total_debit", "total_credit",
    "created_by", "approved_by", "posted_by",
    "reversed_by_entry_id", "correction_of_entry_id", "metadata_json",
]
LINE_DB_COLS = [
    "id", "tenant_id", "journal_entry_id", "line_no", "account_code",
    "account_name", "debit", "credit", "currency", "exchange_rate", "amount_gel",
]
SOURCE_DB_COLS = [
    "id", "tenant_id", "journal_entry_id", "source_type", "source_id",
]


def abort(msg: str) -> None:
    print(f"[H53] ABORT: {msg}", file=sys.stderr)
    sys.exit(1)


def check_guard() -> None:
    val = os.environ.get(REQUIRED_GUARD_VAR, "")
    if val != REQUIRED_GUARD_VALUE:
        abort(
            f"{REQUIRED_GUARD_VAR} is not set to '{REQUIRED_GUARD_VALUE}'. "
            "This helper must only run during the approved H53 local dry-run."
        )
    print(f"[H53] Guard check passed: {REQUIRED_GUARD_VAR}={val}")


def check_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        abort("DATABASE_URL is not set.")
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 5432
    if host not in ALLOWED_HOSTS:
        abort(
            f"DATABASE_URL host '{host}' is not allowed. "
            f"Only {ALLOWED_HOSTS} are permitted. "
            "This helper must only connect to the local disposable H53 Docker DB."
        )
    if port != REQUIRED_PORT:
        abort(
            f"DATABASE_URL port '{port}' is not the expected H53 port ({REQUIRED_PORT}). "
            "Refusing to connect to a non-H53 local DB."
        )
    redacted = url.replace(f":{parsed.password}@", ":***@") if parsed.password else url
    print(f"[H53] DATABASE_URL host={host} port={port} — local-only check PASSED ({redacted})")
    return url


def check_feature_flag() -> None:
    flag = os.environ.get("POSTED_LEDGER_REPORTS_ENABLED", "")
    if flag.strip().lower() in ("1", "true", "yes"):
        abort(
            "POSTED_LEDGER_REPORTS_ENABLED is enabled. "
            "This helper must not run with the feature flag active."
        )
    print("[H53] POSTED_LEDGER_REPORTS_ENABLED is OFF — check PASSED")


def verify_fixture_sha256(path: str) -> None:
    if not os.path.exists(path):
        abort(f"Fixture not found at: {path}")
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    actual = sha.hexdigest().upper()
    if actual != EXPECTED_SHA256:
        abort(
            f"Fixture SHA-256 mismatch!\n"
            f"  Expected: {EXPECTED_SHA256}\n"
            f"  Actual:   {actual}\n"
            "Refusing to load — fixture file has been modified."
        )
    print(f"[H53] Fixture SHA-256 verified: {actual}")


def insert_headers(conn, headers: list) -> int:
    with conn.cursor() as cur:
        for h in headers:
            row = {}
            for col in HEADER_DB_COLS:
                val = h.get(col)
                if isinstance(val, dict):
                    val = json.dumps(val)
                row[col] = val
            cols_sql = ", ".join(HEADER_DB_COLS)
            vals_sql = ", ".join(["%s"] * len(HEADER_DB_COLS))
            cur.execute(
                f"INSERT INTO journal_entry_headers ({cols_sql}) VALUES ({vals_sql})",
                [row[c] for c in HEADER_DB_COLS],
            )
    return len(headers)


def insert_lines(conn, lines: list) -> int:
    with conn.cursor() as cur:
        for line in lines:
            row = {col: line.get(col) for col in LINE_DB_COLS}
            cols_sql = ", ".join(LINE_DB_COLS)
            vals_sql = ", ".join(["%s"] * len(LINE_DB_COLS))
            cur.execute(
                f"INSERT INTO journal_entry_lines ({cols_sql}) VALUES ({vals_sql})",
                [row[c] for c in LINE_DB_COLS],
            )
    return len(lines)


def insert_sources(conn, sources: list) -> int:
    with conn.cursor() as cur:
        for src in sources:
            row = {col: src.get(col) for col in SOURCE_DB_COLS}
            cols_sql = ", ".join(SOURCE_DB_COLS)
            vals_sql = ", ".join(["%s"] * len(SOURCE_DB_COLS))
            cur.execute(
                f"INSERT INTO journal_entry_sources ({cols_sql}) VALUES ({vals_sql})",
                [row[c] for c in SOURCE_DB_COLS],
            )
    return len(sources)


def capture_snapshots(conn) -> dict:
    snapshots = {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

        # 1. Trial balance by account
        cur.execute("""
            SELECT
                account_code,
                account_name,
                SUM(debit)  AS sum_debit,
                SUM(credit) AS sum_credit,
                SUM(debit) - SUM(credit) AS net_balance,
                COUNT(*)    AS line_count
            FROM journal_entry_lines
            GROUP BY account_code, account_name
            ORDER BY account_code
        """)
        snapshots["trial_balance"] = [dict(r) for r in cur.fetchall()]

        # 2. Total balance check
        cur.execute("""
            SELECT
                SUM(debit)           AS total_debit,
                SUM(credit)          AS total_credit,
                SUM(debit)-SUM(credit) AS difference
            FROM journal_entry_lines
        """)
        snapshots["balance_check"] = dict(cur.fetchone())

        # 3. Status summary
        cur.execute("""
            SELECT status, COUNT(*) AS header_count
            FROM journal_entry_headers
            GROUP BY status
            ORDER BY status
        """)
        snapshots["status_summary"] = [dict(r) for r in cur.fetchall()]

        # 4. Tenant summary
        cur.execute("""
            SELECT
                h.tenant_id,
                COUNT(DISTINCT h.id)  AS header_count,
                COUNT(l.id)           AS line_count,
                SUM(l.debit)          AS total_debit,
                SUM(l.credit)         AS total_credit
            FROM journal_entry_headers h
            JOIN journal_entry_lines l ON l.journal_entry_id = h.id
            GROUP BY h.tenant_id
            ORDER BY h.tenant_id
        """)
        snapshots["tenant_summary"] = [dict(r) for r in cur.fetchall()]

        # 5. Source summary
        cur.execute("""
            SELECT source_type, COUNT(*) AS source_count
            FROM journal_entry_sources
            GROUP BY source_type
            ORDER BY source_type
        """)
        snapshots["source_summary"] = [dict(r) for r in cur.fetchall()]

        # 6. Correction/reversal summary
        cur.execute("""
            SELECT
                COUNT(CASE WHEN correction_of_entry_id IS NOT NULL THEN 1 END) AS correction_count,
                COUNT(CASE WHEN reversed_by_entry_id   IS NOT NULL THEN 1 END) AS reversal_count,
                COUNT(CASE WHEN correction_of_entry_id IS NOT NULL
                            OR  reversed_by_entry_id   IS NOT NULL THEN 1 END) AS linked_entry_count
            FROM journal_entry_headers
        """)
        snapshots["correction_reversal_summary"] = dict(cur.fetchone())

        # 7. General ledger summary (by period + account)
        cur.execute("""
            SELECT
                h.period,
                l.account_code,
                l.account_name,
                SUM(l.debit)  AS period_debit,
                SUM(l.credit) AS period_credit
            FROM journal_entry_headers h
            JOIN journal_entry_lines l ON l.journal_entry_id = h.id
            GROUP BY h.period, l.account_code, l.account_name
            ORDER BY h.period, l.account_code
        """)
        snapshots["general_ledger_summary"] = [dict(r) for r in cur.fetchall()]

    return snapshots


def format_decimal(v) -> str:
    if v is None:
        return "0.00"
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return str(v)


def main() -> None:
    print("[H53] Starting H53 local report snapshot capture")
    print("[H53] All data is synthetic — no real PII, no production data")

    check_guard()
    db_url = check_database_url()
    check_feature_flag()
    verify_fixture_sha256(FIXTURE_PATH)

    print(f"[H53] Loading fixture from: {FIXTURE_PATH}")
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    headers = data.get("journal_entry_headers", [])
    lines   = data.get("journal_entry_lines",   [])
    sources = data.get("journal_entry_sources", [])
    print(f"[H53] Fixture: {len(headers)} headers, {len(lines)} lines, {len(sources)} sources")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        h_count = insert_headers(conn, headers)
        l_count = insert_lines(conn, lines)
        s_count = insert_sources(conn, sources)
        conn.commit()
        total = h_count + l_count + s_count
        print(f"[H53] COMMIT OK — {h_count} headers, {l_count} lines, {s_count} sources, {total} total rows")

        # Read back snapshots in a fresh read transaction
        conn.autocommit = True
        snaps = capture_snapshots(conn)

        print("\n" + "=" * 60)
        print("H53 LOCAL REPORT SNAPSHOTS")
        print("=" * 60)

        bc = snaps["balance_check"]
        td = format_decimal(bc["total_debit"])
        tc = format_decimal(bc["total_credit"])
        diff = format_decimal(bc["difference"])
        balanced = abs(float(bc["difference"] or 0)) < 0.01
        print(f"\n[BALANCE CHECK] total_debit={td} GEL  total_credit={tc} GEL  diff={diff}  balanced={balanced}")

        print("\n[TRIAL BALANCE BY ACCOUNT]")
        for row in snaps["trial_balance"]:
            print(f"  {row['account_code']:8s}  {str(row['account_name'])[:30]:30s}  "
                  f"dr={format_decimal(row['sum_debit']):>12s}  "
                  f"cr={format_decimal(row['sum_credit']):>12s}  "
                  f"net={format_decimal(row['net_balance']):>12s}  lines={row['line_count']}")

        print("\n[STATUS SUMMARY]")
        for row in snaps["status_summary"]:
            print(f"  status={row['status']:20s}  count={row['header_count']}")

        print("\n[TENANT SUMMARY]")
        for row in snaps["tenant_summary"]:
            print(f"  tenant={row['tenant_id']:20s}  headers={row['header_count']}  "
                  f"lines={row['line_count']}  dr={format_decimal(row['total_debit'])}  "
                  f"cr={format_decimal(row['total_credit'])}")

        print("\n[SOURCE SUMMARY]")
        for row in snaps["source_summary"]:
            print(f"  source_type={row['source_type']:20s}  count={row['source_count']}")

        cr = snaps["correction_reversal_summary"]
        print(f"\n[CORRECTION/REVERSAL SUMMARY]")
        print(f"  correction_count={cr['correction_count']}  reversal_count={cr['reversal_count']}  linked={cr['linked_entry_count']}")

        print("\n[GENERAL LEDGER SUMMARY (by period + account)]")
        for row in snaps["general_ledger_summary"]:
            print(f"  period={row['period']}  {row['account_code']:8s}  "
                  f"dr={format_decimal(row['period_debit']):>12s}  cr={format_decimal(row['period_credit']):>12s}")

        print("\n" + "=" * 60)
        print("SNAPSHOT CAPTURE COMPLETE")
        print(f"balanced={balanced}")
        print("No production DB was touched. All data is synthetic.")
        print("=" * 60)

        # Output machine-readable JSON for evidence
        output = {
            "snapshot_id": "H53-SNAPSHOT-2026-001",
            "fixture_sha256": EXPECTED_SHA256,
            "db_target": "127.0.0.1:55433 (local Docker only)",
            "rows_loaded": {"headers": h_count, "lines": l_count, "sources": s_count, "total": total},
            "balance_check": {
                "total_debit": str(bc["total_debit"]),
                "total_credit": str(bc["total_credit"]),
                "difference": str(bc["difference"]),
                "balanced": balanced,
            },
            "trial_balance_rows": len(snaps["trial_balance"]),
            "status_summary": [dict(r) for r in snaps["status_summary"]],
            "tenant_summary": [{"tenant_id": r["tenant_id"], "header_count": r["header_count"],
                                 "line_count": r["line_count"],
                                 "total_debit": str(r["total_debit"]),
                                 "total_credit": str(r["total_credit"])} for r in snaps["tenant_summary"]],
            "source_summary": [dict(r) for r in snaps["source_summary"]],
            "correction_reversal_summary": {k: int(v or 0) for k, v in cr.items()},
        }
        print("\n[H53 JSON OUTPUT]")
        print(json.dumps(output, indent=2, default=str))

    except Exception as exc:
        conn.rollback()
        print(f"[H53] ERROR: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()

    print("[H53] No production DB was touched.")


if __name__ == "__main__":
    main()
