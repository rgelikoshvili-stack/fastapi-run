"""app/startup/migrations_tables.py — CREATE TABLE IF NOT EXISTS migrations."""
import logging

log = logging.getLogger(__name__)


def run_table_migrations(cur):
    """Create all application tables (idempotent — IF NOT EXISTS)."""
    conn = cur.connection

    # Expense articles + expenses
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expense_articles (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            code        TEXT,
            name        TEXT NOT NULL,
            account     TEXT,
            vat_rate    NUMERIC DEFAULT 18,
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id              SERIAL PRIMARY KEY,
            tenant_id       TEXT NOT NULL DEFAULT 'default',
            article_id      INTEGER REFERENCES expense_articles(id),
            description     TEXT NOT NULL,
            amount          NUMERIC NOT NULL,
            currency        TEXT DEFAULT 'GEL',
            expense_date    DATE,
            supplier        TEXT,
            supplier_inn    TEXT,
            vat_amount      NUMERIC DEFAULT 0,
            status          TEXT DEFAULT 'draft',
            notes           TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Invoices
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id              SERIAL PRIMARY KEY,
            tenant_id       TEXT NOT NULL DEFAULT 'default',
            invoice_number  TEXT,
            customer_id     INTEGER REFERENCES customers(id),
            customer_name   TEXT,
            customer_inn    TEXT,
            invoice_date    DATE,
            due_date        DATE,
            subtotal        NUMERIC DEFAULT 0,
            vat_amount      NUMERIC DEFAULT 0,
            total           NUMERIC DEFAULT 0,
            currency        TEXT DEFAULT 'GEL',
            status          TEXT DEFAULT 'draft',
            notes           TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS invoice_lines (
            id          SERIAL PRIMARY KEY,
            invoice_id  INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            description TEXT NOT NULL,
            quantity    NUMERIC DEFAULT 1,
            unit_price  NUMERIC NOT NULL,
            vat_rate    NUMERIC DEFAULT 18,
            line_total  NUMERIC,
            account     TEXT
        );
    """)

    # invoices — FX columns
    for _inv_sql in [
        "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS original_rate NUMERIC DEFAULT 1.0",
        "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC DEFAULT 1.0",
    ]:
        try:
            cur.execute(_inv_sql)
            conn.commit()
        except Exception:
            conn.rollback()

    # Collaboration
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            entity_type TEXT NOT NULL,
            entity_id   INTEGER NOT NULL,
            author      TEXT,
            content     TEXT NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS attachments (
            id          SERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            entity_type TEXT NOT NULL,
            entity_id   INTEGER NOT NULL,
            file_name   TEXT NOT NULL,
            file_size   INTEGER,
            mime_type   TEXT,
            gcs_path    TEXT,
            uploaded_by TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Chat sessions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          SERIAL PRIMARY KEY,
            session_id  TEXT UNIQUE NOT NULL,
            tenant_id   TEXT NOT NULL DEFAULT 'default',
            user_id     TEXT,
            messages    JSONB DEFAULT '[]',
            context     JSONB DEFAULT '{}',
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    for _cs_sql in [
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id TEXT",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS messages JSONB DEFAULT '[]'",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS context JSONB DEFAULT '{}'",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
    ]:
        try:
            cur.execute(_cs_sql)
            conn.commit()
        except Exception:
            conn.rollback()
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant_session ON chat_sessions(tenant_id, session_id)")
    except Exception:
        conn.rollback()

    # Idempotency keys
    cur.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            id              SERIAL PRIMARY KEY,
            tenant_id       TEXT NOT NULL,
            idempotent_key  TEXT NOT NULL,
            endpoint        TEXT,
            response        JSONB,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(tenant_id, idempotent_key, endpoint)
        );
        CREATE INDEX IF NOT EXISTS idx_idempotency_keys_lookup
            ON idempotency_keys(tenant_id, idempotent_key, endpoint);
    """)

    # Search index
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS search_index (
                id         SERIAL PRIMARY KEY,
                doc_id     VARCHAR(100),
                doc_type   VARCHAR(50),
                filename   VARCHAR(300),
                amount     FLOAT,
                state      VARCHAR(50),
                tags       TEXT[],
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
    except Exception:
        conn.rollback()

    # Bank reconciliation
    for recon_sql in [
        """
        CREATE TABLE IF NOT EXISTS bank_reconciliations (
            id                   SERIAL PRIMARY KEY,
            tenant_id            TEXT NOT NULL,
            bank_transaction_id  INTEGER NOT NULL,
            draft_id             INTEGER NOT NULL,
            reconciled_at        TIMESTAMPTZ DEFAULT NOW(),
            reconciled_by        TEXT
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reconciliation_unique
            ON bank_reconciliations(bank_transaction_id, draft_id)
        """,
        "CREATE INDEX IF NOT EXISTS idx_reconciliation_tenant ON bank_reconciliations(tenant_id)",
    ]:
        try:
            cur.execute(recon_sql)
            conn.commit()
        except Exception:
            conn.rollback()
