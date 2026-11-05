from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
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

# --- accounts ----------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)

class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int                # seconds
    user: UserOut

# --- history -----------------------------------------------------------------

class HistoryItem(BaseModel):
    query_id: int
    dataset_id: str
    filename: Optional[str] = None # None once the dataset has expired
    question: str
    status: str                    # ok | error
    error: Optional[str] = None
    row_count: Optional[int] = None
    cached: bool = False
    feedback: Optional[bool] = None
    created_at: datetime

class HistoryPage(BaseModel):
    items: list[HistoryItem]
    next_before: Optional[int] = None   # pass as ?before= for the next page

class HistoryAnswer(QueryResponse):
    dataset_id: str
    dataset_available: bool        # False: the data is gone, only the SQL and insight remain
    created_at: datetime

class DatasetSummary(BaseModel):
    dataset_id: str
    filename: str
    status: str
    rows: int = 0
    tables: int = 1
    created_at: datetime
