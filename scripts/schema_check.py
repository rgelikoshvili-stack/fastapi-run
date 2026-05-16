# SEC-1: Hardcoded production credentials removed.
# This script previously contained:
#   - A hardcoded production DB URL with a hardcoded password (<PLACEHOLDER_ONLY>)
#   - A hardcoded SSH connection to a production IP as root with a hardcoded password
# All hardcoded values have been replaced with required environment variables.
# This script must NEVER run against a production server without explicit human approval.
#
# Required environment variables:
#   SSH_HOST     — non-production SSH host only; script refuses known production IPs
#   SSH_USER     — SSH username
#   SSH_PASSWORD — SSH password (use key-based auth in preference)
#   DB_URL       — full DB URL for the remote schema check; must not contain known prod credentials
#
# Example (non-production only):
#   export SSH_HOST=<NON_PROD_SSH_HOST>
#   export SSH_USER=<NON_PROD_SSH_USER>
#   export SSH_PASSWORD=<NON_PROD_SSH_PASSWORD>
#   export DB_URL=postgresql://<NON_PROD_DB_USER>:<NON_PROD_DB_PASSWORD>@<NON_PROD_DB_HOST>:<NON_PROD_DB_PORT>/<DISPOSABLE_DB>

import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_KNOWN_PRODUCTION_SSH_HOSTS = {"116.203.134.24", "35.192.214.120"}

SSH_HOST = os.getenv("SSH_HOST")
SSH_USER = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")
DB_URL = os.getenv("DB_URL")

if not SSH_HOST:
    print("ERROR: SSH_HOST is not set. Set to a non-production host.", file=sys.stderr)
    print("  Example: export SSH_HOST=<NON_PROD_SSH_HOST>", file=sys.stderr)
    sys.exit(1)
if not SSH_USER:
    print("ERROR: SSH_USER is not set.", file=sys.stderr)
    sys.exit(1)
if not SSH_PASSWORD:
    print("ERROR: SSH_PASSWORD is not set.", file=sys.stderr)
    sys.exit(1)
if not DB_URL:
    print("ERROR: DB_URL is not set.", file=sys.stderr)
    print("  Example: export DB_URL=postgresql://<USER>:<PASSWORD>@<HOST>/<DB>", file=sys.stderr)
    sys.exit(1)
if SSH_HOST in _KNOWN_PRODUCTION_SSH_HOSTS:
    print(f"ERROR: SSH_HOST={SSH_HOST!r} matches a known production IP. Refusing.", file=sys.stderr)
    sys.exit(1)

try:
    import paramiko
except ImportError:
    print("ERROR: paramiko is not installed. Run: pip install paramiko", file=sys.stderr)
    sys.exit(1)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SSH_HOST, username=SSH_USER, password=SSH_PASSWORD, timeout=15)

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
with sftp.open("/tmp/schema_check.py", "w") as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command(
    "/opt/bridge-hub/.venv/bin/python3 /tmp/schema_check.py", timeout=15
)
print(stdout.read().decode("utf-8", errors="replace"))
err = stderr.read().decode("utf-8", errors="replace")
if err:
    print("ERR:", err[:500])
ssh.close()
