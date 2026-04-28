import fitz
from app.schemas.canonical import CanonicalDocument

def parse_pdf_document(filepath: str) -> CanonicalDocument:
    try:
        doc = fitz.open(filepath)
        full_text = "".join(doc[i].get_text() for i in range(len(doc)))
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
