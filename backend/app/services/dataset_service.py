import uuid, os, json, time, threading
import duckdb
import pandas as pd
from fastapi import UploadFile, HTTPException
from app.services.loader import get_loader

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
QUERY_TIMEOUT = float(os.getenv("QUERY_TIMEOUT_SECONDS", "20"))
MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "1000"))
DATASET_TTL = float(os.getenv("DATASET_TTL_HOURS", "24")) * 3600   # 0 = keep forever
CHUNK = 1024 * 1024

os.makedirs(UPLOAD_DIR, exist_ok=True)
_datasets: dict[str, dict] = {}   # dataset_id → metadata (mirrored to <id>.json on disk)

def _db_path(dataset_id: str) -> str:
    return f"{UPLOAD_DIR}/{dataset_id}.duckdb"

def _meta_path(dataset_id: str) -> str:
    return f"{UPLOAD_DIR}/{dataset_id}.json"

def _records(df: pd.DataFrame) -> list[dict]:
    # to_json handles NaN → null, timestamps → ISO, numpy scalars → native
    return json.loads(df.to_json(orient="records", date_format="iso"))

def _load_registry():
    for name in os.listdir(UPLOAD_DIR):
        if not name.endswith(".json"):
            continue
        with open(f"{UPLOAD_DIR}/{name}") as f:
            meta = json.load(f)
        if os.path.exists(_db_path(meta["dataset_id"])):
            _datasets[meta["dataset_id"]] = meta

def _cleanup_old():
    if not DATASET_TTL:
        return
    cutoff = time.time() - DATASET_TTL
    for name in os.listdir(UPLOAD_DIR):
        if not name.endswith(".json"):
            continue
        dataset_id = name[:-5]
        path = _meta_path(dataset_id)
        if os.path.getmtime(path) < cutoff:
            for p in (path, _db_path(dataset_id)):
                if os.path.exists(p):
                    os.remove(p)
            _datasets.pop(dataset_id, None)

_cleanup_old()
_load_registry()

def get_dataset(dataset_id: str) -> dict:
    # ids are uuids we minted — anything else is not a real dataset (and would
    # otherwise be joined straight into a file path)
    try:
        uuid.UUID(dataset_id)
    except ValueError:
        raise HTTPException(404, "Dataset not found. Upload a file first.")

    meta = _datasets.get(dataset_id)
    if meta is None and os.path.exists(_meta_path(dataset_id)) and os.path.exists(_db_path(dataset_id)):
        # another worker (or a previous process) wrote it
        with open(_meta_path(dataset_id)) as f:
            meta = json.load(f)
        _datasets[dataset_id] = meta
    if not meta:
        raise HTTPException(404, "Dataset not found. Upload a file first.")
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

async def save_and_parse(file: UploadFile) -> dict:
    _cleanup_old()
    dataset_id = str(uuid.uuid4())
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    raw_path = f"{UPLOAD_DIR}/{dataset_id}{ext}"

    await _write_upload(file, raw_path)

    try:
        result = get_loader(file.filename).load(raw_path)

        # Every format ends up as one DuckDB file so queries can open it read-only.
        db = duckdb.connect(_db_path(dataset_id))
        try:
            if ext == ".parquet":
                db.execute("CREATE TABLE data AS SELECT * FROM read_parquet(?)", [raw_path])
            else:
                db.register("df", result.df)
                db.execute("CREATE TABLE data AS SELECT * FROM df")
        finally:
            db.close()
    finally:
        if os.path.exists(raw_path):
            os.remove(raw_path)

    meta = {
        "dataset_id": dataset_id,
        "filename": file.filename,
        "rows": result.row_count,
        "columns": result.df.columns.tolist(),
        "detected_types": result.detected_types,
        "preview": _records(result.df.head(5)),
        "warnings": result.warnings,
    }
    with open(_meta_path(dataset_id), "w") as f:
        json.dump(meta, f)
    _datasets[dataset_id] = meta
    return meta

def execute_query(dataset_id: str, sql: str) -> tuple[list[dict], bool]:
    """Run an already-validated SELECT against a dataset. Returns (rows, truncated)."""
    get_dataset(dataset_id)

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
