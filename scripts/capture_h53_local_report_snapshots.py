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


def abort(msg):
    print(f"[H53] ABORT: {msg}", file=sys.stderr)
    sys.exit(1)


def check_guard():
    val = os.environ.get(REQUIRED_GUARD_VAR, "")
    if val != REQUIRED_GUARD_VALUE:
        abort(f"{REQUIRED_GUARD_VAR} must be '1'. Set {REQUIRED_GUARD_VAR}=1 to proceed.")
    print(f"[H53] Guard: {REQUIRED_GUARD_VAR}={val} OK")


def check_database_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        abort("DATABASE_URL not set.")
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 5432
    if host not in ALLOWED_HOSTS:
        abort(f"Host '{host}' not allowed. Only {ALLOWED_HOSTS}.")
    if port != REQUIRED_PORT:
        abort(f"Port '{port}' is not H53 port ({REQUIRED_PORT}).")
    redacted = url.replace(f":{parsed.password}@", ":***@") if parsed.password else url
    print(f"[H53] DB: {redacted} — local-only PASS")
    return url


def check_feature_flag():
    flag = os.environ.get("POSTED_LEDGER_REPORTS_ENABLED", "")
    if flag.strip().lower() in ("1", "true", "yes"):
        abort("POSTED_LEDGER_REPORTS_ENABLED is enabled — refusing to run.")
    print("[H53] POSTED_LEDGER_REPORTS_ENABLED OFF — PASS")


def verify_fixture_sha256(path):
    if not os.path.exists(path):
        abort(f"Fixture not found: {path}")
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    actual = sha.hexdigest().upper()
    if actual != EXPECTED_SHA256:
        abort(f"Fixture SHA-256 mismatch! Expected={EXPECTED_SHA256} Actual={actual}")
    print(f"[H53] Fixture SHA-256 verified: {actual}")


def insert_headers(conn, headers):
    with conn.cursor() as cur:
        for h in headers:
            row = {col: json.dumps(h[col]) if isinstance(h.get(col), dict) else h.get(col) for col in HEADER_DB_COLS}
            cols = ", ".join(HEADER_DB_COLS)
            vals = ", ".join(["%s"] * len(HEADER_DB_COLS))
            cur.execute(f"INSERT INTO journal_entry_headers ({cols}) VALUES ({vals})", [row[c] for c in HEADER_DB_COLS])
    return len(headers)


def insert_lines(conn, lines):
    with conn.cursor() as cur:
        for line in lines:
            row = {col: line.get(col) for col in LINE_DB_COLS}
            cols = ", ".join(LINE_DB_COLS)
            vals = ", ".join(["%s"] * len(LINE_DB_COLS))
            cur.execute(f"INSERT INTO journal_entry_lines ({cols}) VALUES ({vals})", [row[c] for c in LINE_DB_COLS])
    return len(lines)


def insert_sources(conn, sources):
    with conn.cursor() as cur:
        for src in sources:
            row = {col: src.get(col) for col in SOURCE_DB_COLS}
            cols = ", ".join(SOURCE_DB_COLS)
            vals = ", ".join(["%s"] * len(SOURCE_DB_COLS))
            cur.execute(f"INSERT INTO journal_entry_sources ({cols}) VALUES ({vals})", [row[c] for c in SOURCE_DB_COLS])
    return len(sources)


def capture_snapshots(conn):
    snaps = {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT l.account_code, l.account_name,
                   SUM(l.debit) AS sum_debit, SUM(l.credit) AS sum_credit,
                   SUM(l.debit)-SUM(l.credit) AS net_balance, COUNT(*) AS line_count
            FROM journal_entry_lines l
            JOIN journal_entry_headers h ON h.id=l.journal_entry_id
            WHERE h.tenant_id='tenant_alpha' AND h.status IN ('posted','correction')
            GROUP BY l.account_code, l.account_name ORDER BY l.account_code""")
        snaps["trial_balance"] = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT SUM(debit) AS total_debit, SUM(credit) AS total_credit, SUM(debit)-SUM(credit) AS difference FROM journal_entry_lines")
        snaps["balance_check"] = dict(cur.fetchone())

        cur.execute("""
            SELECT SUM(l.debit) AS total_volume_dr, SUM(l.credit) AS total_volume_cr
            FROM journal_entry_lines l JOIN journal_entry_headers h ON h.id=l.journal_entry_id
            WHERE h.tenant_id='tenant_alpha' AND h.status IN ('posted','correction')""")
        snaps["standard_net_volume"] = dict(cur.fetchone())

        cur.execute("""
            SELECT SUM(CASE WHEN l.account_code LIKE '4%' THEN l.credit-l.debit ELSE 0 END) AS total_income,
                   SUM(CASE WHEN l.account_code LIKE '5%' THEN l.debit-l.credit ELSE 0 END) AS total_expense,
                   SUM(CASE WHEN l.account_code LIKE '4%' THEN l.credit-l.debit ELSE 0 END)
                   -SUM(CASE WHEN l.account_code LIKE '5%' THEN l.debit-l.credit ELSE 0 END) AS net_profit_loss
            FROM journal_entry_lines l JOIN journal_entry_headers h ON h.id=l.journal_entry_id
            WHERE h.tenant_id='tenant_alpha' AND h.status IN ('posted','correction')""")
        snaps["pl_summary"] = dict(cur.fetchone())

        cur.execute("""
            SELECT SUM(CASE WHEN l.account_code LIKE '1%' THEN l.debit-l.credit ELSE 0 END) AS total_assets,
                   SUM(CASE WHEN l.account_code LIKE '2%' THEN l.credit-l.debit ELSE 0 END) AS total_liabilities,
                   SUM(CASE WHEN l.account_code LIKE '3%' THEN l.credit-l.debit ELSE 0 END) AS equity_share_capital
            FROM journal_entry_lines l JOIN journal_entry_headers h ON h.id=l.journal_entry_id
            WHERE h.tenant_id='tenant_alpha' AND h.status IN ('posted','correction')""")
        snaps["balance_sheet"] = dict(cur.fetchone())

        cur.execute("""
            SELECT SUM(CASE WHEN l.account_code='1211' THEN l.debit ELSE 0 END) AS vat_input,
                   SUM(CASE WHEN l.account_code='2200' THEN l.credit ELSE 0 END) AS vat_output
            FROM journal_entry_lines l JOIN journal_entry_headers h ON h.id=l.journal_entry_id
            WHERE h.tenant_id='tenant_alpha' AND h.status IN ('posted','correction')""")
        snaps["vat"] = dict(cur.fetchone())

        cur.execute("SELECT h.tenant_id, COUNT(DISTINCT h.id) AS headers, COUNT(l.id) AS lines, SUM(l.debit) AS dr, SUM(l.credit) AS cr FROM journal_entry_headers h JOIN journal_entry_lines l ON l.journal_entry_id=h.id GROUP BY h.tenant_id ORDER BY h.tenant_id")
        snaps["tenant_summary"] = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT status, COUNT(*) AS cnt FROM journal_entry_headers GROUP BY status ORDER BY status")
        snaps["status_summary"] = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT source_type, COUNT(*) AS cnt FROM journal_entry_sources GROUP BY source_type ORDER BY source_type")
        snaps["source_summary"] = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT COUNT(CASE WHEN correction_of_entry_id IS NOT NULL THEN 1 END) AS correction_count, COUNT(CASE WHEN reversed_by_entry_id IS NOT NULL THEN 1 END) AS reversal_count FROM journal_entry_headers")
        snaps["correction_reversal"] = dict(cur.fetchone())

        cur.execute("SELECT COUNT(*) AS standard_net_count FROM journal_entry_headers WHERE tenant_id='tenant_alpha' AND status IN ('posted','correction')")
        snaps["standard_net_count"] = dict(cur.fetchone())

    return snaps


def fmt(v):
    try: return f"{float(v):,.2f}"
    except: return str(v)


def main():
    print("[H53] Starting H53 local snapshot capture")
    check_guard()
    db_url = check_database_url()
    check_feature_flag()
    verify_fixture_sha256(FIXTURE_PATH)

    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    headers = data.get("journal_entry_headers", [])
    lines   = data.get("journal_entry_lines", [])
    sources = data.get("journal_entry_sources", [])
    print(f"[H53] Fixture: {len(headers)} headers, {len(lines)} lines, {len(sources)} sources")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        h = insert_headers(conn, headers)
        l = insert_lines(conn, lines)
        s = insert_sources(conn, sources)
        conn.commit()
        print(f"[H53] COMMIT OK — {h}h + {l}l + {s}s = {h+l+s} rows")
        conn.autocommit = True
        snaps = capture_snapshots(conn)
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

    bc = snaps["balance_check"]
    vol = snaps["standard_net_volume"]
    pl = snaps["pl_summary"]
    bs = snaps["balance_sheet"]
    vat = snaps["vat"]
    cr = snaps["correction_reversal"]
    balanced_full = abs(float(bc["difference"] or 0)) < 0.01
    balanced_net  = abs(float(vol["total_volume_dr"] or 0) - float(vol["total_volume_cr"] or 0)) < 0.01

    print(f"\n[BALANCE] full={fmt(bc['total_debit'])}/{fmt(bc['total_credit'])} balanced={balanced_full}")
    print(f"[STD-NET VOLUME] {fmt(vol['total_volume_dr'])}/{fmt(vol['total_volume_cr'])} balanced={balanced_net}")
    print(f"[P&L] income={fmt(pl['total_income'])} expense={fmt(pl['total_expense'])} net={fmt(pl['net_profit_loss'])}")
    print(f"[BS] assets={fmt(bs['total_assets'])} liabilities={fmt(bs['total_liabilities'])} equity_capital={fmt(bs['equity_share_capital'])}")
    print(f"[VAT] input={fmt(vat['vat_input'])} output={fmt(vat['vat_output'])}")
    print(f"[CORRECTION/REVERSAL] corrections={cr['correction_count']} reversals={cr['reversal_count']}")
    print(f"[STD-NET COUNT] {snaps['standard_net_count']['standard_net_count']}")

    # Compare against expected_reports
    er = data.get("expected_reports", {}).get("tenant_alpha", {})
    jel = er.get("journal_entries_list", {})
    tb  = er.get("trial_balance", {})
    pls = er.get("pl_summary", {})
    bss = er.get("balance_sheet_summary", {})
    vr  = er.get("vat_register", {})

    results = {}
    results["std_net_count"]    = snaps["standard_net_count"]["standard_net_count"] == er.get("standard_net_entry_count", 12)
    results["std_net_volume_dr"] = abs(float(vol["total_volume_dr"] or 0) - float(jel.get("total_volume_dr", 23945))) < 0.01
    results["std_net_volume_cr"] = abs(float(vol["total_volume_cr"] or 0) - float(jel.get("total_volume_cr", 23945))) < 0.01
    results["pl_income"]         = abs(float(pl["total_income"] or 0) - float(pls.get("total_income", 2300))) < 0.01
    results["pl_expense"]        = abs(float(pl["total_expense"] or 0) - float(pls.get("total_expense", 3525))) < 0.01
    results["pl_net"]            = abs(float(pl["net_profit_loss"] or 0) - float(pls.get("net_profit_loss", -1225))) < 0.01
    results["bs_assets"]         = abs(float(bs["total_assets"] or 0) - float(bss.get("total_assets", 10955))) < 0.01
    results["bs_liabilities"]    = abs(float(bs["total_liabilities"] or 0) - float(bss.get("total_liabilities", 2180))) < 0.01
    results["vat_input"]         = abs(float(vat["vat_input"] or 0) - float(vr.get("vat_input_reclaimable", 180))) < 0.01
    results["vat_output"]        = abs(float(vat["vat_output"] or 0) - float(vr.get("vat_output_payable", 180))) < 0.01

    all_pass = all(results.values())
    print(f"\n[COMPARISON] all_pass={all_pass}")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")

    print(json.dumps({
        "rows": {"headers": h, "lines": l, "sources": s, "total": h+l+s},
        "balance": {"full_dr": str(bc["total_debit"]), "full_cr": str(bc["total_credit"]), "balanced": balanced_full},
        "std_net_volume": {"dr": str(vol["total_volume_dr"]), "cr": str(vol["total_volume_cr"])},
        "pl": {"income": str(pl["total_income"]), "expense": str(pl["total_expense"]), "net": str(pl["net_profit_loss"])},
        "bs": {"assets": str(bs["total_assets"]), "liabilities": str(bs["total_liabilities"]), "equity_capital": str(bs["equity_share_capital"])},
        "vat": {"input": str(vat["vat_input"]), "output": str(vat["vat_output"])},
        "tenant_summary": [{"id": r["tenant_id"], "h": r["headers"], "l": r["lines"], "dr": str(r["dr"]), "cr": str(r["cr"])} for r in snaps["tenant_summary"]],
        "status_summary": [{"status": r["status"], "count": r["cnt"]} for r in snaps["status_summary"]],
        "source_summary": [{"type": r["source_type"], "count": r["cnt"]} for r in snaps["source_summary"]],
        "correction_reversal": {"corrections": int(cr["correction_count"] or 0), "reversals": int(cr["reversal_count"] or 0)},
        "comparison_all_pass": all_pass,
        "comparison_results": results,
    }, indent=2, default=str))
    print("[H53] Done. No production DB touched.")


if __name__ == "__main__":
    main()
