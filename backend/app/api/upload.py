import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from app.services.dataset_service import save_upload, ingest, get_dataset, tables_of, set_dictionary
from app.models.schemas import UploadResponse, DictionaryUpdate
from app.services.rate_limit import limit

router = APIRouter(prefix="/api", tags=["datasets"])

SUPPORTED = {".csv", ".json", ".xlsx", ".xls", ".parquet"}

def _response(meta: dict) -> UploadResponse:
    if meta["status"] != "ready":
        return UploadResponse(**meta)
    return UploadResponse(**{**meta, "tables": tables_of(meta)})

@router.post("/upload", response_model=UploadResponse, dependencies=[Depends(limit("upload"))])
async def upload_dataset(response: Response, file: UploadFile = File(...)):
    if "." not in file.filename:
        raise HTTPException(400, f"File needs an extension. Use: {sorted(SUPPORTED)}")
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in SUPPORTED:
        raise HTTPException(400, f"Unsupported: {ext}. Use: {sorted(SUPPORTED)}")

    dataset_id, raw_path, queued = await save_upload(file)
    if queued:
        # a worker picks it up; the client polls GET /api/datasets/{id}
        response.status_code = 202
        return _response(get_dataset(dataset_id))

    # no Redis — parse right here, off the event loop
    await asyncio.to_thread(ingest, dataset_id, raw_path, file.filename)
    meta = get_dataset(dataset_id)
    if meta["status"] == "failed":
        raise HTTPException(400, meta["error"])
    return _response(meta)

@router.get("/datasets/{dataset_id}", response_model=UploadResponse)
async def dataset_info(dataset_id: str):
    return _response(get_dataset(dataset_id))

@router.put("/datasets/{dataset_id}/dictionary", response_model=UploadResponse)
def update_dictionary(dataset_id: str, req: DictionaryUpdate):
    """Column notes ("amount — revenue in INR, after discount") that go into
    the prompt next to each column."""
    return _response(set_dictionary(dataset_id, req.tables))
