import psycopg2

conn = psycopg2.connect(
    host="35.192.214.120",
    dbname="bridgehub",
    user="postgres",
    password="BridgeHub2026x",
)
conn.autocommit = True
cur = conn.cursor()

sqls = [
    "ALTER TABLE processed_bank_files ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'",
    "UPDATE processed_bank_files SET tenant_id = 'default' WHERE tenant_id IS NULL",
    "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'",
    "UPDATE journal_drafts SET tenant_id = 'default' WHERE tenant_id IS NULL",
    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'",
    "UPDATE bank_transactions SET tenant_id = 'default' WHERE tenant_id IS NULL",
    "ALTER TABLE posting_logs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'",
    "UPDATE posting_logs SET tenant_id = 'default' WHERE tenant_id IS NULL",
]

for sql in sqls:
    print("Running:", sql[:70])
    try:
        cur.execute(sql)
        print("OK")
    except Exception as e:
        print("Skip:", e)

print("Done!")
cur.close()
conn.close()