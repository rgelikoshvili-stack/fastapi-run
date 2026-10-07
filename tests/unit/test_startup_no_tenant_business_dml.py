"""Guard against tenant business-data repairs running from startup migrations."""

from concurrent.futures import ThreadPoolExecutor

from app.startup.migrations_indexes import run_index_migrations


PROTECTED_BUSINESS_TABLES = {
    "journal_drafts",
    "processed_documents",
    "learning_patterns",
    "audit_log",
    "bank_transactions",
    "chart_of_accounts",
}


class RecordingConnection:
    def __init__(self):
        self.rollbacks = 0
        self.commits = 0

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        self.commits += 1


class RecordingCursor:
    def __init__(self):
        self.connection = RecordingConnection()
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(" ".join(sql.lower().split()))


def _run_index_startup():
    cursor = RecordingCursor()
    run_index_migrations(cursor)
    return cursor


def test_index_startup_never_reads_or_mutates_protected_business_rows():
    cursor = _run_index_startup()
    forbidden = ("select ", "update ", "delete ", "insert ")
    unsafe = [
        statement
        for statement in cursor.statements
        if statement.startswith(forbidden)
        and any(table in statement for table in PROTECTED_BUSINESS_TABLES)
    ]
    assert unsafe == []


def test_startup_does_not_run_tenant_normalization_or_draft_classification():
    cursor = _run_index_startup()
    sql = "\n".join(cursor.statements)
    assert "from tenants t" not in sql
    assert "auto_classify_drafts" not in sql
    assert " or 'default'" not in sql
    assert not any(
        statement.startswith("update journal_drafts")
        or statement.startswith("update processed_documents")
        for statement in cursor.statements
    )


def test_concurrent_startups_cannot_trigger_business_data_repair():
    with ThreadPoolExecutor(max_workers=2) as executor:
        cursors = list(executor.map(lambda _: _run_index_startup(), range(2)))

    for cursor in cursors:
        assert not any(
            statement.startswith(("update ", "delete ", "insert "))
            and any(table in statement for table in PROTECTED_BUSINESS_TABLES)
            for statement in cursor.statements
        )
