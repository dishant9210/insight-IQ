import uuid, os, json, threading
from datetime import datetime, timedelta, timezone
import duckdb
import pandas as pd
from fastapi import UploadFile, HTTPException
from sqlalchemy import select

from app.db import SessionLocal, Dataset, UPLOAD_DIR
from app.queue import get_queue, JOB_TIMEOUT
from app.services.loader import get_loader

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
QUERY_TIMEOUT = float(os.getenv("QUERY_TIMEOUT_SECONDS", "20"))
MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "1000"))
DATASET_TTL = float(os.getenv("DATASET_TTL_HOURS", "24")) * 3600   # 0 = keep forever
CHUNK = 1024 * 1024

def _db_path(dataset_id: str) -> str:
    return f"{UPLOAD_DIR}/{dataset_id}.duckdb"

def _records(df: pd.DataFrame) -> list[dict]:
    # to_json handles NaN → null, timestamps → ISO, numpy scalars → native
    return json.loads(df.to_json(orient="records", date_format="iso"))

def _remove(*paths: str):
    for p in paths:
        if os.path.exists(p):
            os.remove(p)

def to_meta(ds: Dataset) -> dict:
    return {
        "dataset_id": ds.id,
        "filename": ds.filename,
        "status": ds.status,
        "error": ds.error,
        "rows": ds.rows or 0,
        "columns": ds.columns or [],
        "detected_types": ds.detected_types or {},
        "preview": ds.preview or [],
        "warnings": ds.warnings or [],
        "tables": ds.tables or [],
    }

def tables_of(meta: dict) -> list[dict]:
    """Table list for a dataset. Every format has at least one table called 'data'."""
    return meta.get("tables") or [{
        "name": "data",
        "sheet": None,
        "rows": meta["rows"],
        "columns": meta["columns"],
        "detected_types": meta["detected_types"],
        "preview": meta["preview"],
    }]

def cleanup_old():
    if not DATASET_TTL:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=DATASET_TTL)
    with SessionLocal() as s:
        old = s.scalars(select(Dataset).where(Dataset.created_at < cutoff)).all()
        for ds in old:
            _remove(_db_path(ds.id))
            s.delete(ds)
        s.commit()

def get_dataset(dataset_id: str) -> dict:
    # ids are uuids we minted — anything else is not a real dataset (and would
    # otherwise be joined straight into a file path)
    try:
        uuid.UUID(dataset_id)
    except ValueError:
        raise HTTPException(404, "Dataset not found. Upload a file first.")

    with SessionLocal() as s:
        ds = s.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found. Upload a file first.")
    return to_meta(ds)

def get_ready_dataset(dataset_id: str) -> dict:
    meta = get_dataset(dataset_id)
    if meta["status"] == "failed":
        raise HTTPException(409, f"This dataset failed to load: {meta['error']}")
    if meta["status"] != "ready":
        raise HTTPException(409, "Dataset is still processing. Try again in a moment.")
    return meta

async def _write_upload(file: UploadFile, dest: str) -> int:
    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(CHUNK):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                break
            f.write(chunk)
    if size > MAX_UPLOAD_BYTES:
        os.remove(dest)
        raise HTTPException(413, f"File too large. Limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    return size

async def save_upload(file: UploadFile) -> tuple[str, str, bool]:
    """Store the raw file and register the dataset.
    Returns (dataset_id, raw_path, queued) — queued is False when there's no Redis."""
    cleanup_old()
    dataset_id = str(uuid.uuid4())
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    raw_path = f"{UPLOAD_DIR}/{dataset_id}{ext}"

    await _write_upload(file, raw_path)

    with SessionLocal() as s:
        s.add(Dataset(id=dataset_id, filename=file.filename, status="pending", warnings=[]))
        s.commit()

    queue = get_queue()
    if queue is None:
        return dataset_id, raw_path, False

    queue.enqueue_call(
        ingest,
        args=(dataset_id, raw_path, file.filename),
        timeout=JOB_TIMEOUT,
        result_ttl=0,
        failure_ttl=24 * 3600,
        job_id=dataset_id,
    )
    return dataset_id, raw_path, True

def _set(dataset_id: str, **fields):
    with SessionLocal() as s:
        ds = s.get(Dataset, dataset_id)
        if ds is None:          # cleaned up while it was queued
            return
        for k, v in fields.items():
            setattr(ds, k, v)
        s.commit()

def ingest(dataset_id: str, raw_path: str, filename: str):
    """Parse an uploaded file into its own DuckDB database. Runs on the worker
    (or in-process without Redis); the outcome is recorded on the dataset row."""
    _set(dataset_id, status="processing")
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    try:
        results = get_loader(filename).load_all(raw_path)

        # Every format ends up as one DuckDB file so queries can open it read-only.
        # Workbooks get one table per sheet; "data" always points at the first one.
        db = duckdb.connect(_db_path(dataset_id))
        try:
            if ext == ".parquet":
                db.execute("CREATE TABLE data AS SELECT * FROM read_parquet(?)", [raw_path])
            else:
                for r in results:
                    db.register("df", r.df)
                    db.execute(f'CREATE TABLE "{r.name}" AS SELECT * FROM df')
                    db.unregister("df")
                if results[0].name != "data":
                    db.execute(f'CREATE VIEW data AS SELECT * FROM "{results[0].name}"')
        finally:
            db.close()
    except Exception as e:
        _remove(_db_path(dataset_id))
        error = e.detail if isinstance(e, HTTPException) else f"Could not parse file: {e}"
        _set(dataset_id, status="failed", error=error)
        return
    finally:
        _remove(raw_path)

    first = results[0]
    tables = [{
        "name": r.name,
        "sheet": r.sheet,
        "rows": r.row_count,
        "columns": r.df.columns.tolist(),
        "detected_types": r.detected_types,
        "preview": _records(r.df.head(5)),
    } for r in results]

    _set(
        dataset_id,
        status="ready",
        rows=first.row_count,
        columns=first.df.columns.tolist(),
        detected_types=first.detected_types,
        preview=tables[0]["preview"],
        warnings=[w for r in results for w in r.warnings],
        tables=tables,
    )

def execute_query(dataset_id: str, sql: str) -> tuple[list[dict], bool]:
    """Run an already-validated SELECT against a dataset. Returns (rows, truncated)."""
    get_ready_dataset(dataset_id)

    conn = duckdb.connect(_db_path(dataset_id), read_only=True)
    try:
        # The SQL came from an LLM, so treat it as untrusted: no reading other
        # files off disk, no network, and the config can't be flipped back.
        conn.execute("SET enable_external_access = false")
        conn.execute("SET lock_configuration = true")

        timer = threading.Timer(QUERY_TIMEOUT, conn.interrupt)
        timer.start()
        try:
            df = conn.execute(
                f"SELECT * FROM ({sql}) AS q LIMIT {MAX_RESULT_ROWS + 1}"
            ).fetchdf()
        finally:
            timer.cancel()
    finally:
        conn.close()

    truncated = len(df) > MAX_RESULT_ROWS
    return _records(df.head(MAX_RESULT_ROWS)), truncated
