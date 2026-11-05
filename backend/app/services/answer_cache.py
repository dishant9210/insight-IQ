"""Answers keyed by dataset + question. A dataset's data never changes after
upload, so the same question has the same answer — no need to pay the LLM
twice. Editing the column notes changes what the model sees, so the notes'
hash is part of the key and old answers simply stop matching."""
import hashlib
import json
import logging
import os
from app.store import get_store

log = logging.getLogger(__name__)

TTL = int(os.getenv("ANSWER_CACHE_TTL_SECONDS", "3600"))   # 0 turns the cache off

def _key(dataset_id: str, question: str, dictionary: dict | None) -> str:
    # "Total revenue by city?" and "total  revenue by city" are the same question
    norm = " ".join(question.lower().split()).rstrip("?").strip()
    notes = json.dumps(dictionary or {}, sort_keys=True)
    digest = hashlib.sha256(f"{norm}\0{notes}".encode()).hexdigest()[:32]
    return f"answer:{dataset_id}:{digest}"

def get(dataset_id: str, question: str, dictionary: dict | None = None) -> dict | None:
    if TTL <= 0:
        return None
    try:
        raw = get_store().get(_key(dataset_id, question, dictionary))
    except Exception as e:   # a cache outage shouldn't fail the question
        log.warning("answer cache read failed: %s", e)
        return None
    return json.loads(raw) if raw else None

def put(dataset_id: str, question: str, answer: dict, dictionary: dict | None = None):
    if TTL <= 0:
        return
    try:
        get_store().set(_key(dataset_id, question, dictionary), json.dumps(answer, default=str), TTL)
    except Exception as e:
        log.warning("answer cache write failed: %s", e)

def drop(dataset_id: str, question: str, dictionary: dict | None = None):
    """Forget an answer the user said was wrong, so the next ask goes to the model."""
    try:
        get_store().delete(_key(dataset_id, question, dictionary))
    except Exception as e:
        log.warning("answer cache delete failed: %s", e)
