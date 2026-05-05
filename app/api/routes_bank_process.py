from fastapi import APIRouter, UploadFile, File, Request

from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.workflows.bank_processing_workflow import process_bank_file_workflow

router = APIRouter(prefix="/bank-csv", tags=["bank-csv"])


@router.post("/process")
async def process_bank_file(request: Request, file: UploadFile = File(...)):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    content = await file.read()
    return process_bank_file_workflow(file.filename or "", content, tenant_id=tenant_id)