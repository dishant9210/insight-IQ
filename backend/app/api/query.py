import asyncio
import logging
import time
from fastapi import APIRouter, Depends, HTTPException
from app.db import SessionLocal, QueryLog
from app.models.schemas import QueryRequest, QueryResponse, FeedbackRequest
from app.services import answer_cache, retrieval
from app.services.embeddings import embed_one, get_embedder
from app.services.llm_service import answer_question
from app.services.dataset_service import get_ready_dataset, get_dataset, tables_of
from app.services.rate_limit import limit
from app import metrics
from app.tracing import tracer

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])

def _log(**fields) -> int:
    with SessionLocal() as s:
        row = QueryLog(**fields)
        s.add(row)
        s.commit()
        return row.id

async def _retrieve(question: str, schema: str, tables: list[dict], dictionary: dict):
    """(question vector, few-shot examples, tables to show). Retrieval only
    improves the prompt, so if it breaks the question still goes through."""
    with tracer.start_as_current_span("retrieve") as span, metrics.Timer() as t:
        try:
            vector = await asyncio.to_thread(embed_one, question)
            examples = await asyncio.to_thread(retrieval.find_examples, schema, vector)
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
async def query_dataset(req: QueryRequest):
    meta = get_ready_dataset(req.dataset_id)
    tables, dictionary = tables_of(meta), meta["dictionary"]
    schema = retrieval.schema_hash(tables)
    base = dict(dataset_id=req.dataset_id, question=req.question, schema_hash=schema)

    started = time.perf_counter()
    elapsed = lambda: int((time.perf_counter() - started) * 1000)

    cached = answer_cache.get(req.dataset_id, req.question, dictionary)
    metrics.ANSWER_CACHE.labels("miss" if cached is None else "hit").inc()
    if cached is not None:
        # no embedding: the original row already represents this question for retrieval
        qid = _log(**base, sql=cached["sql"], status="ok", row_count=len(cached["result"]),
                   latency_ms=elapsed(), cached=True)
        metrics.QUERIES.labels("cached").inc()
        metrics.QUERY_LATENCY.labels("true").observe(elapsed() / 1000)
        return QueryResponse(question=req.question, query_id=qid, cached=True, **cached)

    vector, examples, chosen = await _retrieve(req.question, schema, tables, dictionary)
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
               latency_ms=elapsed(), embedding=vector,
               embedder=get_embedder().name if vector is not None else None)
    metrics.QUERIES.labels("ok").inc()
    metrics.QUERY_LATENCY.labels("false").observe(elapsed() / 1000)
    return QueryResponse(question=req.question, query_id=qid, **result)

@router.post("/queries/{query_id}/feedback", dependencies=[Depends(limit("feedback"))])
def query_feedback(query_id: int, req: FeedbackRequest):
    """Thumbs up keeps a query in the few-shot pool; thumbs down takes its SQL
    out of the pool and drops the cached answer so the next ask is fresh."""
    with SessionLocal() as s:
        row = s.get(QueryLog, query_id)
        if row is None or row.status != "ok":
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
