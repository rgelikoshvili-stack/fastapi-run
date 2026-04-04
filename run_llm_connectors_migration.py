import os, psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur  = conn.cursor()

steps = [
    ("tax_rules ცხრილი", """
        CREATE TABLE IF NOT EXISTS tax_rules (
            id        SERIAL PRIMARY KEY,
            tenant_id VARCHAR(100) DEFAULT 'default',
            rule_name VARCHAR(100),
            condition JSONB,
            action    JSONB,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """),
    ("llm_cost_log ცხრილი", """
        CREATE TABLE IF NOT EXISTS llm_cost_log (
            id         SERIAL PRIMARY KEY,
            tenant_id  VARCHAR(100) DEFAULT 'default',
            model      VARCHAR(50),
            tokens_in  INT DEFAULT 0,
            tokens_out INT DEFAULT 0,
            cost_usd   DECIMAL(10,6) DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """),
    ("journal_drafts index", """
        CREATE INDEX IF NOT EXISTS idx_journal_drafts_tenant_status
        ON journal_drafts(tenant_id, status)
    """),
    ("learning_patterns index", """
        CREATE INDEX IF NOT EXISTS idx_learning_patterns_tenant_type
        ON learning_patterns(tenant_id, pattern_type, status)
    """),
]

for name, sql in steps:
    try:
        cur.execute(sql)
        conn.commit()
        print(f"OK: {name}")
    except Exception as e:
        conn.rollback()
        print(f"ERROR {name}: {e}")

cur.close()
conn.close()
print("Done!")
