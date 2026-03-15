from app.api.db import get_db

conn = get_db()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM journal_drafts WHERE tx_fingerprint IS NULL")
print(cur.fetchone()[0])

cur.close()
conn.close()