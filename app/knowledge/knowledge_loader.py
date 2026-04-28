"""app/knowledge/knowledge_loader.py — File loading, learned rules, DB operations"""
import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)

import psycopg2
from psycopg2.extras import RealDictCursor

from app.knowledge.chart_of_accounts import CHART_OF_ACCOUNTS

# ── File-loaded text (module-level globals) ──────────────────────────────────
_TAX_TEXT = ""
_ACC_TEXT = ""
_FILES_LOADED = False

_TAX_FILENAME_KEYWORDS = (
    "საგადასახადო", "გადასახადი", "დღგ", "შემოსავლო",
    "tax", "vat", "income_tax",
)


def _get_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(database_url)


def _find(text, kw, size=3000):
    if not text or not kw:
        return ""
    i = text.lower().find(kw.lower())
    return text[i:i + size].strip() if i >= 0 else ""


def _load_files():
    global _TAX_TEXT, _ACC_TEXT, _FILES_LOADED
    if _FILES_LOADED:
        return

    dirs = [
        os.path.abspath("knowledge_files"),
        os.path.abspath("/app/knowledge_files"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_files")),
    ]

    for d in dirs:
        if not os.path.exists(d):
            continue
        for root, _, files in os.walk(d):
            if "archive" in root.lower():
                continue
            for fn in files:
                fp = os.path.join(root, fn)
                try:
                    if fn.lower().endswith(".docx"):
                        import docx
                        doc = docx.Document(fp)
                        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                        _TAX_TEXT += "\n\n" + text
                    elif fn.lower().endswith(".pdf"):
                        import fitz
                        pdf = fitz.open(fp)
                        text = "".join(pdf[i].get_text() for i in range(len(pdf)))
                        if any(kw in fn.lower() for kw in _TAX_FILENAME_KEYWORDS):
                            _TAX_TEXT += "\n\n" + text
                        else:
                            _ACC_TEXT += "\n\n" + text
                except Exception as e:
                    log.warning("KB load error: %s: %s", fn, e)

    _FILES_LOADED = True
    log.info("KB loaded: TAX=%d chars ACC=%d chars", len(_TAX_TEXT), len(_ACC_TEXT))


def get_tax_section(topic):
    _load_files()
    kws = {
        "vat": "დღგ", "pit": "საშემოსავლო", "cit": "მოგების გადასახადი",
        "withholding": "გადახდის წყაროსთან", "property": "ქონების გადასახადი",
        "penalty": "საგადასახადო სანქცია", "non_resident": "არარეზიდენტ", "micro": "მცირე ბიზნეს",
    }
    return _find(_TAX_TEXT, kws.get(topic, topic), 4000)


def get_accounting_section(topic):
    _load_files()
    kws = {
        "principles": "ბუღალტრული აღრიცხვის პრინციპები", "vat": "დღგ",
        "inventory": "მარაგ", "receivables": "მოთხოვნ", "payables": "ვალდებულ",
        "salary": "შრომის ანაზღაურ", "dividends": "დივიდენდ",
        "fixed_assets": "ძირითადი საშუალებ", "depreciation": "ამორტიზაცი",
        "capital": "კაპიტალ", "shortage": "დანაკლის", "loan": "სესხ",
    }
    return _find(_ACC_TEXT, kws.get(topic, topic), 4000)


def _load_learned_from_db():
    try:
        conn = _get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT tenant_id,
                   pattern_value AS pattern,
                   account_code AS account,
                   reason AS note,
                   confidence_score AS confidence,
                   created_at,
                   source
            FROM learning_patterns
            WHERE pattern_type = 'description_exact'
              AND source IN ('human', 'feedback_learning', 'db_migrated')
              AND status IN ('active', 'candidate')
            ORDER BY created_at ASC
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "tenant_id": r.get("tenant_id") or "global",
                "pattern": r.get("pattern") or "",
                "account": r.get("account") or "",
                "note": r.get("note") or "",
                "confidence": float(r.get("confidence") or 0.99),
                "created_at": r.get("created_at").isoformat() if r.get("created_at") else datetime.now().isoformat(),
                "source": r.get("source") or "db",
            }
            for r in rows
        ]
    except Exception as e:
        log.warning("DB learned load failed: %s", e)
        return []


def _load_learned():
    return _load_learned_from_db()


def migrate_json_to_db():
    """One-time: move learned_rules.json entries → learning_patterns table."""
    json_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "learned_rules.json")
    )
    bak = json_path + ".bak"
    if not os.path.exists(json_path):
        return
    if os.path.exists(bak):
        return
    try:
        import json
        with open(json_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        if not rules:
            os.rename(json_path, bak)
            return
        conn = _get_db()
        cur = conn.cursor()
        migrated = 0
        for r in rules:
            pattern = (r.get("pattern") or "").strip()
            account = (r.get("account") or "").strip()
            if not pattern or not account:
                continue
            cur.execute(
                """
                INSERT INTO learning_patterns
                    (tenant_id, pattern_type, pattern_value, account_code, reason,
                     confidence_score, autopilot_eligible, support_count, success_count,
                     failure_count, usage_count, status, source, created_at, updated_at,
                     last_seen_at, last_confirmed_at)
                VALUES
                    ('global','description_exact',%s,%s,%s,
                     0.99,false,1,1,0,0,'active','human',NOW(),NOW(),NOW(),NOW())
                ON CONFLICT DO NOTHING
                """,
                (pattern, account, r.get("note", "")),
            )
            migrated += 1
        conn.commit()
        cur.close()
        conn.close()
        os.rename(json_path, bak)
        log.info("JSON->DB migration: %d rules migrated, file archived as .bak", migrated)
    except Exception as e:
        log.warning("JSON->DB migration failed (non-fatal): %s", e)


def learn_new_rule(pattern, account, tenant_id="global", note=""):
    pattern = (pattern or "").strip()
    account = (account or "").strip()
    tenant_id = (tenant_id or "global").strip()
    note = (note or "").strip()

    if not pattern or not account:
        return {"status": "error", "message": "pattern და account სავალდებულოა"}

    try:
        conn = _get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT id FROM learning_patterns
            WHERE tenant_id = %s
              AND pattern_type = 'description_exact'
              AND LOWER(TRIM(COALESCE(pattern_value, ''))) = LOWER(TRIM(%s))
            LIMIT 1
            """,
            (tenant_id, pattern),
        )
        existing = cur.fetchone()

        if existing:
            cur.execute(
                """
                UPDATE learning_patterns
                SET account_code = %s, reason = %s, confidence_score = 0.99,
                    status = 'active', source = 'human',
                    updated_at = NOW(), last_confirmed_at = NOW(), last_seen_at = NOW()
                WHERE id = %s
                RETURNING id, tenant_id, pattern_value, account_code, reason, confidence_score, source, created_at
                """,
                (account, note, existing["id"]),
            )
            row = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return {
                "status": "updated",
                "message": f"♻️ '{pattern}' განახლდა → {account} ({CHART_OF_ACCOUNTS.get(account, {}).get('name', account)})",
                "rule": {
                    "pattern": row["pattern_value"],
                    "account": row["account_code"],
                    "tenant_id": row["tenant_id"],
                    "note": row["reason"] or "",
                    "confidence": float(row["confidence_score"] or 0.99),
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else datetime.now().isoformat(),
                    "source": row["source"] or "human",
                },
            }

        cur.execute(
            """
            INSERT INTO learning_patterns
                (tenant_id, pattern_type, pattern_value, account_code, reason,
                 confidence_score, autopilot_eligible, support_count, success_count,
                 failure_count, usage_count, status, source,
                 created_at, updated_at, last_seen_at, last_confirmed_at)
            VALUES
                (%s,'description_exact',%s,%s,%s,
                 0.99,false,1,1,0,0,'active','human',
                 NOW(),NOW(),NOW(),NOW())
            RETURNING id, tenant_id, pattern_value, account_code, reason, confidence_score, source, created_at
            """,
            (tenant_id, pattern, account, note),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {
            "status": "learned",
            "message": f"✅ '{pattern}' → {account} ({CHART_OF_ACCOUNTS.get(account, {}).get('name', account)})",
            "rule": {
                "pattern": row["pattern_value"],
                "account": row["account_code"],
                "tenant_id": row["tenant_id"],
                "note": row["reason"] or "",
                "confidence": float(row["confidence_score"] or 0.99),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else datetime.now().isoformat(),
                "source": row["source"] or "human",
            },
        }

    except Exception as e:
        log.error("DB learn failed: %s", e)
        return {"status": "error", "message": f"DB შეცდომა: {e}"}
