import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("DB_HOST", "35.192.214.120")
dbname = os.getenv("DB_NAME", "bridgehub")
user = os.getenv("DB_USER", "postgres")
password = os.getenv("DB_PASSWORD", "BridgeHub2026x")

sql_commands = [
    "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS usage_count INT DEFAULT 0;",
    "UPDATE learning_patterns SET usage_count = 0 WHERE usage_count IS NULL;",
    "CREATE INDEX IF NOT EXISTS idx_learning_patterns_usage_count ON learning_patterns(usage_count);",

    "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP;",
    "CREATE INDEX IF NOT EXISTS idx_learning_patterns_last_used_at ON learning_patterns(last_used_at);",

    "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS weighted_success_score FLOAT DEFAULT 0;",
    "UPDATE learning_patterns SET weighted_success_score = 0 WHERE weighted_success_score IS NULL;",

    "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS weighted_failure_score FLOAT DEFAULT 0;",
    "UPDATE learning_patterns SET weighted_failure_score = 0 WHERE weighted_failure_score IS NULL;",
]

conn = psycopg2.connect(
    host=host,
    dbname=dbname,
    user=user,
    password=password,
)

conn.autocommit = True

try:
    with conn.cursor() as cur:
        for sql in sql_commands:
            print(f"Running: {sql}")
            cur.execute(sql)
    print("Learning pattern upgrade migration completed successfully.")
finally:
    conn.close()