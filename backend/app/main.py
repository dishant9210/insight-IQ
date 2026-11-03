import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.api.upload import router as upload_router
from app.api.query import router as query_router

origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

app = FastAPI(
    title="InsightIQ",
    description="Natural language analytics",
    version="0.2.0"
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

@app.get("/")
async def root():
    return {"message": "InsightIQ API"}

app.include_router(upload_router)
app.include_router(query_router)
