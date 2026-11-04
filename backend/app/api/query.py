import time
from fastapi import APIRouter, HTTPException
from app.db import SessionLocal, QueryLog
from app.models.schemas import QueryRequest, QueryResponse
from app.services.llm_service import answer_question
from app.services.dataset_service import get_ready_dataset, tables_of

router = APIRouter(prefix="/api", tags=["query"])

def _log(**fields):
    with SessionLocal() as s:
        s.add(QueryLog(**fields))
        s.commit()

@router.post("/query", response_model=QueryResponse)
async def query_dataset(req: QueryRequest):
    meta = get_ready_dataset(req.dataset_id)

    started = time.perf_counter()
    elapsed = lambda: int((time.perf_counter() - started) * 1000)
    try:
        result = await answer_question(
            question=req.question,
            dataset_id=req.dataset_id,
            tables=tables_of(meta),
        )
    except HTTPException as e:
        _log(dataset_id=req.dataset_id, question=req.question, sql=getattr(e, "sql", None),
             status="error", error=str(e.detail), latency_ms=elapsed())
        raise

    _log(dataset_id=req.dataset_id, question=req.question, sql=result["sql"],
         status="ok", row_count=len(result["result"]), latency_ms=elapsed())
    return QueryResponse(question=req.question, **result)
