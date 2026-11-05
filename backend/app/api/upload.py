import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from app.api.deps import Viewer, require_user, viewer
from app.services.dataset_service import (
    save_upload, ingest, get_dataset, tables_of, set_dictionary, list_datasets, delete_dataset,
)
from app.models.schemas import UploadResponse, DictionaryUpdate, DatasetSummary
from app.services.rate_limit import limit

router = APIRouter(prefix="/api", tags=["datasets"])

SUPPORTED = {".csv", ".json", ".xlsx", ".xls", ".parquet"}

def _response(meta: dict) -> UploadResponse:
    if meta["status"] != "ready":
        return UploadResponse(**meta)
    return UploadResponse(**{**meta, "tables": tables_of(meta)})

@router.post("/upload", response_model=UploadResponse, dependencies=[Depends(limit("upload"))])
async def upload_dataset(response: Response, file: UploadFile = File(...),
                         user: Viewer | None = Depends(viewer)):
    if "." not in file.filename:
        raise HTTPException(400, f"File needs an extension. Use: {sorted(SUPPORTED)}")
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in SUPPORTED:
        raise HTTPException(400, f"Unsupported: {ext}. Use: {sorted(SUPPORTED)}")

    dataset_id, raw_path, queued = await save_upload(file, user.id if user else None)
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

@router.get("/datasets", response_model=list[DatasetSummary])
def my_datasets(user: Viewer = Depends(require_user)):
    """Datasets uploaded while signed in, newest first."""
    return [
        DatasetSummary(dataset_id=d.id, filename=d.filename, status=d.status, rows=d.rows or 0,
                       tables=len(d.tables or []) or 1, created_at=d.created_at)
        for d in list_datasets(user.id)
    ]

@router.get("/datasets/{dataset_id}", response_model=UploadResponse)
def dataset_info(dataset_id: str, user: Viewer | None = Depends(viewer)):
    return _response(get_dataset(dataset_id, user.id if user else None))

@router.delete("/datasets/{dataset_id}", status_code=204)
def remove_dataset(dataset_id: str, user: Viewer = Depends(require_user)):
    delete_dataset(dataset_id, user.id)
    return Response(status_code=204)

@router.put("/datasets/{dataset_id}/dictionary", response_model=UploadResponse)
def update_dictionary(dataset_id: str, req: DictionaryUpdate, user: Viewer | None = Depends(viewer)):
    """Column notes ("amount — revenue in INR, after discount") that go into
    the prompt next to each column."""
    return _response(set_dictionary(dataset_id, req.tables, user.id if user else None))
