"""
bridge_hub_knowledge.py  —  Bridge Hub Knowledge Base V4
სრული გაერთიანებული ვერსია (V2 + V3 merged)
 
წყაროები:
  knowledge_files/997097182-საგადასახადო.docx
  knowledge_files/457292620-ბუღალტრული-აღრიცხვა-pdf.pdf
 
შესაძლებლობები:
  ✅ 2 ფაილის ავტომ. წაკითხვა
  ✅ VAT/PIT/CIT/Withholding/Property სრული გაანგ.
  ✅ Dr/Cr journal + Balance.ge payload
  ✅ Self-learning (learned_rules.json)
  ✅ Tenant-specific წესები
  ✅ IFRS 15/16, IAS 2/16, F2/F9
  ✅ ტრანზ. ავტ. კლასიფ.
  ✅ LLM კონტ. გამოძახება
"""
 
import json, os, re
from datetime import date, datetime
from typing import Optional
 
# ══════════════════════════════════════════════════════════════
# 1. FILE LOADING
# ══════════════════════════════════════════════════════════════
 
_TAX_TEXT = ""
_ACC_TEXT = ""
_FILES_LOADED = False
 
def _load_files():
    global _TAX_TEXT, _ACC_TEXT, _FILES_LOADED

    if _FILES_LOADED:
        return

    dirs = [
        os.path.abspath("knowledge_files"),
        os.path.abspath("/app/knowledge_files"),
        os.path.abspath(os.path.dirname(__file__) + "/knowledge_files"),
    ]

    for d in dirs:
        if not os.path.exists(d):
            continue

        for root, _, files in os.walk(d):
            # ❌ გამოტოვე archive ფოლდერი
            if "archive" in root:
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
                        _ACC_TEXT += "\n\n" + text

                except Exception as e:
                    print(f"⚠️ KB load error: {fn}: {e}")

    _FILES_LOADED = True

    print(f"✅ TAX TEXT: {len(_TAX_TEXT)} chars")
    print(f"✅ ACC TEXT: {len(_ACC_TEXT)} chars")


def _find(text, kw, size=3000):
    if not text or not kw:
        return ""
    i = text.lower().find(kw.lower())
    return text[i:i+size].strip() if i >= 0 else ""


def get_tax_section(topic):
    _load_files()
    kws = {
        "vat": "დღგ",
        "pit": "საშემოსავლო",
        "cit": "მოგების გადასახადი",
        "withholding": "გადახდის წყაროსთან",
        "property": "ქონების გადასახადი",
        "penalty": "საგადასახადო სანქცია",
        "non_resident": "არარეზიდენტ",
        "micro": "მცირე ბიზნეს",
    }
    return _find(_TAX_TEXT, kws.get(topic, topic), 4000)


def get_accounting_section(topic):
    _load_files()
    kws = {
        "principles": "ბუღალტრული აღრიცხვის პრინციპები",
        "vat": "დღგ",
        "inventory": "მარაგ",
        "receivables": "მოთხოვნ",
        "payables": "ვალდებულ",
        "salary": "შრომის ანაზღაურ",
        "dividends": "დივიდენდ",
        "fixed_assets": "ძირითადი საშუალებ",
        "depreciation": "ამორტიზაცი",
        "capital": "კაპიტალ",
        "shortage": "დანაკლის",
        "loan": "სესხ",
    }
    return _find(_ACC_TEXT, kws.get(topic, topic), 4000)
 
 
# ══════════════════════════════════════════════════════════════
# 2. TAX RULES (full logic + exceptions)
# ══════════════════════════════════════════════════════════════
 
TAX_RULES = {
    "VAT": {
        "rate": 0.18, "threshold": 100000, "registration_days": 2,
        "description": "დამატებული ღირებულების გადასახადი — 18%",
        "rules": [
            "VAT = ნეტო × 0.18",
            "ნეტო = ბრუტო ÷ 1.18 (VAT-ჩათვლ.)",
            "ბრ. > 100,000₾ → 2 სამ. დღეში რეგ.",
            "Paid: Dr1120/Cr6110/Cr3310 | Unpaid: Dr1210/Cr6110/Cr3310",
            "დეკლ.: კვ. 15-ე",
        ],
        "exempt_no_credit": [
            "სამედ. მომს. და მედიკ.",
            "განათ. მომს.",
            "ფინ. მომს. (სესხი, დეპ., სადაზღ.)",
            "საც. ბინ. გაქ.",
        ],
        "exempt_with_credit": [
            "ექსპ. — 0% + ჩათვ. უფ.",
            "საერთ. სატრ. მომს.",
            "FIZ მიწ.",
        ],
        "reverse_charge": [
            "არარეზ. ელ. მომს. (Google/FB/Netflix) — Dr3310/Cr3310",
        ],
    },
    "PIT": {
        "rate": 0.20, "payg_employee": 0.02, "payg_employer": 0.02,
        "description": "საშემოსავლო — 20% + PAYG 2%",
        "rules": [
            "PIT = Gross × 20%",
            "EmpPension = Gross × 2% (თანამ.)",
            "EmplPension = Gross × 2% (კომ., თანამ. არ აკლდება)",
            "Net = Gross - PIT - EmpPension",
            "Gross-up: Gross = Net ÷ 0.78 (ON) / ÷ 0.80 (OFF)",
            "Dr7210/Cr3320/Cr3330/Cr3360 + Dr7220/Cr3335",
            "ვ.: თვ. 15-ე (ფ.N4)",
        ],
    },
    "CIT": {
        "rate": 0.15, "divisor": 0.85,
        "description": "მოგ. გადასახ. — ესტ. მოდ. 15%",
        "rules": [
            "მხ. განაწ. მოგ. (ესტ. მოდ.)",
            "ბაზა = განაც ÷ 0.85",
            "CIT = ბაზა × 15%",
            "Dr4210/Cr3370 → Dr3370/Cr3340/Cr1120",
            "ვ.: 15 დღე (ფ.N101)",
        ],
        "deemed": [
            "წარმ.ხ. > 1% შემ. — ზედ. ნაწ.",
            "არარეზ. პროც./Royalty",
        ],
    },
    "WITHHOLDING": {
        "rates": {"dividend":0.05,"interest":0.05,"royalty":0.10,"services":0.10},
        "description": "გადახდ. წ. გადასახ.",
        "rules": ["არარ.დივ.:5% | Royalty:10% | პროც.:5% | მომს.:10% | ვ.:15დ."],
    },
    "PROPERTY_TAX": {
        "rate_max": 0.01,
        "rules": ["მაქს.1% საბ.ღ-ბ. | ფიზ.: 40,000₾-გათ. | 15ივ.+15დეკ."],
    },
    "MICRO_SMALL": {
        "rules": ["მიკ.: <30,000₾→0% | მც.: <500,000₾→1% ან 3%"],
    },
}
 
TAX_RATES = {
    "vat":0.18,"vat_threshold":100000,"vat_registration_days":2,
    "pit":0.20,"payg_employee":0.02,"payg_employer":0.02,
    "cit":0.15,"cit_divisor":0.85,
    "withholding_dividend":0.05,"withholding_royalty":0.10,
    "withholding_interest":0.05,"withholding_services":0.10,
    "property_max":0.01,"micro_business":0.01,"small_business":0.03,
}
 
 
# ══════════════════════════════════════════════════════════════
# 3. CHART OF ACCOUNTS
# ══════════════════════════════════════════════════════════════
 
CHART_OF_ACCOUNTS = {
    "1110":{"name":"სალარო (ნაღდი)","type":"asset","keywords":["ნაღდი","სალარო","cash","კასა"]},
    "1120":{"name":"საბანკო ანგ.","type":"asset","keywords":["საბ.ანგ","გადარ","bank account"]},
    "1130":{"name":"სხვა ფ.ეკვ.","type":"asset","keywords":[]},
    "1210":{"name":"მოთხ. კლ-ზე","type":"asset","keywords":["მოთხ","დებ","receivable"]},
    "1220":{"name":"სათ. მოთხ.","type":"asset","keywords":[]},
    "1310":{"name":"მარ. / საქ.","type":"asset","keywords":["საქ","მარ","inventory","stock","product"]},
    "1320":{"name":"მზა პროდ.","type":"asset","keywords":[]},
    "1330":{"name":"უდ. წარმ.","type":"asset","keywords":[]},
    "1410":{"name":"სხვ. მოკლ. მოთხ.","type":"asset","keywords":["წინ","prepaid"]},
    "1420":{"name":"გადახ. ავ.","type":"asset","keywords":["ავანს","advance","prepay"]},
    "1430":{"name":"წინ. გადახ. ხ.","type":"asset","keywords":[]},
    "1510":{"name":"ძირ. საშ.","type":"asset","keywords":["ძირ","fixed","შენ","მანქ","ტექ","equipment"]},
    "1520":{"name":"დარ. ამ. (კ.)","type":"contra_asset","keywords":["ამ","depreciation"]},
    "1610":{"name":"არ. აქტ.","type":"asset","keywords":["პატ","ლიც","intangible","software","პრ"]},
    "1620":{"name":"გრ.ვ.ინვ.","type":"asset","keywords":[]},
    "1710":{"name":"ROU (IFRS16)","type":"asset","keywords":["rou","ifrs 16","ლიზ","leasing"]},
    "3110":{"name":"კრ. დავ.","type":"liability","keywords":["მიწ","კრედ","payable","AP"]},
    "3120":{"name":"მიღ. ავ.","type":"liability","keywords":["ავ","advance"]},
    "3130":{"name":"გად. ხ.","type":"liability","keywords":[]},
    "3310":{"name":"დღგ გად.","type":"liability","keywords":["დღგ","vat","დამ.ღ"]},
    "3311":{"name":"ჩათვ. დღგ","type":"asset","keywords":["vat input","ჩათ.დღგ","3311"]},
    "3320":{"name":"PIT / საშ.","type":"liability","keywords":["pit","საშ","income tax"]},
    "3330":{"name":"დასაქ. საპ.","type":"liability","keywords":["payg","pension","საპ"]},
    "3335":{"name":"დამ. საპ.","type":"liability","keywords":[]},
    "3340":{"name":"CIT / მოგ.","type":"liability","keywords":["cit","მოგ","profit tax"]},
    "3350":{"name":"Withholding","type":"liability","keywords":["withholding","არარ","nonres"]},
    "3360":{"name":"გად.ხ.Net","type":"liability","keywords":[]},
    "3370":{"name":"გად. დივ.","type":"liability","keywords":["დივ","dividend"]},
    "3380":{"name":"ქ.გ. გად.","type":"liability","keywords":[]},
    "3410":{"name":"სასეხ.ვ.მ.","type":"liability","keywords":["სესხ","loan","კრ"]},
    "3420":{"name":"გ.თ.","type":"liability","keywords":[]},
    "3430":{"name":"ფ.იჯ.(IFRS16)","type":"liability","keywords":["ლიზ","ifrs 16"]},
    "3510":{"name":"გ.ვ.სესხ.ვ.","type":"liability","keywords":[]},
    "4110":{"name":"საწ.კაპ.","type":"equity","keywords":["კაპ","equity","capital","საწ"]},
    "4120":{"name":"დამ.კაპ.","type":"equity","keywords":[]},
    "4210":{"name":"გ.მ.(RE)","type":"equity","keywords":["მოგ","retained","RE"]},
    "4220":{"name":"სარ.კაპ.","type":"equity","keywords":[]},
    "6110":{"name":"გ-ვ. შემ.","type":"revenue","keywords":["გ-ვ","revenue","income","შემ","invoice","ინვ","sale"]},
    "6120":{"name":"მომ. შემ.","type":"revenue","keywords":["მომსახურება","კონსულტაცია","revenue service"]},
    "6130":{"name":"სხვ.ო.შ.","type":"revenue","keywords":[]},
    "6140":{"name":"პ.შ.","type":"revenue","keywords":[]},
    "6150":{"name":"სხვ.შ.","type":"revenue","keywords":[]},
    "7110":{"name":"COGS","type":"expense","keywords":["cogs","cost of goods","ღ-ბ"]},
    "7120":{"name":"პ.ხ.","type":"expense","keywords":[]},
    "7210":{"name":"ხ.ხ.","type":"expense","keywords":["ხელფ","salary","payroll","მუშ","თანამ"]},
    "7220":{"name":"დ.სპ.ხ.","type":"expense","keywords":[]},
    "7230":{"name":"სხ.შ.ხ.","type":"expense","keywords":[]},
    "7310":{"name":"ქ.ხ.","type":"expense","keywords":["ქ-ა","rent","იჯ","ოფ","office"]},
    "7320":{"name":"ო.ლ.ხ.","type":"expense","keywords":[]},
    "7410":{"name":"კ.ხ.","type":"expense","keywords":["კომ","utilities","electric","წყ","გ","gas"]},
    "7510":{"name":"სბ.სკ.","type":"expense","keywords":["საბ. საკ","commission","bank fee","tbc","bog","tbc bank","bank of georgia","საკომისიო","სბ.სკ","სრვ"]},
    "7520":{"name":"სბ.პ.","type":"expense","keywords":["პ","interest","სარგ"]},
    "7610":{"name":"ამ.ხ.","type":"expense","keywords":["ამ","depreciation"]},
    "7710":{"name":"რ.ხ.","type":"expense","keywords":["რ","marketing","advertising","facebook","google ad","instagram"]},
    "7720":{"name":"წ.ხ.","type":"expense","keywords":["წ","entertainment","representative","რ-ნ","wolt","glovo"]},
    "7730":{"name":"ს.ხ.","type":"expense","keywords":["სატ","transport","taxi","bolt"]},
    "7810":{"name":"სხ.ა.ხ.","type":"expense","keywords":["aws","amazon","azure","cloud","software"]},
    "7910":{"name":"სხვ.ხ.","type":"expense","keywords":["სხვ","other","misc"]},
    "7920":{"name":"გ.კ.ზ.","type":"expense","keywords":["გ-ვ","exchange"]},
}
 
 
# ══════════════════════════════════════════════════════════════
# 4. IFRS / ACCA
# ══════════════════════════════════════════════════════════════
 
ACCA_STANDARDS = {
    "IFRS_15":{"title":"IFRS 15 — შემ. აღ. (5-ნ.)","steps":["1.კ-ტ","2.PO","3.ფ-ი","4.გ-ა","5.შ.ვ."]},
    "IFRS_16":{"title":"IFRS 16 — იჯ.","lessee_accounting":[
        "ROU=PV(გ-ბ)+საწ. Dr1710/Cr3430",
        "ამ: Dr7610/Cr1520. პ: Dr7520/Cr3430",
        "<12თ/<$5k→ოპ.ხ."]},
    "IAS_2":{"title":"IAS 2 — მარ.","rules":["ღ. ან NRV","FIFO/WAvg (LIFO დ.)","ჩ: Dr7110/Cr1310"]},
    "IAS_16":{"title":"IAS 16 — ძ.საშ.","rules":["SL=(Cost-Res)÷Life","DB=BV×%","Dr7610/Cr1520"]},
    "F2":{"title":"F2 Mgmt","formulas":["BE=Fix÷Contrib/u","Contrib=SP-VC"]},
    "F9":{"title":"F9 Finance","formulas":["NPV=Σ(CF÷(1+r)^t)-I0","WACC=E/V×Re+D/V×Rd×(1-T)","CAPM:Re=Rf+β×(Rm-Rf)"]},
}
 
 
# ══════════════════════════════════════════════════════════════
# 5. SELF-LEARNING
# ══════════════════════════════════════════════════════════════
 
LEARNED_RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned_rules.json")
 
def _load_learned():
    if os.path.exists(LEARNED_RULES_FILE):
        try:
            with open(LEARNED_RULES_FILE,"r",encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []
 
def _save_learned(rules):
    try:
        with open(LEARNED_RULES_FILE,"w",encoding="utf-8") as f:
            json.dump(rules,f,ensure_ascii=False,indent=2)
    except Exception as e:
        print(f"⚠️ save: {e}")
 
 
def learn_new_rule(pattern, account, tenant_id="global", note=""):
    """ბუღ. ასწავლის AI-ს. learn_new_rule('Wolt','7720',note='წარმ.')"""
    rules = _load_learned()

    for r in rules:
        if r["pattern"].lower() == pattern.lower() and r["tenant_id"] == tenant_id:
            r["account"], r["note"] = account, note
            r["updated_at"] = datetime.now().isoformat()
            _save_learned(rules)

            return {
                "status": "updated",
                "message": f"♻️ '{pattern}' განახლდა → {account} ({CHART_OF_ACCOUNTS.get(account, {}).get('name', account)})",
                "rule": r
            }

    new_r = {
        "pattern": pattern,
        "account": account,
        "tenant_id": tenant_id,
        "note": note,
        "confidence": 0.99,
        "created_at": datetime.now().isoformat(),
        "source": "human"
    }

    rules.append(new_r)
    _save_learned(rules)

    return {
        "status": "learned",
        "message": f"✅ '{pattern}' → {account} ({CHART_OF_ACCOUNTS.get(account, {}).get('name', account)})",
        "rule": new_r
    }
 
 
# ══════════════════════════════════════════════════════════════
# 6. CLASSIFICATION
# ══════════════════════════════════════════════════════════════
 
_CLS_RULES=[
    (["tbc საკომ","bog საკომ","bank fee","commission","საბ. საკ"],"7510",0.95),
    (["ხელფ","salary","wage","payroll","მუშ","თანამ"],"7210",0.93),
    (["ქირ","rent","იჯ","ოფ"],"7310",0.92),
    (["კომ","utilities","electric","წყ","გაზ","gas"],"7410",0.91),
    (["რეკლ","marketing","advertising","facebook","google ad"],"7710",0.90),
    (["wolt","glovo","წარმ","entertainment","representative","რ-ნ"],"7720",0.88),
    (["bolt","taxi","სატ"],"7730",0.85),
    (["ამ","depreciation"],"7610",0.93),
    (["პ","interest","სარგ"],"7520",0.87),
    (["დივ","dividend"],"3370",0.97),
    (["დღგ","vat"],"3310",0.87),
    (["pit","საშ"],"3320",0.92),
    (["cit","მოგ","profit tax"],"3340",0.92),
    (["withholding","არარ"],"3350",0.92),
    (["ინვ","invoice","გ-ვ","sale","revenue","შემ"],"6110",0.85),
    (["მომსახურება","კონსსერვისი","consulting revenue"],"6120",0.83),
    (["მარ","inventory","stock","საქ","product"],"1310",0.82),
    (["ძირ","equipment","machine","asset","მანქ"],"1510",0.82),
    (["სალ","cash","ნაღ"],"1110",0.87),
    (["bank transfer","გადარიცვა","wire transfer"],"1120",0.85),
    (["ავ","advance","prepay"],"1420",0.82),
    (["სესხ","loan","kredit"],"3410",0.82),
    (["კაპ","capital"],"4110",0.80),
    (["მოთხ","receiv","დებ"],"1210",0.80),
    (["კრ","payable","ვალდ","AP"],"3110",0.80),
    (["დანაკლ","shortage"],"7110",0.75),
    (["aws","amazon","azure","google cloud"],"7810",0.83),
]
 
 
def classify_transaction(description, tenant_id="global"):
    desc=description.lower()
    for r in _load_learned():
        if r["tenant_id"] in (tenant_id,"global") and r["pattern"].lower() in desc:
            return {"account":r["account"],"account_name":CHART_OF_ACCOUNTS.get(r["account"],{}).get("name",""),"confidence":r["confidence"],"matched_on":r["pattern"],"source":"learned"}
    all_kw=[(kw,code,info) for code,info in CHART_OF_ACCOUNTS.items() for kw in info.get("keywords",[]) if kw]
    all_kw.sort(key=lambda x:len(x[0]),reverse=True)
    for kw,code,info in all_kw:
        if kw in desc:
            return {"account":code,"account_name":info["name"],"confidence":0.88,"matched_on":kw,"source":"coa"}
    for kws,acc,conf in _CLS_RULES:
        for kw in kws:
            if kw in desc:
                return {"account":acc,"account_name":CHART_OF_ACCOUNTS.get(acc,{}).get("name",acc),"confidence":conf,"matched_on":kw,"source":"rules"}
    return {"account":"7910","account_name":"სხვ.ხ.","confidence":0.30,"matched_on":"default","source":"fallback"}
 
 
# ══════════════════════════════════════════════════════════════
# 7. UTILITY
# ══════════════════════════════════════════════════════════════
 
def _fmt(a): return f"{a:,.2f}₾"
 
def _jl(side,acc,amount):
    name=CHART_OF_ACCOUNTS.get(acc,{}).get("name",acc)
    return f"  {side} {acc} {name}{' '*(max(0,34-len(f'{side} {acc} {name}')))} {_fmt(amount)}"
 
def _journal(*lines): return "\n".join(_jl(s,a,v) for s,a,v in lines)
 
def _payload(desc,lines,dt=None):
    return {"journal_date":dt or date.today().isoformat(),"description":desc,
            "lines":[{"account_code":a,"debit":dr,"credit":cr} for a,dr,cr in lines]}
 
 
# ══════════════════════════════════════════════════════════════
# 8. CALCULATORS
# ══════════════════════════════════════════════════════════════
 
def calculate_vat(amount, inclusive=True, service_type="standard"):
    """VAT — საგ.კოდ. თ.XIII / ბუღ.ლ.4"""
    _load_files()
    exempt={"medical":"სამედ.გათ.","education":"განათ.გათ.",
            "export":"ექსპ.0%+ჩათვ.","financial":"ფინ.გათ.","apartment":"ბინ.გათ."}
    for k,note in exempt.items():
        if k in service_type.lower():
            return {"vat":0,"net":amount,"gross":amount,"rate":"0%","note":note,"source":"საგ.კოდ.მ.168-172"}
    r=TAX_RATES["vat"]
    if inclusive:
        net=round(amount/(1+r),2); vat=round(amount-net,2); gross=amount
    else:
        net=amount; vat=round(amount*r,2); gross=round(amount+vat,2)
    return {
        "net":net,"vat":vat,"gross":gross,"rate":18,
        "journal_paid":   _journal(("Dr","1120",gross),("Cr","6110",net),("Cr","3310",vat)),
        "journal_unpaid": _journal(("Dr","1210",gross),("Cr","6110",net),("Cr","3310",vat)),
        "balance_ge_paid":_payload("VAT sale",[("1120",gross,0),("6110",0,net),("3310",0,vat)]),
        "note":f"{'ჩ-ვ' if inclusive else 'დ-ბ'}: net={_fmt(net)},vat={_fmt(vat)}",
        "deadline":"კვ.15-ე","source":"საგ.კოდ.მ.160-172/ბუღ.ლ.4",
    }
 
 
def calculate_payroll(gross, include_pension=True, mode="gross"):
    """Payroll — საგ.კოდ.მ.154 / ბუღ."""
    _load_files()
    ep=TAX_RATES["payg_employee"] if include_pension else 0.0
    erp=TAX_RATES["payg_employer"] if include_pension else 0.0
    p=TAX_RATES["pit"]
    if mode=="net":
        g=gross; gross=round(g/(1-p-ep),2)
    pit=round(gross*p,2); emp_p=round(gross*ep,2)
    net=round(gross-pit-emp_p,2); erp_a=round(gross*erp,2)
    jl=[("Dr","7210",gross),("Cr","3320",pit)]
    if emp_p: jl.append(("Cr","3330",emp_p))
    jl.append(("Cr","3360",net))
    j=_journal(*jl)
    if erp_a: j+="\n\n  — დამ.საპ. —\n"+_journal(("Dr","7220",erp_a),("Cr","3335",erp_a))
    pl=[("7210",gross,0),("3320",0,pit)]
    if emp_p: pl.append(("3330",0,emp_p))
    pl.append(("3360",0,net))
    return {"gross":gross,"pit":pit,"payg_employee":emp_p,"payg_employer":erp_a,
            "net":net,"total_employer_cost":round(gross+erp_a,2),
            "journal":j,"balance_ge":_payload("Salary",pl),
            "deadline":"თვ.15-ე(N4)","source":"საგ.კოდ.მ.154-155/ბუღ."}
 
 
def calculate_cit(distributed_profit):
    """CIT — ესტ.მოდ. საგ.კოდ.მ.97(3)"""
    _load_files()
    tb=round(distributed_profit/TAX_RATES["cit_divisor"],2)
    cit=round(tb*TAX_RATES["cit"],2); nd=round(distributed_profit-cit,2)
    j1=_journal(("Dr","4210",distributed_profit),("Cr","3370",distributed_profit))
    j2=_journal(("Dr","3370",distributed_profit),("Cr","3340",cit),("Cr","1120",nd))
    return {"distributed_profit":distributed_profit,"tax_base":tb,"cit":cit,"net_dividend":nd,
            "journal":f"ეტ.1:\n{j1}\n\nეტ.2:\n{j2}",
            "balance_ge_step1":_payload("Div.accrual",[("4210",distributed_profit,0),("3370",0,distributed_profit)]),
            "balance_ge_step2":_payload("Div.payment",[("3370",distributed_profit,0),("3340",0,cit),("1120",0,nd)]),
            "deadline":"15დ.","source":"საგ.კოდ.მ.97(3)/ბუღ.ლ.6"}
 
 
def calculate_withholding(amount, payment_type="dividend", is_resident=True):
    """Withholding — საგ.კოდ.მ.134"""
    _load_files()
    rate=TAX_RATES.get(f"withholding_{payment_type}",0.10)
    if is_resident and payment_type not in ["royalty"]: rate=0
    tax=round(amount*rate,2); net=round(amount-tax,2)
    return {"amount":amount,"rate":int(rate*100),"tax":tax,"net":net,
            "journal":_journal(("Dr","3350",tax),("Cr","1120",tax)) if tax else "",
            "deadline":"15დ.","source":"საგ.კოდ.მ.134"}
 
 
def calculate_depreciation(cost, residual, useful_life_years, method="straight_line"):
    """ამ. — IAS16/ბუღ.ლ.8"""
    _load_files()
    ann=round((cost-residual)/useful_life_years,2) if method=="straight_line" else round(cost*0.20,2)
    mon=round(ann/12,2)
    return {"cost":cost,"residual":residual,"useful_life":useful_life_years,
            "method":method,"annual":ann,"monthly":mon,
            "journal":_journal(("Dr","7610",mon),("Cr","1520",mon)),
            "source":"IAS16/ბუღ.ლ.8"}
 
 
def calculate_inventory_shortage(shortage_amount, has_culprit=False):
    """დ-სი — IAS2/ბუღ.ლ.3"""
    _load_files()
    lines=[("Dr","7110",shortage_amount),("Cr","1310",shortage_amount)]
    if has_culprit: lines+=[("Dr","1210",shortage_amount),("Cr","7110",shortage_amount)]
    return {"shortage":shortage_amount,"vat_liability":round(shortage_amount*TAX_RATES["vat"],2),
            "journal":_journal(*lines),
            "note":"⚠️ VAT!"+(" + თ.ანაზ." if has_culprit else ""),
            "source":"IAS2/ბუღ.ლ.3/საგ.კოდ."}
 
 
# ══════════════════════════════════════════════════════════════
# 9. KNOWLEDGE ITEMS + SEARCH
# ══════════════════════════════════════════════════════════════
 
_KB=[
    {"title":"VAT/დღგ 18%","content":"18%. >100k→2სამ.დ.რეგ. ექ:0%. Paid:Dr1120/Cr6110/Cr3310. Unp:Dr1210/Cr6110/Cr3310. კვ.15-ე.","keywords":["vat","დღგ","18%","100000","ექ","invoice"],"category":"vat","source":"საგ.კ.მ.160-172|ბ.ლ.4"},
    {"title":"PIT 20%+PAYG2%","content":"PIT20%.EmpP2%.EmplP2%.Net=Gr×0.78/0.80.Gross-up:÷0.78.Dr7210/Cr3320/Cr3330/Cr3360+Dr7220/Cr3335.თვ.15-ე(N4).","keywords":["pit","საშ","ხ","20%","payg","pension","salary","2%","net","gross"],"category":"pit","source":"საგ.კ.მ.154"},
    {"title":"CIT 15% ესტ.","content":"მხ.განაწ.მოგ.15%.ბ=გან÷0.85.CIT=ბ×15%.Dr4210/Cr3370→Dr3370/Cr3340/Cr1120.15დ.(N101).","keywords":["cit","მოგ","15%","დივ","ესტ","0.85","განაწ","profit"],"category":"cit","source":"საგ.კ.მ.97(3)"},
    {"title":"Withholding","content":"არარ.დ:5%.Ry:10%.პ:5%.მ:10%.15დ.","keywords":["withholding","არარ","royalty","5%","10%","non-res"],"category":"wth","source":"საგ.კ.მ.134"},
    {"title":"ბუღ.პრინც.","content":"Dr=Cr.ყ.ოპ.≥2ანგ.Aktiv=Liab+Eq.FIFO/WAvg.Dr↑Akt.Cr↑Liab.","keywords":["ორმ","double","Dr","Cr","ბალ","aktiv"],"category":"prin","source":"ბ.ლ.1"},
    {"title":"VAT გ-ა","content":"paid:Dr1120/Cr6110/Cr3310. unpaid:Dr1210/Cr6110/Cr3310. შ.(ჩ.):Dr1310+Dr3311/Cr1120.","keywords":["vat გ","dghg","6110","3310","3311","ჩ"],"category":"vat_p","source":"ბ.ლ.4"},
    {"title":"ხ.გ-ა","content":"Dr7210=Gr.Cr3320=PIT.Cr3330=EmpP.Cr3360=Net.Dr7220/Cr3335=EmplP.","keywords":["7210","3320","3330","3360","salary","payroll"],"category":"sal_p","source":"ბ."},
    {"title":"დ-ს გ-ა","content":"ეტ.1:Dr4210/Cr3370. ეტ.2:Dr3370/Cr3340/Cr1120.","keywords":["4210","3370","3340","dividend"],"category":"div_p","source":"ბ.ლ.6"},
    {"title":"მარ.გ-ა","content":"შ:Dr1310/Cr3110.COGS:Dr7110/Cr1310.დ-სი:Dr7110/Cr1310+VAT!FIFO/LIFO.","keywords":["1310","7110","inventory","COGS","FIFO","LIFO","დ-სი","მარ"],"category":"inv","source":"ბ.ლ.3"},
    {"title":"ძ.საშ.+ამ.","content":"შ:Dr1510/Cr1120.ამ:Dr7610/Cr1520.SL=(C-R)÷L.DB=BV×%.","keywords":["1510","1520","7610","dep","ამ","fixed","FA"],"category":"fa","source":"IAS16/ბ.ლ.8"},
    {"title":"მოთხ.","content":"Dr1210/Cr6110.გ:Dr1120/Cr1210.ჩ:Dr7910/Cr1210.","keywords":["receivable","მოთხ","1210","bad","უიმ"],"category":"rec","source":"ბ.ლ.5"},
    {"title":"ვალდ.","content":"Dr1310/Cr3110.გ:Dr3110/Cr1120.ავ:Dr1120/Cr3120.","keywords":["payable","3110","3120","ვალდ","AP","ავ"],"category":"pay","source":"ბ.ლ.6"},
    {"title":"კაპ.","content":"გ-ა:Dr1120/Cr4110.მ:Dr6/Cr4210.ზ:Dr4210/Cr7.დ:Dr4210/Cr3370.","keywords":["4110","4210","RE","equity","capital","კაპ"],"category":"cap","source":"ბ.ლ.9"},
    {"title":"ქ.გ-ა","content":"მ.1%.ფ:40k-გ.15ივ+15დ.","keywords":["ქ","property","1%"],"category":"prop","source":"საგ.კ."},
    {"title":"მ/მ ბ-ი","content":"მ:<30k→0%.მც:<500k→1%/3%.","keywords":["მ","small","micro","30000","500000"],"category":"ms","source":"საგ.კ."},
    {"title":"სესხი","content":"მ:Dr1120/Cr3410.პ:Dr7520/Cr3xxx.დ:Dr3410/Cr1120.","keywords":["სესხ","loan","3410","7520","ვალ"],"category":"loan","source":"ბ.ლ.7"},
    {"title":"IFRS16","content":"ROU=PV(გ-ბ)+საწ.Dr1710/Cr3430.ამ:Dr7610/Cr1520.პ:Dr7520.<12თ→ოპ.","keywords":["ifrs16","rou","leasing","ლ","1710","3430"],"category":"ifrs16","source":"IFRS16"},
    {"title":"IFRS15","content":"5-ნ:კ-ტ→PO→ფ→გ-ა→შ.ვ.შ. კ.გ.→შ.ა.","keywords":["ifrs15","revenue","შ.აღ","performance"],"category":"ifrs15","source":"IFRS15"},
]
 
 
def search_knowledge(query, top_k=5):
    _load_files()
    q=query.lower()
    sc=[]
    for item in _KB:
        s=sum(1 for kw in item["keywords"] if kw in q)
        if s: sc.append((s,item))
    for sn,sd in ACCA_STANDARDS.items():
        for k in ["steps","rules","key_rules","formulas","lessee_accounting"]:
            for t in sd.get(k,[]):
                if any(w in t.lower() for w in q.split() if len(w)>3):
                    sc.append((0.5,{"title":sd["title"],"content":t,"source":sn,"category":"acca"}))
    for tn,td in TAX_RULES.items():
        for r in td.get("rules",[]):
            if any(w in r.lower() for w in q.split() if len(w)>2):
                sc.append((0.6,{"title":tn,"content":r,"source":tn,"category":"tax"}))
    sc.sort(key=lambda x:-x[0])
    res=[i for _,i in sc[:top_k]]
    if _TAX_TEXT and len(res)<2:
        s=_find(_TAX_TEXT,query[:20],1000)
        if s: res.append({"title":f"საგ.კ.—{query[:20]}","content":s,"source":"საგ.კ.","category":"raw_t"})
    if _ACC_TEXT and len(res)<3:
        s=_find(_ACC_TEXT,query[:20],1000)
        if s: res.append({"title":f"ბ.სხ.—{query[:20]}","content":s,"source":"ბ.სხ.","category":"raw_a"})
    return res
 
 
def get_context_for_llm(query, max_chars=3000):
    res=search_knowledge(query,6)
    parts,total=[],0
    for r in res:
        c=f"[{r['source']}]\n{r['content']}\n"
        if total+len(c)>max_chars: break
        parts.append(c); total+=len(c)
    if _TAX_TEXT:
        raw=_find(_TAX_TEXT,query[:25],800)
        if raw and total+len(raw)<max_chars: parts.append(f"[საგ.კ.]\n{raw}\n")
    if _ACC_TEXT:
        raw=_find(_ACC_TEXT,query[:25],800)
        if raw and total+len(raw)<max_chars: parts.append(f"[ბ.სხ.]\n{raw}\n")
    return "\n".join(parts)
 
 
# ══════════════════════════════════════════════════════════════
# 10. STATS
# ══════════════════════════════════════════════════════════════
 
def get_stats():
    _load_files()
    lr=_load_learned()
    return {
        "tax_rules":len(TAX_RULES),"acca":len(ACCA_STANDARDS),
        "accounts":len(CHART_OF_ACCOUNTS),"cls_rules":len(_CLS_RULES),
        "knowledge_items":len(_KB),"learned":len(lr),
        "tax_loaded":bool(_TAX_TEXT),"acc_loaded":bool(_ACC_TEXT),
        "tax_chars":len(_TAX_TEXT),"acc_chars":len(_ACC_TEXT),
        "total":len(_KB)+len(_CLS_RULES)+len(CHART_OF_ACCOUNTS)+len(TAX_RULES)+len(ACCA_STANDARDS)+len(lr),
    }
 
 
# ══════════════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🧪 Bridge Hub KB V4\n")

    v = calculate_vat(5900)
    print(f"✅ VAT: net={v['net']}₾ vat={v['vat']}₾\n{v['journal_paid']}")

    p = calculate_payroll(2000)
    print(f"\n✅ Payroll: pit={p['pit']}₾ net={p['net']}₾\n{p['journal']}")

    c = calculate_cit(10000)
    print(f"\n✅ CIT: cit={c['cit']}₾ nd={c['net_dividend']}₾\n{c['journal']}")

    d = calculate_depreciation(12000, 2000, 5)
    print(f"\n✅ Depr: {d['annual']}₾/y {d['monthly']}₾/m")

    cl = classify_transaction("TBC საბანკო საკომ 45₾")
    print(f"\n✅ Cls: {cl['account']} ({cl['confidence'] * 100:.0f}%)")

    r = learn_new_rule("Wolt", "7720", "global", "წარმ.")
    learn_msg = r.get("message") or f"updated -> {r['rule']['account']}"
    print(f"✅ Learn: {learn_msg}")

    cl2 = classify_transaction("Wolt 35₾")
    print(f"✅ Learned: {cl2['account']} ({cl2['source']})")

    st = get_stats()
    print(f"\n📊 total={st['total']} | tax={st['tax_chars']} | acc={st['acc_chars']}")

    # ══════════════════════════════════════════════════════════════
# 11. DOCUMENT → ACCOUNTING ENGINE
# ══════════════════════════════════════════════════════════════

def build_journal_from_text(text):
    """
    დოკუმენტის ტექსტიდან ბუღალტრული გატარება
    """

    text = text.lower()

    # თანხის ამოღება
    match = re.search(r'(\d[\d,\.]*)\s*(?:₾|lari|ლარი)', text)
    if not match:
        return {
            "message": "❌ თანხა ვერ მოიძებნა",
            "lines": []
        }

    amount = float(match.group(1).replace(",", ""))

    # კლასიფიკაცია
    cls = classify_transaction(text)
    account = cls["account"]

    # VAT detect
    has_vat = "დღგ" in text or "vat" in text

    if has_vat:
        vat = round(amount * 0.18 / 1.18, 2)
        net = round(amount - vat, 2)

        lines = [
            ("6110", 0, net),
            ("3310", 0, vat),
            ("1120", amount, 0),
        ]

        return {
            "message": f"📊 გაყიდვა (VAT ჩათვლით)\nNet: {_fmt(net)} | VAT: {_fmt(vat)}",
            "lines": lines,
            "description": "VAT Sale"
        }

    # Expense
    if CHART_OF_ACCOUNTS.get(account, {}).get("type") == "expense":
        lines = [
            (account, amount, 0),
            ("1120", 0, amount),
        ]

        return {
            "message": f"📊 ხარჯი ({account})",
            "lines": lines,
            "description": "Expense Posting"
        }

    # Revenue
    if CHART_OF_ACCOUNTS.get(account, {}).get("type") == "revenue":
        lines = [
            ("1120", amount, 0),
            (account, 0, amount),
        ]

        return {
            "message": f"📊 შემოსავალი ({account})",
            "lines": lines,
            "description": "Revenue Posting"
        }

    return {
        "message": "⚠️ ვერ განისაზღვრა ტიპი",
        "lines": []
    }