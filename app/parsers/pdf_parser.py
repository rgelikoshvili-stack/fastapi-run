import pdfplumber
from app.schemas.canonical import CanonicalDocument

def parse_pdf_document(filepath: str) -> CanonicalDocument:
    try:
        with pdfplumber.open(filepath) as pdf:
            full_text = ''
            for page in pdf.pages:
                full_text += page.extract_text() or ''
        return CanonicalDocument(
            doc_type='unknown',
            filename=filepath.split('/')[-1],
            extracted_text=full_text[:10000],
            source='upload',
            confidence=0.80,
        )
    except Exception as e:
        return CanonicalDocument(
            doc_type='unknown',
            filename=filepath.split('/')[-1],
            extracted_text='',
            source='upload',
            confidence=0.0,
            structured_fields={'error': str(e)},
        )
