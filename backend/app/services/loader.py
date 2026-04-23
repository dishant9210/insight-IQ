from app.services.loaders.csv_loader import CsvLoader
from app.services.loaders.json_loader import JsonLoader
from app.services.loaders.excel_loader import ExcelLoader
from app.services.loaders.parquet_loader import ParquetLoader
from app.services.loaders.base import BaseLoader 
from fastapi import HTTPException

LOADERS = {
    ".csv":     CsvLoader,
    ".json":    JsonLoader,
    ".xlsx":    ExcelLoader,
    ".xls":     ExcelLoader,
    ".parquet": ParquetLoader,
}

def get_loader(filename: str) -> "BaseLoader":
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    cls = LOADERS.get(ext)
    if not cls:
        raise HTTPException(
            400,
            f"Unsupported format: {ext}. Supported: {list(LOADERS.keys())}"
        )
    return cls()