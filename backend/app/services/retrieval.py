"""Retrieval-augmented prompting.

- Few-shot: past questions on the same schema that ran fine and weren't
  marked unhelpful, nearest first. On Postgres the search is a pgvector
  HNSW lookup; on SQLite the recent rows are scored in Python.
- Schema selection: a workbook with many sheets only sends the tables
  closest to the question, so the prompt stays small and focused.
"""
import hashlib
import json
import os
import numpy as np
from sqlalchemy import Float, select
from app.db import SessionLocal, QueryLog, engine
from app.services.embeddings import get_embedder

FEW_SHOT_K = int(os.getenv("FEW_SHOT_K", "3"))          # 0 turns few-shot off
SCHEMA_MAX_TABLES = int(os.getenv("SCHEMA_MAX_TABLES", "6"))
SCAN_LIMIT = 500   # SQLite fallback: how many recent rows to score

def schema_hash(tables: list[dict]) -> str:
    """Same table names and columns → same hash, whatever the file was called."""
    shape = sorted((t["name"], list(t["columns"])) for t in tables)
    return hashlib.sha256(json.dumps(shape).encode()).hexdigest()[:32]

def _norm_sql(sql: str) -> str:
    return " ".join(sql.lower().split()).rstrip(";")

def find_examples(schema: str, vector: list[float], k: int = FEW_SHOT_K) -> list[dict]:
    """Up to k {question, sql, score} from past successful queries on this schema."""
    if k <= 0:
        return []
    embedder = get_embedder()
    ok = (
        (QueryLog.schema_hash == schema)
        & (QueryLog.status == "ok")
        & (QueryLog.embedder == embedder.name)
        & QueryLog.embedding.is_not(None)
    )
    with SessionLocal() as s:
        # a thumbs-down on any copy of a query rules that SQL out everywhere
        # (cached copies have no embedding, so this can't reuse the filter above)
        bad = {_norm_sql(q) for q in s.scalars(
            select(QueryLog.sql).where((QueryLog.schema_hash == schema) & QueryLog.feedback.is_(False))
        ) if q}
        if engine.dialect.name == "postgresql":
            # pgvector's cosine distance; the column type is the cross-database
            # Embedding decorator, so spell out the operator
            distance = QueryLog.embedding.op("<=>", return_type=Float)(vector)
            rows = s.execute(
                select(QueryLog.question, QueryLog.sql, (1 - distance).label("score"))
                .where(ok & QueryLog.feedback.is_not(False))
                .order_by(distance)
                .limit(k * 5)
            ).all()
        else:
            recent = s.execute(
                select(QueryLog.question, QueryLog.sql, QueryLog.embedding)
                .where(ok & QueryLog.feedback.is_not(False))
                .order_by(QueryLog.id.desc())
                .limit(SCAN_LIMIT)
            ).all()
            if not recent:
                return []
            scores = np.array([r.embedding for r in recent]) @ np.array(vector)
            rows = sorted(
                ((r.question, r.sql, float(sc)) for r, sc in zip(recent, scores)),
                key=lambda r: -r[2],
            )

    examples, seen = [], set()
    for question, sql, score in rows:
        key = _norm_sql(sql)
        if score < embedder.min_similarity or key in seen or key in bad:
            continue
        seen.add(key)
        examples.append({"question": question, "sql": sql, "score": round(float(score), 3)})
        if len(examples) == k:
            break
    return examples

def _table_doc(t: dict, dictionary: dict) -> str:
    notes = dictionary.get(t["name"], {})
    cols = ", ".join(f"{c} ({notes[c]})" if notes.get(c) else c for c in t["columns"])
    return f"{t['name'].replace('_', ' ')} {t.get('sheet') or ''}: {cols}"

def select_tables(tables: list[dict], vector: list[float], dictionary: dict | None = None,
                  limit: int = SCHEMA_MAX_TABLES) -> list[dict]:
    """All tables when there are few; otherwise the `limit` closest to the question, in workbook order."""
    if len(tables) <= limit:
        return tables
    docs = get_embedder().embed([_table_doc(t, dictionary or {}) for t in tables])
    scores = docs @ np.array(vector)
    keep = set(np.argsort(-scores)[:limit].tolist())
    return [t for i, t in enumerate(tables) if i in keep]
