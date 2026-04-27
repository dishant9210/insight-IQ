from pydantic import BaseModel
from typing import Optional, Any

class QueryRequest(BaseModel):
    question: str
    dataset_id: str
    conversation_id: Optional[str] = None

class QueryResponse(BaseModel):
    question: str
    result: list[dict[str, Any]]
    insight: str
    chart_type: str  # "bar" | "line" | "pie" | "table"

class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    rows: int
    columns: list[str]
    preview: list[dict[str, Any]]  # first 5 rows