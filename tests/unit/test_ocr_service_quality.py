def test_missing_journal_entries_column_detection_by_exception_name():
    from app.api.services.ocr_service import _is_missing_journal_entries_column

    UndefinedColumnError = type("UndefinedColumnError", (Exception,), {})

    assert _is_missing_journal_entries_column(UndefinedColumnError("column missing")) is True


def test_missing_journal_entries_column_detection_by_message():
    from app.api.services.ocr_service import _is_missing_journal_entries_column

    exc = Exception('column "journal_entries" does not exist')

    assert _is_missing_journal_entries_column(exc) is True


def test_non_schema_insert_error_does_not_trigger_fallback():
    from app.api.services.ocr_service import _is_missing_journal_entries_column

    exc = Exception("duplicate key value violates unique constraint")

    assert _is_missing_journal_entries_column(exc) is False
