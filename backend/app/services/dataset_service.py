import uuid, os
import pandas as pd
import duckdb
from fastapi import UploadFile
from app.services.loader import get_loader

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
_datasets: dict[str, dict] = {}   # dataset_id → {path, ext, columns, dtypes}

async def save_and_parse(file: UploadFile) -> dict:
    dataset_id = str(uuid.uuid4())
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    file_path = f"{UPLOAD_DIR}/{dataset_id}{ext}"

    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # Factory picks the right loader
    loader = get_loader(file.filename)
    result = loader.load(file_path)

    # For non-CSV formats, also save a CSV copy for DuckDB compatibility
    csv_path = f"{UPLOAD_DIR}/{dataset_id}.csv"
    if ext != ".csv":
        result.df.to_csv(csv_path, index=False)

    _datasets[dataset_id] = {
        "path": csv_path if ext != ".parquet" else file_path,
        "ext": ext,
        "columns": result.df.columns.tolist(),
        "dtypes": result.detected_types,
        "sample": result.df.head(5).to_dict(orient="records"),
    }

    return {
        "dataset_id": dataset_id,
        "filename": file.filename,
        "rows": result.row_count,
        "columns": result.df.columns.tolist(),
        "preview": result.df.head(5).to_dict(orient="records"),
        "warnings": result.warnings,    # show user if encoding was fixed etc.
        "detected_types": result.detected_types,
    }

def execute_query(dataset_id: str, sql: str) -> list[dict]:
    meta = _datasets[dataset_id]   # now stores {path, ext}
    file_path = meta["path"]
    ext = meta["ext"]

    conn = duckdb.connect()

    if ext == ".parquet":
        # DuckDB reads Parquet natively — no load needed
        conn.execute(f"CREATE VIEW data AS SELECT * FROM read_parquet('{file_path}')")
    else:
        # CSV/JSON/Excel: file already converted to CSV on disk
        conn.execute(f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{file_path}')")

    result = conn.execute(sql).fetchdf()
    conn.close()

    return result.to_dict(orient="records")

   