"""
H52 — Local-only synthetic fixture loader.

SAFETY CONTRACT:
- Requires H52_LOCAL_DRY_RUN=1 env var. Will abort otherwise.
- Requires DATABASE_URL pointing to localhost or 127.0.0.1 only.
- Verifies fixture SHA-256 before inserting a single row.
- Does NOT import FastAPI, app startup, or any runtime service.
- Does NOT call external APIs or read production .env.
- Loads only: journal_entry_headers, journal_entry_lines, journal_entry_sources.
- All data is synthetic — no real PII, no production data.

Usage:
  H52_LOCAL_DRY_RUN=1 \
  DATABASE_URL=postgresql://bridge_hub_h52:<local-disposable-password>@127.0.0.1:55432/bridge_hub_h52 \
  POSTED_LEDGER_REPORTS_ENABLED= \
  python scripts/load_h52_synthetic_fixture_local_only.py
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
REQUIRED_GUARD_VAR = "H52_LOCAL_DRY_RUN"
REQUIRED_GUARD_VALUE = "1"

# Fields to skip when inserting (not in DB schema)
HEADER_SKIP_FIELDS = {"_comment"}

# DB schema columns for each table
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
    print(f"[H52 LOADER] ABORT: {msg}", file=sys.stderr)
    sys.exit(1)


def check_guard() -> None:
    val = os.environ.get(REQUIRED_GUARD_VAR, "")
    if val != REQUIRED_GUARD_VALUE:
        abort(
            f"{REQUIRED_GUARD_VAR} is not set to '{REQUIRED_GUARD_VALUE}'. "
            "This loader must only run during the approved H52 local dry-run. "
            f"Set {REQUIRED_GUARD_VAR}=1 to proceed."
        )
    print(f"[H52 LOADER] Guard check passed: {REQUIRED_GUARD_VAR}={val}")


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
            "This loader must only connect to the local disposable Docker DB."
        )
    if port != 55432:
        abort(
            f"DATABASE_URL port '{port}' is not the expected H52 port (55432). "
            "Refusing to connect to a non-H52 local DB."
        )
    print(f"[H52 LOADER] DATABASE_URL host={host} port={port} — local-only check PASSED")
    return url


def check_feature_flag() -> None:
    flag = os.environ.get("POSTED_LEDGER_REPORTS_ENABLED", "")
    if flag.strip().lower() in ("1", "true", "yes"):
        abort(
            "POSTED_LEDGER_REPORTS_ENABLED is enabled. "
            "This loader must not run with the feature flag active."
        )
    print("[H52 LOADER] POSTED_LEDGER_REPORTS_ENABLED is OFF — check PASSED")


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
    print(f"[H52 LOADER] Fixture SHA-256 verified: {actual}")


def load_fixture(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def make_row(record: dict, cols: list, skip: set) -> tuple:
    row = []
    for col in cols:
        if col in skip:
            continue
        val = record.get(col)
        if isinstance(val, dict):
            val = json.dumps(val)
        row.append(val)
    return tuple(row)


def insert_headers(conn, headers: list) -> int:
    inserted = 0
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
            inserted += 1
    return inserted


def insert_lines(conn, lines: list) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for line in lines:
            row = {col: line.get(col) for col in LINE_DB_COLS}
            cols_sql = ", ".join(LINE_DB_COLS)
            vals_sql = ", ".join(["%s"] * len(LINE_DB_COLS))
            cur.execute(
                f"INSERT INTO journal_entry_lines ({cols_sql}) VALUES ({vals_sql})",
                [row[c] for c in LINE_DB_COLS],
            )
            inserted += 1
    return inserted


def insert_sources(conn, sources: list) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for src in sources:
            row = {col: src.get(col) for col in SOURCE_DB_COLS}
            cols_sql = ", ".join(SOURCE_DB_COLS)
            vals_sql = ", ".join(["%s"] * len(SOURCE_DB_COLS))
            cur.execute(
                f"INSERT INTO journal_entry_sources ({cols_sql}) VALUES ({vals_sql})",
                [row[c] for c in SOURCE_DB_COLS],
            )
            inserted += 1
    return inserted


def main() -> None:
    print("[H52 LOADER] Starting H52 local synthetic fixture loader")
    print("[H52 LOADER] All data is synthetic — no real PII, no production data")

    check_guard()
    db_url = check_database_url()
    check_feature_flag()
    verify_fixture_sha256(FIXTURE_PATH)

    print(f"[H52 LOADER] Loading fixture from: {FIXTURE_PATH}")
    data = load_fixture(FIXTURE_PATH)

    headers = data.get("journal_entry_headers", [])
    lines = data.get("journal_entry_lines", [])
    sources = data.get("journal_entry_sources", [])

    print(f"[H52 LOADER] Fixture contents: {len(headers)} headers, {len(lines)} lines, {len(sources)} sources")
    parsed_for_log = urllib.parse.urlparse(db_url)
    redacted = db_url.replace(f":{parsed_for_log.password}@", ":***@") if parsed_for_log.password else db_url
    print(f"[H52 LOADER] Connecting to local DB: {redacted}")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        h_count = insert_headers(conn, headers)
        print(f"[H52 LOADER] Inserted journal_entry_headers: {h_count}")

        l_count = insert_lines(conn, lines)
        print(f"[H52 LOADER] Inserted journal_entry_lines: {l_count}")

        s_count = insert_sources(conn, sources)
        print(f"[H52 LOADER] Inserted journal_entry_sources: {s_count}")

        conn.commit()
        print(f"[H52 LOADER] COMMIT OK — total rows: {h_count + l_count + s_count}")
        print("[H52 LOADER] Fixture load complete. DB target: local Docker only.")
        print("[H52 LOADER] No production DB was touched.")

    except Exception as exc:
        conn.rollback()
        print(f"[H52 LOADER] ERROR — rolled back: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
