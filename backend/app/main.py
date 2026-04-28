from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

from app.api.upload import router as upload_router
from app.api.query import router as query_router


import os 

load_dotenv()

origins = [
    "http://localhost:5173",  # Vite default
    "http://127.0.0.1:5173", # Some browsers prefer the IP
    # "http://localhost:3000",  # Standard React default
]

app = FastAPI(
    title="InsightIQ",
    description="Natural language analytics",
    version="0.1.0"
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
    return {"status": "ok", "version": "0.1.0"}

@app.get("/")
async def root():
    return {"message": "InsightIQ API"}

app.include_router(upload_router)

app.include_router(query_router)