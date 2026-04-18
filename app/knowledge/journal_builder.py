"""app/knowledge/journal_builder.py — Classification, search, journal building"""
import re

from app.knowledge.chart_of_accounts import (
    CHART_OF_ACCOUNTS, ACCA_STANDARDS, _journal, _payload, _fmt,
)
from app.knowledge.tax_rules import TAX_RULES
from app.knowledge.knowledge_loader import _load_files, _load_learned, _find, _TAX_TEXT, _ACC_TEXT

_CLS_RULES = [
    (["tbc საკომ", "bog საკომ", "tbc bank commission", "bank of georgia commission", "bank fee", "commission", "საბ. საკ"], "7510", 0.95),
    (["amazon aws", "amazon cloud", "google cloud", "aws", "amazon", "azure"], "7810", 0.93),
    (["ხელფ", "salary", "wage", "payroll", "მუშ", "თანამ"], "7210", 0.93),
    (["ქირ", "rent", "იჯ", "ოფ"], "7310", 0.92),
    (["კომ", "utilities", "electric", "წყ", "გაზ", "gas"], "7410", 0.91),
    (["რეკლ", "marketing", "advertising", "facebook", "google ad"], "7710", 0.90),
    (["wolt", "glovo", "წარმ", "entertainment", "representative", "რ-ნ"], "7720", 0.88),
    (["bolt", "taxi", "სატ"], "7730", 0.85),
    (["ამ", "depreciation"], "7610", 0.93),
    (["პ", "interest", "სარგ"], "7520", 0.87),
    (["დივ", "dividend"], "3370", 0.97),
    (["დღგ", "vat"], "3310", 0.87),
    (["pit", "საშ"], "3320", 0.92),
    (["cit", "მოგ", "profit tax"], "3340", 0.92),
    (["withholding", "არარ"], "3350", 0.92),
    (["ინვ", "invoice", "გ-ვ", "sale", "revenue", "შემ"], "6110", 0.85),
    (["მომსახურება", "კონსსერვისი", "consulting revenue"], "6120", 0.83),
    (["მარ", "inventory", "stock", "საქ", "product"], "1310", 0.82),
    (["ძირ", "equipment", "machine", "asset", "მანქ"], "1510", 0.82),
    (["სალ", "cash", "ნაღ"], "1110", 0.87),
    (["bank transfer", "გადარიცვა", "wire transfer"], "1120", 0.85),
    (["ავ", "advance", "prepay"], "1420", 0.82),
    (["სესხ", "loan", "kredit"], "3410", 0.82),
    (["კაპ", "capital"], "4110", 0.80),
    (["მოთხ", "receiv", "დებ"], "1210", 0.80),
    (["კრ", "payable", "ვალდ", "AP"], "3110", 0.80),
    (["დანაკლ", "shortage"], "7110", 0.75),
]

_KB = [
    {"title": "VAT/დღგ 18%", "content": "18%. >100k→2სამ.დ.რეგ. ექ:0%. Paid:Dr1120/Cr6110/Cr3310. Unp:Dr1210/Cr6110/Cr3310. კვ.15-ე.", "keywords": ["vat", "დღგ", "18%", "100000", "ექ", "invoice"], "category": "vat", "source": "საგ.კ.მ.160-172|ბ.ლ.4"},
    {"title": "PIT 20%+PAYG2%", "content": "PIT20%.EmpP2%.EmplP2%.Net=Gr×0.78/0.80.Gross-up:÷0.78.Dr7210/Cr3320/Cr3330/Cr3360+Dr7220/Cr3335.თვ.15-ე(N4).", "keywords": ["pit", "საშ", "ხ", "20%", "payg", "pension", "salary", "2%", "net", "gross"], "category": "pit", "source": "საგ.კ.მ.154"},
    {"title": "CIT 15% ესტ.", "content": "მხ.განაწ.მოგ.15%.ბ=გან÷0.85.CIT=ბ×15%.Dr4210/Cr3370→Dr3370/Cr3340/Cr1120.15დ.(N101).", "keywords": ["cit", "მოგ", "15%", "დივ", "ესტ", "0.85", "განაწ", "profit"], "category": "cit", "source": "საგ.კ.მ.97(3)"},
    {"title": "Withholding", "content": "არარ.დ:5%.Ry:10%.პ:5%.მ:10%.15დ.", "keywords": ["withholding", "არარ", "royalty", "5%", "10%", "non-res"], "category": "wth", "source": "საგ.კ.მ.134"},
    {"title": "ბუღ.პრინც.", "content": "Dr=Cr.ყ.ოპ.≥2ანგ.Aktiv=Liab+Eq.FIFO/WAvg.Dr↑Akt.Cr↑Liab.", "keywords": ["ორმ", "double", "Dr", "Cr", "ბალ", "aktiv"], "category": "prin", "source": "ბ.ლ.1"},
    {"title": "VAT გ-ა", "content": "paid:Dr1120/Cr6110/Cr3310. unpaid:Dr1210/Cr6110/Cr3310. შ.(ჩ.):Dr1310+Dr3311/Cr1120.", "keywords": ["vat გ", "dghg", "6110", "3310", "3311", "ჩ"], "category": "vat_p", "source": "ბ.ლ.4"},
    {"title": "ხ.გ-ა", "content": "Dr7210=Gr.Cr3320=PIT.Cr3330=EmpP.Cr3360=Net.Dr7220/Cr3335=EmplP.", "keywords": ["7210", "3320", "3330", "3360", "salary", "payroll"], "category": "sal_p", "source": "ბ."},
    {"title": "დ-ს გ-ა", "content": "ეტ.1:Dr4210/Cr3370. ეტ.2:Dr3370/Cr3340/Cr1120.", "keywords": ["4210", "3370", "3340", "dividend"], "category": "div_p", "source": "ბ.ლ.6"},
    {"title": "მარ.გ-ა", "content": "შ:Dr1310/Cr3110.COGS:Dr7110/Cr1310.დ-სი:Dr7110/Cr1310+VAT!FIFO/LIFO.", "keywords": ["1310", "7110", "inventory", "COGS", "FIFO", "LIFO", "დ-სი", "მარ"], "category": "inv", "source": "ბ.ლ.3"},
    {"title": "ძ.საშ.+ამ.", "content": "შ:Dr1510/Cr1120.ამ:Dr7610/Cr1520.SL=(C-R)÷L.DB=BV×%.", "keywords": ["1510", "1520", "7610", "dep", "ამ", "fixed", "FA"], "category": "fa", "source": "IAS16/ბ.ლ.8"},
    {"title": "მოთხ.", "content": "Dr1210/Cr6110.გ:Dr1120/Cr1210.ჩ:Dr7910/Cr1210.", "keywords": ["receivable", "მოთხ", "1210", "bad", "უიმ"], "category": "rec", "source": "ბ.ლ.5"},
    {"title": "ვალდ.", "content": "Dr1310/Cr3110.გ:Dr3110/Cr1120.ავ:Dr1120/Cr3120.", "keywords": ["payable", "3110", "3120", "ვალდ", "AP", "ავ"], "category": "pay", "source": "ბ.ლ.6"},
    {"title": "კაპ.", "content": "გ-ა:Dr1120/Cr4110.მ:Dr6/Cr4210.ზ:Dr4210/Cr7.დ:Dr4210/Cr3370.", "keywords": ["4110", "4210", "RE", "equity", "capital", "კაპ"], "category": "cap", "source": "ბ.ლ.9"},
    {"title": "ქ.გ-ა", "content": "მ.1%.ფ:40k-გ.15ივ+15დ.", "keywords": ["ქ", "property", "1%"], "category": "prop", "source": "საგ.კ."},
    {"title": "მ/მ ბ-ი", "content": "მ:<30k→0%.მც:<500k→1%/3%.", "keywords": ["მ", "small", "micro", "30000", "500000"], "category": "ms", "source": "საგ.კ."},
    {"title": "სესხი", "content": "მ:Dr1120/Cr3410.პ:Dr7520/Cr3xxx.დ:Dr3410/Cr1120.", "keywords": ["სესხ", "loan", "3410", "7520", "ვალ"], "category": "loan", "source": "ბ.ლ.7"},
    {"title": "IFRS16", "content": "ROU=PV(გ-ბ)+საწ.Dr1710/Cr3430.ამ:Dr7610/Cr1520.პ:Dr7520.<12თ→ოპ.", "keywords": ["ifrs16", "rou", "leasing", "ლ", "1710", "3430"], "category": "ifrs16", "source": "IFRS16"},
    {"title": "IFRS15", "content": "5-ნ:კ-ტ→PO→ფ→გ-ა→შ.ვ.შ. კ.გ.→შ.ა.", "keywords": ["ifrs15", "revenue", "შ.აღ", "performance"], "category": "ifrs15", "source": "IFRS15"},
]


def classify_transaction(description, tenant_id="global"):
    desc = (description or "").lower()

    for r in _load_learned():
        if r["tenant_id"] in (tenant_id, "global") and r["pattern"].lower() in desc:
            return {
                "account": r["account"],
                "account_name": CHART_OF_ACCOUNTS.get(r["account"], {}).get("name", ""),
                "confidence": r.get("confidence", 0.99),
                "matched_on": r["pattern"],
                "source": "learned",
            }

    for kws, acc, conf in _CLS_RULES:
        for kw in kws:
            if kw in desc:
                return {
                    "account": acc,
                    "account_name": CHART_OF_ACCOUNTS.get(acc, {}).get("name", acc),
                    "confidence": conf,
                    "matched_on": kw,
                    "source": "rules",
                }

    all_kw = [
        (kw, code, info)
        for code, info in CHART_OF_ACCOUNTS.items()
        for kw in info.get("keywords", [])
        if kw
    ]
    all_kw.sort(key=lambda x: len(x[0]), reverse=True)

    for kw, code, info in all_kw:
        if kw in desc:
            return {
                "account": code,
                "account_name": info["name"],
                "confidence": 0.88,
                "matched_on": kw,
                "source": "coa",
            }

    return {"account": "7910", "account_name": "სხვ.ხ.", "confidence": 0.30, "matched_on": "default", "source": "fallback"}


def search_knowledge(query, top_k=5):
    import app.knowledge.knowledge_loader as _kl
    _load_files()
    q = query.lower()
    scored = []

    for item in _KB:
        score = sum(1 for kw in item["keywords"] if kw in q)
        if score:
            scored.append((score, item))

    for std_name, std_data in ACCA_STANDARDS.items():
        for key in ["steps", "rules", "key_rules", "formulas", "lessee_accounting"]:
            for text in std_data.get(key, []):
                if any(w in text.lower() for w in q.split() if len(w) > 3):
                    scored.append((0.5, {"title": std_data["title"], "content": text, "source": std_name, "category": "acca"}))

    for tax_name, tax_data in TAX_RULES.items():
        for rule in tax_data.get("rules", []):
            if any(w in rule.lower() for w in q.split() if len(w) > 2):
                scored.append((0.6, {"title": tax_name, "content": rule, "source": tax_name, "category": "tax"}))

    scored.sort(key=lambda x: -x[0])
    res = [i for _, i in scored[:top_k]]

    if _kl._TAX_TEXT and len(res) < 2:
        s = _find(_kl._TAX_TEXT, query[:20], 1000)
        if s:
            res.append({"title": f"საგ.კ.—{query[:20]}", "content": s, "source": "საგ.კ.", "category": "raw_t"})

    if _kl._ACC_TEXT and len(res) < 3:
        s = _find(_kl._ACC_TEXT, query[:20], 1000)
        if s:
            res.append({"title": f"ბ.სხ.—{query[:20]}", "content": s, "source": "ბ.სხ.", "category": "raw_a"})

    return res


def get_context_for_llm(query, max_chars=3000):
    import app.knowledge.knowledge_loader as _kl
    res = search_knowledge(query, 6)
    parts = []
    total = 0

    for r in res:
        chunk = f"[{r['source']}]\n{r['content']}\n"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)

    if _kl._TAX_TEXT:
        raw = _find(_kl._TAX_TEXT, query[:25], 800)
        if raw and total + len(raw) < max_chars:
            parts.append(f"[საგ.კ.]\n{raw}\n")

    if _kl._ACC_TEXT:
        raw = _find(_kl._ACC_TEXT, query[:25], 800)
        if raw and total + len(raw) < max_chars:
            parts.append(f"[ბ.სხ.]\n{raw}\n")

    return "\n".join(parts)


def build_journal_from_text(text):
    text = text.lower()
    match = re.search(r"(\d[\d,\.]*)\s*(?:₾|lari|ლარი)", text)
    if not match:
        return {"message": "❌ თანხა ვერ მოიძებნა", "lines": []}

    amount = float(match.group(1).replace(",", ""))
    cls = classify_transaction(text)
    account = cls["account"]
    has_vat = "დღგ" in text or "vat" in text

    if has_vat:
        vat = round(amount * 0.18 / 1.18, 2)
        net = round(amount - vat, 2)
        return {
            "message": f"📊 გაყიდვა (VAT ჩათვლით)\nNet: {_fmt(net)} | VAT: {_fmt(vat)}",
            "lines": [("6110", 0, net), ("3310", 0, vat), ("1120", amount, 0)],
            "description": "VAT Sale",
        }

    if CHART_OF_ACCOUNTS.get(account, {}).get("type") == "expense":
        return {
            "message": f"📊 ხარჯი ({account})",
            "lines": [(account, amount, 0), ("1120", 0, amount)],
            "description": "Expense Posting",
        }

    if CHART_OF_ACCOUNTS.get(account, {}).get("type") == "revenue":
        return {
            "message": f"📊 შემოსავალი ({account})",
            "lines": [("1120", amount, 0), (account, 0, amount)],
            "description": "Revenue Posting",
        }

    return {"message": "⚠️ ვერ განისაზღვრა ტიპი", "lines": []}


def get_stats():
    import app.knowledge.knowledge_loader as _kl
    _load_files()
    lr = _load_learned()
    return {
        "tax_rules": len(TAX_RULES),
        "acca": len(ACCA_STANDARDS),
        "accounts": len(CHART_OF_ACCOUNTS),
        "cls_rules": len(_CLS_RULES),
        "knowledge_items": len(_KB),
        "learned": len(lr),
        "tax_loaded": bool(_kl._TAX_TEXT),
        "acc_loaded": bool(_kl._ACC_TEXT),
        "tax_chars": len(_kl._TAX_TEXT),
        "acc_chars": len(_kl._ACC_TEXT),
        "total": len(_KB) + len(_CLS_RULES) + len(CHART_OF_ACCOUNTS) + len(TAX_RULES) + len(ACCA_STANDARDS) + len(lr),
    }
