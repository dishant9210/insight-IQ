import asyncio
import duckdb
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from app.api.deps import Viewer, require_user, viewer
from app.db import SessionLocal, QueryLog, Dataset
from app.models.schemas import (
    QueryRequest, QueryResponse, FeedbackRequest, HistoryItem, HistoryPage, HistoryAnswer,
)
from app.services import answer_cache, retrieval, sql_guard
from app.services.embeddings import embed_one, get_embedder
from app.services.llm_service import answer_question
from app.services.dataset_service import get_ready_dataset, get_dataset, tables_of, execute_query
from app.services.rate_limit import limit
from app import metrics
from app.tracing import tracer

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])

def _visible(row: QueryLog, user: Viewer | None) -> bool:
    """A signed-in user's questions are theirs alone; guest questions are open."""
    return row.user_id is None or (user is not None and row.user_id == user.id)

def _log(**fields) -> int:
    with SessionLocal() as s:
        row = QueryLog(**fields)
        s.add(row)
        s.commit()
        return row.id

async def _retrieve(question: str, schema: str, tables: list[dict], dictionary: dict,
                    user_id: str | None):
    """(question vector, few-shot examples, tables to show). Retrieval only
    improves the prompt, so if it breaks the question still goes through."""
    with tracer.start_as_current_span("retrieve") as span, metrics.Timer() as t:
        try:
            vector = await asyncio.to_thread(embed_one, question)
            examples = await asyncio.to_thread(retrieval.find_examples, schema, vector, user_id=user_id)
            chosen = await asyncio.to_thread(retrieval.select_tables, tables, vector, dictionary)
        except Exception as e:
            log.warning("retrieval failed, answering without it: %s", e)
            span.set_attribute("retrieval.error", str(e))
            vector, examples, chosen = None, [], tables
        span.set_attribute("retrieval.examples", len(examples))
        span.set_attribute("retrieval.tables", len(chosen))
    metrics.RETRIEVAL_LATENCY.observe(t.seconds)
    metrics.FEWSHOT.observe(len(examples))
    return vector, examples, chosen

@router.post("/query", response_model=QueryResponse, dependencies=[Depends(limit("query"))])
async def query_dataset(req: QueryRequest, user: Viewer | None = Depends(viewer)):
    user_id = user.id if user else None
    meta = get_ready_dataset(req.dataset_id, user_id)
    tables, dictionary = tables_of(meta), meta["dictionary"]
    schema = retrieval.schema_hash(tables)
    base = dict(dataset_id=req.dataset_id, question=req.question, schema_hash=schema, user_id=user_id)

    started = time.perf_counter()
    elapsed = lambda: int((time.perf_counter() - started) * 1000)

    cached = answer_cache.get(req.dataset_id, req.question, dictionary)
    metrics.ANSWER_CACHE.labels("miss" if cached is None else "hit").inc()
    if cached is not None:
        # no embedding: the original row already represents this question for retrieval
        qid = _log(**base, sql=cached["sql"], status="ok", row_count=len(cached["result"]),
                   insight=cached["insight"], chart_type=cached["chart_type"],
                   latency_ms=elapsed(), cached=True)
        metrics.QUERIES.labels("cached").inc()
        metrics.QUERY_LATENCY.labels("true").observe(elapsed() / 1000)
        return QueryResponse(question=req.question, query_id=qid, cached=True, **cached)

    vector, examples, chosen = await _retrieve(req.question, schema, tables, dictionary, user_id)
    try:
        result = await answer_question(
            question=req.question,
            dataset_id=req.dataset_id,
            tables=chosen,
            dictionary=dictionary,
            examples=examples,
        )
    except HTTPException as e:
        _log(**base, sql=getattr(e, "sql", None), status="error", error=str(e.detail), latency_ms=elapsed())
        metrics.QUERIES.labels(str(e.status_code)).inc()
        raise

    result |= {"examples_used": len(examples), "tables_used": [t["name"] for t in chosen]}
    answer_cache.put(req.dataset_id, req.question, result, dictionary)
    qid = _log(**base, sql=result["sql"], status="ok", row_count=len(result["result"]),
               insight=result["insight"], chart_type=result["chart_type"],
               latency_ms=elapsed(), embedding=vector,
               embedder=get_embedder().name if vector is not None else None)
    metrics.QUERIES.labels("ok").inc()
    metrics.QUERY_LATENCY.labels("false").observe(elapsed() / 1000)
    return QueryResponse(question=req.question, query_id=qid, **result)

@router.post("/queries/{query_id}/feedback", dependencies=[Depends(limit("feedback"))])
def query_feedback(query_id: int, req: FeedbackRequest, user: Viewer | None = Depends(viewer)):
    """Thumbs up keeps a query in the few-shot pool; thumbs down takes its SQL
    out of the pool and drops the cached answer so the next ask is fresh."""
    with SessionLocal() as s:
        row = s.get(QueryLog, query_id)
        if row is None or row.status != "ok" or not _visible(row, user):
            raise HTTPException(404, "No answered question with that id")
        row.feedback = req.helpful
        s.commit()
        dataset_id, question = row.dataset_id, row.question
    metrics.FEEDBACK.labels(str(req.helpful).lower()).inc()

    if not req.helpful:
        try:
            dictionary = get_dataset(dataset_id)["dictionary"]
        except HTTPException:          # dataset already cleaned up — nothing cached to drop
            dictionary = None
        if dictionary is not None:
            answer_cache.drop(dataset_id, question, dictionary)
    return {"query_id": query_id, "helpful": req.helpful}

# --- history ---------------------------------------------------------------

@router.get("/queries", response_model=HistoryPage)
def history(user: Viewer = Depends(require_user),
            dataset_id: str | None = None,
            before: int | None = Query(None, description="query_id cursor from next_before"),
            limit: int = Query(20, ge=1, le=100)):
    """Your questions, newest first, paged by id."""
    where = QueryLog.user_id == user.id
    if dataset_id:
        where &= QueryLog.dataset_id == dataset_id
    if before:
        where &= QueryLog.id < before
    with SessionLocal() as s:
        rows = s.execute(
            select(QueryLog, Dataset.filename)
            .outerjoin(Dataset, Dataset.id == QueryLog.dataset_id)
            .where(where).order_by(QueryLog.id.desc()).limit(limit + 1)
        ).all()
    items = [
        HistoryItem(query_id=q.id, dataset_id=q.dataset_id, filename=filename, question=q.question,
                    status=q.status, error=q.error, row_count=q.row_count, cached=bool(q.cached),
                    feedback=q.feedback, created_at=q.created_at)
        for q, filename in rows[:limit]
    ]
    return HistoryPage(items=items, next_before=items[-1].query_id if len(rows) > limit else None)

@router.get("/queries/{query_id}", response_model=HistoryAnswer)
def history_answer(query_id: int, user: Viewer = Depends(require_user)):
    """A past answer, with its rows re-read from the dataset (no model call).
    If the dataset has expired, the question, SQL and insight are still there."""
    with SessionLocal() as s:
        row = s.get(QueryLog, query_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "No question with that id in your history")
    if row.status != "ok":
        raise HTTPException(409, f"That question failed: {row.error}")

    result, truncated, available = [], False, True
    try:
        get_ready_dataset(row.dataset_id, user.id)
        # the SQL passed the guard when it was generated; check again before running it
        result, truncated = execute_query(row.dataset_id, sql_guard.validate_sql(row.sql))
    except HTTPException as e:
        if e.status_code not in (404, 409):
            raise
        available = False
    except (ValueError, duckdb.Error) as e:
        log.warning("could not re-run query %s: %s", query_id, e)
        available = False
    return HistoryAnswer(
        question=row.question, sql=row.sql, result=result, truncated=truncated,
        insight=row.insight or "", chart_type=row.chart_type or "table",
        cached=bool(row.cached), query_id=row.id, dataset_id=row.dataset_id,
        dataset_available=available, created_at=row.created_at,
    )
