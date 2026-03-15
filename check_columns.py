import sys
sys.path.insert(0, ".")

from app.api.db import get_db

conn = get_db()
cur = conn.cursor()

cur.execute("""
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'journal_drafts'
ORDER BY ordinal_position
""")

print([r[0] for r in cur.fetchall()])

cur.close()
conn.close()