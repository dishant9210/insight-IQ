from fastapi import APIRouter, HTTPException
from app.models.schemas import QueryRequest, QueryResponse
from app.services.llm_service import answer_question
from app.services.dataset_service import _datasets
import pandas as pd

router = APIRouter(prefix="/api", tags=["query"])

@router.post("/query", response_model=QueryResponse)
async def query_dataset(req: QueryRequest):
    
    if req.dataset_id not in _datasets:
        raise HTTPException(404, "Dataset not found. Upload a CSV first.")
    print(req.dataset_id)
    # Get schema info from the stored CSV
    file_path = _datasets[req.dataset_id]["path"]
    # file_path+=".csv"
    print(f"file path is : {file_path}")
    df = pd.read_csv(file_path, nrows=5)  # only read 5 rows for schema
    
    result = await answer_question(
        question=req.question,
        dataset_id=req.dataset_id,
        columns=df.columns.tolist(),
        dtypes=df.dtypes.astype(str).to_dict(),
        sample=df.to_dict(orient="records"),
    )
    return QueryResponse(**result)