import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_URL = 'postgresql://bridgehub:BridgeHub2026x@localhost/bridgehub'
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('116.203.134.24', username='root', password='BridgeHub2026x!', timeout=15)

script = f"""
import psycopg2
conn = psycopg2.connect('{DB_URL}')
cur = conn.cursor()
for tbl in ['pipeline_runs']:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (tbl,))
    cols = [r[0] for r in cur.fetchall()]
    print(tbl + ':', cols if cols else '(no table)')
conn.close()
"""

sftp = ssh.open_sftp()
with sftp.open('/tmp/schema_check.py', 'w') as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('/opt/bridge-hub/.venv/bin/python3 /tmp/schema_check.py', timeout=15)
print(stdout.read().decode('utf-8', errors='replace'))
err = stderr.read().decode('utf-8', errors='replace')
if err: print('ERR:', err[:500])
ssh.close()
