import psycopg2

conn = psycopg2.connect(
    host="35.192.214.120",
    dbname="bridgehub",
    user="postgres",
    password="BridgeHub2026x",
)

cur = conn.cursor()

cur.execute("ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS partner TEXT DEFAULT '';")
cur.execute("ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'GEL';")
cur.execute("ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS lines_json JSONB DEFAULT '[]'::jsonb;")

conn.commit()
cur.close()
conn.close()

print("OK")
