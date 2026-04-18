import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS users")
cur.execute("""
    CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        tenant_id VARCHAR(100) DEFAULT 'default',
        role VARCHAR(50) DEFAULT 'accountant',
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW(),
        last_login TIMESTAMP,
        UNIQUE(email, tenant_id)
    )
""")
conn.commit()
cur.close()
conn.close()
print("Done!")
