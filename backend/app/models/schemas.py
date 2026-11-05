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
    cached: bool = False           # served from the answer cache, no LLM call
    query_id: Optional[int] = None # for POST /api/queries/{id}/feedback
    examples_used: int = 0         # past answers retrieved into the prompt
    tables_used: list[str] = []    # tables the model was shown

class FeedbackRequest(BaseModel):
    helpful: bool

class DictionaryUpdate(BaseModel):
    # {table: {column: note}}; replaces the whole dictionary, blank notes are dropped
    tables: dict[str, dict[str, str]]

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
    status: str = "ready"          # pending | processing | ready | failed
    error: Optional[str] = None
    rows: int = 0
    columns: list[str] = []
    preview: list[dict[str, Any]] = []  # first 5 rows
    warnings: list[str] = []
    detected_types: dict[str, str] = {}
    tables: list[TableInfo] = []   # one per sheet for workbooks, else a single "data"
    dictionary: dict[str, dict[str, str]] = {}  # column notes the user wrote
