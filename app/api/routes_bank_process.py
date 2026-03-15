from fastapi import APIRouter, UploadFile, File

from app.api.workflows.bank_processing_workflow import process_bank_file_workflow

router = APIRouter(prefix="/bank-csv", tags=["bank-csv"])


@router.post("/process")
async def process_bank_file(file: UploadFile = File(...)):
    content = await file.read()
    return process_bank_file_workflow(file.filename or "", content)