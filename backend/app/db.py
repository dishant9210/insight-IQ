import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, String, Integer, Text, DateTime, JSON, Boolean, ForeignKey, false as sa_false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator
from pgvector.sqlalchemy import Vector

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

EMBEDDING_DIM = 384

class Embedding(TypeDecorator):
    """pgvector `vector(384)` on Postgres (indexed nearest-neighbour search),
    a JSON list elsewhere (SQLite fallback, compared in Python)."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(EMBEDDING_DIM))
        return dialect.type_descriptor(JSON())

    def process_result_value(self, value, dialect):
        return None if value is None else [float(x) for x in value]

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)     # stored lowercased
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class RefreshToken(Base):
    """One row per refresh token handed out. Only the hash is stored. Each
    refresh revokes the token it used and issues the next one in the same
    family; a revoked token coming back means it was copied, so the whole
    family is revoked."""
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # null = uploaded without signing in; anyone holding the id can use it
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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
    # {table: {column: description}}, written by the user, shown to the model
    dictionary: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

class QueryLog(Base):
    """Every question asked, with the SQL it produced. Successful rows are
    retrieved as few-shot examples for similar questions on the same schema;
    failed ones show where the prompt is weak."""
    __tablename__ = "query_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # no FK — logs outlive the datasets they were asked against
    dataset_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)   # null = guest
    question: Mapped[str] = mapped_column(Text)
    sql: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))        # ok | error
    error: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    # kept so history can show the answer again without another model call
    insight: Mapped[str | None] = mapped_column(Text)
    chart_type: Mapped[str | None] = mapped_column(String(16))
    latency_ms: Mapped[int] = mapped_column(Integer)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    # same tables + columns → same hash, so examples carry over between uploads of the same file
    schema_hash: Mapped[str | None] = mapped_column(String(32), index=True)
    embedding: Mapped[list | None] = mapped_column(Embedding())
    embedder: Mapped[str | None] = mapped_column(String(32))   # vectors only compare within one embedder
    feedback: Mapped[bool | None] = mapped_column(Boolean)     # thumbs up / down from the user
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
