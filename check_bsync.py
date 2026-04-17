c = open('app/api/connectors/bank_sync_connector.py', 'r', encoding='utf-8').read()
lines = c.split('\n')
print('BEFORE line 271:', repr(lines[270]))

old = """                        '1210', '1210', '1210',
                        'bank_sync', 0.5, 'pending_approval',"""

new = """                        dr_account, cr_account, acc_code,
                        'bank_sync', confidence, 'pending_approval',"""

# ვნახოთ INSERT-ის სრული context (260-285)
for i in range(259, 286):
    print(f'{i+1}: {lines[i]}')
