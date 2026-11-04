import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, Text, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def _database_url() -> str:
    # No DATABASE_URL → a SQLite file next to the datasets, so a single
    # container still works without Postgres.
    url = os.getenv("DATABASE_URL") or f"sqlite:///{UPLOAD_DIR}/insightiq.db"
    # hosted Postgres often hands out postgres:// — point it at psycopg 3
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url

DATABASE_URL = _database_url()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    # pending → processing → ready | failed
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    rows: Mapped[int | None] = mapped_column(Integer)
    columns: Mapped[list | None] = mapped_column(JSON)
    detected_types: Mapped[dict | None] = mapped_column(JSON)
    preview: Mapped[list | None] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    tables: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

class QueryLog(Base):
    """Every question asked, with the SQL it produced. Successful rows become
    few-shot examples later, failed ones show where the prompt is weak."""
    __tablename__ = "query_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # no FK — logs outlive the datasets they were asked against
    dataset_id: Mapped[str] = mapped_column(String(36), index=True)
    question: Mapped[str] = mapped_column(Text)
    sql: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))        # ok | error
    error: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
