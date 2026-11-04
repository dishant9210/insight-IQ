import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.api.upload import router as upload_router
from app.api.query import router as query_router
from app.db import engine
from app.queue import get_queue

origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

app = FastAPI(
    title="InsightIQ",
    description="Natural language analytics",
    version="0.3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}

@app.get("/ready")
def ready():
    """Readiness: can we reach the database, and Redis if one is configured?"""
    checks = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e.__class__.__name__}"

    queue = get_queue()
    if queue is None:
        checks["queue"] = "disabled (uploads parsed in-process)"
    else:
        try:
            queue.connection.ping()
            checks["queue"] = "ok"
        except Exception as e:
            checks["queue"] = f"error: {e.__class__.__name__}"

    healthy = all(v == "ok" or v.startswith("disabled") for v in checks.values())
    return JSONResponse(checks, status_code=200 if healthy else 503)

@app.get("/")
async def root():
    return {"message": "InsightIQ API"}

app.include_router(upload_router)
app.include_router(query_router)
