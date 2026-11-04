from pydantic import BaseModel
from typing import Optional, Any

class QueryRequest(BaseModel):
    question: str
    dataset_id: str
    conversation_id: Optional[str] = None

class QueryResponse(BaseModel):
    question: Optional[str] = None
    sql: str
    result: list[dict[str, Any]]
    insight: str
    chart_type: str  # "bar" | "line" | "pie" | "table"
    truncated: bool = False

class TableInfo(BaseModel):
    name: str                      # table name to use in SQL
    sheet: Optional[str] = None    # original Excel sheet name
    rows: int
    columns: list[str]
    detected_types: dict[str, str] = {}
    preview: list[dict[str, Any]] = []

class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    rows: int
    columns: list[str]
    preview: list[dict[str, Any]]  # first 5 rows
    warnings: list[str] = []
    detected_types: dict[str, str] = {}
    tables: list[TableInfo] = []   # one per sheet for workbooks, else a single "data"
