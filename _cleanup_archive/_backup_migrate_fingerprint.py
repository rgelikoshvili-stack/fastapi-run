import psycopg2

conn = psycopg2.connect(
    host="35.192.214.120",
    dbname="bridgehub",
    user="postgres",
    password="BridgeHub2026x",
)
conn.set_client_encoding("UTF8")
cur = conn.cursor()

cur.execute("""
    ALTER TABLE journal_drafts 
    ADD COLUMN IF NOT EXISTS tx_fingerprint TEXT;
""")

cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_drafts_fingerprint 
    ON journal_drafts(tx_fingerprint) 
    WHERE tx_fingerprint IS NOT NULL;
""")

cur.execute("""
    ALTER TABLE posting_logs
    ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN DEFAULT FALSE;
""")

conn.commit()
cur.close()
conn.close()
print("Migration OK")
