import psycopg2
import os

def get_db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.set_client_encoding("UTF8")
    return conn