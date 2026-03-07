import psycopg2
import os

def get_db():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "35.192.214.120"),
        dbname=os.environ.get("DB_NAME", "bridgehub"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "BridgeHub2026x")
    )
