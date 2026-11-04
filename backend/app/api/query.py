from fastapi import APIRouter
from app.models.schemas import QueryRequest, QueryResponse
from app.services.llm_service import answer_question
from app.services.dataset_service import get_dataset, tables_of

router = APIRouter(prefix="/api", tags=["query"])

@router.post("/query", response_model=QueryResponse)
async def query_dataset(req: QueryRequest):
    meta = get_dataset(req.dataset_id)

    result = await answer_question(
        question=req.question,
        dataset_id=req.dataset_id,
        tables=tables_of(meta),
    )
    return QueryResponse(question=req.question, **result)
