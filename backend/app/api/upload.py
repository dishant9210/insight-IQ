from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.dataset_service import save_and_parse
from app.models.schemas import UploadResponse

router = APIRouter(prefix="/api", tags=["datasets"])

SUPPORTED = {".csv", ".json", ".xlsx", ".xls", ".parquet"}

@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)):
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in SUPPORTED:
        raise HTTPException(400, f"Unsupported: {ext}. Use: {SUPPORTED}")
    try:
        result = await save_and_parse(file)
        return UploadResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Parse failed: {str(e)}")