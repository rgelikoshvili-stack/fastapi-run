from app.api.db import get_db

conn = get_db()
cur = conn.cursor()

cur.execute("""
SELECT tx_fingerprint, COUNT(*)
FROM journal_drafts
GROUP BY tx_fingerprint
HAVING COUNT(*) > 1
""")

rows = cur.fetchall()

print("duplicate fingerprints:", len(rows))

for r in rows[:10]:
    print(r)

cur.close()
conn.close()