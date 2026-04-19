from fastapi import APIRouter, UploadFile, File, HTTPException
import tempfile, os
from app.parsers.auto_detect import detect_file_type, get_parser
from app.storage.event_log import write as audit_write

router = APIRouter(prefix='/bank', tags=['bank'])

@router.post('/upload')
async def bank_upload(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        file_type = detect_file_type(tmp_path)
        parser = get_parser(tmp_path)
        if not parser:
            raise HTTPException(400, f'Unsupported file type: {file_type}')
        results = parser(tmp_path)
        if isinstance(results, list):
            txs = [r.model_dump() for r in results]
            for tx in txs:
                tx['date'] = str(tx['date'])
                tx['amount'] = str(tx['amount'])
                audit_write(tx['id'], 'transaction', '', 'received', 'system', f'uploaded from {file.filename}')
            return {'ok': True, 'file_type': file_type, 'count': len(txs), 'transactions': txs}
        else:
            doc = results.model_dump()
            return {'ok': True, 'file_type': file_type, 'document': doc}
    finally:
        os.unlink(tmp_path)

@router.get('/audit-log')
def get_audit_log():
    from app.storage.event_log import get_log
    return {'ok': True, 'events': get_log()}
