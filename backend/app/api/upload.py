from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.dataset_service import save_and_parse, get_dataset
from app.models.schemas import UploadResponse

router = APIRouter(prefix="/api", tags=["datasets"])

SUPPORTED = {".csv", ".json", ".xlsx", ".xls", ".parquet"}

@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)):
    if "." not in file.filename:
        raise HTTPException(400, f"File needs an extension. Use: {sorted(SUPPORTED)}")
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in SUPPORTED:
        raise HTTPException(400, f"Unsupported: {ext}. Use: {sorted(SUPPORTED)}")
    try:
        result = await save_and_parse(file)
        return UploadResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Parse failed: {str(e)}")

@router.get("/datasets/{dataset_id}", response_model=UploadResponse)
async def dataset_info(dataset_id: str):
    return UploadResponse(**get_dataset(dataset_id))
