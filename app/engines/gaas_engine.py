from decimal import Decimal
from typing import Optional

GAAS_COA = {}
_coa_lines = """account,name_en_ge,class,normal_balance,vat_behavior
1110,Cash on hand (სალარო),Asset,Debit,none
1120,Bank accounts (ბანკი),Asset,Debit,none
1210,Accounts receivable (მყიდველები),Asset,Debit,none
1230,Advances paid to suppliers (მომწოდებლის ავანსი),Asset,Debit,none
1310,Inventory - merchandise (მარაგი),Asset,Debit,none
1410,Prepaids (წინასწარ გადახდილი),Asset,Debit,none
1420,VAT receivable / input VAT (დასაბრუნებელი დღგ),Asset,Debit,input
1520,Fixed assets - PPE (ძირითადი საშუალებები),Asset,Debit,none
1590,Accumulated depreciation (დაგროვილი ამორტიზაცია),Contra-Asset,Credit,none
2110,Accounts payable (მომწოდებლები),Liability,Credit,none
2120,Advances received from customers (კლიენტის ავანსი),Liability,Credit,none
2130,Accrued liabilities (დარიცხული ვალდებულებები),Liability,Credit,none
2140,Suspense / unidentified bank (გაურკვეველი),Liability,Credit,none
2210,VAT payable / output VAT (გადასახდელი დღგ),Liability,Credit,output
2220,PIT payable (საშემოსავლო),Liability,Credit,none
2230,Pension payable (საპენსიო),Liability,Credit,none
2310,Loans payable (სესხი),Liability,Credit,none
3100,Share capital (კაპიტალი),Equity,Credit,none
3200,Retained earnings (გაუნაწილებელი მოგება),Equity,Credit,none
4110,Revenue - goods (შემოსავალი საქონლის),Revenue,Credit,output
4120,Revenue - services (შემოსავალი მომსახურების),Revenue,Credit,output
4300,Other income (სხვა შემოსავალი),Other Income,Credit,none
5110,COGS (თვითღირებულება),COGS,Debit,none
5210,Salaries expense (ხელფასი),Expense,Debit,none
5220,Rent expense (ქირა),Expense,Debit,input
5230,Utilities expense (კომუნალური),Expense,Debit,input
5250,Marketing expense (რეკლამა),Expense,Debit,input
5260,Bank fees (ბანკის საკომისიო),Expense,Debit,none
5270,Depreciation expense (ამორტიზაცია),Expense,Debit,none
5290,Other operating expense (სხვა ხარჯი),Expense,Debit,none
5310,Interest expense (პროცენტი),Expense,Debit,none
9999,Unclassified (განუსაზღვრელი),Suspense,Debit,none""".strip().split("\n")[1:]
for line in _coa_lines:
    p = line.split(",", 4)
    if len(p) >= 2:
        GAAS_COA[p[0]] = {"code":p[0],"name":p[1],"class":p[2] if len(p)>2 else "","normal_balance":p[3] if len(p)>3 else "Debit","vat_behavior":p[4] if len(p)>4 else "none"}

GAAS_RULES = [('F3.SALES.INV', ['invoice_sales'], '1120', '4110', 'OUT_STANDARD_18', 0.98), ('F3.PURCH.INV', ['invoice_purchase_inventory'], '1310', '2110', 'IN_STANDARD_DED', 0.98), ('F3.BANK.FEE', ['bank_fee'], '5260', '1120', 'NON_VAT', 0.98), ('F3.BANK.PAY.SUP', ['bank_payment_supplier'], '2110', '1120', 'NON_VAT', 0.97), ('F3.BANK.REC.CUS', ['bank_receipt_customer'], '1120', '1210', 'NON_VAT', 0.97), ('F3.SALARY', ['payroll', 'salary_payment'], '5210', '1120', 'NON_VAT', 0.97), ('F3.RENT', ['rent_payment'], '5220', '2110', 'IN_STANDARD_DED', 0.96), ('F3.PREPAID', ['prepaid_payment'], '1410', '1120', 'NON_VAT', 0.95), ('F3.FA.CAP', ['invoice_purchase_fixed_asset'], '1520', '2110', 'IN_STANDARD_DED', 0.96), ('F3.FA.DEP', ['depreciation_monthly'], '5270', '1590', 'NON_VAT', 0.98), ('F3.INV.COGS', ['inventory_issue_sale'], '5110', '1310', 'NON_VAT', 0.97), ('F3.ADV.REC', ['advance_received_customer'], '1120', '2120', 'OUT_STANDARD_18', 0.95), ('F3.ADV.PAY', ['advance_paid_supplier'], '1230', '1120', 'IN_STANDARD_DED', 0.95), ('F3.ACCRUAL', ['accrual'], '5290', '2130', 'NON_VAT', 0.92), ('F3.SUSPENSE', ['bank_suspense'], '1120', '2140', 'NON_VAT', 0.9), ('F3.TAX.VAT', ['vat_payment'], '2210', '1120', 'NON_VAT', 0.98), ('F3.TAX.PIT', ['pit_payment', 'income_tax_payment'], '2220', '1120', 'NON_VAT', 0.98), ('F3.LOAN.REC', ['loan_received'], '1120', '2310', 'NON_VAT', 0.97), ('F3.LOAN.PAY', ['loan_repayment'], '2310', '1120', 'NON_VAT', 0.97), ('F3.UTIL', ['utility_payment'], '5230', '2130', 'IN_STANDARD_DED', 0.95), ('F3.MARKETING', ['marketing_payment'], '5250', '2110', 'IN_STANDARD_DED', 0.93)]
VAT_RATE = Decimal("0.18")
VAT_CLASSES = {
    "OUT_STANDARD_18":{"rate":Decimal("0.18"),"direction":"output","deductible":False},
    "IN_STANDARD_DED":{"rate":Decimal("0.18"),"direction":"input","deductible":True},
    "IN_STANDARD_BLOCKED":{"rate":Decimal("0.18"),"direction":"input","deductible":False},
    "OUT_ZERO_0":{"rate":Decimal("0"),"direction":"output","deductible":False},
    "OUT_EXEMPT":{"rate":Decimal("0"),"direction":"output","deductible":False},
    "RC_VAT_DUE_DED":{"rate":Decimal("0.18"),"direction":"both","deductible":True},
    "NON_VAT":{"rate":Decimal("0"),"direction":"none","deductible":False},
}

def gaas_classify_doc_type(doc_type: str) -> Optional[dict]:
    for rule_id, doc_types, dr, cr, vat_class, conf in GAAS_RULES:
        if doc_type in doc_types:
            return {"rule_id":rule_id,"debit":dr,"debit_name":GAAS_COA.get(dr,{}).get("name",dr),"credit":cr,"credit_name":GAAS_COA.get(cr,{}).get("name",cr),"vat_class":vat_class,"confidence":conf,"match_method":"rule"}
    return None

def gaas_classify_text(description: str, counterparty: str = "") -> Optional[dict]:
    text = f"{description} {counterparty}".lower()
    keyword_map = [
        (["invoice","ანგარიშფაქტურა","sale","გაყიდვა"],     "invoice_sales"),
        (["purchase","შესყიდვა","inventory","მარაგი"],       "invoice_purchase_inventory"),
        (["salary","ხელფასი","payroll","პრემია"],            "salary_payment"),
        (["rent","ქირა","იჯარა"],                            "rent_payment"),
        (["depreciation","ამორტიზაცია"],                    "depreciation_monthly"),
        (["bank fee","commission","საბანკო","საკომისიო"],   "bank_fee"),
        (["vat","დღგ","rs.ge","revenue service"],            "vat_payment"),
        (["income tax","pit","საშემოსავლო"],                 "income_tax_payment"),
        (["loan","სესხი"],                                   "loan_received"),
        (["utility","electric","water","კომუნალური"],        "utility_payment"),
        (["marketing","advertising","რეკლამა"],              "marketing_payment"),
        (["supplier payment","მომწოდე"],                     "bank_payment_supplier"),
    ]
    for keywords, doc_type in keyword_map:
        if any(kw in text for kw in keywords):
            result = gaas_classify_doc_type(doc_type)
            if result:
                result = dict(result)
                result["confidence"] = round(max(0.70, result["confidence"] - 0.10), 2)
                result["match_method"] = "keyword"
                return result
    return None

def compute_vat_split(gross: Decimal, vat_class: str) -> dict:
    vc = VAT_CLASSES.get(vat_class, VAT_CLASSES["NON_VAT"])
    rate = vc["rate"]
    if rate == 0:
        return {"net":gross,"vat":Decimal("0"),"gross":gross,"vat_class":vat_class,"rate":0.0}
    vat = (gross * rate / (1 + rate)).quantize(Decimal("0.01"))
    return {"net":gross-vat,"vat":vat,"gross":gross,"vat_class":vat_class,"rate":float(rate)}

def compute_vat_return(docs: list) -> dict:
    """F4 — period VAT return aggregation."""
    vat_out = Decimal("0")
    vat_in  = Decimal("0")
    rc_due  = Decimal("0")
    rc_ded  = Decimal("0")
    adjs    = Decimal("0")
    for d in docs:
        vc = d.get("vat_class","NON_VAT")
        vat_amount = Decimal(str(d.get("vat_amount","0")))
        if vc in ["OUT_STANDARD_18","OUT_ZERO_0","ADJ_OUT_DEBIT"]: vat_out += vat_amount
        elif vc == "ADJ_OUT_CREDIT": adjs -= vat_amount
        elif vc in ["IN_STANDARD_DED","IMPORT_VAT_DED"]: vat_in += vat_amount
        elif vc == "RC_VAT_DUE_DED": rc_due += vat_amount; rc_ded += vat_amount
        elif vc == "RC_VAT_DUE_BLOCKED": rc_due += vat_amount
    payable = vat_out + rc_due + adjs - vat_in - rc_ded
    return {"vat_out_total":float(vat_out),"vat_in_deductible_total":float(vat_in),"reverse_charge_vat_due":float(rc_due),"reverse_charge_vat_deductible":float(rc_ded),"adjustments_net":float(adjs),"vat_payable":float(payable)}
