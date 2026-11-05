import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from opentelemetry import trace

load_dotenv()

from app import logging_setup, metrics, tracing
logging_setup.setup()

from app.api.auth import router as auth_router
from app.api.upload import router as upload_router
from app.api.query import router as query_router
from app.db import engine
from app.queue import get_queue
from app.store import get_store

origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    metrics.register_state_collector()
    metrics.serve()
    yield

app = FastAPI(
    title="InsightIQ",
    description="Natural language analytics",
    version="0.7.0",
    lifespan=lifespan,
)
tracing.setup("insightiq-api", app)

_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

@app.middleware("http")
async def http_metrics(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    # the gateway's id when there is one, so its access log and ours line up
    rid = request.headers.get("X-Request-ID", "")
    if not _REQUEST_ID.fullmatch(rid):
        rid = uuid.uuid4().hex
    token = logging_setup.request_id.set(rid)
    trace.get_current_span().set_attribute("http.request_id", rid)
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        logging_setup.request_id.reset(token)
        # the route template, not the raw path, so ids don't explode the label set
        route = getattr(request.scope.get("route"), "path", "unmatched")
        metrics.HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
        metrics.HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - started)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # let the browser read the limit headers on cross-origin responses
    expose_headers=["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset",
                    "X-Request-ID"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}

@app.get("/ready")
def ready():
    """Readiness: can we reach the database, and Redis (queue + cache) if one is configured?"""
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

    store = get_store()
    try:
        store.ping()
        checks["cache"] = "ok" if store.name == "redis" else "disabled (in-process memory)"
    except Exception as e:
        checks["cache"] = f"error: {e.__class__.__name__}"

    healthy = all(v == "ok" or v.startswith("disabled") for v in checks.values())
    return JSONResponse(checks, status_code=200 if healthy else 503)

@app.get("/")
async def root():
    return {"message": "InsightIQ API"}

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(query_router)
