"""Answers keyed by dataset + question. A dataset never changes after upload,
so the same question always has the same answer — no need to pay the LLM twice."""
import hashlib
import json
import logging
import os
from app.store import get_store

log = logging.getLogger(__name__)

TTL = int(os.getenv("ANSWER_CACHE_TTL_SECONDS", "3600"))   # 0 turns the cache off

def _key(dataset_id: str, question: str) -> str:
    # "Total revenue by city?" and "total  revenue by city" are the same question
    norm = " ".join(question.lower().split()).rstrip("?").strip()
    return f"answer:{dataset_id}:{hashlib.sha256(norm.encode()).hexdigest()[:32]}"

def get(dataset_id: str, question: str) -> dict | None:
    if TTL <= 0:
        return None
    try:
        raw = get_store().get(_key(dataset_id, question))
    except Exception as e:   # a cache outage shouldn't fail the question
        log.warning("answer cache read failed: %s", e)
        return None
    return json.loads(raw) if raw else None

def put(dataset_id: str, question: str, answer: dict):
    if TTL <= 0:
        return
    try:
        get_store().set(_key(dataset_id, question), json.dumps(answer, default=str), TTL)
    except Exception as e:
        log.warning("answer cache write failed: %s", e)
