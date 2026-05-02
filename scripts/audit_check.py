import urllib.request, urllib.error, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = 'http://116.203.134.24'

def login():
    data = json.dumps({'email':'r.gelikoshvili@gmail.com','password':'Admin2026!'}).encode()
    req = urllib.request.Request(BASE+'/auth/login', data=data, headers={'Content-Type':'application/json'})
    resp = urllib.request.urlopen(req, timeout=10)
    body = json.loads(resp.read())
    return body['data']['access_token']

token = login()
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

def get(path):
    try:
        req = urllib.request.Request(BASE+path, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read())
        return resp.status, body
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read())
        except: body = {}
        return e.code, body
    except Exception as ex:
        return 0, str(ex)

def post(path, payload={}):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(BASE+path, data=data, headers=headers, method='POST')
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read())
        return resp.status, body
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read())
        except: body = {}
        return e.code, body
    except Exception as ex:
        return 0, str(ex)

def chk(label, code, body, info=''):
    status = 'OK  ' if code == 200 else 'FAIL'
    extra = ''
    if isinstance(body, dict):
        if info:
            extra = ' | ' + str(info)
        elif body.get('ok') is True:
            extra = ' | ok=True'
        elif 'error' in body:
            err = body['error']
            if isinstance(err, dict):
                extra = ' | ' + str(err.get('message', err))
            else:
                extra = ' | ' + str(err)[:80]
    elif code != 200:
        extra = ' | ' + str(body)[:80]
    print(f'  {status} [{code}] {label}{extra}')

print()
print('== CORE SYSTEM ==')
s,b = get('/health/'); chk('health', s, b)
s,b = get('/version'); chk('version', s, b, info=b.get('version','') if isinstance(b,dict) else '')
s,b = get('/system/overview'); chk('system overview', s, b)

print()
print('== AUTH ==')
s,b = post('/auth/login', {'email':'r.gelikoshvili@gmail.com','password':'Admin2026!'})
chk('login', s, b)
s,b = get('/auth/me')
email = b.get('data',{}).get('email','') if isinstance(b,dict) else ''
chk('auth/me', s, b, info=email)
s,b = get('/auth/roles'); chk('roles', s, b)

print()
print('== APPROVAL QUEUE ==')
s,b = get('/approval/queue?limit=5')
cnt = len(b.get('data',{}).get('items',[])) if isinstance(b,dict) else '?'
chk('queue', s, b, info=f'items={cnt}')
s,b = get('/approval/stats')
chk('stats', s, b, info=f'pending={b.get("pending_count","?")}' if isinstance(b,dict) else '')
s,b = get('/approval/audit?limit=5'); chk('audit log', s, b)
s,b = get('/approval/awaiting-cfo'); chk('awaiting CFO', s, b)

print()
print('== POSTING ==')
s,b = get('/posting/history?limit=5'); chk('posting history', s, b)
s,b = get('/posting/approved-drafts'); chk('approved drafts', s, b)
s,b = get('/posting/logs'); chk('posting logs', s, b)
s,b = get('/posting/balance-status'); chk('balance status', s, b)

print()
print('== DOCUMENTS ==')
s,b = get('/documents/waybills'); chk('waybills', s, b)
s,b = get('/documents/tax-invoices'); chk('tax invoices', s, b)

print()
print('== CHART OF ACCOUNTS ==')
s,b = get('/coa/list?limit=5'); chk('coa list', s, b)
s,b = get('/coa/summary'); chk('coa summary', s, b, info=f'total={b.get("total_accounts","?")}' if isinstance(b,dict) else '')
s,b = get('/coa/categories'); chk('coa categories', s, b)

print()
print('== REPORTS ==')
s,b = get('/reports/trial-balance'); chk('trial-balance', s, b)
s,b = get('/reports/balance-sheet'); chk('balance-sheet', s, b)
s,b = get('/reports/pnl'); chk('P&L', s, b)
s,b = get('/reports/cashflow'); chk('cashflow', s, b)
s,b = get('/reports/journal?limit=5'); chk('journal report', s, b)
s,b = get('/reports/aging/receivables'); chk('aged receivables', s, b)
s,b = get('/reports/aging/payables'); chk('aged payables', s, b)
s,b = get('/reports/gl-reconciliation'); chk('GL reconciliation', s, b)
s,b = get('/reports/monthly?year=2025'); chk('monthly report', s, b)
s,b = get('/reports/payroll?year=2025'); chk('payroll report', s, b)

print()
print('== BANK ==')
s,b = get('/bank-accounts/list')
cnt = len(b.get('data',[])) if isinstance(b,dict) else '?'
chk('bank accounts', s, b, info=f'count={cnt}')
s,b = get('/bank-accounts/summary'); chk('bank summary', s, b)
s,b = get('/reconciliation/history?limit=5'); chk('reconciliation history', s, b)
s,b = get('/bank-csv/history?limit=5'); chk('bank CSV history', s, b)

print()
print('== INVOICES ==')
s,b = get('/invoices/list?limit=5')
tot = b.get('data',{}).get('total',0) if isinstance(b,dict) else '?'
chk('invoices list', s, b, info=f'total={tot}')
s,b = get('/invoices/stats/summary'); chk('invoice stats', s, b)

print()
print('== EXPENSES ==')
s,b = get('/expenses/list?limit=5'); chk('expenses list', s, b)
s,b = get('/expenses/summary'); chk('expenses summary', s, b)
s,b = get('/expenses/categories'); chk('expense categories', s, b)
s,b = get('/expense-articles/list'); chk('expense articles', s, b)

print()
print('== CONTRACTS ==')
s,b = get('/contracts/list?limit=5'); chk('contracts list', s, b)
s,b = get('/contracts/summary/stats'); chk('contracts stats', s, b)

print()
print('== CRM ==')
s,b = get('/crm/customers?limit=5'); chk('customers', s, b)
s,b = get('/crm/summary'); chk('CRM summary', s, b)

print()
print('== PAYROLL ==')
s,b = get('/employees?limit=5')
cnt = len(b.get('data',{}).get('items',[])) if isinstance(b,dict) else '?'
chk('employees', s, b, info=f'count={cnt}')
s,b = get('/payroll/history?limit=5'); chk('payroll history', s, b)
s,b = get('/payroll/status'); chk('payroll status', s, b)

print()
print('== TAX ==')
s,b = get('/tax/rates'); chk('tax rates', s, b)
s,b = post('/tax/corporate', {'profit':50000,'distributed':True}); chk('tax corporate 2025', s, b)
s,b = get('/tax/from-journal/2025'); chk('tax from-journal 2025', s, b)
s,b = post('/tax/annual-summary', {'annual_revenue':200000,'annual_expenses':150000,'employee_count':5,'avg_salary':2000}); chk('tax annual 2025', s, b)
s,b = post('/tax/salary', {'gross_salary':3000,'employee_type':'resident'}); chk('tax salary calc', s, b)
s,b = post('/tax/vat', {'amount':1000,'inclusive':False}); chk('VAT calc', s, b)
s,b = post('/tax/dividend', {'gross_amount':10000}); chk('dividend tax', s, b)

print()
print('== CURRENCY ==')
s,b = get('/currency/rates')
cnt = len(b.get('data',{}).get('rates',[])) if isinstance(b,dict) else '?'
chk('currency rates', s, b, info=f'{cnt} currencies')
s,b = post('/currency/convert', {'amount':100,'from_currency':'USD','to_currency':'GEL'})
chk('currency convert', s, b)

print()
print('== INVENTORY ==')
s,b = get('/inventory/items?limit=5'); chk('inventory items', s, b)
s,b = get('/inventory/purchase-orders?limit=5'); chk('purchase orders', s, b)
s,b = get('/inventory/valuation'); chk('inventory valuation', s, b)
s,b = get('/inventory/reorder-report'); chk('reorder report', s, b)
s,b = get('/inventory/warehouses'); chk('warehouses', s, b)

print()
print('== FIXED ASSETS ==')
s,b = get('/fixed-assets/'); chk('fixed assets list', s, b)
s,b = get('/fixed-assets/depreciation-report' if '/fixed-assets/depreciation-report' in [] else '/fixed-assets/'); chk('depreciation', s, b)

print()
print('== BUDGET ==')
s,b = get('/budget/list/2025'); chk('budget 2025', s, b)
s,b = get('/budget/vs-actual/2025'); chk('budget vs actual', s, b)
s,b = get('/budget/forecast/2025'); chk('budget forecast', s, b)

print()
print('== COST CENTERS ==')
s,b = get('/cost-centers'); chk('cost centers', s, b)
s,b = get('/cost-centers/analysis'); chk('cost center analysis', s, b)

print()
print('== FX ==')
s,b = get('/fx/exposure'); chk('fx exposure (fixed)', s, b)
s,b = get('/fx/rates/USD')
rate = (b.get('data') or {}).get('rate_gel','?') if isinstance(b,dict) else '?'
chk('fx USD rate', s, b, info=f'1 USD = {rate} GEL')
s,b = post('/fx/calculate', {'currency':'USD','amount':1000,'original_rate':2.7})
chk('fx calculate', s, b)

print()
print('== AUDIT TRAIL ==')
s,b = get('/audit-trail/recent?limit=5')
cnt = b.get('data',{}).get('count',0) if isinstance(b,dict) else '?'
chk('audit-trail recent (fixed)', s, b, info=f'events={cnt}')

print()
print('== ACCOUNTING PERIODS ==')
s,b = get('/accounting/periods'); chk('accounting periods', s, b)

print()
print('== WEBHOOKS ==')
s,b = get('/webhooks/list'); chk('webhooks', s, b)
s,b = get('/webhooks/events'); chk('webhook events', s, b)

print()
print('== INTEGRATIONS ==')
s,b = get('/integrations/status'); chk('integrations', s, b)

print()
print('== AI ==')
s,b = post('/api/ai/classify', {'description':'Wolt delivery'})
chk('classify Wolt', s, b, info=f'account={b.get("account","?")} conf={b.get("confidence","?")}' if isinstance(b,dict) else '')
s,b = post('/api/ai/classify', {'description':'TBC Bank loan repayment'})
chk('classify TBC loan', s, b, info=f'account={b.get("account","?")}' if isinstance(b,dict) else '')
s,b = post('/api/ai/payroll', {'gross':3000})
chk('ai payroll 3000', s, b, info=f'net={b.get("net","?")} pit={b.get("pit","?")}' if isinstance(b,dict) else '')
s,b = post('/api/ai/vat', {'amount':1000,'inclusive':False})
chk('ai vat excl', s, b, info=f'vat={b.get("vat_amount","?")} total={b.get("total","?")}' if isinstance(b,dict) else '')
s,b = get('/api/ai/recommend'); chk('ai recommend', s, b)
s,b = get('/api/ai/stats'); chk('ai stats', s, b)
s,b = get('/learning/stats'); chk('learning stats', s, b)
s,b = get('/learning/patterns/top'); chk('top patterns', s, b)

print()
print('== DASHBOARD ==')
s,b = get('/dashboard/'); chk('dashboard (SPA root=HTML)', s, b if s==200 else b)
s,b = get('/dashboard/insights'); chk('dashboard insights', s, b)
s,b = get('/dashboard/live/kpi'); chk('live KPI', s, b)
s,b = get('/dashboard/live/summary'); chk('live summary', s, b)

print()
print('== CLIENT PORTAL ==')
s,b = get('/client/status'); chk('client portal status', s, b)

print()
print('== SEARCH ==')
s,b = post('/search/query', {'q':'invoice','limit':5}); chk('search query', s, b)
s,b = get('/search/stats'); chk('search stats', s, b)

print()
print('== NOTIFICATIONS ==')
s,b = get('/notifications/list'); chk('notifications', s, b)
s,b = get('/notifications/feed'); chk('notification feed', s, b)

print()
print('== AUDIT ENGINE ==')
s,b = get('/audit-engine/summary'); chk('audit engine summary', s, b)
s,b = get('/audit-engine/anomalies'); chk('anomalies', s, b)
s,b = get('/audit-engine/duplicates'); chk('duplicates check', s, b)

print()
print('AUDIT COMPLETE')
