import pandas as pd
import duckdb
import uuid
import os
from fastapi import UploadFile

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# In-memory store: dataset_id → file path
# Week 2 will move this to Redis/Postgres
_datasets: dict[str, str] = {}

async def save_and_parse(file: UploadFile) -> dict:
    """Save uploaded CSV and return metadata."""
    dataset_id = str(uuid.uuid4())
    file_path = f"{UPLOAD_DIR}/{dataset_id}.csv"

    # Write file to disk
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # Parse with pandas to get metadata
    df = pd.read_csv(file_path)

    _datasets[dataset_id] = file_path

    return {
        "dataset_id": dataset_id,
        "filename": file.filename,
        "rows": len(df),
        "columns": df.columns.tolist(),
        "preview": df.head(5).to_dict(orient="records"),
        "dtypes": df.dtypes.astype(str).to_dict(),  # column → type
    }

def execute_query(dataset_id: str, sql: str) -> list[dict]:
    """Run SQL on the uploaded CSV using DuckDB."""
    file_path = _datasets.get(dataset_id)
    if not file_path:
        raise ValueError(f"Dataset {dataset_id} not found")

    # DuckDB can query CSV files directly — no DB setup needed
    conn = duckdb.connect()
    # Register the CSV as a table named 'data'
    conn.execute(f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{file_path}')")

    result = conn.execute(sql).fetchdf()  # returns a pandas DataFrame
    conn.close()

    return result.to_dict(orient="records")