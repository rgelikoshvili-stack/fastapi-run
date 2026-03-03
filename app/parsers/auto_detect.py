from pathlib import Path

MIME_MAP = {
    'application/pdf': 'pdf',
    'text/csv': 'csv',
    'text/plain': 'csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/vnd.ms-excel': 'xls',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
}

def detect_file_type(filepath: str) -> str:
    ext = Path(filepath).suffix.lower().lstrip('.')
    if ext in ['csv', 'pdf', 'xlsx', 'xls', 'docx']:
        return ext
    try:
        import magic
        mime = magic.from_file(filepath, mime=True)
        return MIME_MAP.get(mime, 'unknown')
    except:
        return 'unknown'

def get_parser(filepath: str):
    file_type = detect_file_type(filepath)
    if file_type == 'csv':
        from app.parsers.csv_parser import parse_csv_bank_statement
        return parse_csv_bank_statement
    elif file_type == 'pdf':
        from app.parsers.pdf_parser import parse_pdf_document
        return parse_pdf_document
    elif file_type in ['xlsx', 'xls']:
        from app.parsers.xlsx_parser import parse_xlsx_statement
        return parse_xlsx_statement
    return None
